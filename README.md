# Rubik's Cube AI Toolkit

Reliable, deterministic Rubik's Cube primitives for AI agents and reproducible
technical research.

The project focuses on capabilities an agent can execute and independently check:
canonical cube-state modeling, physical reachability validation, deterministic solving
through a pluggable solver interface, independent solution verification, and reproducible
benchmarks.

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
- local stdio MCP tools for those same five verified operations;
- an optional `rubik-solver-py` backend isolated behind a supervised JSON subprocess.

The solver extra is deliberately optional. Without it, `solve` reports an actionable
`unavailable` result; modeling, validation, move application, and verification remain
dependency-free. MCP and solver dependencies are separate optional extras. Agent skills
and computer vision remain out of scope.

## Requirements

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/) for the reproducible development environment
- Node.js 20.9 or newer and npm for the interactive web demo

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

Install the local MCP server, with the solver backend when `cube_solve` is required:

```console
uv sync --dev --extra mcp --extra solver
```

If the machine-wide `uv` cache is unavailable, use an ignored local cache:

```console
$env:UV_CACHE_DIR = ".uv-cache"
uv sync --dev
```

## Interactive web demo

The local demo uses a FastAPI adapter on port 8000 and a Next.js frontend on port
3000. Install the API and reviewed solver dependencies, then start the backend from
the repository root:

```console
uv sync --dev --extra api --extra solver
uv run uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, install the locked frontend dependencies and start Next.js:

```console
cd apps/web
npm ci
npm run dev
```

Open <http://localhost:3000>. The frontend uses <http://localhost:8000> by default.
To use a different API origin, set `NEXT_PUBLIC_API_URL` in an ignored
`apps/web/.env.local` file before starting Next.js. If the frontend origin changes,
also include it in the backend's comma-separated `CUBE_CORS_ORIGINS` environment
variable.

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

## MCP server

`cube-ai-mcp` runs a local stdio server using the official Python MCP SDK. It exposes
exactly five tools: `cube_scramble`, `cube_validate`, `cube_apply`, `cube_solve`, and
`cube_verify`. Every tool returns a JSON object with `ok`, `tool`, `data`, and `error`
fields. Invalid physical states and invalid notation are structured tool results rather
than silently accepted inputs. Successful solve results have passed the independent
sticker-cycle verifier.

Example configuration for clients that accept a JSON stdio server definition:

```json
{
  "mcpServers": {
    "rubiks-cube": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/rubiks-cube-ai-toolkit",
        "run",
        "--extra",
        "mcp",
        "--extra",
        "solver",
        "cube-ai-mcp"
      ]
    }
  }
}
```

Use an absolute repository path, restart the client after changing its configuration, and
omit `--extra solver` if solving is not needed. In an installed environment, configure
the client with `"command": "cube-ai-mcp"` and no arguments. The server writes protocol
messages only to stdio; do not wrap it with a command that prints to stdout.

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

## Solver benchmark

The fixed-seed Windows 11 / Python 3.12 benchmark processed 1,000 twenty-move scrambles
(seeds 0–999; corpus SHA-256
`6ed57f361dff6d61a7b51b95318623ae1713991e7701175bc15bdea7348f5428`) with
`rubik-solver-py==0.1.1`. It returned 999 independently verified solutions and one
10-second timeout (seed 650); there were no crashes. Verified solve rate was 99.9%.
End-to-end P50/P95/P99 latency was 0.98/2.86/5.08 seconds; successful solutions averaged
21.65 moves, with a maximum of 22. Peak observed process-tree memory was 79.5 MB, generated
tables occupied 8.74 MB, and cold initialization took 27.02 seconds. See the complete
[benchmark methodology and result](docs/phase2-benchmark.md), including the timeout and
reproduction command.

## License

Original project code is licensed under the [MIT License](LICENSE). Third-party solver and
MCP dependencies have documented license notices; their licenses remain their own.
Computer-vision dependencies will receive review before integration.

Optional dependency attribution is recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Contributing

Read [AGENTS.md](AGENTS.md), [docs/test-strategy.md](docs/test-strategy.md), and the
[roadmap](docs/roadmap.md) before making architectural changes. Contributions should be
small, typed, documented, deterministic by default, and covered by tests.
