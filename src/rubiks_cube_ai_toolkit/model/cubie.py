"""Immutable cubie-coordinate representation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

from rubiks_cube_ai_toolkit.model.moves import Move

if TYPE_CHECKING:
    from rubiks_cube_ai_toolkit.model.facelets import FaceletState


class Corner(IntEnum):
    """Corner identities and positions in canonical order."""

    URF = 0
    UFL = 1
    ULB = 2
    UBR = 3
    DFR = 4
    DLF = 5
    DBL = 6
    DRB = 7


class Edge(IntEnum):
    """Edge identities and positions in canonical order."""

    UR = 0
    UF = 1
    UL = 2
    UB = 3
    DR = 4
    DF = 5
    DL = 6
    DB = 7
    FR = 8
    FL = 9
    BL = 10
    BR = 11


@dataclass(frozen=True, slots=True)
class CubieState:
    """A cube represented by corner/edge permutations and orientations.

    Construction enforces coordinate shape and range, but deliberately does not enforce
    reachability. The validator owns uniqueness, orientation-sum, and parity checks.
    """

    corner_permutation: tuple[int, ...]
    corner_orientation: tuple[int, ...]
    edge_permutation: tuple[int, ...]
    edge_orientation: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "corner_permutation", tuple(self.corner_permutation))
        object.__setattr__(self, "corner_orientation", tuple(self.corner_orientation))
        object.__setattr__(self, "edge_permutation", tuple(self.edge_permutation))
        object.__setattr__(self, "edge_orientation", tuple(self.edge_orientation))
        self._check_coordinates(self.corner_permutation, 8, 8, "corner permutation")
        self._check_coordinates(self.corner_orientation, 8, 3, "corner orientation")
        self._check_coordinates(self.edge_permutation, 12, 12, "edge permutation")
        self._check_coordinates(self.edge_orientation, 12, 2, "edge orientation")

    @staticmethod
    def _check_coordinates(values: Sequence[int], length: int, limit: int, name: str) -> None:
        if len(values) != length:
            raise ValueError(f"{name} must contain {length} values")
        if any(not isinstance(value, int) or not 0 <= value < limit for value in values):
            raise ValueError(f"{name} values must be integers in range [0, {limit})")

    @classmethod
    def solved(cls) -> CubieState:
        """Return the canonical solved state."""
        return cls(tuple(range(8)), (0,) * 8, tuple(range(12)), (0,) * 12)

    @classmethod
    def from_dict(cls, data: Mapping[str, Sequence[int]]) -> CubieState:
        """Deserialize coordinates from a JSON-compatible mapping."""
        return cls(
            tuple(data["corner_permutation"]),
            tuple(data["corner_orientation"]),
            tuple(data["edge_permutation"]),
            tuple(data["edge_orientation"]),
        )

    def to_dict(self) -> dict[str, list[int]]:
        """Serialize coordinates to a JSON-compatible mapping."""
        return {
            "corner_permutation": list(self.corner_permutation),
            "corner_orientation": list(self.corner_orientation),
            "edge_permutation": list(self.edge_permutation),
            "edge_orientation": list(self.edge_orientation),
        }

    def to_facelets(self) -> FaceletState:
        """Convert this state to canonical facelets."""
        from rubiks_cube_ai_toolkit.model.facelets import FaceletState

        return FaceletState.from_cubie(self)

    def apply_move(self, move: Move) -> CubieState:
        """Return a new state after applying one face move."""
        return self.to_facelets().apply_move(move).to_cubie()

    def apply_moves(self, moves: Iterable[Move]) -> CubieState:
        """Return a new state after applying moves in order."""
        state = self
        for move in moves:
            state = state.apply_move(move)
        return state

    @property
    def is_solved(self) -> bool:
        """Return whether all cubies are in their solved positions and orientations."""
        return self == self.solved()
