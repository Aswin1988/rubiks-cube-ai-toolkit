# Phase 2 Solver Benchmark

## Production runner

`benchmarks/phase2_solver_benchmark.py` exercises the same supervised subprocess and
independent verification path used by `cube-ai solve`. It constructs 20-move scrambles
from integer seeds beginning at zero, hashes the complete canonical corpus before solving,
writes every attempt as JSON Lines, and derives a separate JSON summary without dropping
failures.

Example:

```console
uv run python benchmarks/phase2_solver_benchmark.py \
  --count 1000 \
  --cache-root <external-cache-directory> \
  --output <external-results.jsonl> \
  --summary <external-summary.json>
```

Defaults bound each warm solve to 10 seconds, cap the process tree at 1 GiB, cap generated
tables at 64 MiB, and stop the full run after two hours. A process resource violation
stops the corpus and produces a partial summary. Ordinary per-state failures and timeouts
remain recorded and do not disappear from rate calculations.

## Phase 2C result

The completed run used Windows 11, Python 3.12.12, package version 0.2.0,
`rubik-solver-py==0.1.1`, NumPy 2.5.5, and psutil 7.2.2. The benchmark implementation was
at commit `872b8a6887c60ad33112f763efb7af46f9e64c22`. It processed all 1,000 cases (20-move
scrambles, seeds 0–999), with corpus SHA-256
`6ed57f361dff6d61a7b51b95318623ae1713991e7701175bc15bdea7348f5428`.

| Metric | Result |
| --- | ---: |
| Independently verified solutions | 999 / 1,000 (99.9%) |
| Timeouts / crashes | 1 / 0 |
| End-to-end latency P50 / P95 / P99 | 0.975 / 2.857 / 5.077 s |
| Worker solve latency P50 / P95 / P99 | 0.463 / 2.323 / 4.458 s |
| Successful solution length, average / maximum | 21.65 / 22 moves |
| Successful QTM, average / maximum | 32.35 / 38 |
| Cold initialization, total / worker | 27.02 / 26.48 s |
| Warm worker initialization, average / maximum | 0.0117 / 0.0405 s |
| Peak process-tree memory | 79,458,304 bytes (about 75.8 MiB) |
| Generated cache | 8,739,681 bytes (about 8.34 MiB) |
| Total run duration | 1,320.29 s |

Seed 650 was the single timeout. Its scramble was `F' R2 L2 D R2 B D2 U B' U2 R B R2
U' L R F2 L' R' L2`. The per-solve worker deadline was 10 seconds; recorded end-to-end
duration was 10.616 s, worker duration 10.587 s, and observed peak process-tree memory
43,266,048 bytes. The benchmark record reports approximately 2.025 seconds of solver
computation, but that timing is emitted by the worker only on successful return; it does
not explain the remaining worker lifetime and was not independently instrumented. Treat
the internal timing attribution for this one timeout as uncertain. The outcome remains a
timeout; the production deadline was not increased.

The earlier independent-engine conformance workload remains 20,000 intermediate-state
comparisons across seeds 0 through 999; it is a transition cross-check, not this solve
benchmark. The original JSONL and summary artifacts are retained outside the repository
under `D:\AI-Lab\experiments\rubiks-solver-evaluation\phase2c-production-872b8a6` and are
not committed.
