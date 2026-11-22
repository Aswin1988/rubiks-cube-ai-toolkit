"""Generate deterministic TypeScript conformance vectors from the Python engine."""

from __future__ import annotations

import json
from pathlib import Path

from rubiks_cube_ai_toolkit.model import FaceletState, Move, generate_scramble
from rubiks_cube_ai_toolkit.model.moves import facelet_permutation

OUTPUT = Path(__file__).parents[1] / "apps" / "web" / "src" / "generated" / "conformance.json"
SEEDS = tuple(f"web-conformance-{index}" for index in range(16))


def build_vectors() -> dict[str, object]:
    """Return fixed golden vectors covering all moves and representative states."""
    representatives: list[dict[str, object]] = []
    for seed in SEEDS:
        state = FaceletState.solved().apply_moves(generate_scramble(20, seed=seed))
        representatives.append(
            {
                "seed": seed,
                "state": state.serialize(),
                "after": {move.value: state.apply_move(move).serialize() for move in Move},
            }
        )
    return {
        "schemaVersion": 1,
        "convention": "URFDLB row-major, clockwise viewed from outside",
        "solved": FaceletState.solved().serialize(),
        "permutations": {move.value: list(facelet_permutation(move)) for move in Move},
        "representatives": representatives,
    }


def main() -> None:
    """Write the canonical JSON fixture with stable formatting."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build_vectors(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
