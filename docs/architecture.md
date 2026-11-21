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

## Independent verification boundary

The verification engine advances stickers through literal four-cycles transcribed from
external conformance data. It does not import the geometry permutation generator.
Verification validates the initial state, rejects malformed notation, returns the final
state, and reports HTM and QTM counts.

## Solver boundary

Third-party deterministic solvers implement the small `Solver` protocol. `VerifiedSolver`
validates inputs, handles solved cubes, enforces time and move limits, and independently
checks every proposed solution. A backend response cannot become `success` when this gate
fails.

The reviewed implementation is `RubikSolverSubprocess`, backed by the optional
`rubik-solver-py==0.1.1` extra. The main process sends one size-bounded JSON request to a
private module worker and accepts one size-bounded JSON response. The worker never imports
the mathematical transition engine or the independent verifier. The parent remains the
only authority that can validate physical reachability and report verified success.

## Subprocess safety

The supervisor invokes the current Python interpreter without a shell. Standard output
and error are drained concurrently but retained only up to configured bounds. Public
errors use stable messages and never include captured stderr or cache paths.

Each worker receives a new process group/session. On Windows the supervisor uses
`taskkill /T /F` plus a captured psutil descendant set; on POSIX it kills the process
group plus captured descendants. Cleanup runs from `finally` even when monitoring or IPC
fails.

Wall-clock deadlines are hard from the parent's perspective. Process-tree resident memory
and generated-directory growth are sampled with psutil and filesystem measurements. A
sampled limit violation kills the tree, but these are not identical to kernel quotas:

- Windows has no Job Object quota in this implementation; a very fast allocation may
  briefly exceed the configured budget between samples.
- Linux and macOS use the same sampling policy rather than `RLIMIT_AS`, because NumPy and
  BLAS may reserve virtual address space far beyond resident memory.
- Descendants that deliberately escape their process group and re-parent between samples
  cannot be guaranteed catchable on every OS. The reviewed worker does not daemonize or
  launch solver children.

Generated tables live in a versioned operating-system user cache, never the repository.
Initialization uses an exclusive lock, a same-filesystem staging directory, exact file
and size checks, NumPy magic checks, SHA-256 integrity metadata, and atomic directory
publication. Incomplete or corrupted caches are rebuilt under the lock. Cold
initialization and warm solving have separate deadlines.
