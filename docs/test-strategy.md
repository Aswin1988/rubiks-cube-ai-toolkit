# Test Strategy

## Layers

Unit tests cover state construction, known move vectors, notation, normalization,
conversion, serialization, and each validation diagnostic. Algebraic tests cover move
inverses, four quarter turns, round trips, and deterministic scrambles.

Externally grounded move vectors and their provenance are recorded in
`docs/conformance-vectors.md`. Corner identification tests cover every identity in every
orientation as well as mirrored and substituted-color adversarial inputs.

Future conformance tests will compare the mathematical engine with independent published
vectors and solver adapters. The solution verifier must not import solver transition code.

## Required gates

- Ruff formatting check
- Ruff linting
- Pytest on supported Python versions
- Branch coverage of at least 90 percent during the foundation phase
- Source distribution and wheel build smoke tests when publishing is introduced

## Failure policy

Tests must use fixed seeds and expose the failing state and move sequence. Timeouts and
unsupported inputs are explicit outcomes. Tests may not silently retry nondeterministic
failures or update golden files during CI.
