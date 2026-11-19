"""Physical reachability validator tests."""

from rubiks_cube_ai_toolkit import CubieState, FaceletState, Move, ValidationCode, validate_state


def _with_coordinates(
    *,
    corners: tuple[int, ...] | None = None,
    corner_orientation: tuple[int, ...] | None = None,
    edges: tuple[int, ...] | None = None,
    edge_orientation: tuple[int, ...] | None = None,
) -> CubieState:
    solved = CubieState.solved()
    return CubieState(
        corners or solved.corner_permutation,
        corner_orientation or solved.corner_orientation,
        edges or solved.edge_permutation,
        edge_orientation or solved.edge_orientation,
    )


def test_solved_state_is_valid_and_serializable() -> None:
    result = validate_state(FaceletState.solved())
    assert result.valid
    assert result.issues == ()
    assert result.state == CubieState.solved()
    assert result.to_dict()["valid"] is True


def test_every_legal_face_move_produces_a_reachable_state() -> None:
    solved = CubieState.solved()
    assert all(validate_state(solved.apply_move(move)).valid for move in Move)


def test_serialized_shape_and_unknown_symbols_are_diagnostic() -> None:
    count_result = validate_state("U")
    assert count_result.has_code(ValidationCode.FACELET_COUNT)
    unknown_result = validate_state("X" + FaceletState.solved().serialize()[1:])
    assert unknown_result.has_code(ValidationCode.UNKNOWN_FACELET)
    assert unknown_result.to_dict()["issues"][0]["code"] == "UNKNOWN_FACELET"  # type: ignore[index]


def test_wrong_color_count_is_diagnostic() -> None:
    serialized = "R" + FaceletState.solved().serialize()[1:]
    result = validate_state(serialized)
    assert result.has_code(ValidationCode.COLOR_COUNT)


def test_wrong_center_mapping_is_diagnostic() -> None:
    facelets = list(FaceletState.solved().facelets)
    facelets[4], facelets[13] = facelets[13], facelets[4]
    result = validate_state(FaceletState(tuple(facelets)))
    assert result.has_code(ValidationCode.CENTER_MAPPING)


def test_invalid_corner_and_missing_corner_are_diagnostic() -> None:
    facelets = list(FaceletState.solved().facelets)
    facelets[9], facelets[18] = facelets[18], facelets[9]
    result = validate_state(FaceletState(tuple(facelets)))
    assert result.has_code(ValidationCode.INVALID_CORNER)
    assert result.has_code(ValidationCode.MISSING_CORNER)


def test_invalid_edge_and_missing_edge_are_diagnostic() -> None:
    facelets = list(FaceletState.solved().facelets)
    facelets[5], facelets[19] = facelets[19], facelets[5]
    result = validate_state(FaceletState(tuple(facelets)))
    assert result.has_code(ValidationCode.INVALID_EDGE)
    assert result.has_code(ValidationCode.MISSING_EDGE)


def test_duplicate_and_missing_corner_are_diagnostic() -> None:
    state = _with_coordinates(corners=(0, 0, 2, 3, 4, 5, 6, 7))
    result = validate_state(state)
    assert result.has_code(ValidationCode.DUPLICATE_CORNER)
    assert result.has_code(ValidationCode.MISSING_CORNER)


def test_duplicate_and_missing_edge_are_diagnostic() -> None:
    state = _with_coordinates(edges=(0, 0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11))
    result = validate_state(state.to_facelets())
    assert result.has_code(ValidationCode.DUPLICATE_EDGE)
    assert result.has_code(ValidationCode.MISSING_EDGE)


def test_single_twisted_corner_is_impossible() -> None:
    state = _with_coordinates(corner_orientation=(1,) + (0,) * 7)
    result = validate_state(state.to_facelets())
    assert result.has_code(ValidationCode.CORNER_ORIENTATION)


def test_single_flipped_edge_is_impossible() -> None:
    state = _with_coordinates(edge_orientation=(1,) + (0,) * 11)
    result = validate_state(state.to_facelets())
    assert result.has_code(ValidationCode.EDGE_ORIENTATION)


def test_single_cubie_swap_has_wrong_parity() -> None:
    state = _with_coordinates(corners=(1, 0, 2, 3, 4, 5, 6, 7))
    result = validate_state(state.to_facelets())
    assert result.has_code(ValidationCode.PERMUTATION_PARITY)


def test_duplicate_permutation_does_not_emit_meaningless_parity() -> None:
    state = _with_coordinates(corners=(0, 0, 2, 3, 4, 5, 6, 7))
    result = validate_state(state)
    assert not result.has_code(ValidationCode.PERMUTATION_PARITY)
