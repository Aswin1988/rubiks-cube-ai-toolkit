"""Guard the committed frontend move vectors against Python engine drift."""

import json
from pathlib import Path

from rubiks_cube_ai_toolkit.model import FaceletState, Move
from rubiks_cube_ai_toolkit.model.moves import facelet_permutation

FIXTURE = Path(__file__).parents[1] / "apps" / "web" / "src" / "generated" / "conformance.json"


def test_frontend_golden_vectors_match_engine() -> None:
    vectors = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert vectors["schemaVersion"] == 1
    assert vectors["solved"] == FaceletState.solved().serialize()
    assert set(vectors["permutations"]) == {move.value for move in Move}
    for move in Move:
        assert vectors["permutations"][move.value] == list(facelet_permutation(move))
    for sample in vectors["representatives"]:
        state = FaceletState.parse(sample["state"])
        for move in Move:
            assert sample["after"][move.value] == state.apply_move(move).serialize()
