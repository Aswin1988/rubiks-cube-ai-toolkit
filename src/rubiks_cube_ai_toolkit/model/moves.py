"""Singmaster moves and deterministic move-sequence operations."""

from __future__ import annotations

import random
from collections.abc import Iterable
from enum import StrEnum
from functools import cache


class Face(StrEnum):
    """Canonical face and color labels."""

    U = "U"
    R = "R"
    F = "F"
    D = "D"
    L = "L"
    B = "B"


class Move(StrEnum):
    """The 18 legal outer-face moves in standard Singmaster notation."""

    U = "U"
    U2 = "U2"
    U_PRIME = "U'"
    R = "R"
    R2 = "R2"
    R_PRIME = "R'"
    F = "F"
    F2 = "F2"
    F_PRIME = "F'"
    D = "D"
    D2 = "D2"
    D_PRIME = "D'"
    L = "L"
    L2 = "L2"
    L_PRIME = "L'"
    B = "B"
    B2 = "B2"
    B_PRIME = "B'"

    @property
    def face(self) -> Face:
        """Return the face affected by this move."""
        return Face(self.value[0])

    @property
    def quarter_turns(self) -> int:
        """Return clockwise quarter turns modulo four."""
        if self.value.endswith("2"):
            return 2
        if self.value.endswith("'"):
            return 3
        return 1

    def inverse(self) -> Move:
        """Return the inverse move."""
        return _move_from_parts(self.face, (-self.quarter_turns) % 4)


class MoveParseError(ValueError):
    """Raised when a move sequence contains an unsupported token."""


def _move_from_parts(face: Face, quarter_turns: int) -> Move:
    turns = quarter_turns % 4
    if turns == 0:
        raise ValueError("zero quarter turns do not form a move")
    suffix = {1: "", 2: "2", 3: "'"}[turns]
    return Move(face.value + suffix)


def parse_moves(sequence: str | Iterable[str | Move]) -> tuple[Move, ...]:
    """Parse whitespace-delimited Singmaster tokens into immutable moves."""
    tokens: Iterable[str | Move]
    tokens = sequence.split() if isinstance(sequence, str) else sequence
    parsed: list[Move] = []
    for index, token in enumerate(tokens):
        if isinstance(token, Move):
            parsed.append(token)
            continue
        try:
            parsed.append(Move(token))
        except ValueError as error:
            raise MoveParseError(f"invalid move token at index {index}: {token!r}") from error
    return tuple(parsed)


def invert_moves(moves: Iterable[Move]) -> tuple[Move, ...]:
    """Return the inverse of an entire move sequence."""
    materialized = tuple(moves)
    return tuple(move.inverse() for move in reversed(materialized))


def normalize_moves(moves: Iterable[Move]) -> tuple[Move, ...]:
    """Combine adjacent turns of the same face without reordering moves."""
    normalized: list[Move] = []
    for move in moves:
        if not normalized or normalized[-1].face is not move.face:
            normalized.append(move)
            continue
        turns = (normalized.pop().quarter_turns + move.quarter_turns) % 4
        if turns:
            normalized.append(_move_from_parts(move.face, turns))
    return tuple(normalized)


def generate_scramble(
    length: int = 20, *, seed: int | str | bytes | None = None
) -> tuple[Move, ...]:
    """Generate a reproducible scramble with no repeated adjacent face."""
    if length < 0:
        raise ValueError("scramble length must be non-negative")
    rng = random.Random(seed)
    faces = tuple(Face)
    turns = (1, 2, 3)
    result: list[Move] = []
    previous_face: Face | None = None
    for _ in range(length):
        candidates = tuple(face for face in faces if face is not previous_face)
        face = rng.choice(candidates)
        result.append(_move_from_parts(face, rng.choice(turns)))
        previous_face = face
    return tuple(result)


Vector = tuple[int, int, int]

_FACE_BASIS: dict[Face, tuple[Vector, Vector, Vector]] = {
    Face.U: ((0, 1, 0), (1, 0, 0), (0, 0, -1)),
    Face.R: ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    Face.F: ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    Face.D: ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    Face.L: ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    Face.B: ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
}


def _add(*vectors: Vector) -> Vector:
    x = sum(vector[0] for vector in vectors)
    y = sum(vector[1] for vector in vectors)
    z = sum(vector[2] for vector in vectors)
    return x, y, z


def _scale(vector: Vector, factor: int) -> Vector:
    return vector[0] * factor, vector[1] * factor, vector[2] * factor


def _facelet_geometry(index: int) -> tuple[Vector, Vector]:
    face = tuple(Face)[index // 9]
    offset = index % 9
    row, column = divmod(offset, 3)
    normal, right, up = _FACE_BASIS[face]
    position = _add(normal, _scale(right, column - 1), _scale(up, 1 - row))
    return position, normal


_GEOMETRY_TO_FACELET = {_facelet_geometry(index): index for index in range(54)}


def _rotate_positive(vector: Vector, axis: int) -> Vector:
    x, y, z = vector
    if axis == 0:
        return x, -z, y
    if axis == 1:
        return z, y, -x
    return -y, x, z


def _rotate(vector: Vector, axis: int, quarter_turns: int) -> Vector:
    result = vector
    for _ in range(quarter_turns % 4):
        result = _rotate_positive(result, axis)
    return result


@cache
def facelet_permutation(move: Move) -> tuple[int, ...]:
    """Return destination indices for every source facelet under ``move``."""
    normal = _FACE_BASIS[move.face][0]
    axis = next(index for index, value in enumerate(normal) if value)
    sign = normal[axis]
    rotation = (-sign * move.quarter_turns) % 4
    destinations: list[int] = []
    for source in range(54):
        position, sticker_normal = _facelet_geometry(source)
        if position[axis] == sign:
            position = _rotate(position, axis, rotation)
            sticker_normal = _rotate(sticker_normal, axis, rotation)
        destinations.append(_GEOMETRY_TO_FACELET[(position, sticker_normal)])
    return tuple(destinations)
