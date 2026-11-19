"""Solver protocol and independent verification-gate tests."""

from dataclasses import dataclass

import pytest

from rubiks_cube_ai_toolkit.model import FaceletState, generate_scramble, invert_moves
from rubiks_cube_ai_toolkit.solvers import (
    SolveLimits,
    SolverTimeoutError,
    SolveStatus,
    UnavailableSolver,
    VerifiedSolver,
)


@dataclass
class ResponseSolver:
    response: str
    name: str = "test-backend"

    def solve(self, state: FaceletState, limits: SolveLimits) -> str:
        del state, limits
        return self.response


class TimeoutSolver:
    name = "timeout-backend"

    def solve(self, state: FaceletState, limits: SolveLimits) -> str:
        del state, limits
        raise SolverTimeoutError("deadline expired")


class BrokenSolver:
    name = "broken-backend"

    def solve(self, state: FaceletState, limits: SolveLimits) -> str:
        del state, limits
        raise OSError("backend crashed")


def _scrambled() -> tuple[FaceletState, str]:
    scramble = generate_scramble(8, seed="solver-gate")
    state = FaceletState.solved().apply_moves(scramble)
    solution = " ".join(move.value for move in invert_moves(scramble))
    return state, solution


def test_verified_solver_accepts_only_independently_verified_response() -> None:
    state, solution = _scrambled()
    result = VerifiedSolver(ResponseSolver(solution)).solve(state)
    assert result.status is SolveStatus.SUCCESS
    assert result.success
    assert result.verification is not None and result.verification.verified
    assert result.to_dict()["success"] is True


def test_deliberately_incorrect_solver_response_fails_gate() -> None:
    state, _ = _scrambled()
    result = VerifiedSolver(ResponseSolver("R U")).solve(state)
    assert result.status is SolveStatus.VERIFICATION_FAILED
    assert not result.success
    assert result.verification is not None and not result.verification.verified


def test_malformed_and_overlong_solver_responses_fail() -> None:
    state, solution = _scrambled()
    malformed = VerifiedSolver(ResponseSolver("X")).solve(state)
    overlong = VerifiedSolver(ResponseSolver(solution)).solve(state, SolveLimits(max_moves=1))
    assert malformed.status is SolveStatus.FAILURE
    assert overlong.status is SolveStatus.FAILURE
    assert overlong.moves


def test_elapsed_execution_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    state, solution = _scrambled()
    clock = iter((0.0, 2.0))
    monkeypatch.setattr(
        "rubiks_cube_ai_toolkit.solvers.protocol.time.perf_counter", lambda: next(clock)
    )
    result = VerifiedSolver(ResponseSolver(solution)).solve(state, SolveLimits(timeout_seconds=1.0))
    assert result.status is SolveStatus.TIMEOUT


def test_timeout_unavailable_invalid_and_solved_outcomes() -> None:
    state, _ = _scrambled()
    timeout = VerifiedSolver(TimeoutSolver()).solve(state)
    unavailable = VerifiedSolver(UnavailableSolver()).solve(state)
    invalid = VerifiedSolver(UnavailableSolver()).solve("U")
    solved = VerifiedSolver(UnavailableSolver()).solve(FaceletState.solved())
    broken = VerifiedSolver(BrokenSolver()).solve(state)
    assert timeout.status is SolveStatus.TIMEOUT
    assert unavailable.status is SolveStatus.UNAVAILABLE
    assert invalid.status is SolveStatus.INVALID_STATE
    assert solved.status is SolveStatus.ALREADY_SOLVED and solved.success
    assert broken.status is SolveStatus.FAILURE


@pytest.mark.parametrize(
    ("timeout", "moves"),
    [(0.0, 30), (-1.0, 30), (1.0, 0), (1.0, -1)],
)
def test_limits_must_be_positive(timeout: float, moves: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        SolveLimits(timeout, moves)
