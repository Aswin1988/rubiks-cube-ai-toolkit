"""Tests for the optional local MCP server and all five tool contracts."""

import asyncio
import builtins
from dataclasses import dataclass

import pytest
from mcp import Client

from rubiks_cube_ai_toolkit import mcp_server
from rubiks_cube_ai_toolkit.mcp_server import (
    create_server,
    cube_apply,
    cube_scramble,
    cube_solve,
    cube_validate,
    cube_verify,
)
from rubiks_cube_ai_toolkit.model import FaceletState, Move, invert_moves
from rubiks_cube_ai_toolkit.solvers import SolveLimits, SolveResult, SolveStatus

SOLVED = "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB"


def _scrambled_state() -> tuple[str, str]:
    scramble = (Move.R, Move.U, Move.F2)
    state = FaceletState.solved().apply_moves(scramble).serialize()
    solution = " ".join(move.value for move in invert_moves(scramble))
    return state, solution


def test_cube_scramble_is_seeded_and_rejects_invalid_input() -> None:
    first = cube_scramble(12, "mcp-test")
    second = cube_scramble(12, "mcp-test")
    assert first == second
    assert first["ok"] is True
    assert len(first["data"]["moves"]) == 12  # type: ignore[index]
    assert cube_scramble(0)["error"] == {
        "code": "INVALID_INPUT",
        "message": "length must be positive",
    }
    assert cube_scramble(True)["ok"] is False
    assert cube_scramble(101)["ok"] is False
    assert cube_scramble(1, 1.5)["ok"] is False  # type: ignore[arg-type]


def test_cube_validate_reports_reachability_diagnostics() -> None:
    valid = cube_validate(SOLVED)
    invalid = cube_validate("U")
    assert valid["ok"] is True
    assert valid["data"]["valid"] is True  # type: ignore[index]
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "INVALID_STATE"  # type: ignore[index]
    assert invalid["data"]["issues"][0]["code"] == "FACELET_COUNT"  # type: ignore[index]
    assert cube_validate(1)["error"]["code"] == "INVALID_INPUT"  # type: ignore[arg-type,index]


def test_cube_apply_uses_engine_and_rejects_state_and_moves() -> None:
    applied = cube_apply(SOLVED, "R U")
    expected = FaceletState.solved().apply_moves((Move.R, Move.U)).serialize()
    assert applied["ok"] is True
    assert applied["data"]["state"] == expected  # type: ignore[index]
    assert cube_apply("U", "R")["error"]["code"] == "INVALID_STATE"  # type: ignore[index]
    assert cube_apply(SOLVED, "X")["error"]["code"] == "INVALID_MOVES"  # type: ignore[index]
    assert cube_apply(SOLVED, 1)["error"]["code"] == "INVALID_INPUT"  # type: ignore[arg-type,index]


def test_cube_verify_accepts_solution_and_returns_failed_final_state() -> None:
    state, solution = _scrambled_state()
    verified = cube_verify(state, solution)
    rejected = cube_verify(state, "R")
    assert verified["ok"] is True
    assert verified["data"]["verified"] is True  # type: ignore[index]
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "NOT_SOLVED"  # type: ignore[index]
    assert rejected["data"]["final_state"] is not None  # type: ignore[index]
    assert cube_verify("U", "")["error"]["code"] == "INVALID_STATE"  # type: ignore[index]
    assert cube_verify(SOLVED, "X")["error"]["code"] == "INVALID_MOVES"  # type: ignore[index]


@dataclass
class StubSolver:
    result: SolveResult
    observed_limits: SolveLimits | None = None

    def solve(self, state: str, limits: SolveLimits) -> SolveResult:
        assert len(state) == 54
        self.observed_limits = limits
        return self.result


def test_cube_solve_forwards_limits_and_structures_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = StubSolver(SolveResult(SolveStatus.ALREADY_SOLVED, "stub", 0.0))
    observed_config = []

    def factory(config: object) -> StubSolver:
        observed_config.append(config)
        return stub

    monkeypatch.setattr(mcp_server, "_solver_factory", factory)
    result = cube_solve(
        SOLVED,
        timeout_seconds=2.5,
        max_moves=22,
        initialization_timeout_seconds=30,
        memory_limit_mb=512,
        cache_limit_mb=32,
    )
    assert result["ok"] is True
    assert stub.observed_limits == SolveLimits(2.5, 22)
    config = observed_config[0]
    assert config.initialization_timeout_seconds == 30
    assert config.memory_limit_bytes == 512 << 20
    assert config.cache_limit_bytes == 32 << 20


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (SolveStatus.TIMEOUT, "TIMEOUT"),
        (SolveStatus.UNAVAILABLE, "UNAVAILABLE"),
        (SolveStatus.RESOURCE_LIMIT, "RESOURCE_LIMIT"),
    ],
)
def test_cube_solve_returns_structured_solver_failures(
    monkeypatch: pytest.MonkeyPatch, status: SolveStatus, code: str
) -> None:
    state, _ = _scrambled_state()
    stub = StubSolver(SolveResult(status, "stub", 1.0, error="controlled failure"))
    monkeypatch.setattr(mcp_server, "_solver_factory", lambda config: stub)
    result = cube_solve(state)
    assert result["ok"] is False
    assert result["error"] == {"code": code, "message": "controlled failure"}
    assert result["data"]["status"] == status.value  # type: ignore[index]


def test_cube_solve_rejects_invalid_state_and_limits() -> None:
    assert cube_solve("U")["error"]["code"] == "INVALID_STATE"  # type: ignore[index]
    assert cube_solve(SOLVED, timeout_seconds=0)["error"]["code"] == "INVALID_INPUT"  # type: ignore[index]
    assert cube_solve(SOLVED, max_moves=True)["error"]["code"] == "INVALID_INPUT"  # type: ignore[index]
    assert cube_solve(SOLVED, memory_limit_mb=0)["error"]["code"] == "INVALID_INPUT"  # type: ignore[index]


def test_mcp_server_registers_exactly_five_tools() -> None:
    tools = asyncio.run(create_server().list_tools())
    assert {tool.name for tool in tools} == {
        "cube_scramble",
        "cube_validate",
        "cube_apply",
        "cube_solve",
        "cube_verify",
    }


def test_mcp_client_receives_structured_tool_response() -> None:
    async def call_tool() -> object:
        async with Client(create_server()) as client:
            return await client.call_tool("cube_validate", {"state": SOLVED})

    result = asyncio.run(call_tool())
    assert result.structured_content == {
        "ok": True,
        "tool": "cube_validate",
        "data": cube_validate(SOLVED)["data"],
        "error": None,
    }


def test_missing_mcp_dependency_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "mcp.server":
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(RuntimeError, match="install the package with the 'mcp' extra"):
        create_server()


def test_main_reports_missing_dependency(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        mcp_server, "create_server", lambda: (_ for _ in ()).throw(RuntimeError("missing"))
    )
    assert mcp_server.main() == 1
    assert "error: missing" in capsys.readouterr().err


def test_main_runs_stdio_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubServer:
        transport: str | None = None

        def run(self, *, transport: str) -> None:
            self.transport = transport

    server = StubServer()
    monkeypatch.setattr(mcp_server, "create_server", lambda: server)
    assert mcp_server.main() == 0
    assert server.transport == "stdio"
