"""Physical reachability validation with machine-readable diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from rubiks_cube_ai_toolkit.model.cubie import Corner, CubieState, Edge
from rubiks_cube_ai_toolkit.model.facelets import (
    CORNER_COLORS,
    CORNER_FACELETS,
    EDGE_COLORS,
    EDGE_FACELETS,
    FaceletState,
)
from rubiks_cube_ai_toolkit.model.moves import Face


class ValidationCode(StrEnum):
    """Stable diagnostic codes returned by physical validation."""

    FACELET_COUNT = "FACELET_COUNT"
    UNKNOWN_FACELET = "UNKNOWN_FACELET"
    COLOR_COUNT = "COLOR_COUNT"
    CENTER_MAPPING = "CENTER_MAPPING"
    INVALID_CORNER = "INVALID_CORNER"
    DUPLICATE_CORNER = "DUPLICATE_CORNER"
    MISSING_CORNER = "MISSING_CORNER"
    INVALID_EDGE = "INVALID_EDGE"
    DUPLICATE_EDGE = "DUPLICATE_EDGE"
    MISSING_EDGE = "MISSING_EDGE"
    CORNER_ORIENTATION = "CORNER_ORIENTATION"
    EDGE_ORIENTATION = "EDGE_ORIENTATION"
    PERMUTATION_PARITY = "PERMUTATION_PARITY"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One validation failure with stable code and contextual details."""

    code: ValidationCode
    message: str
    details: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible issue representation."""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The complete result of a physical validation attempt."""

    issues: tuple[ValidationIssue, ...]
    state: CubieState | None = None

    @property
    def valid(self) -> bool:
        """Return whether no physical constraint was violated."""
        return not self.issues

    def has_code(self, code: ValidationCode) -> bool:
        """Return whether a specific diagnostic code is present."""
        return any(issue.code is code for issue in self.issues)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible result representation."""
        return {
            "valid": self.valid,
            "issues": [issue.to_dict() for issue in self.issues],
            "state": self.state.to_dict() if self.state is not None else None,
        }


def _duplicates(values: Sequence[int]) -> list[int]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _permutation_parity(values: Sequence[int]) -> int:
    return (
        sum(
            values[left] > values[right]
            for left in range(len(values))
            for right in range(left + 1, len(values))
        )
        % 2
    )


def _coordinate_issues(state: CubieState) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    duplicate_corners = _duplicates(state.corner_permutation)
    missing_corners = sorted(set(range(8)) - set(state.corner_permutation))
    duplicate_edges = _duplicates(state.edge_permutation)
    missing_edges = sorted(set(range(12)) - set(state.edge_permutation))

    if duplicate_corners:
        issues.append(
            ValidationIssue(
                ValidationCode.DUPLICATE_CORNER,
                "One or more corner cubies appear more than once.",
                {"cubies": [Corner(value).name for value in duplicate_corners]},
            )
        )
    if missing_corners:
        issues.append(
            ValidationIssue(
                ValidationCode.MISSING_CORNER,
                "One or more corner cubies are missing.",
                {"cubies": [Corner(value).name for value in missing_corners]},
            )
        )
    if duplicate_edges:
        issues.append(
            ValidationIssue(
                ValidationCode.DUPLICATE_EDGE,
                "One or more edge cubies appear more than once.",
                {"cubies": [Edge(value).name for value in duplicate_edges]},
            )
        )
    if missing_edges:
        issues.append(
            ValidationIssue(
                ValidationCode.MISSING_EDGE,
                "One or more edge cubies are missing.",
                {"cubies": [Edge(value).name for value in missing_edges]},
            )
        )

    corner_sum = sum(state.corner_orientation) % 3
    if corner_sum:
        issues.append(
            ValidationIssue(
                ValidationCode.CORNER_ORIENTATION,
                "Corner orientations do not sum to zero modulo three.",
                {"remainder": corner_sum},
            )
        )
    edge_sum = sum(state.edge_orientation) % 2
    if edge_sum:
        issues.append(
            ValidationIssue(
                ValidationCode.EDGE_ORIENTATION,
                "Edge orientations do not sum to zero modulo two.",
                {"remainder": edge_sum},
            )
        )

    permutations_complete = not (
        duplicate_corners or missing_corners or duplicate_edges or missing_edges
    )
    if permutations_complete:
        corner_parity = _permutation_parity(state.corner_permutation)
        edge_parity = _permutation_parity(state.edge_permutation)
        if corner_parity != edge_parity:
            issues.append(
                ValidationIssue(
                    ValidationCode.PERMUTATION_PARITY,
                    "Corner and edge permutation parity differ.",
                    {"corner_parity": corner_parity, "edge_parity": edge_parity},
                )
            )
    return issues


def _identify_facelet_cubies(
    state: FaceletState, issues: list[ValidationIssue]
) -> CubieState | None:
    corner_permutation: list[int] = []
    corner_orientation: list[int] = []
    for position, indices in enumerate(CORNER_FACELETS):
        observed = tuple(state.facelets[index] for index in indices)
        orientation = next(
            (index for index, color in enumerate(observed) if color in (Face.U, Face.D)),
            None,
        )
        cubie: int | None = None
        if orientation is not None:
            side_colors = observed[(orientation + 1) % 3], observed[(orientation + 2) % 3]
            cubie = next(
                (index for index, colors in enumerate(CORNER_COLORS) if colors[1:] == side_colors),
                None,
            )
        if orientation is None or cubie is None:
            issues.append(
                ValidationIssue(
                    ValidationCode.INVALID_CORNER,
                    "A corner position does not contain a recognized oriented cubie.",
                    {
                        "position": Corner(position).name,
                        "colors": [color.value for color in observed],
                    },
                )
            )
            continue
        corner_permutation.append(cubie)
        corner_orientation.append(orientation)

    edge_permutation: list[int] = []
    edge_orientation: list[int] = []
    for position, indices in enumerate(EDGE_FACELETS):
        observed = tuple(state.facelets[index] for index in indices)
        cubie = next(
            (index for index, colors in enumerate(EDGE_COLORS) if colors == observed), None
        )
        orientation = 0
        if cubie is None:
            cubie = next(
                (
                    index
                    for index, colors in enumerate(EDGE_COLORS)
                    if colors == tuple(reversed(observed))
                ),
                None,
            )
            orientation = 1
        if cubie is None:
            issues.append(
                ValidationIssue(
                    ValidationCode.INVALID_EDGE,
                    "An edge position does not contain a recognized oriented cubie.",
                    {
                        "position": Edge(position).name,
                        "colors": [color.value for color in observed],
                    },
                )
            )
            continue
        edge_permutation.append(cubie)
        edge_orientation.append(orientation)

    recognized_corner_set = set(corner_permutation)
    recognized_edge_set = set(edge_permutation)
    duplicate_corners = _duplicates(corner_permutation)
    duplicate_edges = _duplicates(edge_permutation)
    missing_corners = sorted(set(range(8)) - recognized_corner_set)
    missing_edges = sorted(set(range(12)) - recognized_edge_set)
    if duplicate_corners:
        issues.append(
            ValidationIssue(
                ValidationCode.DUPLICATE_CORNER,
                "One or more recognized corner cubies appear more than once.",
                {"cubies": [Corner(value).name for value in duplicate_corners]},
            )
        )
    if missing_corners:
        issues.append(
            ValidationIssue(
                ValidationCode.MISSING_CORNER,
                "One or more corner cubies are missing.",
                {"cubies": [Corner(value).name for value in missing_corners]},
            )
        )
    if duplicate_edges:
        issues.append(
            ValidationIssue(
                ValidationCode.DUPLICATE_EDGE,
                "One or more recognized edge cubies appear more than once.",
                {"cubies": [Edge(value).name for value in duplicate_edges]},
            )
        )
    if missing_edges:
        issues.append(
            ValidationIssue(
                ValidationCode.MISSING_EDGE,
                "One or more edge cubies are missing.",
                {"cubies": [Edge(value).name for value in missing_edges]},
            )
        )

    if len(corner_permutation) != 8 or len(edge_permutation) != 12:
        return None
    cubie_state = CubieState(
        tuple(corner_permutation),
        tuple(corner_orientation),
        tuple(edge_permutation),
        tuple(edge_orientation),
    )
    issues.extend(
        issue
        for issue in _coordinate_issues(cubie_state)
        if issue.code
        not in {
            ValidationCode.DUPLICATE_CORNER,
            ValidationCode.MISSING_CORNER,
            ValidationCode.DUPLICATE_EDGE,
            ValidationCode.MISSING_EDGE,
        }
    )
    return cubie_state


def _validate_facelets(state: FaceletState) -> ValidationResult:
    issues: list[ValidationIssue] = []
    counts = Counter(state.facelets)
    incorrect_counts = {face.value: counts[face] for face in Face if counts[face] != 9}
    if incorrect_counts:
        issues.append(
            ValidationIssue(
                ValidationCode.COLOR_COUNT,
                "Every face label must occur exactly nine times.",
                {"expected": 9, "actual": incorrect_counts},
            )
        )

    center_indices = (4, 13, 22, 31, 40, 49)
    centers = tuple(state.facelets[index] for index in center_indices)
    if centers != tuple(Face):
        issues.append(
            ValidationIssue(
                ValidationCode.CENTER_MAPPING,
                "Center labels must establish canonical URFDLB face mapping.",
                {
                    "expected": [face.value for face in Face],
                    "actual": [face.value for face in centers],
                },
            )
        )

    cubie_state = _identify_facelet_cubies(state, issues)
    return ValidationResult(tuple(issues), cubie_state)


def validate_state(value: str | FaceletState | CubieState) -> ValidationResult:
    """Validate cube structure and all physical reachability invariants."""
    if isinstance(value, CubieState):
        return ValidationResult(tuple(_coordinate_issues(value)), value)
    if isinstance(value, FaceletState):
        return _validate_facelets(value)

    serialized = "".join(value.split()).upper()
    if len(serialized) != 54:
        return ValidationResult(
            (
                ValidationIssue(
                    ValidationCode.FACELET_COUNT,
                    "A serialized cube must contain exactly 54 facelet symbols.",
                    {"expected": 54, "actual": len(serialized)},
                ),
            )
        )
    unknown = sorted(set(serialized) - {face.value for face in Face})
    if unknown:
        return ValidationResult(
            (
                ValidationIssue(
                    ValidationCode.UNKNOWN_FACELET,
                    "Serialized cube contains unknown facelet symbols.",
                    {"symbols": unknown},
                ),
            )
        )
    return _validate_facelets(FaceletState.parse(serialized))
