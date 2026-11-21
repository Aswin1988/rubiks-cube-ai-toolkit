"""Killable subprocess adapter for the optional rubik-solver-py backend."""

from __future__ import annotations

import importlib.util
import json
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from rubiks_cube_ai_toolkit.model.facelets import FaceletState
from rubiks_cube_ai_toolkit.solvers.cache import SolverTableCache
from rubiks_cube_ai_toolkit.solvers.protocol import (
    SolveLimits,
    SolverProtocolError,
    SolverResourceError,
    SolverTimeoutError,
    SolverUnavailableError,
)
from rubiks_cube_ai_toolkit.solvers.supervisor import (
    SupervisedProcessResult,
    SupervisorLimits,
    TerminationReason,
    run_supervised,
    worker_command,
)

WORKER_MODULE = "rubiks_cube_ai_toolkit.solvers.worker"
PROTOCOL_VERSION = 1


@dataclass(frozen=True, slots=True)
class RubikSolverConfig:
    """Operational limits and cache location for the subprocess backend."""

    cache_root: Path | None = None
    initialization_timeout_seconds: float = 60.0
    memory_limit_bytes: int = 1 << 30
    cache_limit_bytes: int = 64 << 20
    disk_growth_limit_bytes: int = 96 << 20
    stdout_limit_bytes: int = 64 << 10
    stderr_limit_bytes: int = 64 << 10
    poll_seconds: float = 0.05

    def __post_init__(self) -> None:
        values = (
            self.initialization_timeout_seconds,
            self.memory_limit_bytes,
            self.cache_limit_bytes,
            self.disk_growth_limit_bytes,
            self.stdout_limit_bytes,
            self.stderr_limit_bytes,
            self.poll_seconds,
        )
        if any(value <= 0 for value in values):
            raise ValueError("solver configuration limits must be positive")


@dataclass(frozen=True, slots=True)
class SolverProcessMetrics:
    """Non-sensitive process measurements from the most recent worker call."""

    elapsed_seconds: float
    peak_memory_bytes: int
    returncode: int
    termination_reason: str | None
    stdout_truncated: bool
    stderr_truncated: bool


def _dependencies_available() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("psutil", "rubik_solver"))


class RubikSolverSubprocess:
    """Run rubik-solver-py in a bounded child and return only structured output."""

    name = "rubik-solver-py-0.1.1"
    enforces_hard_timeout = True

    def __init__(
        self,
        config: RubikSolverConfig | None = None,
        *,
        _runner: Callable[..., SupervisedProcessResult] = run_supervised,
        _dependency_check: Callable[[], bool] = _dependencies_available,
        _command: Sequence[str] | None = None,
    ) -> None:
        self.config = config or RubikSolverConfig()
        self.cache = SolverTableCache(
            self.config.cache_root, maximum_bytes=self.config.cache_limit_bytes
        )
        self._runner = _runner
        self._dependency_check = _dependency_check
        self._command = tuple(_command or worker_command(WORKER_MODULE))
        self.last_metrics: SolverProcessMetrics | None = None
        self.initialization_metrics: SolverProcessMetrics | None = None
        self.last_worker_initialization_seconds: float | None = None
        self.last_worker_solve_seconds: float | None = None
        self._last_stderr = b""

    def _limits(self, timeout_seconds: float) -> SupervisorLimits:
        return SupervisorLimits(
            timeout_seconds=timeout_seconds,
            memory_bytes=self.config.memory_limit_bytes,
            disk_growth_bytes=min(
                self.config.disk_growth_limit_bytes, self.config.cache_limit_bytes
            ),
            stdout_bytes=self.config.stdout_limit_bytes,
            stderr_bytes=self.config.stderr_limit_bytes,
            poll_seconds=self.config.poll_seconds,
        )

    def _invoke(
        self, request: dict[str, object], *, cache_path: Path, timeout_seconds: float
    ) -> dict[str, object]:
        payload = json.dumps(request, separators=(",", ":"), sort_keys=True).encode("utf-8")
        environment = os.environ.copy()
        environment.update(
            {
                "RUBIK_SOLVER_CACHE_DIR": str(cache_path),
                "PYTHONUTF8": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
            }
        )
        try:
            result = self._runner(
                self._command,
                payload,
                limits=self._limits(timeout_seconds),
                environment=environment,
                monitored_path=cache_path,
            )
        except OSError:
            raise RuntimeError("solver worker could not be started") from None
        metrics = SolverProcessMetrics(
            elapsed_seconds=result.elapsed_seconds,
            peak_memory_bytes=result.peak_memory_bytes,
            returncode=result.returncode,
            termination_reason=(
                result.termination_reason.value if result.termination_reason is not None else None
            ),
            stdout_truncated=result.stdout_truncated,
            stderr_truncated=result.stderr_truncated,
        )
        self.last_metrics = metrics
        self._last_stderr = result.stderr
        if result.termination_reason is TerminationReason.TIMEOUT:
            raise SolverTimeoutError("solver process exceeded its execution deadline")
        if result.termination_reason in {TerminationReason.MEMORY, TerminationReason.DISK}:
            raise SolverResourceError("solver process exceeded its resource limit")
        if result.stdout_truncated or result.stderr_truncated:
            raise SolverProtocolError("solver worker diagnostic output exceeded its limit")
        try:
            response = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SolverProtocolError("solver worker returned an invalid response") from None
        if not isinstance(response, dict) or response.get("protocol") != PROTOCOL_VERSION:
            raise SolverProtocolError("solver worker returned an invalid response")
        status = response.get("status")
        if status == "dependency_missing":
            raise SolverUnavailableError(
                "optional solver dependencies are missing; install with the 'solver' extra"
            )
        if status == "resource_error":
            raise SolverResourceError("solver worker exhausted an allocated resource")
        if status == "no_solution":
            raise RuntimeError("solver did not find a solution within the move limit")
        if result.returncode != 0:
            raise RuntimeError("solver worker exited unexpectedly")
        if status != "ok":
            raise SolverProtocolError("solver worker returned an invalid response")
        initialization_seconds = response.get("initialization_seconds")
        solve_seconds = response.get("solve_seconds")
        self.last_worker_initialization_seconds = (
            float(initialization_seconds)
            if isinstance(initialization_seconds, int | float)
            else None
        )
        self.last_worker_solve_seconds = (
            float(solve_seconds) if isinstance(solve_seconds, int | float) else None
        )
        return response

    def _ensure_cache(self) -> None:
        if self.cache.inspect().valid:
            return
        deadline = time.monotonic() + self.config.initialization_timeout_seconds
        with self.cache.initialization_lock(deadline=deadline):
            if self.cache.inspect().valid:
                return
            staging = self.cache.new_staging_directory()
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SolverTimeoutError("solver table initialization timed out")
                self._invoke(
                    {"protocol": PROTOCOL_VERSION, "action": "initialize"},
                    cache_path=staging,
                    timeout_seconds=remaining,
                )
                self.initialization_metrics = self.last_metrics
                if not self.cache.inspect(staging).valid:
                    raise SolverProtocolError("solver generated an invalid table cache")
                self.cache.publish(staging)
            finally:
                self.cache.discard(staging)

    def prepare(self) -> None:
        """Ensure optional dependencies and a complete generated-table cache are ready."""
        if not self._dependency_check():
            raise SolverUnavailableError(
                "optional solver dependencies are missing; install with the 'solver' extra"
            )
        try:
            self._ensure_cache()
        except OSError:
            raise SolverResourceError("solver cache could not be prepared") from None

    def solve(self, state: FaceletState, limits: SolveLimits) -> str:
        """Return a proposed solution produced under hard process limits."""
        self.prepare()
        response = self._invoke(
            {
                "protocol": PROTOCOL_VERSION,
                "action": "solve",
                "state": state.serialize(),
                "max_moves": limits.max_moves,
            },
            cache_path=self.cache.tables,
            timeout_seconds=limits.timeout_seconds,
        )
        solution = response.get("solution")
        if not isinstance(solution, str) or len(solution.encode("utf-8")) > 1024:
            raise SolverProtocolError("solver worker returned an invalid solution")
        return solution

    @property
    def bounded_stderr(self) -> bytes:
        """Return bounded private diagnostics; never include this in public errors."""
        return self._last_stderr
