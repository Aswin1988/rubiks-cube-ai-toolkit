"""Move notation, geometry, and algebra tests."""

from itertools import pairwise

import pytest

from rubiks_cube_ai_toolkit import (
    CubieState,
    Face,
    FaceletState,
    Move,
    MoveParseError,
    generate_scramble,
    invert_moves,
    normalize_moves,
    parse_moves,
)


def test_all_18_moves_are_exposed() -> None:
    assert len(Move) == 18
    assert {move.face for move in Move} == set(Face)


@pytest.mark.parametrize("move", Move)
def test_move_and_inverse_restore_state(move: Move) -> None:
    state = FaceletState.solved().apply_moves((move, move.inverse()))
    assert state.is_solved


@pytest.mark.parametrize("face", Face)
def test_four_quarter_turns_restore_state(face: Face) -> None:
    move = Move(face.value)
    assert FaceletState.solved().apply_moves((move,) * 4).is_solved


def test_known_u_move_cubie_vector() -> None:
    state = CubieState.solved().apply_move(Move.U)
    assert state.corner_permutation == (3, 0, 1, 2, 4, 5, 6, 7)
    assert state.corner_orientation == (0,) * 8
    assert state.edge_permutation == (3, 0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11)
    assert state.edge_orientation == (0,) * 12


def test_known_r_move_cubie_vector() -> None:
    state = CubieState.solved().apply_move(Move.R)
    assert state.corner_permutation == (4, 1, 2, 0, 7, 5, 6, 3)
    assert state.corner_orientation == (2, 0, 0, 1, 1, 0, 0, 2)
    assert state.edge_permutation == (8, 1, 2, 3, 11, 5, 6, 7, 4, 9, 10, 0)
    assert state.edge_orientation == (0,) * 12


def test_known_f_move_cubie_vector() -> None:
    state = CubieState.solved().apply_move(Move.F)
    assert state.corner_permutation == (1, 5, 2, 3, 0, 4, 6, 7)
    assert state.corner_orientation == (1, 2, 0, 0, 2, 1, 0, 0)
    assert state.edge_permutation == (0, 9, 2, 3, 4, 8, 6, 7, 1, 5, 10, 11)
    assert state.edge_orientation == (0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0)


def test_parse_invert_and_apply_sequence() -> None:
    moves = parse_moves("R U R' U'")
    assert moves == (Move.R, Move.U, Move.R_PRIME, Move.U_PRIME)
    scrambled = FaceletState.solved().apply_moves(moves)
    assert not scrambled.is_solved
    assert scrambled.apply_moves(invert_moves(moves)).is_solved


def test_parse_accepts_iterable_and_rejects_invalid_token() -> None:
    assert parse_moves([Move.R, "U2"]) == (Move.R, Move.U2)
    with pytest.raises(MoveParseError, match="index 1"):
        parse_moves("R X")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("R R", (Move.R2,)),
        ("R R2", (Move.R_PRIME,)),
        ("R R'", ()),
        ("R R R R", ()),
        ("R U U' R'", ()),
        ("R U R'", (Move.R, Move.U, Move.R_PRIME)),
    ],
)
def test_normalization(source: str, expected: tuple[Move, ...]) -> None:
    moves = parse_moves(source)
    normalized = normalize_moves(moves)
    assert normalized == expected
    assert FaceletState.solved().apply_moves(moves) == FaceletState.solved().apply_moves(normalized)


def test_scramble_is_seeded_and_avoids_repeated_faces() -> None:
    scramble = generate_scramble(20, seed=42)
    assert " ".join(move.value for move in scramble) == (
        "B U' D R U' B L2 U R F' B L B2 R2 B2 U L2 F R2 U"
    )
    assert all(left.face is not right.face for left, right in pairwise(scramble))


def test_scramble_length_validation() -> None:
    assert generate_scramble(0, seed=1) == ()
    with pytest.raises(ValueError, match="non-negative"):
        generate_scramble(-1)
