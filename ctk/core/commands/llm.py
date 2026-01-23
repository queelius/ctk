"""
LLM control commands for shell mode.

Commands:
- temp: Get/set temperature
- model: Get/set current model
- models: List available models
- regenerate: Regenerate last assistant response
- retry: Retry last user message with optional temperature
"""

from typing import Any, Callable, Dict, Optional

from ctk.core.command_dispatcher import CommandResult


def create_llm_commands(
    tui_instance=None,
) -> Dict[str, Callable]:
    """
    Create LLM control command handlers.

    Args:
        tui_instance: TUI instance for access to LLM provider

    Returns:
        Dictionary mapping command names to handler functions
    """

    def cmd_temp(args: str) -> CommandResult:
        """Get or set LLM temperature.

        Usage: temp [value]

        Without argument, shows current temperature.
        With argument, sets temperature (0.0-2.0).

        Examples:
            temp           Show current temperature
            temp 0.7       Set temperature to 0.7
            temp 0         Set temperature to 0 (deterministic)
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        if not args:
            return CommandResult(
                success=True,
                output=f"Current temperature: {tui_instance.temperature}"
            )

        try:
            temp = float(args.strip())
            if temp < 0.0 or temp > 2.0:
                return CommandResult(
                    success=False,
                    output="",
                    error="Temperature must be between 0.0 and 2.0"
                )
            tui_instance.temperature = temp
            return CommandResult(success=True, output=f"Temperature set to {temp}")
        except ValueError:
            return CommandResult(success=False, output="", error=f"Invalid temperature: {args}")

    def cmd_model(args: str) -> CommandResult:
        """Get or set current LLM model.

        Usage: model [name]

        Without argument, shows current model info.
        With argument, switches to the specified model.

        Examples:
            model               Show current model
            model llama3.2      Switch to llama3.2
            model gpt-4         Switch to gpt-4
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not tui_instance.provider:
            return CommandResult(success=False, output="", error="No LLM provider configured")

        if not args:
            # Show current model info
            output_lines = [
                f"Current model: {tui_instance.provider.model}",
                f"Provider: {tui_instance.provider.name}",
            ]

            # Show provider-specific info
            if hasattr(tui_instance.provider, "base_url"):
                output_lines.append(f"Base URL: {tui_instance.provider.base_url}")

            # Get detailed model info if available
            try:
                model_info = tui_instance.provider.get_model_info(
                    tui_instance.provider.model
                )
                if model_info:
                    output_lines.append("\nModel details:")
                    if "details" in model_info:
                        details = model_info["details"]
                        if "family" in details:
                            output_lines.append(f"  Family: {details['family']}")
                        if "parameter_size" in details:
                            output_lines.append(f"  Size: {details['parameter_size']}")
                        if "quantization_level" in details:
                            output_lines.append(
                                f"  Quantization: {details['quantization_level']}"
                            )
            except Exception as e:
                output_lines.append(f"  (Could not retrieve model details: {e})")

            return CommandResult(success=True, output="\n".join(output_lines))
        else:
            old_model = tui_instance.provider.model
            tui_instance.provider.model = args.strip()
            return CommandResult(
                success=True,
                output=f"Model changed from {old_model} to {args.strip()}"
            )

    def cmd_models(args: str) -> CommandResult:
        """List available LLM models.

        Usage: models

        Lists all models available from the current provider.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not tui_instance.provider:
            return CommandResult(success=False, output="", error="No LLM provider configured")

        try:
            tui_instance.list_models()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error listing models: {e}")

    def cmd_regenerate(args: str) -> CommandResult:
        """Regenerate the last assistant response.

        Usage: regenerate

        Removes the last assistant message and generates a new response
        to the same context. Useful for getting alternative responses.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        try:
            tui_instance.regenerate_last_response()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Regenerate error: {e}")

    def cmd_retry(args: str) -> CommandResult:
        """Retry the last user message.

        Usage: retry [temperature]

        Re-sends the last user message to get a new response.
        Optionally specify a different temperature for this retry.

        Examples:
            retry           Retry with current temperature
            retry 0.5       Retry with temperature 0.5
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        temp = None
        if args:
            try:
                temp = float(args.strip())
                if temp < 0.0 or temp > 2.0:
                    return CommandResult(
                        success=False,
                        output="",
                        error="Temperature must be between 0.0 and 2.0"
                    )
            except ValueError:
                return CommandResult(success=False, output="", error=f"Invalid temperature: {args}")

        try:
            tui_instance.retry_last_message(temp)
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Retry error: {e}")

    def cmd_stream(args: str) -> CommandResult:
        """Toggle streaming mode for responses.

        Usage: stream

        Toggles between streaming (real-time) and non-streaming output.
        Streaming shows tokens as they are generated.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        tui_instance.streaming = not tui_instance.streaming
        status = "enabled" if tui_instance.streaming else "disabled"
        return CommandResult(success=True, output=f"Streaming {status}")

    def cmd_num_ctx(args: str) -> CommandResult:
        """Get or set context window size.

        Usage: num_ctx [size]

        Without argument, shows current context window size.
        With argument, sets the context window size in tokens.

        Examples:
            num_ctx          Show current context size
            num_ctx 8192     Set to 8192 tokens
            num_ctx 32000    Set to 32000 tokens
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        if not args:
            if tui_instance.num_ctx:
                return CommandResult(
                    success=True,
                    output=f"Context window: {tui_instance.num_ctx:,} tokens"
                )
            else:
                return CommandResult(
                    success=True,
                    output="Context window: not set (using model default)"
                )
        else:
            try:
                size = int(args.strip())
                if size < 128:
                    return CommandResult(
                        success=False,
                        output="",
                        error="Context window must be at least 128 tokens"
                    )
                tui_instance.num_ctx = size
                return CommandResult(
                    success=True,
                    output=f"Context window set to {size:,} tokens"
                )
            except ValueError:
                return CommandResult(success=False, output="", error=f"Invalid context size: {args}")

    return {
        "temp": cmd_temp,
        "model": cmd_model,
        "models": cmd_models,
        "regenerate": cmd_regenerate,
        "retry": cmd_retry,
        "stream": cmd_stream,
        "num_ctx": cmd_num_ctx,
    }
