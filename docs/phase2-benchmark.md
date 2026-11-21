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

The full 1,000-state production run will be recorded here after the integration revision
passes the complete local correctness, safety, packaging, and interpreter-matrix gates.
The earlier independent-engine conformance workload remains 20,000 intermediate-state
comparisons across seeds 0 through 999; it is a transition cross-check, not a solve
benchmark.
