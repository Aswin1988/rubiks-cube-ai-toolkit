# Agent Engineering Guide

## Mission

Build trustworthy, reusable Rubik's Cube capabilities for AI agents. Prefer explicit
contracts, deterministic behavior, structured failures, and independent verification.

## Working rules

- Use Python 3.12 through `uv`.
- Keep the mathematical core free of runtime dependencies.
- Add type hints and docstrings to public APIs.
- Preserve the canonical conventions in `docs/architecture.md`.
- Never silently accept an invalid physical cube.
- Never claim a solution is correct without independent verification.
- Keep solver integrations behind the `Solver` protocol and review their licenses.
- Keep MCP, solver, and computer-vision dependencies optional.
- Use injected or recorded seeds for randomized research workloads.
- Do not commit generated tables, raw captures, credentials, or local caches.
- Run Ruff and the complete pytest suite before requesting review.

## Change discipline

Architectural or state-format changes require documentation, migration impact notes, and
golden-vector tests. Bug fixes should include a regression test. Benchmark changes must
record corpus and metric changes rather than silently replacing historical results.
