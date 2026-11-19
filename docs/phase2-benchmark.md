# Phase 2 Benchmark Status

The requested 1,000-state solver benchmark was not executed because no solver dependency
passed both license and operational review. Reporting latency percentiles, move counts,
memory, or success rates without a functioning integrated solver would be fabricated.

The independent-engine conformance workload did run as an automated test. It uses seeds
0 through 999, creates a 20-move scramble for each seed, and compares the existing
geometry engine with the independent sticker-cycle engine after every move (20,000
intermediate comparisons). This is a correctness cross-check, not a solve benchmark.

See [solver-evaluation.md](solver-evaluation.md) for the blocker and the measurements that
must be recorded when an adapter becomes eligible.
