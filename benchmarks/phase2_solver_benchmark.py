"""Bounded fixed-seed benchmark for the production subprocess solver path."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from rubiks_cube_ai_toolkit import __version__
from rubiks_cube_ai_toolkit.model import FaceletState, generate_scramble
from rubiks_cube_ai_toolkit.solvers import (
    RubikSolverConfig,
    RubikSolverSubprocess,
    SolveLimits,
    SolveStatus,
    VerifiedSolver,
)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    )
    return result.stdout.strip()


def _build_corpus(count: int, length: int) -> tuple[list[dict[str, object]], str]:
    corpus = []
    for seed in range(count):
        moves = generate_scramble(length, seed=seed)
        state = FaceletState.solved().apply_moves(moves)
        corpus.append(
            {
                "seed": seed,
                "scramble": [move.value for move in moves],
                "state": state.serialize(),
            }
        )
    encoded = json.dumps(corpus, separators=(",", ":"), sort_keys=True).encode()
    return corpus, hashlib.sha256(encoded).hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--scramble-length", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-moves", type=int, default=22)
    parser.add_argument("--overall-timeout", type=float, default=7200.0)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.count <= 0 or args.scramble_length < 0 or args.overall_timeout <= 0:
        raise SystemExit("count and time limits must be positive")
    if args.output.exists() or args.summary.exists():
        raise SystemExit("refusing to replace an existing benchmark artifact")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    corpus, corpus_hash = _build_corpus(args.count, args.scramble_length)
    backend = RubikSolverSubprocess(RubikSolverConfig(cache_root=args.cache_root))
    started = time.perf_counter()
    backend.prepare()
    cold_elapsed = time.perf_counter() - started
    cold_metrics = backend.initialization_metrics
    cold_worker_seconds = backend.last_worker_initialization_seconds
    limits = SolveLimits(args.timeout, args.max_moves)
    statuses: Counter[str] = Counter()
    latencies: list[float] = []
    worker_latencies: list[float] = []
    warm_initializations: list[float] = []
    lengths: list[int] = []
    htm_values: list[int] = []
    qtm_values: list[int] = []
    peak_memory = cold_metrics.peak_memory_bytes if cold_metrics else 0
    stopped_reason: str | None = None

    with args.output.open("w", encoding="utf-8") as output:
        for item in corpus:
            if time.perf_counter() - started >= args.overall_timeout:
                stopped_reason = "overall_timeout"
                break
            solve_started = time.perf_counter()
            result = VerifiedSolver(backend).solve(item["state"], limits)
            elapsed = time.perf_counter() - solve_started
            metrics = backend.last_metrics
            peak_memory = max(peak_memory, metrics.peak_memory_bytes if metrics else 0)
            record = {
                **item,
                "status": result.status.value,
                "verified": bool(result.verification and result.verification.verified),
                "elapsed_seconds": elapsed,
                "worker_process_seconds": metrics.elapsed_seconds if metrics else None,
                "worker_solve_seconds": backend.last_worker_solve_seconds,
                "worker_initialization_seconds": backend.last_worker_initialization_seconds,
                "peak_process_tree_memory_bytes": metrics.peak_memory_bytes if metrics else None,
                "moves": [move.value for move in result.moves],
                "htm": result.verification.htm if result.verification else None,
                "qtm": result.verification.qtm if result.verification else None,
                "error": result.error,
            }
            output.write(json.dumps(record, sort_keys=True) + "\n")
            output.flush()
            statuses[result.status.value] += 1
            latencies.append(elapsed)
            if backend.last_worker_solve_seconds is not None:
                worker_latencies.append(backend.last_worker_solve_seconds)
            if backend.last_worker_initialization_seconds is not None:
                warm_initializations.append(backend.last_worker_initialization_seconds)
            if result.verification is not None:
                lengths.append(len(result.moves))
                htm_values.append(result.verification.htm)
                qtm_values.append(result.verification.qtm)
            if result.status is SolveStatus.RESOURCE_LIMIT:
                stopped_reason = "resource_limit"
                break

    completed = sum(statuses.values())
    verified = statuses[SolveStatus.SUCCESS.value]
    cache_inspection = backend.cache.inspect()
    summary = {
        "schema_version": 1,
        "git_commit": _git_commit(),
        "package_version": __version__,
        "solver_package": importlib.metadata.version("rubik-solver-py"),
        "numpy_package": importlib.metadata.version("numpy"),
        "psutil_package": importlib.metadata.version("psutil"),
        "python": sys.version,
        "platform": platform.platform(),
        "corpus": {
            "count_requested": args.count,
            "count_completed": completed,
            "scramble_length": args.scramble_length,
            "seed_range": [0, args.count - 1],
            "sha256": corpus_hash,
        },
        "limits": {
            "warm_timeout_seconds": args.timeout,
            "overall_timeout_seconds": args.overall_timeout,
            "max_moves": args.max_moves,
            "memory_bytes": backend.config.memory_limit_bytes,
            "cache_bytes": backend.config.cache_limit_bytes,
        },
        "cold_initialization": {
            "total_seconds": cold_elapsed,
            "process_seconds": cold_metrics.elapsed_seconds if cold_metrics else None,
            "worker_seconds": cold_worker_seconds,
        },
        "warm_initialization": {
            "average_seconds": statistics.fmean(warm_initializations)
            if warm_initializations
            else None,
            "maximum_seconds": max(warm_initializations) if warm_initializations else None,
        },
        "status_counts": dict(statuses),
        "verified_solve_rate": verified / completed if completed else 0.0,
        "rejected_or_invalid_responses": completed - verified,
        "latency_seconds": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        },
        "worker_solve_seconds": {
            "p50": _percentile(worker_latencies, 0.50),
            "p95": _percentile(worker_latencies, 0.95),
            "p99": _percentile(worker_latencies, 0.99),
        },
        "solution_length": {
            "average": statistics.fmean(lengths) if lengths else None,
            "maximum": max(lengths) if lengths else None,
        },
        "htm": {
            "average": statistics.fmean(htm_values) if htm_values else None,
            "maximum": max(htm_values) if htm_values else None,
        },
        "qtm": {
            "average": statistics.fmean(qtm_values) if qtm_values else None,
            "maximum": max(qtm_values) if qtm_values else None,
        },
        "timeouts": statuses[SolveStatus.TIMEOUT.value],
        "crashes_or_failures": statuses[SolveStatus.FAILURE.value],
        "peak_process_tree_memory_bytes": peak_memory,
        "generated_cache_bytes": cache_inspection.total_bytes,
        "stopped_reason": stopped_reason,
        "total_elapsed_seconds": time.perf_counter() - started,
    }
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if completed == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
