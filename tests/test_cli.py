"""Minimal package entry-point tests."""

import sys

import pytest

from rubiks_cube_ai_toolkit.cli import main


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
    assert "cube-ai 0.1.0" in capsys.readouterr().out
