# Test Strategy

## Layers

Unit tests cover state construction, known move vectors, notation, normalization,
conversion, serialization, and each validation diagnostic. Algebraic tests cover move
inverses, four quarter turns, round trips, and deterministic scrambles.

Externally grounded move vectors and their provenance are recorded in
`docs/conformance-vectors.md`. Corner identification tests cover every identity in every
orientation as well as mirrored and substituted-color adversarial inputs.

Conformance tests compare all 18 moves against the independent sticker-cycle engine over
1,000 fixed seeds and assert every intermediate state. Deliberately incorrect solver
responses test the mandatory verification gate. The solution verifier must not import
solver transition code.

MCP tests call every tool contract directly for valid and invalid inputs, assert the exact
five-tool registration surface, exercise timeout, resource-limit, and unavailable solver
outcomes through an injected verified-solver service, and check the actionable failure when
the optional SDK is absent. Direct contract tests avoid starting a real stdio loop while
the wheel smoke test confirms the optional MCP extra can construct the packaged server.

Subprocess tests use lightweight synthetic workers to exercise bounded IPC, malformed
JSON, crashes, hard deadlines, memory/disk stops, output truncation, and full descendant
termination. Cache tests cover incomplete files, wrong sizes and headers, same-size hash
corruption, stale locks, atomic replacement, and concurrent initialization. One marked
test invokes the real pinned solver from an empty temporary cache and independently
verifies its result. The CI matrix installs the optional solver extra on Python 3.12 and
3.13 across Windows, Linux, and macOS.

## Required gates

- Ruff formatting check
- Ruff linting
- Pytest on supported Python versions
- Branch coverage of at least 90 percent during the foundation phase
- Source distribution and wheel build smoke tests on every pull request
- Real optional-solver subprocess and cache initialization on supported interpreters
- MCP server construction from the built wheel with only the optional `mcp` extra

## Failure policy

Tests must use fixed seeds and expose the failing state and move sequence. Timeouts and
unsupported inputs are explicit outcomes. Tests may not silently retry nondeterministic
failures or update golden files during CI.
