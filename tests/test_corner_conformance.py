"""Corner-identification conformance and adversarial regression tests."""

import pytest

from rubiks_cube_ai_toolkit import CubieState, Face, FaceletState, ValidationCode, validate_state
from rubiks_cube_ai_toolkit.model.facelets import CORNER_FACELETS

REPORTED_IMPOSSIBLE_STATE = "UUUUUUUUDRRRRRRRRRFFFFFFFFFDDUDDDDDDLLLLLLLLLBBBBBBBBB"


def test_reported_impossible_corner_state_is_rejected() -> None:
    result = validate_state(REPORTED_IMPOSSIBLE_STATE)
    assert not result.valid
    assert result.has_code(ValidationCode.INVALID_CORNER)


def test_reported_impossible_corner_state_cannot_convert_to_cubies() -> None:
    state = FaceletState.parse(REPORTED_IMPOSSIBLE_STATE)
    with pytest.raises(ValueError, match="unrecognized corner"):
        state.to_cubie()


@pytest.mark.parametrize("corner", range(8))
@pytest.mark.parametrize("orientation", range(3))
def test_all_corner_identities_in_all_orientations_round_trip(
    corner: int, orientation: int
) -> None:
    orientations = [0] * 8
    orientations[corner] = orientation
    orientations[(corner + 1) % 8] = (-orientation) % 3
    cubies = CubieState(
        tuple(range(8)),
        tuple(orientations),
        tuple(range(12)),
        (0,) * 12,
    )

    facelets = cubies.to_facelets()

    assert facelets.to_cubie() == cubies
    assert validate_state(facelets).valid


@pytest.mark.parametrize(
    "mirrored_colors",
    [
        (Face.U, Face.F, Face.R),
        (Face.R, Face.U, Face.F),
        (Face.F, Face.R, Face.U),
    ],
)
def test_mirrored_corner_color_orders_are_rejected(
    mirrored_colors: tuple[Face, Face, Face],
) -> None:
    facelets = list(FaceletState.solved().facelets)
    for index, color in zip(CORNER_FACELETS[0], mirrored_colors, strict=True):
        facelets[index] = color
    state = FaceletState(tuple(facelets))

    result = validate_state(state)

    assert not result.valid
    assert result.has_code(ValidationCode.INVALID_CORNER)
    with pytest.raises(ValueError, match="unrecognized corner"):
        state.to_cubie()
