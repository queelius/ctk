"""
Settings command handlers

Implements: set, get
"""

from typing import Any, Callable, Dict, List

from ctk.core.command_dispatcher import CommandResult

# Define available settings with their defaults and validators
SHELL_SETTINGS = {
    "uuid_prefix_len": {
        "default": 8,
        "type": int,
        "min": 4,
        "max": 36,
        "description": "Number of UUID characters to display (4-36)",
    },
}


class SettingsCommands:
    """Handler for shell settings commands"""

    def __init__(self, tui_instance=None):
        """
        Initialize settings command handlers

        Args:
            tui_instance: TUI instance for settings storage
        """
        self.tui = tui_instance

    def _get_setting(self, name: str) -> Any:
        """Get a setting value from TUI or return default"""
        if self.tui and hasattr(self.tui, name):
            return getattr(self.tui, name)
        if name in SHELL_SETTINGS:
            return SHELL_SETTINGS[name]["default"]
        return None

    def _set_setting(self, name: str, value: Any) -> tuple[bool, str]:
        """
        Set a setting value on TUI

        Returns:
            (success, error_message)
        """
        if name not in SHELL_SETTINGS:
            return (False, f"Unknown setting: {name}")

        spec = SHELL_SETTINGS[name]

        # Type conversion
        try:
            if spec["type"] == int:
                value = int(value)
            elif spec["type"] == float:
                value = float(value)
            elif spec["type"] == bool:
                value = value.lower() in ("true", "1", "yes", "on")
            elif spec["type"] == str:
                value = str(value)
        except ValueError:
            return (
                False,
                f"Invalid value type for {name}: expected {spec['type'].__name__}",
            )

        # Range validation for numeric types
        if spec["type"] in (int, float):
            if "min" in spec and value < spec["min"]:
                return (False, f"{name} must be >= {spec['min']}")
            if "max" in spec and value > spec["max"]:
                return (False, f"{name} must be <= {spec['max']}")

        # Apply to TUI
        if self.tui:
            setattr(self.tui, name, value)
            return (True, "")
        else:
            return (False, "No TUI instance available")

    def cmd_set(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Set a shell setting

        Usage:
            set                          - Show all settings
            set <name>                   - Show specific setting
            set <name> <value>           - Set a value

        Available settings:
            uuid_prefix_len <4-36>       - UUID prefix length in ls output (default 8)

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        if not args:
            # Show all settings
            lines = ["Shell Settings:", ""]
            for name, spec in SHELL_SETTINGS.items():
                current = self._get_setting(name)
                lines.append(f"  {name} = {current}")
                lines.append(f"    {spec['description']}")
                lines.append("")
            return CommandResult(success=True, output="\n".join(lines) + "\n")

        name = args[0]

        if len(args) == 1:
            # Show specific setting
            if name not in SHELL_SETTINGS:
                return CommandResult(
                    success=False,
                    output="",
                    error=f"set: Unknown setting '{name}'. Use 'set' to list available settings.",
                )
            current = self._get_setting(name)
            spec = SHELL_SETTINGS[name]
            return CommandResult(
                success=True, output=f"{name} = {current}\n  {spec['description']}\n"
            )

        # Set value
        value = args[1]
        success, error = self._set_setting(name, value)

        if success:
            return CommandResult(success=True, output=f"Set {name} = {value}\n")
        else:
            return CommandResult(success=False, output="", error=f"set: {error}")

    def cmd_get(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Get a shell setting value

        Usage:
            get <name>           - Get setting value

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with setting value
        """
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="get: Specify a setting name. Use 'set' to list available settings.",
            )

        name = args[0]

        if name not in SHELL_SETTINGS:
            return CommandResult(
                success=False, output="", error=f"get: Unknown setting '{name}'"
            )

        value = self._get_setting(name)
        return CommandResult(success=True, output=f"{value}\n")


def create_settings_commands(tui_instance=None) -> Dict[str, Callable]:
    """
    Create settings command handlers

    Args:
        tui_instance: TUI instance for settings storage

    Returns:
        Dictionary mapping command names to handlers
    """
    settings = SettingsCommands(tui_instance)

    return {
        "set": settings.cmd_set,
        "get": settings.cmd_get,
    }
