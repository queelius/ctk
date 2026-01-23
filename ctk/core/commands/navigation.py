"""
Navigation command handlers

Implements: cd, ls, pwd
"""

from typing import Callable, Dict, List

from ctk.core.command_dispatcher import CommandResult
from ctk.core.vfs import VFSPathParser
from ctk.core.vfs_navigator import VFSNavigator


class NavigationCommands:
    """Handler for VFS navigation commands"""

    def __init__(self, navigator: VFSNavigator, tui_instance=None):
        """
        Initialize navigation command handlers

        Args:
            navigator: VFS navigator for path resolution
            tui_instance: Reference to TUI for state (required for cd/ls/pwd)
        """
        self.navigator = navigator
        self.tui = tui_instance

        if not tui_instance:
            raise ValueError(
                "NavigationCommands requires tui_instance for state tracking"
            )

    def cmd_cd(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Change directory in VFS

        Usage:
            cd <path>       - Change to path
            cd /chats       - Change to /chats
            cd abc123       - Change to conversation (with prefix resolution)
            cd ..           - Go up one level
            cd /            - Go to root

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        if not args:
            # No arguments: go to root
            new_path = "/"
        else:
            path_arg = args[0]

            # Get current path from TUI state
            current_path = self.tui.vfs_cwd

            # Handle relative paths
            if path_arg == "..":
                # Go up one level
                if current_path == "/":
                    return CommandResult(success=True, output="Already at root\n")
                # Remove last segment
                parts = current_path.rstrip("/").split("/")
                new_path = "/".join(parts[:-1]) or "/"
            elif path_arg.startswith("/"):
                # Absolute path
                new_path = path_arg
            else:
                # Relative path - combine with current
                if current_path.endswith("/"):
                    new_path = current_path + path_arg
                else:
                    new_path = current_path + "/" + path_arg

        # Validate and resolve the path
        try:
            # Parse the path
            parsed_path = VFSPathParser.parse(new_path)

            # Try prefix resolution if it looks like a partial ID
            result_path = new_path
            resolved_prefix = False

            # Check if last segment looks like it might be a prefix
            segments = new_path.rstrip("/").split("/")
            last_segment = segments[-1] if segments else ""

            if (
                last_segment
                and len(last_segment) >= 3
                and not last_segment.startswith("/")
            ):
                # Try prefix resolution in parent directory
                parent_path = "/".join(segments[:-1]) or "/"
                parent_parsed = VFSPathParser.parse(parent_path)

                try:
                    resolved_id = self.navigator.resolve_prefix(
                        last_segment, parent_parsed
                    )
                    if resolved_id:
                        result_path = parent_path + "/" + resolved_id
                        resolved_prefix = True
                    # If resolve_prefix returns None, prefix didn't match
                except ValueError:
                    # Prefix resolution failed, use original path
                    pass

            # Validate the final path exists by trying to parse it
            # This will raise ValueError if the path is invalid
            final_parsed = VFSPathParser.parse(result_path)

            # For directory paths, verify it can be listed (catches non-existent IDs)
            if final_parsed.is_directory:
                try:
                    # Try to list the directory to verify it exists
                    self.navigator.list_directory(final_parsed)
                except ValueError as e:
                    # Directory doesn't exist
                    return CommandResult(
                        success=False, output="", error=f"cd: {str(e)}"
                    )

            # Update TUI state
            self.tui.vfs_cwd = result_path
            self.tui._update_environment()

            # Show resolution message if prefix was resolved
            if resolved_prefix:
                output = f"Resolved '{last_segment}' to: {resolved_id}\n"
            else:
                output = ""

            return CommandResult(success=True, output=output)

        except ValueError as e:
            return CommandResult(success=False, output="", error=f"cd: {str(e)}")

    def cmd_ls(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        List directory contents

        Usage:
            ls              - List current directory
            ls <path>       - List specified directory
            ls -l           - Long format with metadata

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with directory listing
        """
        # Parse arguments
        path = None
        long_format = False

        for arg in args:
            if arg.startswith("-"):
                if "l" in arg:
                    long_format = True
            else:
                path = arg

        # Get path to list
        if path:
            # Resolve relative to current path
            current_path = self.tui.vfs_cwd
            if not path.startswith("/"):
                if current_path.endswith("/"):
                    full_path = current_path + path
                else:
                    full_path = current_path + "/" + path
            else:
                full_path = path
        else:
            full_path = self.tui.vfs_cwd

        # Parse and list directory
        try:
            parsed_path = VFSPathParser.parse(full_path)
            entries = self.navigator.list_directory(parsed_path)

            if not entries:
                return CommandResult(success=True, output="")

            # Get UUID prefix length setting (default 8)
            uuid_prefix_len = 8
            if self.tui:
                val = getattr(self.tui, "uuid_prefix_len", None)
                if isinstance(val, int):
                    uuid_prefix_len = val

            # Format output
            output_lines = []
            for entry in entries:
                name = self._format_entry_name(entry, long_format, uuid_prefix_len)
                output_lines.append(name)

            output = "\n".join(output_lines) + "\n"
            return CommandResult(success=True, output=output)

        except ValueError as e:
            return CommandResult(success=False, output="", error=f"ls: {str(e)}")

    def _format_entry_name(self, entry, long_format: bool, uuid_prefix_len: int) -> str:
        """Format an entry name for ls output"""
        # Message nodes inside a conversation - use simple name (m1, m2, etc.)
        if entry.message_id:
            if entry.is_directory:
                name = entry.name + "/"
            else:
                name = entry.name
            # Add role indicator for long format
            if long_format and entry.role:
                name = f"[{entry.role}] {name}"
            return name

        # For conversation entries, show slug with UUID prefix in parens
        if entry.conversation_id:
            uuid_prefix = entry.conversation_id[:uuid_prefix_len]
            if entry.slug:
                # Slug is primary, UUID in parens
                name = f"{entry.slug} ({uuid_prefix})"
            else:
                # No slug, use title or just UUID
                if entry.title:
                    # Create a display name from title
                    display = entry.title[:40]
                    if len(entry.title) > 40:
                        display += "..."
                    name = f"{display} ({uuid_prefix})"
                else:
                    name = uuid_prefix
            if entry.is_directory:
                name += "/"

            # Add long format details for conversations
            if long_format:
                flags = ""
                if entry.starred:
                    flags += "⭐"
                if entry.pinned:
                    flags += "📌"
                if entry.archived:
                    flags += "📦"
                if flags:
                    name = f"{flags} {name}"
                if entry.model:
                    name += f"  [{entry.model}]"
            return name

        # Regular directory/file entries
        if entry.is_directory:
            name = entry.name + "/"
        else:
            name = entry.name

        return name

    def cmd_pwd(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Print working directory

        Usage:
            pwd             - Show current VFS path

        Args:
            args: Command arguments (ignored)
            stdin: Standard input (ignored)

        Returns:
            CommandResult with current path
        """
        current_path = self.tui.vfs_cwd
        return CommandResult(success=True, output=f"{current_path}\n")


def create_navigation_commands(
    navigator: VFSNavigator, tui_instance=None
) -> Dict[str, Callable]:
    """
    Create navigation command handlers

    Args:
        navigator: VFS navigator
        tui_instance: Optional TUI instance for state updates

    Returns:
        Dictionary mapping command names to handlers
    """
    nav = NavigationCommands(navigator, tui_instance)

    return {
        "cd": nav.cmd_cd,
        "ls": nav.cmd_ls,
        "pwd": nav.cmd_pwd,
    }
