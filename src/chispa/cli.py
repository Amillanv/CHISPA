"""The command line: one entry point for each step of the work.

One command for each step lets a reader make each result again.
"""

import argparse

COMMANDS = {
    "fetch": "Get one source for one year and save its detections.",
    "fuse": "Replay detections and write events and alerts.",
    "evaluate": "Compare alerts with burn scars and write the result tables.",
    "serve": "Start the dashboard.",
    "mcp": "Start the MCP server.",
    "grade": "Run the gold questions and grade the answers.",
}


def main(arguments: list[str] | None = None) -> None:
    """Read the command and run it."""
    parser = argparse.ArgumentParser(prog="chispa", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in COMMANDS.items():
        commands.add_parser(name, help=text)
    chosen = parser.parse_args(arguments)
    parser.exit(1, f"The command '{chosen.command}' is not built. PLAN.md gives the progress.\n")
