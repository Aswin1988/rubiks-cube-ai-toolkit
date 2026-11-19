"""Command-line entry point reserved for the stable CLI milestone."""

import argparse

from rubiks_cube_ai_toolkit import __version__


def main() -> None:
    """Display package information without exposing an unstable command contract."""
    parser = argparse.ArgumentParser(
        prog="cube-ai",
        description="Deterministic Rubik's Cube tools for reliable AI agents.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()
    parser.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
