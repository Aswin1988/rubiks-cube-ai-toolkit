# Deterministic Solver Evaluation

Evaluated 2026-11-19 for Python 3.12/3.13 and MIT-licensed distribution. This
review separates license compatibility from operational suitability: an MIT label
alone is not enough when initialization, timeout enforcement, determinism, or supported
platforms remain unresolved.

## Phase 2C decision (2026-11-21)

`rubik-solver-py==0.1.1` is selected only behind a separately managed subprocess. The
optional `solver` extra pins the evaluated NumPy and psutil versions as well. It is not
safe to call the package in-process because its API has no cooperative wall-clock
deadline.

The isolated Windows evaluation observed:

- cold initialization: 28.150 seconds internally, 8,738,477 bytes of tables;
- peak cold working set: 90,095,616 bytes; peak private allocation: 439,865,344 bytes;
- cached initialization: 0.024 seconds internally;
- fixed 20-state corpus: 20/20 returned and 20/20 independently verified;
- warm solve P50/P95: 0.364/1.873 seconds;
- one identical solution across 11 fresh and reused-process repetitions;
- successful Python 3.13 installation, cached initialization, solve, and verification.

The production adapter adds hard parent-side deadlines, process-tree termination, bounded
JSON IPC and diagnostics, memory/disk monitoring, a 64 MiB cache ceiling, atomic table
publication, concurrent-initializer locking, and SHA-256 corruption detection.

The same evaluation stopped `tcbegley/cube-solver` at the five-minute cold-initialization
deadline. It had reached only 17% of one pruning table, with about 15 minutes reported as
remaining for that table. Peak working set was 913,256,448 bytes. Later solve and
determinism stages were not run.

Raw Phase 2B evidence was kept outside the repository under the approved experiment
directory. The Phase 2C production benchmark and its corpus hash are reported in
[phase2-benchmark.md](phase2-benchmark.md).

## Phase 2 draft decision (2026-11-19)

No third-party solver was integrated in the initial Phase 2 draft. The public `Solver` protocol and
mandatory independent-verification gate are implemented, while the CLI returns the
structured `unavailable` outcome for non-solved inputs. This follows the project rule
that unresolved solver behavior must not be presented as a reliable capability.

`cube-solver` 1.1.4 is the leading candidate for a later adapter after its table lifecycle
is isolated and its resource behavior is understood. `twophase` is the strongest
pure-Python alternative, but its initialization cost and first-result concurrency need
additional reproducibility work.

## Candidate matrix

| Candidate | License and redistribution | Python/platform and installation | Maintenance | Initialization and memory | Determinism and limits | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| [`cube-solver` 1.1.4](https://pypi.org/project/cube-solver/1.1.4/) | MIT; preserve license/copyright notices. PyPI has trusted-publishing provenance tied to release commit `0a92ffefa0b36c83ad0f6f544ea70462c73d7e68`. | Requires Python >=3.9. PyPI publishes CPython 3.12 and 3.13 wheels for Windows, Linux, and macOS architectures. Runtime includes NumPy and CLI dependencies. | Latest release 1.1.4 was published 2025-07-13; no newer PyPI release was present at review time. | Generates transition/pruning `.npz` files in a relative `tables` directory. In the observed Windows run, transition generation completed but pruning initialization did not return. Peak memory was therefore not measured. | Kociemba search order appears sequential, and API exposes `max_length` and an integer timeout. Hard timeout/resource enforcement has not been independently established. | License-compatible, operationally blocked. |
| [`tcbegley/cube-solver`](https://github.com/tcbegley/cube-solver) (`twophase`) | MIT; preserve notice. Installed directly from a Git commit rather than a stable PyPI release. | Python >=3.12. Pure Python suggests Windows/Linux/macOS portability; upstream workflow coverage must be expanded before claiming full support. | Active repository with 82 commits at review time; reviewed head was [`a95c827`](https://github.com/tcbegley/cube-solver/commit/a95c8275e19ef7ac22793bb4610d85af955a66eb) from 2026-08-31. | Project documentation says first solve generates cached tables and can take several minutes; cache path is configurable. Memory is not documented. | Supports float timeout and maximum length. Lower-level concurrent symmetry searches return the first completed result, so repeatable solution selection needs a pinned test. | Defer pending initialization and determinism measurements. |
| [`rubik-solver-py`](https://pypi.org/project/rubik-solver-py/) | MIT; preserve notice. | Python >=3.8 and OS-independent classifier; Python 3.12 is declared, but Python 3.13 support is not declared on the reviewed release. Depends on NumPy. | Latest reviewed PyPI release was published 2026-02-22; the project is comparatively new. | Documentation reports 30-60 seconds for first table generation and about 15 ms cached startup. Cache directory is configurable. | Exposes maximum depth but no execution-time limit in its documented `solve` API. | Defer: missing declared 3.13 support and enforceable timeout. |
| [`kociemba` 1.2.1](https://pypi.org/project/kociemba/) | GPLv2. Redistributing or linking it with this MIT project would add GPL obligations incompatible with the intended permissive distribution model. | Old wheels target historical CPython versions. Its documentation says Windows was not automatically tested and may require Microsoft build tools; Unix may require `libffi-dev`. | Latest PyPI release was 2019-06-26. | C implementation falls back to a much slower Python implementation. Package data is large and current 3.12/3.13 installation evidence is absent. | No documented per-call timeout. | Rejected for license and maintenance/platform reasons. |

## Reproduction notes for the leading candidate

The following checks used Python 3.12.12, Windows, `uv`, and an isolated environment:

1. `cube-solver==1.1.4` installed successfully from PyPI and reported version 1.1.4.
2. Its `Kociemba` API exposed transition/pruning-table toggles, `max_length`, and an
   integer timeout. CPython wheel installation itself succeeded.
3. Initialization with tables wrote `tables/transition.npz` (2,032,628 bytes) and
   `tables/pruning_kociemba.npz` (1,634,214,551 bytes), then terminated before
   reaching the caller's completion marker on repeated attempts. Generated files were
   removed from the repository.
4. Initialization with both table types disabled completed, but solving the five-move
   state `R U F2 L D` returned no solution after 10.0041 seconds.

These are observations from this environment, not claims about every Windows host.
Because initialization did not complete, cold time, peak memory, 1,000-state latency,
failure rate, and solution determinism could not be measured honestly.

## Requirements for reconsideration

- Pin a reviewed release and record every transitive runtime license.
- Put tables in an explicit user cache, never the working tree.
- Complete cold initialization under a measured memory ceiling on all CI operating systems.
- Demonstrate identical results across repeated calls and Python 3.12/3.13.
- Enforce a wall-clock deadline outside the dependency, not only a cooperative timeout.
- Run the fixed 1,000-state corpus with independent verification before enabling `solve`.
