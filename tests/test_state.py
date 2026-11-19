"""State representation and conversion tests."""

from dataclasses import FrozenInstanceError

import pytest

from rubiks_cube_ai_toolkit import CubieState, Face, FaceletState, generate_scramble

SOLVED = "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB"


def test_solved_state_serialization_and_conversion() -> None:
    facelets = FaceletState.solved()
    assert facelets.serialize() == SOLVED
    assert FaceletState.parse(SOLVED.lower()) == facelets
    assert facelets.to_cubie() == CubieState.solved()
    assert CubieState.solved().to_facelets() == facelets


def test_facelet_parser_ignores_whitespace() -> None:
    formatted = "\n".join(SOLVED[index : index + 9] for index in range(0, 54, 9))
    assert FaceletState.parse(formatted).serialize() == SOLVED


def test_facelet_parser_reports_shape_and_alphabet() -> None:
    with pytest.raises(ValueError, match="exactly 54"):
        FaceletState.parse("U")
    with pytest.raises(ValueError, match="unknown"):
        FaceletState.parse("X" + SOLVED[1:])
    with pytest.raises(ValueError, match="exactly 54"):
        FaceletState((Face.U,))
    with pytest.raises(TypeError, match="Face values"):
        FaceletState(tuple("U" for _ in range(54)))  # type: ignore[arg-type]


def test_cubie_state_is_immutable_and_validates_coordinate_shape() -> None:
    state = CubieState.solved()
    with pytest.raises(FrozenInstanceError):
        state.corner_permutation = (0,) * 8  # type: ignore[misc]
    with pytest.raises(ValueError, match="8 values"):
        CubieState((0,), (0,) * 8, tuple(range(12)), (0,) * 12)
    with pytest.raises(ValueError, match=r"range \[0, 3\)"):
        CubieState(tuple(range(8)), (3,) + (0,) * 7, tuple(range(12)), (0,) * 12)


@pytest.mark.parametrize("coordinate", range(4))
def test_boolean_cubie_coordinates_are_rejected(coordinate: int) -> None:
    values = [list(range(8)), [0] * 8, list(range(12)), [0] * 12]
    values[coordinate][0] = False
    with pytest.raises(ValueError, match="must be integers"):
        CubieState(*(tuple(items) for items in values))


def test_cubie_mapping_serialization_round_trip() -> None:
    state = CubieState.solved().apply_moves(generate_scramble(30, seed="mapping"))
    assert CubieState.from_dict(state.to_dict()) == state


@pytest.mark.parametrize("seed", range(20))
def test_cubie_facelet_round_trip_for_seeded_states(seed: int) -> None:
    state = CubieState.solved().apply_moves(generate_scramble(25, seed=seed))
    assert state.to_facelets().to_cubie() == state


def test_unrecognized_cubie_colors_fail_conversion() -> None:
    facelets = list(FaceletState.solved().facelets)
    facelets[9], facelets[18] = facelets[18], facelets[9]
    with pytest.raises(ValueError, match="unrecognized corner"):
        FaceletState(tuple(facelets)).to_cubie()
