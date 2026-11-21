"""Independent sticker-cycle engine and verification tests."""

import pytest

from rubiks_cube_ai_toolkit.model import (
    Face,
    FaceletState,
    Move,
    generate_scramble,
    invert_moves,
)
from rubiks_cube_ai_toolkit.verification import (
    StickerState,
    VerificationStatus,
    move_counts,
    sticker_cycles,
    verify_solution,
)

SOLVED = "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB"

# Literal FaceletMove cycles transcribed from Herbert Kociemba's CubeDefs.
EXTERNAL_CLOCKWISE_CYCLES = {
    Face.U: ((0, 2, 8, 6), (1, 5, 7, 3), (9, 18, 36, 45), (10, 19, 37, 46), (11, 20, 38, 47)),
    Face.R: ((2, 51, 29, 20), (5, 48, 32, 23), (8, 45, 35, 26), (9, 11, 17, 15), (10, 14, 16, 12)),
    Face.F: ((6, 9, 29, 44), (7, 12, 28, 41), (8, 15, 27, 38), (18, 20, 26, 24), (19, 23, 25, 21)),
    Face.D: (
        (27, 29, 35, 33),
        (28, 32, 34, 30),
        (15, 51, 42, 24),
        (16, 52, 43, 25),
        (17, 53, 44, 26),
    ),
    Face.L: ((0, 18, 27, 53), (3, 21, 30, 50), (6, 24, 33, 47), (36, 38, 44, 42), (37, 41, 43, 39)),
    Face.B: ((0, 42, 35, 11), (1, 39, 34, 14), (2, 36, 33, 17), (45, 47, 53, 51), (46, 50, 52, 48)),
}


@pytest.mark.parametrize("face", Face)
def test_literal_cycles_match_external_kociemba_vectors(face: Face) -> None:
    assert sticker_cycles(face) == EXTERNAL_CLOCKWISE_CYCLES[face]


@pytest.mark.parametrize("move", Move)
def test_all_moves_match_geometry_engine_on_nonuniform_state(move: Move) -> None:
    prefix = generate_scramble(20, seed="nonuniform")
    geometry = FaceletState.solved().apply_moves(prefix).apply_move(move)
    independent = StickerState.solved().apply_moves(prefix).apply_move(move)
    assert independent.serialize() == geometry.serialize()


def test_1000_seeded_scrambles_match_at_every_intermediate_state() -> None:
    for seed in range(1000):
        geometry = FaceletState.solved()
        independent = StickerState.solved()
        for move in generate_scramble(20, seed=seed):
            geometry = geometry.apply_move(move)
            independent = independent.apply_move(move)
            assert independent.serialize() == geometry.serialize(), (seed, move)


def test_verifies_inverse_solution_and_reports_metrics_and_final_state() -> None:
    scramble = generate_scramble(12, seed=42)
    state = FaceletState.solved().apply_moves(scramble)
    solution = invert_moves(scramble)
    result = verify_solution(state, solution)
    assert result.status is VerificationStatus.VERIFIED
    assert result.verified
    assert result.final_state == SOLVED
    assert result.htm == 12
    assert result.qtm == sum(2 if move.value.endswith("2") else 1 for move in solution)
    assert result.to_dict()["verified"] is True


def test_rejects_incorrect_and_malformed_solutions() -> None:
    state = FaceletState.solved().apply_move(Move.R)
    incorrect = verify_solution(state, "U")
    malformed = verify_solution(state, "R3")
    assert incorrect.status is VerificationStatus.NOT_SOLVED
    assert incorrect.final_state is not None
    assert malformed.status is VerificationStatus.INVALID_MOVES
    assert malformed.final_state is None


def test_rejects_physically_invalid_initial_state() -> None:
    result = verify_solution("UUUUUUUUDRRRRRRRRRFFFFFFFFFDDUDDDDDDLLLLLLLLLBBBBBBBBB", "")
    assert result.status is VerificationStatus.INVALID_STATE


def test_sticker_state_shape_type_and_move_counts() -> None:
    with pytest.raises(ValueError, match="54"):
        StickerState((Face.U,))
    with pytest.raises(TypeError, match="Face values"):
        StickerState(tuple("U" for _ in range(54)))  # type: ignore[arg-type]
    assert StickerState.parse(SOLVED).serialize() == SOLVED
    assert move_counts((Move.R, Move.U2, Move.F_PRIME)) == (3, 4)
