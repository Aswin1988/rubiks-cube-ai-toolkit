"""Private JSON worker entry point for the optional deterministic solver."""

from __future__ import annotations

import json
import sys
import time
from typing import NoReturn

MAX_INPUT_BYTES = 4 << 10
MAX_OUTPUT_BYTES = 64 << 10
PROTOCOL_VERSION = 1


def _emit(payload: dict[str, object], *, exit_code: int) -> NoReturn:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        encoded = b'{"protocol":1,"status":"internal_error"}'
        exit_code = 1
    sys.stdout.buffer.write(encoded + b"\n")
    sys.stdout.buffer.flush()
    raise SystemExit(exit_code)


def _read_request() -> dict[str, object]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        _emit({"protocol": PROTOCOL_VERSION, "status": "invalid_request"}, exit_code=2)
    try:
        request = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _emit({"protocol": PROTOCOL_VERSION, "status": "invalid_request"}, exit_code=2)
    if not isinstance(request, dict) or request.get("protocol") != PROTOCOL_VERSION:
        _emit({"protocol": PROTOCOL_VERSION, "status": "invalid_request"}, exit_code=2)
    return request


def main() -> int:
    """Initialize tables or solve one validated canonical facelet state."""
    request = _read_request()
    action = request.get("action")
    if action not in {"initialize", "solve"}:
        _emit({"protocol": PROTOCOL_VERSION, "status": "invalid_request"}, exit_code=2)

    try:
        from rubik_solver import Cube, init_solver, solve
    except ModuleNotFoundError:
        _emit({"protocol": PROTOCOL_VERSION, "status": "dependency_missing"}, exit_code=3)

    started = time.perf_counter()
    try:
        init_solver(verbose=False)
        initialized_seconds = time.perf_counter() - started
        if action == "initialize":
            _emit(
                {
                    "protocol": PROTOCOL_VERSION,
                    "status": "ok",
                    "initialization_seconds": initialized_seconds,
                },
                exit_code=0,
            )

        state = request.get("state")
        max_moves = request.get("max_moves")
        if (
            not isinstance(state, str)
            or len(state) != 54
            or set(state) - set("URFDLB")
            or not isinstance(max_moves, int)
            or isinstance(max_moves, bool)
            or not 1 <= max_moves <= 100
        ):
            _emit({"protocol": PROTOCOL_VERSION, "status": "invalid_request"}, exit_code=2)
        cube = Cube.from_string(state)
        solve_started = time.perf_counter()
        solution = solve(cube, max_depth=min(max_moves, 22))
        solve_seconds = time.perf_counter() - solve_started
        _emit(
            {
                "protocol": PROTOCOL_VERSION,
                "status": "ok" if solution is not None else "no_solution",
                "solution": solution,
                "initialization_seconds": initialized_seconds,
                "solve_seconds": solve_seconds,
            },
            exit_code=0 if solution is not None else 4,
        )
    except MemoryError:
        _emit({"protocol": PROTOCOL_VERSION, "status": "resource_error"}, exit_code=5)
    except Exception:
        _emit({"protocol": PROTOCOL_VERSION, "status": "internal_error"}, exit_code=1)


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    main()
