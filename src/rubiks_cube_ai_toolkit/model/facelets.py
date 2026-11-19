"""Canonical 54-facelet representation and cubie conversion."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rubiks_cube_ai_toolkit.model.moves import Face, Move, facelet_permutation

if TYPE_CHECKING:
    from rubiks_cube_ai_toolkit.model.cubie import CubieState

CORNER_FACELETS = (
    (8, 9, 20),
    (6, 18, 38),
    (0, 36, 47),
    (2, 45, 11),
    (29, 26, 15),
    (27, 44, 24),
    (33, 53, 42),
    (35, 17, 51),
)
CORNER_COLORS = (
    (Face.U, Face.R, Face.F),
    (Face.U, Face.F, Face.L),
    (Face.U, Face.L, Face.B),
    (Face.U, Face.B, Face.R),
    (Face.D, Face.F, Face.R),
    (Face.D, Face.L, Face.F),
    (Face.D, Face.B, Face.L),
    (Face.D, Face.R, Face.B),
)
EDGE_FACELETS = (
    (5, 10),
    (7, 19),
    (3, 37),
    (1, 46),
    (32, 16),
    (28, 25),
    (30, 43),
    (34, 52),
    (23, 12),
    (21, 41),
    (50, 39),
    (48, 14),
)
EDGE_COLORS = (
    (Face.U, Face.R),
    (Face.U, Face.F),
    (Face.U, Face.L),
    (Face.U, Face.B),
    (Face.D, Face.R),
    (Face.D, Face.F),
    (Face.D, Face.L),
    (Face.D, Face.B),
    (Face.F, Face.R),
    (Face.F, Face.L),
    (Face.B, Face.L),
    (Face.B, Face.R),
)


def match_corner_colors(observed: tuple[Face, Face, Face]) -> tuple[int, int] | None:
    """Return ``(cubie, orientation)`` for an exact ordered corner-color match."""
    orientation = next(
        (index for index, color in enumerate(observed) if color in (Face.U, Face.D)),
        None,
    )
    if orientation is None:
        return None
    normalized = tuple(observed[(orientation + offset) % 3] for offset in range(3))
    cubie = next(
        (index for index, colors in enumerate(CORNER_COLORS) if colors == normalized),
        None,
    )
    if cubie is None:
        return None
    return cubie, orientation


@dataclass(frozen=True, slots=True)
class FaceletState:
    """An immutable cube state containing 54 canonical face labels."""

    facelets: tuple[Face, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "facelets", tuple(self.facelets))
        if len(self.facelets) != 54:
            raise ValueError("a facelet state must contain exactly 54 facelets")
        if any(not isinstance(facelet, Face) for facelet in self.facelets):
            raise TypeError("facelets must be Face values")

    @classmethod
    def solved(cls) -> FaceletState:
        """Return the canonical solved facelet state."""
        return cls(tuple(face for face in Face for _ in range(9)))

    @classmethod
    def parse(cls, value: str) -> FaceletState:
        """Parse a 54-character canonical `URFDLB` string."""
        serialized = "".join(value.split()).upper()
        if len(serialized) != 54:
            raise ValueError("serialized facelets must contain exactly 54 symbols")
        try:
            return cls(tuple(Face(symbol) for symbol in serialized))
        except ValueError as error:
            invalid = sorted(set(serialized) - {face.value for face in Face})
            raise ValueError(f"unknown facelet symbols: {invalid}") from error

    @classmethod
    def from_cubie(cls, state: CubieState) -> FaceletState:
        """Convert cubie coordinates to canonical facelets."""
        result = list(cls.solved().facelets)
        for position, indices in enumerate(CORNER_FACELETS):
            cubie = state.corner_permutation[position]
            orientation = state.corner_orientation[position]
            for color_index in range(3):
                destination = indices[(color_index + orientation) % 3]
                result[destination] = CORNER_COLORS[cubie][color_index]
        for position, indices in enumerate(EDGE_FACELETS):
            cubie = state.edge_permutation[position]
            orientation = state.edge_orientation[position]
            for color_index in range(2):
                destination = indices[(color_index + orientation) % 2]
                result[destination] = EDGE_COLORS[cubie][color_index]
        return cls(tuple(result))

    def serialize(self) -> str:
        """Return the canonical 54-character representation."""
        return "".join(facelet.value for facelet in self.facelets)

    def to_cubie(self) -> CubieState:
        """Convert recognized facelet cubies into cubie coordinates.

        This conversion is structural. Use the validator to establish physical
        reachability, uniqueness, orientation sums, and parity.
        """
        from rubiks_cube_ai_toolkit.model.cubie import CubieState

        corner_permutation: list[int] = []
        corner_orientation: list[int] = []
        for indices in CORNER_FACELETS:
            observed = tuple(self.facelets[index] for index in indices)
            match = match_corner_colors(observed)
            if match is None:
                raise ValueError(f"unrecognized corner colors: {observed}")
            cubie, orientation = match
            corner_permutation.append(cubie)
            corner_orientation.append(orientation % 3)

        edge_permutation: list[int] = []
        edge_orientation: list[int] = []
        for indices in EDGE_FACELETS:
            observed = tuple(self.facelets[index] for index in indices)
            direct = next(
                (index for index, colors in enumerate(EDGE_COLORS) if colors == observed), None
            )
            if direct is not None:
                edge_permutation.append(direct)
                edge_orientation.append(0)
                continue
            reverse = next(
                (
                    index
                    for index, colors in enumerate(EDGE_COLORS)
                    if colors == tuple(reversed(observed))
                ),
                None,
            )
            if reverse is None:
                raise ValueError(f"unrecognized edge colors: {observed}")
            edge_permutation.append(reverse)
            edge_orientation.append(1)

        return CubieState(
            tuple(corner_permutation),
            tuple(corner_orientation),
            tuple(edge_permutation),
            tuple(edge_orientation),
        )

    def apply_move(self, move: Move) -> FaceletState:
        """Return a new facelet state after one move."""
        result = list(self.facelets)
        for source, destination in enumerate(facelet_permutation(move)):
            result[destination] = self.facelets[source]
        return FaceletState(tuple(result))

    def apply_moves(self, moves: Iterable[Move]) -> FaceletState:
        """Return a new facelet state after applying moves in order."""
        state = self
        for move in moves:
            state = state.apply_move(move)
        return state

    @property
    def is_solved(self) -> bool:
        """Return whether every face is uniform in canonical center colors."""
        return self == self.solved()
