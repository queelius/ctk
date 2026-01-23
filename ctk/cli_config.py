"""
Configuration commands for CTK CLI.

Commands for managing CTK configuration:
- show: Display current configuration
- path: Show configuration file path
- get: Get a configuration value
- set: Set a configuration value
"""

import argparse
import json
from typing import List, Optional

from ctk.core.config import Config, get_config


def cmd_show(args):
    """Show current configuration"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax

    console = Console()
    config = get_config()

    if args.section:
        # Show specific section
        section_data = config.get(args.section)
        if section_data is None:
            print(f"Error: Section '{args.section}' not found")
            return 1
        data = {args.section: section_data}
    else:
        data = config.config

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    # Rich formatted output
    json_str = json.dumps(data, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
    console.print(Panel(syntax, title="CTK Configuration", border_style="cyan"))
    return 0


def cmd_path(args):
    """Show configuration file path"""
    config = get_config()
    print(config.config_path)
    return 0


def cmd_get(args):
    """Get a configuration value"""
    config = get_config()

    value = config.get(args.key)

    if value is None:
        print(f"Error: Key '{args.key}' not found")
        return 1

    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2))
    else:
        print(value)

    return 0


def cmd_set(args):
    """Set a configuration value"""
    config = get_config()

    # Parse the value
    value = args.value

    # Try to parse as JSON for complex types
    try:
        value = json.loads(args.value)
    except json.JSONDecodeError:
        # Keep as string if not valid JSON
        pass

    # Handle boolean strings
    if isinstance(value, str):
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False

    old_value = config.get(args.key)
    config.set(args.key, value)

    if old_value is not None:
        print(f"Updated: {args.key}")
        print(f"  Old: {old_value}")
        print(f"  New: {value}")
    else:
        print(f"Set: {args.key} = {value}")

    return 0


def cmd_reset(args):
    """Reset configuration to defaults"""
    from rich.console import Console

    console = Console()

    if not args.force:
        confirm = input("Reset configuration to defaults? [y/N]: ")
        if confirm.lower() != "y":
            print("Cancelled")
            return 1

    config = get_config()

    if args.section:
        # Reset specific section
        if args.section in Config.DEFAULTS:
            config.config[args.section] = Config.DEFAULTS[args.section].copy()
            config.save()
            console.print(f"[green]Reset section '{args.section}' to defaults[/green]")
        else:
            print(f"Error: Unknown section '{args.section}'")
            return 1
    else:
        # Reset entire config
        config.config = Config.DEFAULTS.copy()
        config.save()
        console.print("[green]Reset all configuration to defaults[/green]")

    return 0


def cmd_edit(args):
    """Open configuration file in editor"""
    import os
    import subprocess

    config = get_config()
    config_path = str(config.config_path)

    # Ensure config file exists
    if not config.config_path.exists():
        config.save()

    # Get editor from environment or use defaults
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")

    if not editor:
        # Try common editors
        for ed in ["nano", "vim", "vi", "notepad"]:
            try:
                subprocess.run(["which", ed], capture_output=True, check=True)
                editor = ed
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue

    if not editor:
        print("Error: No editor found. Set EDITOR environment variable.")
        return 1

    try:
        subprocess.run([editor, config_path])
        return 0
    except Exception as e:
        print(f"Error opening editor: {e}")
        return 1


def add_config_commands(subparsers):
    """Add config command group to parser"""
    config_parser = subparsers.add_parser("config", help="Configuration management")
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", help="Config commands"
    )

    # show
    show_parser = config_subparsers.add_parser(
        "show", help="Show current configuration"
    )
    show_parser.add_argument("section", nargs="?", help="Specific section to show")
    show_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # path
    path_parser = config_subparsers.add_parser("path", help="Show config file path")

    # get
    get_parser = config_subparsers.add_parser("get", help="Get a configuration value")
    get_parser.add_argument(
        "key", help="Configuration key (dot notation, e.g., providers.ollama.base_url)"
    )

    # set
    set_parser = config_subparsers.add_parser("set", help="Set a configuration value")
    set_parser.add_argument("key", help="Configuration key (dot notation)")
    set_parser.add_argument("value", help="Value to set (JSON for complex types)")

    # reset
    reset_parser = config_subparsers.add_parser(
        "reset", help="Reset configuration to defaults"
    )
    reset_parser.add_argument("section", nargs="?", help="Specific section to reset")
    reset_parser.add_argument(
        "--force", "-f", action="store_true", help="Skip confirmation"
    )

    # edit
    edit_parser = config_subparsers.add_parser(
        "edit", help="Open config file in editor"
    )

    return config_parser


def dispatch_config_command(args):
    """Dispatch to appropriate config subcommand"""
    commands = {
        "show": cmd_show,
        "path": cmd_path,
        "get": cmd_get,
        "set": cmd_set,
        "reset": cmd_reset,
        "edit": cmd_edit,
    }

    if hasattr(args, "config_command") and args.config_command:
        if args.config_command in commands:
            return commands[args.config_command](args)
        else:
            print(f"Unknown config command: {args.config_command}")
            return 1
    else:
        print(
            "Error: No config command specified. Use 'ctk config --help' for available commands."
        )
        return 1
