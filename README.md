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
- functional `scramble`, `validate`, `apply`, `solve`, and `verify` CLI commands;
- an optional `rubik-solver-py` backend isolated behind a supervised JSON subprocess.

The solver extra is deliberately optional. Without it, `solve` reports an actionable
`unavailable` result; modeling, validation, move application, and verification remain
dependency-free. MCP tools, agent skills, and computer vision remain out of scope.

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

Install the reviewed deterministic solver stack when solving is required:

```console
uv sync --dev --extra solver
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

`--timeout` is the warm solve deadline. First use may spend up to 60 seconds creating
about 9 MiB of validated tables in the operating system's user cache; use
`--init-timeout` to change that one-time deadline. The default process-tree memory budget
is 1 GiB and the generated-cache ceiling is 64 MiB.

Example verified solve:

```console
cube-ai solve BUUBUULDDLBBLRRBRRUFFUFFURRRDDDDFBBFLLFLLFUBFLLDUBDDRR --json
```

If the optional extra is absent, install it with `uv sync --extra solver` (or install the
wheel with its `[solver]` extra) and retry.

Exit codes are 0 for success, 2 for usage or notation errors, 3 for invalid states or
failed verification, 4 for timeout, and 5 for solver failure or unavailability.

## Reliability policy

Solver output is never treated as correct merely because the solver returned it. The
independent facelet engine uses literal sticker cycles rather than the mathematical
engine's geometry. Research results identify their corpus, seed, software revision,
environment, and verification status.

The optional backend runs with `shell=False` in a separate process group. The supervisor
bounds input, output, time, process-tree memory, and table-directory growth, then kills
the complete discoverable process tree on a limit violation. Memory and disk limits are
sampling-based rather than identical kernel-enforced quotas on every supported OS; see
[the architecture notes](docs/architecture.md#subprocess-safety) for platform details.

## License

Original project code is licensed under the [MIT License](LICENSE). Third-party solver,
MCP, and computer-vision dependencies will receive a documented license review before
integration; their licenses remain their own.

Optional solver attribution is recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Contributing

Read [AGENTS.md](AGENTS.md), [docs/test-strategy.md](docs/test-strategy.md), and the
[roadmap](docs/roadmap.md) before making architectural changes. Contributions should be
small, typed, documented, deterministic by default, and covered by tests.
