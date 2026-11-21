"""Functional package entry-point tests."""

import json
import sys

import pytest

from rubiks_cube_ai_toolkit import cli
from rubiks_cube_ai_toolkit.cli import main
from rubiks_cube_ai_toolkit.model import FaceletState, Move, generate_scramble, invert_moves
from rubiks_cube_ai_toolkit.solvers import SolveResult, SolveStatus, UnavailableSolver

SOLVED = "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB"


def test_cli_prints_help_without_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["cube-ai"])
    main()
    assert "Deterministic Rubik's Cube tools" in capsys.readouterr().out


def test_cli_prints_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["cube-ai", "--version"])
    with pytest.raises(SystemExit, match="0"):
        main()
    assert "cube-ai 0.3.0" in capsys.readouterr().out


def test_scramble_human_and_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scramble", "--length", "2", "--seed", "7"]) == 0
    assert "scramble:" in capsys.readouterr().out
    assert main(["scramble", "--length", "2", "--seed", "7", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["moves"]) == 2
    assert len(payload["state"]) == 54


def test_scramble_rejects_negative_length(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scramble", "--length", "-1", "--json"]) == 2
    assert "non-negative" in json.loads(capsys.readouterr().out)["error"]


def test_validate_reports_valid_and_invalid(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", SOLVED]) == 0
    assert capsys.readouterr().out.strip() == "valid"
    assert main(["validate", "U", "--json"]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False


def test_apply_reports_state_and_rejects_bad_inputs(capsys: pytest.CaptureFixture[str]) -> None:
    expected = FaceletState.solved().apply_move(Move.R).serialize()
    assert main(["apply", SOLVED, "R", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == expected
    assert main(["apply", "U", "R"]) == 3
    assert "invalid" in capsys.readouterr().out
    assert main(["apply", SOLVED, "X"]) == 2
    assert "invalid move" in capsys.readouterr().out


def test_verify_accepts_inverse_and_rejects_wrong_solution(
    capsys: pytest.CaptureFixture[str],
) -> None:
    scramble = generate_scramble(4, seed=4)
    state = FaceletState.solved().apply_moves(scramble).serialize()
    solution = [move.value for move in invert_moves(scramble)]
    assert main(["verify", state, *solution, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verified"] is True
    assert main(["verify", state, "R"]) == 3
    assert "not_solved" in capsys.readouterr().out


def test_solve_handles_solved_unavailable_invalid_and_bad_limits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "RubikSolverSubprocess", lambda config: UnavailableSolver())
    scrambled = FaceletState.solved().apply_move(Move.R).serialize()
    assert main(["solve", SOLVED, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "already_solved"
    assert main(["solve", scrambled]) == 5
    assert "unavailable" in capsys.readouterr().out
    assert main(["solve", "U"]) == 3
    assert "invalid_state" in capsys.readouterr().out
    assert main(["solve", SOLVED, "--timeout", "0"]) == 2
    assert "positive" in capsys.readouterr().out
    assert main(["solve", SOLVED, "--init-timeout", "0", "--json"]) == 2
    assert "positive" in json.loads(capsys.readouterr().out)["error"]
    assert main(["solve", SOLVED, "--memory-limit-mb", "0"]) == 2
    assert "positive" in capsys.readouterr().out


def test_solve_maps_timeout_to_exit_four(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class TimeoutService:
        def __init__(self, backend: object) -> None:
            del backend

        def solve(self, state: str, limits: object) -> SolveResult:
            del state, limits
            return SolveResult(SolveStatus.TIMEOUT, "fake", 1.0, error="expired")

    monkeypatch.setattr(cli, "VerifiedSolver", TimeoutService)
    assert main(["solve", SOLVED, "--json"]) == 4
    assert json.loads(capsys.readouterr().out)["status"] == "timeout"
