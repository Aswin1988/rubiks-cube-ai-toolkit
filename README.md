# Rubik's Cube AI Toolkit

Reliable, deterministic Rubik's Cube primitives for AI agents and reproducible
technical research.

The project focuses on capabilities an agent can execute and independently check:
canonical cube-state modeling, physical reachability validation, deterministic solving
through a pluggable solver interface, independent solution verification, an MCP server,
and reproducible benchmarks.

## Current scope

The current implementation provides:

- immutable cubie and facelet state representations;
- all 18 Singmaster face moves;
- move parsing, inversion, local normalization, and seeded scrambles;
- conversion between cubie and facelet representations;
- structured validation of physical cube constraints.
- an independent sticker-cycle verification engine with HTM/QTM metrics;
- a verification-gated `Solver` protocol and structured failure outcomes;
- functional `scramble`, `validate`, `apply`, `solve`, and `verify` CLI commands.

A reviewed solver dependency is not yet enabled; `solve` reports `unavailable` for
non-solved cubes. The measured blocker and candidate review are documented in
[docs/solver-evaluation.md](docs/solver-evaluation.md). MCP tools, agent skills, and
computer vision remain out of scope.

## Requirements

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/) for the reproducible development environment

## Development

```console
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

If the machine-wide `uv` cache is unavailable, use an ignored local cache:

```console
$env:UV_CACHE_DIR = ".uv-cache"
uv sync --dev
```

## State and notation conventions

Facelets are serialized as 54 symbols in `URFDLB` face order. Each face is read
row-by-row as viewed directly from outside that face. A solved state is:

```text
UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB
```

Moves use standard Singmaster tokens: `U R F D L B`, an optional `2` for a half turn,
or an optional apostrophe for a counter-clockwise turn. Clockwise is always defined as
viewed directly at the rotated face. See [docs/architecture.md](docs/architecture.md)
for cubie ordering and invariants.

## Example

```python
from rubiks_cube_ai_toolkit import CubieState, parse_moves, validate_state

state = CubieState.solved().apply_moves(parse_moves("R U R' U'"))
result = validate_state(state.to_facelets())
assert result.valid
```

## CLI

```console
cube-ai scramble --length 20 --seed research-1 --json
cube-ai validate UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB
cube-ai apply UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB R U "R'" "U'"
cube-ai verify <state> R U2 "F'"
cube-ai solve <state> --timeout 10 --max-moves 30 --json
```

Exit codes are 0 for success, 2 for usage or notation errors, 3 for invalid states or
failed verification, 4 for timeout, and 5 for solver failure or unavailability.

## Reliability policy

Solver output is never treated as correct merely because the solver returned it. The
independent facelet engine uses literal sticker cycles rather than the mathematical
engine's geometry. Research results identify their corpus, seed, software revision,
environment, and verification status.

## License

Original project code is licensed under the [MIT License](LICENSE). Third-party solver,
MCP, and computer-vision dependencies will receive a documented license review before
integration; their licenses remain their own.

## Contributing

Read [AGENTS.md](AGENTS.md), [docs/test-strategy.md](docs/test-strategy.md), and the
[roadmap](docs/roadmap.md) before making architectural changes. Contributions should be
small, typed, documented, deterministic by default, and covered by tests.
