"""Independent tests for subprocess safety and bounded diagnostics."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from rubiks_cube_ai_toolkit.solvers.supervisor import (
    SupervisorLimits,
    TerminationReason,
    run_supervised,
)


def _script(tmp_path: Path, source: str) -> tuple[str, ...]:
    path = tmp_path / "synthetic_worker.py"
    path.write_text(source, encoding="utf-8")
    return (sys.executable, str(path))


def test_supervisor_runs_without_shell_and_captures_bounded_output(tmp_path: Path) -> None:
    command = _script(
        tmp_path,
        "import sys; data=sys.stdin.buffer.read(); print(data.decode()); "
        "sys.stderr.write('diagnostic')",
    )
    result = run_supervised(
        command,
        b'{"ok":true}',
        limits=SupervisorLimits(timeout_seconds=5),
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"ok": True}
    assert result.stderr == b"diagnostic"
    assert result.termination_reason is None


def test_supervisor_rejects_oversized_input_and_truncates_output(tmp_path: Path) -> None:
    command = _script(tmp_path, "print('x' * 10000)")
    limits = SupervisorLimits(timeout_seconds=5, stdout_bytes=100)
    with pytest.raises(ValueError, match="input payload"):
        run_supervised(command, b"x" * (limits.input_bytes + 1), limits=limits)
    result = run_supervised(command, b"", limits=limits)
    assert result.stdout_truncated
    assert len(result.stdout) == 100


def test_hard_timeout_terminates_complete_process_tree(tmp_path: Path) -> None:
    marker = tmp_path / "grandchild-survived"
    child_source = (
        "import time; from pathlib import Path; time.sleep(1); "
        f"Path({str(marker)!r}).write_text('bad')"
    )
    command = _script(
        tmp_path,
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_source!r}]); time.sleep(10)",
    )
    result = run_supervised(
        command,
        b"",
        limits=SupervisorLimits(timeout_seconds=0.2, poll_seconds=0.02),
    )
    assert result.termination_reason is TerminationReason.TIMEOUT
    time.sleep(1.1)
    assert not marker.exists()


def test_memory_and_disk_limits_stop_workers(tmp_path: Path) -> None:
    memory_command = _script(tmp_path, "import time; data=bytearray(64<<20); time.sleep(10)")
    memory = run_supervised(
        memory_command,
        b"",
        limits=SupervisorLimits(timeout_seconds=5, memory_bytes=32 << 20, poll_seconds=0.02),
    )
    assert memory.termination_reason is TerminationReason.MEMORY

    watched = tmp_path / "watched"
    watched.mkdir()
    growth_path = str(watched / "growth.bin")
    disk_command = _script(
        tmp_path,
        f"import pathlib,time; p=pathlib.Path({growth_path!r}); "
        "f=p.open('wb'); "
        "[(f.write(b'x'*(256<<10)),f.flush(),time.sleep(.03)) for _ in range(12)]; "
        "time.sleep(10)",
    )
    disk = run_supervised(
        disk_command,
        b"",
        limits=SupervisorLimits(timeout_seconds=5, disk_growth_bytes=1 << 20, poll_seconds=0.02),
        monitored_path=watched,
    )
    assert disk.termination_reason is TerminationReason.DISK


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": 0},
        {"timeout_seconds": 1, "memory_bytes": 0},
        {"timeout_seconds": 1, "poll_seconds": 0},
    ],
)
def test_supervisor_limits_must_be_positive(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="positive"):
        SupervisorLimits(**kwargs)
