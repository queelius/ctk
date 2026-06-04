import argparse

from ctk.cli import build_parser

EXPECTED_COMMANDS = {
    "import", "export", "query", "sql", "db",
    "net", "auto-tag", "llm", "config", "tui",
}


def test_documented_subcommands_exist():
    parser = build_parser()
    subparser_actions = [
        a for a in parser._actions
        if isinstance(a, argparse._SubParsersAction)
    ]
    assert subparser_actions, "no subparsers registered"
    registered = set(subparser_actions[0].choices.keys())
    assert EXPECTED_COMMANDS <= registered, (
        f"missing: {EXPECTED_COMMANDS - registered}; "
        f"unexpected: {registered - EXPECTED_COMMANDS}"
    )
