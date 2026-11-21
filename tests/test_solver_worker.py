"""Direct contract tests for the private JSON worker."""

from __future__ import annotations

import io
import json
import sys
import types

import pytest

from rubiks_cube_ai_toolkit.solvers import worker


class BinaryStream:
    def __init__(self, value: bytes = b"") -> None:
        self.buffer = io.BytesIO(value)


def run_worker(
    monkeypatch: pytest.MonkeyPatch,
    request: bytes,
    module: types.ModuleType | None,
) -> tuple[int, dict[str, object]]:
    stdin = BinaryStream(request)
    stdout = BinaryStream()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setitem(sys.modules, "rubik_solver", module)
    with pytest.raises(SystemExit) as exit_info:
        worker.main()
    return exit_info.value.code, json.loads(stdout.buffer.getvalue())


def fake_module(*, solution: str | None = "R'", failure: BaseException | None = None):
    module = types.ModuleType("rubik_solver")

    class Cube:
        @classmethod
        def from_string(cls, state: str):
            return state

    def init_solver(*, verbose: bool) -> None:
        assert not verbose
        if failure is not None:
            raise failure

    def solve(cube: str, *, max_depth: int) -> str | None:
        assert len(cube) == 54
        assert max_depth <= 22
        return solution

    module.Cube = Cube
    module.init_solver = init_solver
    module.solve = solve
    return module


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        json.dumps({"protocol": 2, "action": "initialize"}).encode(),
        json.dumps({"protocol": 1, "action": "unknown"}).encode(),
        b"x" * (worker.MAX_INPUT_BYTES + 1),
    ],
)
def test_worker_rejects_invalid_and_oversized_requests(
    monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    code, response = run_worker(monkeypatch, payload, fake_module())
    assert code == 2
    assert response["status"] == "invalid_request"


def test_worker_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    request = json.dumps({"protocol": 1, "action": "initialize"}).encode()
    code, response = run_worker(monkeypatch, request, None)
    assert code == 3
    assert response["status"] == "dependency_missing"


def test_worker_initializes_and_solves(monkeypatch: pytest.MonkeyPatch) -> None:
    initialize = json.dumps({"protocol": 1, "action": "initialize"}).encode()
    code, response = run_worker(monkeypatch, initialize, fake_module())
    assert code == 0
    assert response["status"] == "ok"
    assert isinstance(response["initialization_seconds"], float)

    solve = json.dumps(
        {
            "protocol": 1,
            "action": "solve",
            "state": "U" * 54,
            "max_moves": 30,
        }
    ).encode()
    code, response = run_worker(monkeypatch, solve, fake_module())
    assert code == 0
    assert response["solution"] == "R'"
    assert isinstance(response["solve_seconds"], float)


@pytest.mark.parametrize(
    "payload",
    [
        {"protocol": 1, "action": "solve", "state": "U", "max_moves": 22},
        {"protocol": 1, "action": "solve", "state": "U" * 54, "max_moves": True},
        {"protocol": 1, "action": "solve", "state": "U" * 54, "max_moves": 0},
    ],
)
def test_worker_rejects_invalid_solve_fields(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    code, response = run_worker(monkeypatch, json.dumps(payload).encode(), fake_module())
    assert code == 2
    assert response["status"] == "invalid_request"


def test_worker_reports_no_solution_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    request = json.dumps(
        {
            "protocol": 1,
            "action": "solve",
            "state": "U" * 54,
            "max_moves": 22,
        }
    ).encode()
    code, response = run_worker(monkeypatch, request, fake_module(solution=None))
    assert code == 4
    assert response["status"] == "no_solution"

    initialize = json.dumps({"protocol": 1, "action": "initialize"}).encode()
    code, response = run_worker(monkeypatch, initialize, fake_module(failure=MemoryError()))
    assert code == 5
    assert response["status"] == "resource_error"
    code, response = run_worker(monkeypatch, initialize, fake_module(failure=RuntimeError()))
    assert code == 1
    assert response["status"] == "internal_error"


def test_worker_caps_its_own_output(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = BinaryStream()
    monkeypatch.setattr(sys, "stdout", stream)
    with pytest.raises(SystemExit, match="1"):
        worker._emit({"value": "x" * worker.MAX_OUTPUT_BYTES}, exit_code=0)
    assert json.loads(stream.buffer.getvalue())["status"] == "internal_error"
