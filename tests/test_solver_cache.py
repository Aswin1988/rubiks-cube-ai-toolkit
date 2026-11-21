"""Generated-table cache validation and concurrency tests."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from rubiks_cube_ai_toolkit.solvers.cache import (
    EXPECTED_TABLE_SIZES,
    NUMPY_MAGIC,
    SolverTableCache,
    default_solver_cache_root,
)
from rubiks_cube_ai_toolkit.solvers.protocol import SolverTimeoutError


def write_valid_cache(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name, size in EXPECTED_TABLE_SIZES.items():
        with (path / name).open("wb") as handle:
            handle.write(NUMPY_MAGIC)
            handle.truncate(size)
    SolverTableCache(path.parent).write_manifest(path)


def test_cache_detects_complete_incomplete_corrupt_and_oversized_tables(tmp_path: Path) -> None:
    cache = SolverTableCache(tmp_path / "cache")
    assert not cache.inspect().valid
    write_valid_cache(cache.tables)
    assert cache.inspect().valid
    (cache.tables / next(iter(EXPECTED_TABLE_SIZES))).unlink()
    assert cache.inspect().reason == "set"

    write_valid_cache(cache.tables)
    target = cache.tables / next(iter(EXPECTED_TABLE_SIZES))
    with target.open("r+b") as handle:
        handle.write(b"broken")
    assert cache.inspect().reason == "content"

    write_valid_cache(cache.tables)
    with target.open("r+b") as handle:
        handle.seek(100)
        handle.write(b"changed")
    assert cache.inspect().reason == "hash"

    write_valid_cache(cache.tables)
    small_limit = SolverTableCache(tmp_path / "cache", maximum_bytes=1024)
    assert small_limit.inspect().reason == "size"


def test_cache_publish_is_atomic_and_discards_invalid_staging(tmp_path: Path) -> None:
    cache = SolverTableCache(tmp_path / "cache")
    invalid = cache.new_staging_directory()
    with pytest.raises(ValueError, match="validation"):
        cache.publish(invalid)
    cache.discard(invalid)
    assert not invalid.exists()

    old = cache.tables
    old.mkdir()
    (old / "incomplete.npy").write_bytes(b"bad")
    staging = cache.new_staging_directory()
    write_valid_cache(staging)
    cache.publish(staging)
    assert cache.inspect().valid
    assert not staging.exists()


def test_initialization_lock_serializes_writers_and_times_out(tmp_path: Path) -> None:
    cache = SolverTableCache(tmp_path / "cache")
    entered: list[str] = []

    def first() -> None:
        with cache.initialization_lock(deadline=time.monotonic() + 2):
            entered.append("first")
            time.sleep(0.2)

    def second() -> None:
        time.sleep(0.02)
        with cache.initialization_lock(deadline=time.monotonic() + 2):
            entered.append("second")

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert entered == ["first", "second"]
    assert not cache._lock.exists()

    cache.root.mkdir(parents=True, exist_ok=True)
    cache._lock.write_text("busy", encoding="utf-8")
    with (
        pytest.raises(SolverTimeoutError, match="lock"),
        cache.initialization_lock(deadline=time.monotonic() + 0.05),
    ):
        pass


def test_stale_initialization_lock_is_recovered(tmp_path: Path) -> None:
    cache = SolverTableCache(tmp_path / "cache")
    cache.root.mkdir(parents=True)
    cache._lock.write_text("stale", encoding="utf-8")
    old = time.time() - 1000
    os.utime(cache._lock, (old, old))
    with cache.initialization_lock(deadline=time.monotonic() + 1, stale_after_seconds=1):
        assert cache._lock.exists()
    assert not cache._lock.exists()


def test_default_cache_root_is_versioned_outside_relative_working_tree() -> None:
    root = default_solver_cache_root()
    assert root.is_absolute()
    assert root.parts[-2:] == ("rubik-solver-py", "0.1.1")


def test_cache_limit_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive"):
        SolverTableCache(tmp_path, maximum_bytes=0)
