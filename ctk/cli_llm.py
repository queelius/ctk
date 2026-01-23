"""
LLM provider commands for CTK CLI.

Commands for managing and testing LLM providers:
- providers: List configured providers
- models: List available models for a provider
- test: Test connection to a provider
"""

import argparse
import json
from typing import List, Optional

from ctk.core.config import get_config


def cmd_providers(args):
    """List configured LLM providers"""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    config = get_config()

    providers = config.get("providers", {})

    if args.json:
        print(json.dumps(providers, indent=2))
        return 0

    table = Table(title="LLM Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Base URL", style="dim")
    table.add_column("Default Model", style="green")
    table.add_column("API Key", style="yellow")

    for name, cfg in providers.items():
        api_key = config.get_api_key(name)
        key_status = "Set" if api_key else "Not set"
        table.add_row(
            name, cfg.get("base_url", ""), cfg.get("default_model", ""), key_status
        )

    console.print(table)
    return 0


def cmd_models(args):
    """List available models for a provider"""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    config = get_config()

    provider_name = args.provider or "ollama"
    provider_config = config.get_provider_config(provider_name)

    if not provider_config:
        print(f"Error: Provider '{provider_name}' not configured")
        return 1

    # Try to get models from the provider
    try:
        if provider_name == "ollama":
            from ctk.integrations.llm.ollama import OllamaProvider

            provider = OllamaProvider(
                {
                    "base_url": provider_config.get(
                        "base_url", "http://localhost:11434"
                    ),
                    "model": provider_config.get("default_model", "llama2"),
                }
            )
            models = provider.get_models()

        elif provider_name == "openai":
            # OpenAI provider not yet implemented - list known models
            models = [
                {"id": "gpt-4o", "name": "GPT-4o"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
                {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
                {"id": "gpt-4", "name": "GPT-4"},
                {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo"},
            ]

        elif provider_name == "anthropic":
            # Anthropic doesn't have a models endpoint, list known models
            models = [
                {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus"},
                {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet"},
                {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku"},
                {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
            ]

        else:
            print(f"Error: Model listing not supported for '{provider_name}'")
            return 1

        if args.json:
            print(json.dumps(models, indent=2))
            return 0

        table = Table(title=f"Models ({provider_name})")
        table.add_column("Model ID", style="cyan")
        table.add_column("Name/Details", style="dim")

        for model in models:
            if isinstance(model, dict):
                model_id = model.get("id", model.get("name", str(model)))
                model_name = model.get("name", model.get("id", ""))
            elif hasattr(model, "id"):
                # ModelInfo object
                model_id = model.id
                model_name = model.name if hasattr(model, "name") else ""
            else:
                model_id = str(model)
                model_name = ""

            table.add_row(model_id, model_name)

        console.print(table)
        console.print(f"\n[dim]{len(models)} model(s) available[/dim]")
        return 0

    except Exception as e:
        print(f"Error listing models: {e}")
        return 1


def cmd_test(args):
    """Test connection to an LLM provider"""
    from rich.console import Console

    console = Console()
    config = get_config()

    provider_name = args.provider or "ollama"
    provider_config = config.get_provider_config(provider_name)

    if not provider_config:
        print(f"Error: Provider '{provider_name}' not configured")
        return 1

    console.print(f"Testing connection to [cyan]{provider_name}[/cyan]...")

    try:
        if provider_name == "ollama":
            from ctk.integrations.llm.ollama import OllamaProvider

            provider = OllamaProvider(
                {
                    "base_url": provider_config.get(
                        "base_url", "http://localhost:11434"
                    ),
                    "model": provider_config.get("default_model", "llama2"),
                }
            )

            if provider.is_available():
                console.print(
                    f"[green]OK[/green] - Connected to Ollama at {provider_config.get('base_url')}"
                )

                # Try to list models as additional test
                models = provider.get_models()
                console.print(f"[dim]{len(models)} models available[/dim]")

                # If a specific model is requested, test it
                if args.model:
                    model_ids = [
                        (
                            m.get("id", m.get("name", ""))
                            if isinstance(m, dict)
                            else str(m)
                        )
                        for m in models
                    ]
                    if args.model in model_ids:
                        console.print(
                            f"[green]OK[/green] - Model '{args.model}' is available"
                        )
                    else:
                        console.print(
                            f"[yellow]Warning[/yellow] - Model '{args.model}' not found"
                        )
                return 0
            else:
                console.print(f"[red]FAILED[/red] - Cannot connect to Ollama")
                return 1

        elif provider_name == "openai":
            from ctk.integrations.llm.openai import OpenAIProvider

            api_key = config.get_api_key("openai")
            if not api_key:
                console.print("[red]FAILED[/red] - OPENAI_API_KEY not set")
                return 1

            provider = OpenAIProvider(
                {
                    "api_key": api_key,
                    "model": args.model
                    or provider_config.get("default_model", "gpt-3.5-turbo"),
                }
            )

            if provider.is_available():
                console.print(f"[green]OK[/green] - Connected to OpenAI")
                return 0
            else:
                console.print(f"[red]FAILED[/red] - Cannot connect to OpenAI")
                return 1

        elif provider_name == "anthropic":
            from ctk.integrations.llm.anthropic import AnthropicProvider

            api_key = config.get_api_key("anthropic")
            if not api_key:
                console.print("[red]FAILED[/red] - ANTHROPIC_API_KEY not set")
                return 1

            provider = AnthropicProvider(
                {
                    "api_key": api_key,
                    "model": args.model
                    or provider_config.get("default_model", "claude-3-haiku-20240307"),
                }
            )

            if provider.is_available():
                console.print(f"[green]OK[/green] - Connected to Anthropic")
                return 0
            else:
                console.print(f"[red]FAILED[/red] - Cannot connect to Anthropic")
                return 1

        else:
            console.print(
                f"[yellow]Warning[/yellow] - Testing not implemented for '{provider_name}'"
            )
            return 1

    except Exception as e:
        console.print(f"[red]FAILED[/red] - {e}")
        return 1


def add_llm_commands(subparsers):
    """Add LLM command group to parser"""
    llm_parser = subparsers.add_parser("llm", help="LLM provider operations")
    llm_subparsers = llm_parser.add_subparsers(dest="llm_command", help="LLM commands")

    # providers
    providers_parser = llm_subparsers.add_parser(
        "providers", help="List configured providers"
    )
    providers_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # models
    models_parser = llm_subparsers.add_parser("models", help="List available models")
    models_parser.add_argument(
        "provider", nargs="?", default="ollama", help="Provider name (default: ollama)"
    )
    models_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # test
    test_parser = llm_subparsers.add_parser("test", help="Test provider connection")
    test_parser.add_argument(
        "provider", nargs="?", default="ollama", help="Provider name (default: ollama)"
    )
    test_parser.add_argument("--model", "-m", help="Specific model to test")

    return llm_parser


def dispatch_llm_command(args):
    """Dispatch to appropriate llm subcommand"""
    commands = {
        "providers": cmd_providers,
        "models": cmd_models,
        "test": cmd_test,
    }

    if hasattr(args, "llm_command") and args.llm_command:
        if args.llm_command in commands:
            return commands[args.llm_command](args)
        else:
            print(f"Unknown llm command: {args.llm_command}")
            return 1
    else:
        print(
            "Error: No llm command specified. Use 'ctk llm --help' for available commands."
        )
        return 1
