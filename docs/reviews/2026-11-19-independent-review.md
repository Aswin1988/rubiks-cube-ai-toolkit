# Independent Review: Corner Identification Defect

Date: 2026-11-19

Severity: P0 mathematical correctness

Affected pull request: #1

## Results reported before independent review

The original milestone submission reported:

- Ruff formatting and linting passed.
- 79 tests passed.
- Branch-aware coverage was 98.42%.
- The initial GitHub Actions matrix passed on Python 3.12 and 3.13 across Linux, Windows,
  and macOS.

Those results were accurate, but the test oracle did not cover the defective identity
condition described below.

## Defect and root cause

Both `FaceletState.to_cubie()` and the physical validator located the U/D sticker in an
observed corner but then discarded its color. They identified the cubie using only the
remaining ordered side-color pair. Consequently, `(U, R, F)` and `(D, R, F)` could both be
identified as the URF cubie even though only the first triple is a real corner identity.

The fix rotates the observed triple so its U/D sticker is first and requires the complete
ordered triple to equal one canonical corner identity. The conversion and validator now
share this exact matching rule.

## Reproduction

Starting from the solved facelet string, swap zero-based facelet indices 8 and 29:

```text
UUUUUUUUDRRRRRRRRRFFFFFFFFFDDUDDDDDDLLLLLLLLLBBBBBBBBB
```

Before changing the implementation, two executable regression tests were added and run:

```text
FF                                                                       [100%]
================================== FAILURES ===================================
______________ test_reported_impossible_corner_state_is_rejected ______________

    def test_reported_impossible_corner_state_is_rejected() -> None:
        result = validate_state(REPORTED_IMPOSSIBLE_STATE)
>       assert not result.valid
E       assert not True
E        +  where True = ValidationResult(issues=(), state=CubieState(corner_permutation=(0, 1, 2, 3, 4, 5, 6, 7), corner_orientation=(0, 0, 0,...0, 0), edge_permutation=(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11), edge_orientation=(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))).valid

tests\test_corner_conformance.py:14: AssertionError
_______ test_reported_impossible_corner_state_cannot_convert_to_cubies ________

    def test_reported_impossible_corner_state_cannot_convert_to_cubies() -> None:
        state = FaceletState.parse(REPORTED_IMPOSSIBLE_STATE)
>       with pytest.raises(ValueError, match="unrecognized corner"):
E       Failed: DID NOT RAISE ValueError

tests\test_corner_conformance.py:20: Failed
=========================== short test summary info ===========================
FAILED tests/test_corner_conformance.py::test_reported_impossible_corner_state_is_rejected
FAILED tests/test_corner_conformance.py::test_reported_impossible_corner_state_cannot_convert_to_cubies
2 failed in 0.08s
```

The validator incorrectly returned a valid solved `CubieState`, and conversion did not
raise an error.

## Verification after the fix

The focused regression and corner-conformance suite produced:

```text
.............................                                            [100%]
29 passed in 0.05s
```

The complete suite produced:

```text
collected 115 items
tests\test_cli.py ..                                                     [  1%]
tests\test_corner_conformance.py .............................           [ 26%]
tests\test_moves.py .........................................            [ 62%]
tests\test_state.py ..............................                       [ 88%]
tests\test_validation.py .............                                   [100%]

Required test coverage of 90.0% reached. Total coverage: 98.78%
============================= 115 passed in 0.76s =============================
```

The expanded tests cover all eight corner identities in all three orientations, the
reported substituted U/D case, all three mirrored orders of the URF colors, Boolean
coordinate rejection, and externally grounded D/L/B base-move vectors.

## Why high coverage missed the defect

Coverage established that the corner-identification branches executed; it did not
establish that the matching predicate contained every required mathematical condition.
Existing positive round-trip tests generated facelets from the same canonical tables used
for conversion, so they could not produce a substituted or mirrored identity. Existing
negative tests used obviously invalid side-color combinations, which exercised the failure
branch without challenging the omitted U/D comparison.

The issue was therefore an oracle and input-space weakness, not an unexecuted-code weakness.

## Lessons for AI-generated software verification

- High statement and branch coverage are insufficient evidence of mathematical correctness.
- Round trips using a shared representation can reproduce the same mistaken assumption in
  both directions.
- Identity checks should compare complete canonical values, not a convenient subset.
- Tests need adversarial near-valid inputs that differ from valid inputs by one invariant.
- External conformance vectors should cover every generator, with provenance recorded.
- Independent source review and independently designed test oracles remain necessary even
  when automated checks are green.
