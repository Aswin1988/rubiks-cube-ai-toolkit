"""Local MCP server exposing verified Rubik's Cube operations over stdio."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from rubiks_cube_ai_toolkit.model import (
    FaceletState,
    MoveParseError,
    generate_scramble,
    parse_moves,
)
from rubiks_cube_ai_toolkit.solvers import (
    RubikSolverConfig,
    RubikSolverSubprocess,
    SolveLimits,
    VerifiedSolver,
)
from rubiks_cube_ai_toolkit.validation import ValidationResult, validate_state
from rubiks_cube_ai_toolkit.verification import verify_solution

ToolPayload = dict[str, object]
SolverFactory = Callable[[RubikSolverConfig], VerifiedSolver]


def _success(tool: str, data: dict[str, object]) -> ToolPayload:
    return {"ok": True, "tool": tool, "data": data, "error": None}


def _error(
    tool: str,
    code: str,
    message: str,
    *,
    data: dict[str, object] | None = None,
) -> ToolPayload:
    return {
        "ok": False,
        "tool": tool,
        "data": data,
        "error": {"code": code, "message": message},
    }


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _require_integer(value: object, field: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    if value <= 0:
        raise ValueError(f"{field} must be positive")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} must be at most {maximum}")
    return value


def _require_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field} must be a number")
    result = float(value)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _invalid_state(tool: str, validation: ValidationResult) -> ToolPayload:
    return _error(
        tool,
        "INVALID_STATE",
        "cube state is not physically reachable",
        data=validation.to_dict(),
    )


def cube_scramble(length: int = 20, seed: str | int | None = None) -> ToolPayload:
    """Generate a deterministic scramble and its resulting canonical facelet state."""
    tool = "cube_scramble"
    try:
        checked_length = _require_integer(length, "length", maximum=100)
        if isinstance(seed, bool) or (seed is not None and not isinstance(seed, str | int)):
            raise TypeError("seed must be a string, integer, or null")
        moves = generate_scramble(checked_length, seed=seed)
    except (TypeError, ValueError) as error:
        return _error(tool, "INVALID_INPUT", str(error))
    state = FaceletState.solved().apply_moves(moves)
    return _success(
        tool,
        {"moves": [move.value for move in moves], "state": state.serialize(), "seed": seed},
    )


def cube_validate(state: str) -> ToolPayload:
    """Validate a canonical facelet state for complete physical reachability."""
    tool = "cube_validate"
    try:
        checked_state = _require_string(state, "state")
    except TypeError as error:
        return _error(tool, "INVALID_INPUT", str(error))
    validation = validate_state(checked_state)
    if not validation.valid:
        return _invalid_state(tool, validation)
    return _success(tool, validation.to_dict())


def cube_apply(state: str, moves: str) -> ToolPayload:
    """Apply Singmaster moves to a physically valid canonical facelet state."""
    tool = "cube_apply"
    try:
        checked_state = _require_string(state, "state")
        checked_moves = _require_string(moves, "moves")
    except TypeError as error:
        return _error(tool, "INVALID_INPUT", str(error))
    validation = validate_state(checked_state)
    if not validation.valid:
        return _invalid_state(tool, validation)
    try:
        parsed_moves = parse_moves(checked_moves)
    except (MoveParseError, TypeError) as error:
        return _error(tool, "INVALID_MOVES", str(error))
    final = FaceletState.parse(checked_state).apply_moves(parsed_moves)
    return _success(
        tool,
        {"state": final.serialize(), "moves": [move.value for move in parsed_moves]},
    )


def _default_solver_factory(config: RubikSolverConfig) -> VerifiedSolver:
    return VerifiedSolver(RubikSolverSubprocess(config))


_solver_factory: SolverFactory = _default_solver_factory


def cube_solve(
    state: str,
    timeout_seconds: float = 10.0,
    max_moves: int = 30,
    initialization_timeout_seconds: float = 60.0,
    memory_limit_mb: int = 1024,
    cache_limit_mb: int = 64,
) -> ToolPayload:
    """Solve a valid cube under bounded subprocess limits and verify the result independently."""
    tool = "cube_solve"
    try:
        checked_state = _require_string(state, "state")
        timeout = _require_number(timeout_seconds, "timeout_seconds")
        move_limit = _require_integer(max_moves, "max_moves")
        initialization_timeout = _require_number(
            initialization_timeout_seconds, "initialization_timeout_seconds"
        )
        memory_mb = _require_integer(memory_limit_mb, "memory_limit_mb")
        cache_mb = _require_integer(cache_limit_mb, "cache_limit_mb")
    except (TypeError, ValueError) as error:
        return _error(tool, "INVALID_INPUT", str(error))

    validation = validate_state(checked_state)
    if not validation.valid:
        return _invalid_state(tool, validation)
    config = RubikSolverConfig(
        initialization_timeout_seconds=initialization_timeout,
        memory_limit_bytes=memory_mb << 20,
        cache_limit_bytes=cache_mb << 20,
    )
    result = _solver_factory(config).solve(
        checked_state, SolveLimits(timeout_seconds=timeout, max_moves=move_limit)
    )
    data = result.to_dict()
    if result.success:
        return _success(tool, data)
    return _error(
        tool,
        result.status.value.upper(),
        result.error or f"solver returned {result.status.value}",
        data=data,
    )


def cube_verify(state: str, moves: str) -> ToolPayload:
    """Independently verify that Singmaster moves solve a physically valid cube state."""
    tool = "cube_verify"
    try:
        checked_state = _require_string(state, "state")
        checked_moves = _require_string(moves, "moves")
    except TypeError as error:
        return _error(tool, "INVALID_INPUT", str(error))
    result = verify_solution(checked_state, checked_moves)
    data = result.to_dict()
    if result.verified:
        return _success(tool, data)
    return _error(
        tool,
        result.status.value.upper(),
        result.error or f"verification returned {result.status.value}",
        data=data,
    )


def create_server() -> Any:
    """Create the MCP server, importing the optional SDK only when requested."""
    try:
        from mcp.server import MCPServer
    except ModuleNotFoundError as error:
        if error.name == "mcp":
            raise RuntimeError(
                "MCP support is not installed; install the package with the 'mcp' extra"
            ) from None
        raise

    server = MCPServer("Rubik's Cube AI Toolkit")
    server.tool()(cube_scramble)
    server.tool()(cube_validate)
    server.tool()(cube_apply)
    server.tool()(cube_solve)
    server.tool()(cube_verify)
    return server


def main() -> int:
    """Run the local MCP server using stdio transport."""
    try:
        server = create_server()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
