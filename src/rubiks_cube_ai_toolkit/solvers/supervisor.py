"""Cross-platform supervision for killable solver child processes."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO


class TerminationReason(StrEnum):
    """Reasons a supervised process was forcibly stopped."""

    TIMEOUT = "timeout"
    MEMORY = "memory"
    DISK = "disk"


@dataclass(frozen=True, slots=True)
class SupervisorLimits:
    """Resource and diagnostic limits for one child process."""

    timeout_seconds: float
    memory_bytes: int = 1 << 30
    disk_growth_bytes: int = 96 << 20
    stdout_bytes: int = 64 << 10
    stderr_bytes: int = 64 << 10
    input_bytes: int = 4 << 10
    poll_seconds: float = 0.05

    def __post_init__(self) -> None:
        numeric = (
            self.timeout_seconds,
            self.memory_bytes,
            self.disk_growth_bytes,
            self.stdout_bytes,
            self.stderr_bytes,
            self.input_bytes,
            self.poll_seconds,
        )
        if any(value <= 0 for value in numeric):
            raise ValueError("supervisor limits must be positive")


@dataclass(frozen=True, slots=True)
class SupervisedProcessResult:
    """Bounded observations from a completed child process."""

    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float
    peak_memory_bytes: int
    termination_reason: TerminationReason | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class _BoundedReader:
    def __init__(self, stream: BinaryIO, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self._buffer = bytearray()
        self.truncated = False

    def run(self) -> None:
        while chunk := self._stream.read(8192):
            remaining = self._limit - len(self._buffer)
            if remaining > 0:
                self._buffer.extend(chunk[:remaining])
            if len(chunk) > remaining:
                self.truncated = True

    @property
    def value(self) -> bytes:
        return bytes(self._buffer)


def _directory_bytes(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _process_tree_snapshot(process_id: int) -> tuple[int, list[object]]:
    try:
        import psutil
    except ModuleNotFoundError:
        return 0, []
    try:
        root = psutil.Process(process_id)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0, []
    total = 0
    for process in processes:
        try:
            total += process.memory_info().rss
        except psutil.Error:
            continue
    return total, processes[1:]


def terminate_process_tree(
    process: subprocess.Popen[bytes], known_descendants: Sequence[object] = ()
) -> None:
    """Terminate a process and every discoverable descendant, then reap it."""
    try:
        import psutil
    except ModuleNotFoundError:
        psutil = None
        descendants = list(known_descendants)
    else:
        try:
            discovered = psutil.Process(process.pid).children(recursive=True)
            descendants = list(known_descendants) + discovered
        except psutil.Error:
            descendants = list(known_descendants)
    if os.name == "nt" and process.poll() is None:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            process.kill()
    elif os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
    unique_descendants = {descendant.pid: descendant for descendant in descendants}.values()
    for descendant in reversed(list(unique_descendants)):
        try:
            descendant.kill()
        except psutil.Error:  # type: ignore[union-attr]
            continue
    if descendants:
        psutil.wait_procs(descendants, timeout=5)  # type: ignore[union-attr]
    try:
        if process.poll() is None:
            process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_supervised(
    command: Sequence[str],
    input_payload: bytes,
    *,
    limits: SupervisorLimits,
    environment: Mapping[str, str] | None = None,
    monitored_path: Path | None = None,
) -> SupervisedProcessResult:
    """Run a child without a shell and stop its tree on time, memory, or disk limits."""
    if not command or any(not isinstance(part, str) or not part for part in command):
        raise ValueError("command must contain non-empty strings")
    if len(input_payload) > limits.input_bytes:
        raise ValueError("input payload exceeds the supervisor limit")

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    started = time.perf_counter()
    initial_disk = _directory_bytes(monitored_path)
    process: subprocess.Popen[bytes] | None = None
    stdout_reader: _BoundedReader | None = None
    stderr_reader: _BoundedReader | None = None
    threads: list[threading.Thread] = []
    peak_memory = 0
    known_descendants: dict[int, object] = {}
    termination_reason: TerminationReason | None = None

    try:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(environment) if environment is not None else None,
            shell=False,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        stdout_reader = _BoundedReader(process.stdout, limits.stdout_bytes)
        stderr_reader = _BoundedReader(process.stderr, limits.stderr_bytes)
        threads = [
            threading.Thread(target=stdout_reader.run, daemon=True),
            threading.Thread(target=stderr_reader.run, daemon=True),
        ]
        for thread in threads:
            thread.start()
        process.stdin.write(input_payload)
        process.stdin.close()

        while process.poll() is None:
            elapsed = time.perf_counter() - started
            current_memory, descendants = _process_tree_snapshot(process.pid)
            peak_memory = max(peak_memory, current_memory)
            known_descendants.update({descendant.pid: descendant for descendant in descendants})
            disk_growth = _directory_bytes(monitored_path) - initial_disk
            if elapsed >= limits.timeout_seconds:
                termination_reason = TerminationReason.TIMEOUT
            elif peak_memory >= limits.memory_bytes:
                termination_reason = TerminationReason.MEMORY
            elif disk_growth >= limits.disk_growth_bytes:
                termination_reason = TerminationReason.DISK
            if termination_reason is not None:
                terminate_process_tree(process, tuple(known_descendants.values()))
                break
            time.sleep(limits.poll_seconds)

        if process.poll() is None:
            terminate_process_tree(process, tuple(known_descendants.values()))
        else:
            process.wait(timeout=5)
    finally:
        if process is not None:
            terminate_process_tree(process, tuple(known_descendants.values()))
        for thread in threads:
            thread.join(timeout=5)

    assert process is not None
    assert stdout_reader is not None
    assert stderr_reader is not None
    return SupervisedProcessResult(
        returncode=process.returncode,
        stdout=stdout_reader.value,
        stderr=stderr_reader.value,
        elapsed_seconds=time.perf_counter() - started,
        peak_memory_bytes=peak_memory,
        termination_reason=termination_reason,
        stdout_truncated=stdout_reader.truncated,
        stderr_truncated=stderr_reader.truncated,
    )


def worker_command(module: str) -> tuple[str, ...]:
    """Return the current interpreter command for a module-based worker."""
    return (sys.executable, "-m", module)
