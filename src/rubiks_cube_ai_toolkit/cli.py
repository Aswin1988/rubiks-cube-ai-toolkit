"""Functional command-line interface for deterministic cube operations."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from rubiks_cube_ai_toolkit import __version__
from rubiks_cube_ai_toolkit.model import (
    FaceletState,
    MoveParseError,
    generate_scramble,
    parse_moves,
)
from rubiks_cube_ai_toolkit.solvers import (
    SolveLimits,
    SolveStatus,
    UnavailableSolver,
    VerifiedSolver,
)
from rubiks_cube_ai_toolkit.validation import validate_state
from rubiks_cube_ai_toolkit.verification import verify_solution

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INVALID = 3
EXIT_TIMEOUT = 4
EXIT_FAILURE = 5


def _emit(payload: dict[str, object], *, json_output: bool, human: str) -> None:
    if json_output:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(human)


def _run_scramble(args: argparse.Namespace) -> int:
    try:
        moves = generate_scramble(args.length, seed=args.seed)
    except ValueError as error:
        _emit({"error": str(error)}, json_output=args.json, human=f"error: {error}")
        return EXIT_USAGE
    state = FaceletState.solved().apply_moves(moves)
    notation = " ".join(move.value for move in moves)
    _emit(
        {"moves": [move.value for move in moves], "state": state.serialize()},
        json_output=args.json,
        human=f"scramble: {notation}\nstate: {state.serialize()}",
    )
    return EXIT_OK


def _run_validate(args: argparse.Namespace) -> int:
    result = validate_state(args.state)
    issues = ", ".join(issue.code.value for issue in result.issues)
    _emit(
        result.to_dict(),
        json_output=args.json,
        human="valid" if result.valid else f"invalid: {issues}",
    )
    return EXIT_OK if result.valid else EXIT_INVALID


def _run_apply(args: argparse.Namespace) -> int:
    validation = validate_state(args.state)
    if not validation.valid:
        _emit(validation.to_dict(), json_output=args.json, human="invalid initial cube state")
        return EXIT_INVALID
    try:
        moves = parse_moves(args.moves)
        final = FaceletState.parse(args.state).apply_moves(moves)
    except (MoveParseError, ValueError, TypeError) as error:
        _emit({"error": str(error)}, json_output=args.json, human=f"error: {error}")
        return EXIT_USAGE
    _emit(
        {"state": final.serialize(), "moves": [move.value for move in moves]},
        json_output=args.json,
        human=final.serialize(),
    )
    return EXIT_OK


def _run_verify(args: argparse.Namespace) -> int:
    result = verify_solution(args.state, args.moves)
    _emit(
        result.to_dict(),
        json_output=args.json,
        human=(
            f"{result.status.value}: HTM={result.htm}, QTM={result.qtm}"
            + (f"\nfinal state: {result.final_state}" if result.final_state else "")
        ),
    )
    return EXIT_OK if result.verified else EXIT_INVALID


def _run_solve(args: argparse.Namespace) -> int:
    try:
        limits = SolveLimits(args.timeout, args.max_moves)
    except ValueError as error:
        _emit({"error": str(error)}, json_output=args.json, human=f"error: {error}")
        return EXIT_USAGE
    result = VerifiedSolver(UnavailableSolver()).solve(args.state, limits)
    notation = " ".join(move.value for move in result.moves)
    human = f"{result.status.value}: {notation}" if notation else result.status.value
    if result.error:
        human += f"\nerror: {result.error}"
    _emit(result.to_dict(), json_output=args.json, human=human)
    if result.success:
        return EXIT_OK
    if result.status is SolveStatus.INVALID_STATE:
        return EXIT_INVALID
    if result.status is SolveStatus.TIMEOUT:
        return EXIT_TIMEOUT
    return EXIT_FAILURE


def _add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cube-ai",
        description="Deterministic Rubik's Cube tools for reliable AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    scramble = commands.add_parser("scramble", help="generate a reproducible scramble")
    scramble.add_argument("--length", type=int, default=20)
    scramble.add_argument("--seed", default=None)
    _add_json_argument(scramble)
    scramble.set_defaults(handler=_run_scramble)

    validate = commands.add_parser("validate", help="validate physical reachability")
    validate.add_argument("state", help="54-character URFDLB facelet state")
    _add_json_argument(validate)
    validate.set_defaults(handler=_run_validate)

    apply = commands.add_parser("apply", help="apply moves using the mathematical engine")
    apply.add_argument("state", help="54-character URFDLB facelet state")
    apply.add_argument("moves", nargs="+", help="Singmaster move tokens")
    _add_json_argument(apply)
    apply.set_defaults(handler=_run_apply)

    solve = commands.add_parser("solve", help="solve with mandatory independent verification")
    solve.add_argument("state", help="54-character URFDLB facelet state")
    solve.add_argument("--timeout", type=float, default=10.0, help="time limit in seconds")
    solve.add_argument("--max-moves", type=int, default=30, help="maximum accepted solution length")
    _add_json_argument(solve)
    solve.set_defaults(handler=_run_solve)

    verify = commands.add_parser("verify", help="independently verify a proposed solution")
    verify.add_argument("state", help="54-character URFDLB facelet state")
    verify.add_argument("moves", nargs="*", help="proposed Singmaster solution")
    _add_json_argument(verify)
    verify.set_defaults(handler=_run_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a documented process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return EXIT_OK
    return args.handler(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
