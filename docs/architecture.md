# Architecture

## Dependency direction

The dependency-free mathematical model is the foundation. Validation may depend on the
model. Future solver adapters, verification, CLI, MCP, skills, benchmarks, and vision may
depend on the model and validation, but the model must not depend on them.

## Canonical coordinates

Faces use `U R F D L B`. Facelet serialization contains nine row-major stickers for each
face in that order, viewed directly from outside the face.

Corner positions and cubie identities are ordered:

```text
URF UFL ULB UBR DFR DLF DBL DRB
```

Edge positions and cubie identities are ordered:

```text
UR UF UL UB DR DF DL DB FR FL BL BR
```

Corner orientations are integers modulo 3. Edge orientations are integers modulo 2.
For reachable states, corner orientations sum to 0 modulo 3, edge orientations sum to 0
modulo 2, and corner and edge permutation parity are equal.

## Move convention

A bare face token is a clockwise quarter turn when looking directly at that face. A token
ending in `2` is a half turn and a token ending in `'` is counter-clockwise. The engine
generates facelet permutations from an integer three-dimensional coordinate model to keep
all face conventions explicit and auditable.

## Representation boundaries

`CubieState` stores permutations and orientations and supports efficient invariant checks.
`FaceletState` is the interchange representation used by users, future vision components,
and the independent verifier. Conversion is deterministic and lossless for structurally
recognized states.

## Validation boundary

Parsing establishes only the shape and alphabet of a facelet string. Physical validation
is separate and returns all safely detectable diagnostics. A parsed state is not therefore
assumed reachable.

## Future solver boundary

Mature deterministic solvers will be integrated behind a small `Solver` protocol. Solver
results will be checked by an independently implemented facelet verifier before exposure
through CLI or MCP interfaces.
