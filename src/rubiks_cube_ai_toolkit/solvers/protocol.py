"""Solver contracts and mandatory independent verification gate."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from rubiks_cube_ai_toolkit.model.facelets import FaceletState
from rubiks_cube_ai_toolkit.model.moves import Move, parse_moves
from rubiks_cube_ai_toolkit.validation import validate_state
from rubiks_cube_ai_toolkit.verification import VerificationResult, verify_solution


class SolverTimeoutError(TimeoutError):
    """Raised by a backend when its execution limit expires."""


class SolverUnavailableError(RuntimeError):
    """Raised when an optional solver backend is not installed."""


class SolverResourceError(RuntimeError):
    """Raised when a backend exceeds a configured resource limit."""


class SolverProtocolError(RuntimeError):
    """Raised when a backend violates its structured IPC contract."""


@dataclass(frozen=True, slots=True)
class SolveLimits:
    """Upper bounds passed to a deterministic solver backend."""

    timeout_seconds: float = 10.0
    max_moves: int = 30

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_moves <= 0:
            raise ValueError("max_moves must be positive")


class Solver(Protocol):
    """Minimal protocol implemented by deterministic solver adapters."""

    @property
    def name(self) -> str:
        """Return a stable solver implementation name."""
        ...

    def solve(self, state: FaceletState, limits: SolveLimits) -> str:
        """Return a Singmaster solution or raise a structured backend error."""
        ...


class SolveStatus(StrEnum):
    """Stable outcomes from the verified solving service."""

    SUCCESS = "success"
    ALREADY_SOLVED = "already_solved"
    INVALID_STATE = "invalid_state"
    TIMEOUT = "timeout"
    FAILURE = "failure"
    VERIFICATION_FAILED = "verification_failed"
    UNAVAILABLE = "unavailable"
    RESOURCE_LIMIT = "resource_limit"


@dataclass(frozen=True, slots=True)
class SolveResult:
    """Structured result that can never claim unverified success."""

    status: SolveStatus
    solver: str
    elapsed_seconds: float
    moves: tuple[Move, ...] = ()
    verification: VerificationResult | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Return whether solving succeeded or no moves were needed."""
        return self.status in {SolveStatus.SUCCESS, SolveStatus.ALREADY_SOLVED}

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result."""
        return {
            "success": self.success,
            "status": self.status.value,
            "solver": self.solver,
            "elapsed_seconds": self.elapsed_seconds,
            "moves": [move.value for move in self.moves],
            "verification": self.verification.to_dict() if self.verification else None,
            "error": self.error,
        }


class UnavailableSolver:
    """Backend used when no reviewed solver dependency can be installed."""

    name = "unavailable"

    def solve(self, state: FaceletState, limits: SolveLimits) -> str:
        """Report the reviewed dependency blocker."""
        del state, limits
        raise RuntimeError(
            "no deterministic solver dependency has passed licensing and runtime review"
        )


class VerifiedSolver:
    """Validate input and independently verify every backend response."""

    def __init__(self, backend: Solver) -> None:
        self._backend = backend

    def solve(self, state: str | FaceletState, limits: SolveLimits | None = None) -> SolveResult:
        """Solve under limits, rejecting any unverified backend response."""
        started = time.perf_counter()
        effective_limits = limits or SolveLimits()
        validation = validate_state(state)
        if not validation.valid:
            return SolveResult(
                SolveStatus.INVALID_STATE,
                self._backend.name,
                time.perf_counter() - started,
                error="cube state is not physically reachable",
            )
        facelets = state if isinstance(state, FaceletState) else FaceletState.parse(state)
        if facelets.is_solved:
            verification = verify_solution(facelets, ())
            return SolveResult(
                SolveStatus.ALREADY_SOLVED,
                self._backend.name,
                time.perf_counter() - started,
                verification=verification,
            )
        try:
            raw_moves = self._backend.solve(facelets, effective_limits)
            elapsed = time.perf_counter() - started
            moves = parse_moves(raw_moves)
        except SolverTimeoutError as error:
            return SolveResult(
                SolveStatus.TIMEOUT,
                self._backend.name,
                time.perf_counter() - started,
                error=str(error),
            )
        except SolverUnavailableError as error:
            return SolveResult(
                SolveStatus.UNAVAILABLE,
                self._backend.name,
                time.perf_counter() - started,
                error=str(error),
            )
        except SolverResourceError as error:
            return SolveResult(
                SolveStatus.RESOURCE_LIMIT,
                self._backend.name,
                time.perf_counter() - started,
                error=str(error),
            )
        except Exception as error:
            status = (
                SolveStatus.UNAVAILABLE
                if isinstance(self._backend, UnavailableSolver)
                else SolveStatus.FAILURE
            )
            return SolveResult(
                status,
                self._backend.name,
                time.perf_counter() - started,
                error=str(error),
            )
        if elapsed > effective_limits.timeout_seconds and not getattr(
            self._backend, "enforces_hard_timeout", False
        ):
            return SolveResult(
                SolveStatus.TIMEOUT,
                self._backend.name,
                elapsed,
                error="solver exceeded its execution timeout",
            )
        if len(moves) > effective_limits.max_moves:
            return SolveResult(
                SolveStatus.FAILURE,
                self._backend.name,
                elapsed,
                moves=moves,
                error="solver response exceeds the move limit",
            )
        verification = verify_solution(facelets, moves)
        if not verification.verified:
            return SolveResult(
                SolveStatus.VERIFICATION_FAILED,
                self._backend.name,
                elapsed,
                moves,
                verification,
                "independent sticker-cycle verification rejected the solution",
            )
        return SolveResult(
            SolveStatus.SUCCESS,
            self._backend.name,
            elapsed,
            moves,
            verification,
        )
