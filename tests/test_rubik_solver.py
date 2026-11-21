"""Subprocess solver adapter, IPC, and real-backend integration tests."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from rubiks_cube_ai_toolkit.model import FaceletState, Move
from rubiks_cube_ai_toolkit.solvers import (
    RubikSolverConfig,
    RubikSolverSubprocess,
    SolveLimits,
    SolveStatus,
    VerifiedSolver,
)
from rubiks_cube_ai_toolkit.solvers.cache import (
    EXPECTED_TABLE_SIZES,
    NUMPY_MAGIC,
    SolverTableCache,
)
from rubiks_cube_ai_toolkit.solvers.supervisor import (
    SupervisedProcessResult,
    TerminationReason,
)


def _write_valid_cache(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name, size in EXPECTED_TABLE_SIZES.items():
        with (path / name).open("wb") as handle:
            handle.write(NUMPY_MAGIC)
            handle.truncate(size)
    SolverTableCache(path.parent).write_manifest(path)


def _result(
    payload: dict[str, object] | bytes,
    *,
    returncode: int = 0,
    termination: TerminationReason | None = None,
    stdout_truncated: bool = False,
    stderr_truncated: bool = False,
) -> SupervisedProcessResult:
    stdout = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return SupervisedProcessResult(
        returncode,
        stdout,
        b"private path C:\\sensitive\\cache",
        0.1,
        1000,
        termination,
        stdout_truncated,
        stderr_truncated,
    )


def _backend(
    tmp_path: Path,
    runner,
    *,
    dependency_check=lambda: True,
) -> RubikSolverSubprocess:
    return RubikSolverSubprocess(
        RubikSolverConfig(cache_root=tmp_path / "cache", poll_seconds=0.01),
        _runner=runner,
        _dependency_check=dependency_check,
        _command=("synthetic-worker",),
    )


def _scrambled() -> FaceletState:
    return FaceletState.solved().apply_move(Move.R)


def test_adapter_initializes_cache_and_returns_verified_solution(tmp_path: Path) -> None:
    actions: list[str] = []

    def runner(command, payload, **kwargs):
        del command
        request = json.loads(payload)
        actions.append(request["action"])
        if request["action"] == "initialize":
            _write_valid_cache(kwargs["monitored_path"])
            return _result({"protocol": 1, "status": "ok"})
        return _result({"protocol": 1, "status": "ok", "solution": "R'"})

    backend = _backend(tmp_path, runner)
    result = VerifiedSolver(backend).solve(_scrambled(), SolveLimits(max_moves=22))
    assert result.status is SolveStatus.SUCCESS
    assert result.verification is not None and result.verification.verified
    assert actions == ["initialize", "solve"]
    assert backend.cache.inspect().valid
    assert backend.initialization_metrics is not None


def test_already_solved_and_invalid_states_do_not_invoke_worker(tmp_path: Path) -> None:
    def unexpected(*args, **kwargs):
        del args, kwargs
        raise AssertionError("worker must not run")

    backend = _backend(tmp_path, unexpected, dependency_check=lambda: False)
    solved = VerifiedSolver(backend).solve(FaceletState.solved())
    invalid = VerifiedSolver(backend).solve("U")
    assert solved.status is SolveStatus.ALREADY_SOLVED
    assert invalid.status is SolveStatus.INVALID_STATE


def test_missing_dependency_is_actionable(tmp_path: Path) -> None:
    backend = _backend(tmp_path, lambda *args, **kwargs: None, dependency_check=lambda: False)
    result = VerifiedSolver(backend).solve(_scrambled())
    assert result.status is SolveStatus.UNAVAILABLE
    assert "solver' extra" in (result.error or "")


@pytest.mark.parametrize(
    ("worker_result", "expected"),
    [
        (_result(b"not-json"), SolveStatus.FAILURE),
        (_result({"protocol": 1, "status": "internal_error"}, returncode=1), SolveStatus.FAILURE),
        (
            _result(b"", returncode=1, termination=TerminationReason.TIMEOUT),
            SolveStatus.TIMEOUT,
        ),
        (
            _result(b"", returncode=1, termination=TerminationReason.MEMORY),
            SolveStatus.RESOURCE_LIMIT,
        ),
        (
            _result({"protocol": 1, "status": "ok"}, stdout_truncated=True),
            SolveStatus.FAILURE,
        ),
    ],
)
def test_worker_failures_map_to_structured_statuses(
    tmp_path: Path, worker_result: SupervisedProcessResult, expected: SolveStatus
) -> None:
    cache = tmp_path / "cache" / "tables"
    _write_valid_cache(cache)
    backend = _backend(tmp_path, lambda *args, **kwargs: worker_result)
    result = VerifiedSolver(backend).solve(_scrambled())
    assert result.status is expected
    assert str(tmp_path) not in (result.error or "")
    assert b"sensitive" in backend.bounded_stderr or expected in {
        SolveStatus.TIMEOUT,
        SolveStatus.RESOURCE_LIMIT,
    }


def test_incorrect_response_is_rejected_by_independent_verifier(tmp_path: Path) -> None:
    _write_valid_cache(tmp_path / "cache" / "tables")
    backend = _backend(
        tmp_path,
        lambda *args, **kwargs: _result({"protocol": 1, "status": "ok", "solution": "U"}),
    )
    result = VerifiedSolver(backend).solve(_scrambled())
    assert result.status is SolveStatus.VERIFICATION_FAILED


def test_worker_start_error_does_not_expose_filesystem_path(tmp_path: Path) -> None:
    _write_valid_cache(tmp_path / "cache" / "tables")

    def runner(*args, **kwargs):
        del args, kwargs
        raise OSError(f"cannot execute {tmp_path / 'secret-worker'}")

    result = VerifiedSolver(_backend(tmp_path, runner)).solve(_scrambled())
    assert result.status is SolveStatus.FAILURE
    assert result.error == "solver worker could not be started"
    assert str(tmp_path) not in result.error


def test_corrupted_or_incomplete_cache_is_rebuilt(tmp_path: Path) -> None:
    tables = tmp_path / "cache" / "tables"
    tables.mkdir(parents=True)
    (tables / "partial.npy").write_bytes(b"bad")
    initializations = 0

    def runner(command, payload, **kwargs):
        nonlocal initializations
        del command
        request = json.loads(payload)
        if request["action"] == "initialize":
            initializations += 1
            _write_valid_cache(kwargs["monitored_path"])
            return _result({"protocol": 1, "status": "ok"})
        return _result({"protocol": 1, "status": "ok", "solution": "R'"})

    result = VerifiedSolver(_backend(tmp_path, runner)).solve(_scrambled())
    assert result.success
    assert initializations == 1
    assert not (tables / "partial.npy").exists()


def test_concurrent_adapters_initialize_cache_once(tmp_path: Path) -> None:
    initializations = 0
    lock = threading.Lock()

    def runner(command, payload, **kwargs):
        nonlocal initializations
        del command
        request = json.loads(payload)
        assert request["action"] == "initialize"
        with lock:
            initializations += 1
        time.sleep(0.1)
        _write_valid_cache(kwargs["monitored_path"])
        return _result({"protocol": 1, "status": "ok"})

    backends = [_backend(tmp_path, runner), _backend(tmp_path, runner)]
    threads = [threading.Thread(target=backend._ensure_cache) for backend in backends]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert initializations == 1
    assert backends[0].cache.inspect().valid


def test_invalid_generated_cache_is_rejected_and_staging_removed(tmp_path: Path) -> None:
    backend = _backend(
        tmp_path,
        lambda *args, **kwargs: _result({"protocol": 1, "status": "ok"}),
    )
    result = VerifiedSolver(backend).solve(_scrambled())
    assert result.status is SolveStatus.FAILURE
    assert not list((tmp_path / "cache").glob(".staging-*"))


@pytest.mark.solver
def test_real_solver_process_produces_independently_verified_solution(tmp_path: Path) -> None:
    pytest.importorskip("rubik_solver")
    pytest.importorskip("psutil")
    backend = RubikSolverSubprocess(
        RubikSolverConfig(
            cache_root=tmp_path / "real-cache",
            initialization_timeout_seconds=60,
            poll_seconds=0.05,
        )
    )
    state = FaceletState.solved().apply_moves((Move.R, Move.U, Move.F2, Move.L, Move.D))
    result = VerifiedSolver(backend).solve(state, SolveLimits(timeout_seconds=10, max_moves=22))
    assert result.status is SolveStatus.SUCCESS
    assert result.verification is not None and result.verification.verified
    assert backend.initialization_metrics is not None
    assert backend.initialization_metrics.peak_memory_bytes < 1 << 30
