"""Validated, concurrency-safe table cache for rubik-solver-py 0.1.1."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from rubiks_cube_ai_toolkit.solvers.protocol import SolverTimeoutError

EXPECTED_TABLE_SIZES: dict[str, int] = {
    "v1_mt_flip.npy": 147_584,
    "v1_mt_FRtoBR.npy": 855_488,
    "v1_mt_mergeURtoDF.npy": 451_712,
    "v1_mt_parity.npy": 272,
    "v1_mt_twist.npy": 157_592,
    "v1_mt_UBtoDF.npy": 95_168,
    "v1_mt_URFtoDLF.npy": 1_451_648,
    "v1_mt_URtoDF.npy": 1_451_648,
    "v1_mt_URtoUL.npy": 95_168,
    "v1_pt_sliceFlip.npy": 1_013_888,
    "v1_pt_sliceTwist.npy": 1_082_693,
    "v1_pt_sliceURFtoDLFParity.npy": 967_808,
    "v1_pt_sliceURtoDFParity.npy": 967_808,
}
NUMPY_MAGIC = b"\x93NUMPY"
INTEGRITY_MANIFEST = ".integrity.json"


def default_solver_cache_root() -> Path:
    """Return a platform-appropriate user cache outside the working tree."""
    if sys.platform == "win32":
        parent = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        parent = Path.home() / "Library" / "Caches"
    else:
        parent = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return parent / "rubiks-cube-ai-toolkit" / "rubik-solver-py" / "0.1.1"


@dataclass(frozen=True, slots=True)
class CacheInspection:
    """Result of validating a generated-table directory."""

    valid: bool
    total_bytes: int
    reason: str | None = None


class SolverTableCache:
    """Manage complete table publication and one-writer initialization."""

    def __init__(self, root: Path | None = None, *, maximum_bytes: int = 64 << 20) -> None:
        if maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be positive")
        self.root = (root or default_solver_cache_root()).expanduser().resolve()
        self.tables = self.root / "tables"
        self._lock = self.root / "initialize.lock"
        self.maximum_bytes = maximum_bytes

    def inspect(
        self, path: Path | None = None, *, require_manifest: bool | None = None
    ) -> CacheInspection:
        """Validate exact files, sizes, NumPy magic, and the configured size ceiling."""
        target = path or self.tables
        must_have_manifest = target == self.tables if require_manifest is None else require_manifest
        try:
            files = {item.name: item for item in target.iterdir() if item.is_file()}
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            return CacheInspection(False, 0, "missing")
        expected_names = set(EXPECTED_TABLE_SIZES)
        manifest_path = files.pop(INTEGRITY_MANIFEST, None)
        if set(files) != expected_names:
            return CacheInspection(
                False, sum(item.stat().st_size for item in files.values()), "set"
            )
        if must_have_manifest and manifest_path is None:
            return CacheInspection(
                False, sum(item.stat().st_size for item in files.values()), "hash"
            )
        manifest: dict[str, str] | None = None
        if manifest_path is not None:
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = payload["files"]
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                return CacheInspection(False, 0, "hash")
            if not isinstance(manifest, dict) or set(manifest) != expected_names:
                return CacheInspection(False, 0, "hash")
        total = 0
        for name, expected_size in EXPECTED_TABLE_SIZES.items():
            item = files[name]
            try:
                size = item.stat().st_size
                with item.open("rb") as handle:
                    magic = handle.read(len(NUMPY_MAGIC))
            except OSError:
                return CacheInspection(False, total, "read")
            total += size
            if size != expected_size or magic != NUMPY_MAGIC:
                return CacheInspection(False, total, "content")
            if manifest is not None and manifest[name] != self._sha256(item):
                return CacheInspection(False, total, "hash")
            if total > self.maximum_bytes:
                return CacheInspection(False, total, "size")
        if manifest_path is not None:
            total += manifest_path.stat().st_size
        return CacheInspection(True, total)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1 << 20):
                digest.update(chunk)
        return digest.hexdigest()

    def write_manifest(self, path: Path) -> None:
        """Write deterministic integrity hashes for a structurally valid cache."""
        inspection = self.inspect(path, require_manifest=False)
        if not inspection.valid:
            raise ValueError("cannot hash an invalid solver cache")
        hashes = {name: self._sha256(path / name) for name in sorted(EXPECTED_TABLE_SIZES)}
        payload = json.dumps({"version": 1, "files": hashes}, sort_keys=True)
        temporary = path / f"{INTEGRITY_MANIFEST}.tmp"
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path / INTEGRITY_MANIFEST)

    @contextmanager
    def initialization_lock(
        self, *, deadline: float, stale_after_seconds: float = 180.0
    ) -> Iterator[None]:
        """Acquire an exclusive filesystem lock, waiting only until the deadline."""
        self.root.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                descriptor = os.open(self._lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                try:
                    age = time.time() - self._lock.stat().st_mtime
                    if age > stale_after_seconds:
                        self._lock.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise SolverTimeoutError("solver cache initialization lock timed out") from None
                time.sleep(0.05)
                continue
            else:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump({"pid": os.getpid(), "created": time.time()}, handle)
                break
        try:
            yield
        finally:
            with suppress(FileNotFoundError):
                self._lock.unlink()

    def new_staging_directory(self) -> Path:
        """Create a unique same-filesystem directory for atomic publication."""
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".staging-{uuid.uuid4().hex}"
        staging.mkdir()
        return staging

    def publish(self, staging: Path) -> None:
        """Atomically replace an invalid cache with a validated staging directory."""
        inspection = self.inspect(staging)
        if not inspection.valid:
            raise ValueError("generated solver cache failed validation")
        self.write_manifest(staging)
        if not self.inspect(staging).valid:
            raise ValueError("generated solver cache failed integrity validation")
        old = self.root / f".invalid-{uuid.uuid4().hex}"
        if self.tables.exists():
            self.tables.replace(old)
        try:
            staging.replace(self.tables)
        except BaseException:
            if old.exists() and not self.tables.exists():
                old.replace(self.tables)
            raise
        finally:
            shutil.rmtree(old, ignore_errors=True)

    @staticmethod
    def discard(path: Path) -> None:
        """Remove an unpublished staging directory."""
        shutil.rmtree(path, ignore_errors=True)
