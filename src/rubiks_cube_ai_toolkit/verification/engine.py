"""Independent sticker-cycle facelet engine and solution verification."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from rubiks_cube_ai_toolkit.model.facelets import FaceletState
from rubiks_cube_ai_toolkit.model.moves import Face, Move, MoveParseError, parse_moves
from rubiks_cube_ai_toolkit.validation import validate_state

# Each tuple is a source-to-destination cycle converted from Kociemba's
# published FaceletMove pull tables. The data is independent of geometry.
_CLOCKWISE_CYCLES: dict[Face, tuple[tuple[int, int, int, int], ...]] = {
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


def sticker_cycles(face: Face) -> tuple[tuple[int, int, int, int], ...]:
    """Return literal clockwise sticker cycles for external conformance tests."""
    return _CLOCKWISE_CYCLES[face]


class VerificationStatus(StrEnum):
    """Stable outcomes for independent solution verification."""

    VERIFIED = "verified"
    INVALID_STATE = "invalid_state"
    INVALID_MOVES = "invalid_moves"
    NOT_SOLVED = "not_solved"


@dataclass(frozen=True, slots=True)
class StickerState:
    """Immutable facelets advanced only through literal sticker cycles."""

    facelets: tuple[Face, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "facelets", tuple(self.facelets))
        if len(self.facelets) != 54:
            raise ValueError("a sticker state must contain exactly 54 facelets")
        if any(not isinstance(facelet, Face) for facelet in self.facelets):
            raise TypeError("stickers must be Face values")

    @classmethod
    def solved(cls) -> StickerState:
        """Return the canonical solved sticker state."""
        return cls(tuple(face for face in Face for _ in range(9)))

    @classmethod
    def from_facelets(cls, state: FaceletState) -> StickerState:
        """Copy a canonical facelet state into this independent representation."""
        return cls(state.facelets)

    @classmethod
    def parse(cls, value: str) -> StickerState:
        """Parse a canonical 54-character URFDLB state."""
        return cls.from_facelets(FaceletState.parse(value))

    def serialize(self) -> str:
        """Return canonical URFDLB facelets."""
        return "".join(facelet.value for facelet in self.facelets)

    def apply_move(self, move: Move) -> StickerState:
        """Apply one Singmaster move through explicit sticker cycles."""
        state = self
        for _ in range(move.quarter_turns):
            result = list(state.facelets)
            for cycle in _CLOCKWISE_CYCLES[move.face]:
                for source, destination in zip(cycle, cycle[1:] + cycle[:1], strict=True):
                    result[destination] = state.facelets[source]
            state = StickerState(tuple(result))
        return state

    def apply_moves(self, moves: Iterable[Move]) -> StickerState:
        """Apply moves in order and return the final state."""
        state = self
        for move in moves:
            state = state.apply_move(move)
        return state

    @property
    def is_solved(self) -> bool:
        """Return whether the state is canonical solved."""
        return self == self.solved()


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Machine-readable independent verification result."""

    status: VerificationStatus
    final_state: str | None
    moves: tuple[Move, ...] = ()
    htm: int = 0
    qtm: int = 0
    error: str | None = None

    @property
    def verified(self) -> bool:
        """Return whether the proposed sequence solved the cube."""
        return self.status is VerificationStatus.VERIFIED

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "verified": self.verified,
            "status": self.status.value,
            "final_state": self.final_state,
            "moves": [move.value for move in self.moves],
            "htm": self.htm,
            "qtm": self.qtm,
            "error": self.error,
        }


def move_counts(moves: Iterable[Move]) -> tuple[int, int]:
    """Return half-turn metric and quarter-turn metric counts."""
    materialized = tuple(moves)
    return len(materialized), sum(2 if move.quarter_turns == 2 else 1 for move in materialized)


def verify_solution(
    initial_state: str | FaceletState, proposed_moves: str | Iterable[str | Move]
) -> VerificationResult:
    """Validate and independently execute a proposed solution."""
    validation = validate_state(initial_state)
    if not validation.valid:
        return VerificationResult(
            VerificationStatus.INVALID_STATE,
            None,
            error="initial cube state is not physically reachable",
        )
    try:
        moves = parse_moves(proposed_moves)
    except (MoveParseError, TypeError) as error:
        return VerificationResult(VerificationStatus.INVALID_MOVES, None, error=str(error))

    facelets = (
        initial_state
        if isinstance(initial_state, FaceletState)
        else FaceletState.parse(initial_state)
    )
    final = StickerState.from_facelets(facelets).apply_moves(moves)
    htm, qtm = move_counts(moves)
    status = VerificationStatus.VERIFIED if final.is_solved else VerificationStatus.NOT_SOLVED
    return VerificationResult(status, final.serialize(), moves, htm, qtm)
