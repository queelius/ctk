"""LLM provider commands for CTK CLI.

Commands for managing and testing the OpenAI-compatible LLM endpoints
that ctk ships with — one per named profile under ``providers`` in
``~/.ctk/config.json``:

* ``ctk llm providers`` — show configured provider profiles
* ``ctk llm models``    — list models advertised by the endpoint
* ``ctk llm test``      — probe the endpoint for reachability

``models`` and ``test`` accept ``--provider <name>`` to target a
specific profile instead of the configured default.
"""

from __future__ import annotations

import json

from ctk.core.config import get_config
from ctk.llm.factory import build_provider, list_profile_summaries


def cmd_providers(args):
    """Show configured LLM provider profiles."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    config = get_config()

    if args.json:
        print(json.dumps(config.get("providers", {}), indent=2))
        return 0

    table = Table(title="LLM Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Base URL", style="dim")
    table.add_column("Default Model", style="green")
    table.add_column("API Key", style="yellow")

    for name, pconfig in list_profile_summaries():
        api_key = config.get_api_key(name)
        key_status = "Set" if api_key else "Not set"
        table.add_row(
            name,
            pconfig.get("base_url", ""),
            pconfig.get("default_model", ""),
            key_status,
        )

    console.print(table)
    return 0


def cmd_models(args):
    """List models advertised by the configured endpoint."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    try:
        provider = build_provider(
            model=getattr(args, "model", None),
            base_url=getattr(args, "base_url", None),
            profile=getattr(args, "provider", None),
        )
        models = provider.get_models()
    except Exception as exc:
        print(f"Error listing models: {exc}")
        return 1

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": m.id,
                        "name": m.name,
                        "context_window": m.context_window,
                    }
                    for m in models
                ],
                indent=2,
            )
        )
        return 0

    table = Table(title=f"Models @ {provider.base_url}")
    table.add_column("Model ID", style="cyan")
    table.add_column("Context", style="dim", justify="right")

    for m in models:
        table.add_row(m.id, str(m.context_window))

    console.print(table)
    console.print(f"\n[dim]{len(models)} model(s) available[/dim]")
    return 0


def cmd_test(args):
    """Probe the configured LLM endpoint for reachability."""
    from rich.console import Console

    console = Console()

    try:
        provider = build_provider(
            model=getattr(args, "model", None),
            base_url=getattr(args, "base_url", None),
            profile=getattr(args, "provider", None),
        )
    except Exception as exc:
        console.print(f"[red]FAILED[/red] - could not build provider: {exc}")
        return 1

    console.print(f"Testing connection to [cyan]{provider.base_url}[/cyan]...")
    if not provider.is_available():
        console.print("[red]FAILED[/red] - endpoint unreachable or unauthorized")
        return 1

    console.print("[green]OK[/green] - endpoint reachable")
    try:
        models = provider.get_models()
        console.print(f"[dim]{len(models)} models available[/dim]")
        if getattr(args, "model", None):
            model_ids = {m.id for m in models}
            if args.model in model_ids:
                console.print(f"[green]OK[/green] - model {args.model!r} listed")
            else:
                console.print(
                    f"[yellow]Warning[/yellow] - model {args.model!r} not listed"
                )
    except Exception as exc:
        console.print(f"[yellow]Warning[/yellow] - model listing failed: {exc}")
    return 0


def add_llm_commands(subparsers):
    """Add the ``llm`` command group to the top-level parser."""
    llm_parser = subparsers.add_parser("llm", help="LLM provider operations")
    llm_subparsers = llm_parser.add_subparsers(dest="llm_command", help="LLM commands")

    providers_parser = llm_subparsers.add_parser(
        "providers", help="List configured providers"
    )
    providers_parser.add_argument("--json", action="store_true", help="Output as JSON")

    models_parser = llm_subparsers.add_parser("models", help="List available models")
    models_parser.add_argument(
        "--base-url", default=None, help="Override configured endpoint"
    )
    models_parser.add_argument(
        "--model", default=None, help="Override configured model (informational)"
    )
    models_parser.add_argument(
        "--provider", default=None, help="Named provider profile to use"
    )
    models_parser.add_argument("--json", action="store_true", help="Output as JSON")

    test_parser = llm_subparsers.add_parser("test", help="Test provider connection")
    test_parser.add_argument(
        "--base-url", default=None, help="Override configured endpoint"
    )
    test_parser.add_argument(
        "--model", "-m", default=None, help="Specific model to check for"
    )
    test_parser.add_argument(
        "--provider", default=None, help="Named provider profile to use"
    )
    return llm_parser


def dispatch_llm_command(args):
    """Dispatch to the appropriate ``llm`` subcommand."""
    commands = {
        "providers": cmd_providers,
        "models": cmd_models,
        "test": cmd_test,
    }
    if hasattr(args, "llm_command") and args.llm_command:
        if args.llm_command in commands:
            return commands[args.llm_command](args)
        print(f"Unknown llm command: {args.llm_command}")
        return 1
    print("Error: No llm command specified. Use 'ctk llm --help' for available commands.")
    return 1
