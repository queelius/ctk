"""
Unix-like command handlers

Implements: cat, head, tail, echo, grep
"""

import re
from typing import Callable, Dict, List, Optional

from ctk.core.command_dispatcher import CommandResult
from ctk.core.database import ConversationDB
from ctk.core.vfs import PathType
from ctk.core.vfs_navigator import VFSNavigator


class UnixCommands:
    """Handler for Unix-like commands"""

    def __init__(self, db: ConversationDB, navigator: VFSNavigator, tui_instance=None):
        """
        Initialize Unix command handlers

        Args:
            db: Database instance
            navigator: VFS navigator for path resolution
            tui_instance: Optional TUI instance for current path state
        """
        self.db = db
        self.navigator = navigator
        self.tui = tui_instance

    def cmd_cat(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Display message content

        Usage:
            cat <path>      - Display message at path
            cat m1          - Display message 1
            cat m1/m2       - Display message at path m1/m2
            cat .           - Display current message (if in message node)

        Args:
            args: Command arguments
            stdin: Standard input (piped from previous command)

        Returns:
            CommandResult with message content
        """
        # If no args and stdin provided, just return stdin
        if not args and stdin:
            return CommandResult(success=True, output=stdin)

        if not args:
            return CommandResult(success=False, output="", error="cat: missing operand")

        output_lines = []

        for path_arg in args:
            try:
                # Parse the path
                # Get current path from TUI state
                if self.tui:
                    current_vfs_path = self.tui.vfs_cwd
                else:
                    current_vfs_path = "/"

                if path_arg == ".":
                    # Current location
                    current_path = current_vfs_path
                else:
                    # Resolve path relative to current location
                    if not path_arg.startswith("/"):
                        # Relative path - combine with current
                        if current_vfs_path.endswith("/"):
                            full_path = current_vfs_path + path_arg
                        else:
                            full_path = current_vfs_path + "/" + path_arg
                    else:
                        full_path = path_arg

                    # Parse the full path
                    from ctk.core.vfs import VFSPathParser

                    current_path = VFSPathParser.parse(full_path).normalized_path

                # Check what type of path this is
                parsed_path = VFSPathParser.parse(current_path)
                path_type = parsed_path.path_type

                if path_type == PathType.MESSAGE_FILE:
                    # Read message metadata file
                    conv_id = parsed_path.conversation_id
                    message_path = parsed_path.message_path
                    file_name = parsed_path.file_name

                    # Load conversation
                    conversation = self.db.load_conversation(conv_id)
                    if not conversation:
                        return CommandResult(
                            success=False,
                            output="",
                            error=f"cat: {path_arg}: Conversation not found",
                        )

                    # Navigate to the message
                    current_message_id = None
                    for node_name in message_path:
                        # Extract index from node name (m1 -> 1, m2 -> 2)
                        if not node_name.lower().startswith("m"):
                            return CommandResult(
                                success=False,
                                output="",
                                error=f"cat: {path_arg}: Invalid message node: {node_name}",
                            )

                        try:
                            node_index = int(node_name[1:])  # Remove 'm' prefix
                        except ValueError:
                            return CommandResult(
                                success=False,
                                output="",
                                error=f"cat: {path_arg}: Invalid message node: {node_name}",
                            )

                        # Get available children at this level
                        if current_message_id is None:
                            # At root level
                            available_ids = conversation.root_message_ids
                        else:
                            # Get children of current message
                            children = conversation.get_children(current_message_id)
                            available_ids = [child.id for child in children]

                        # Map index to message ID (1-indexed)
                        if node_index < 1 or node_index > len(available_ids):
                            return CommandResult(
                                success=False,
                                output="",
                                error=f"cat: {path_arg}: Message node {node_name} out of range",
                            )

                        current_message_id = available_ids[node_index - 1]

                    # Get the message
                    message = conversation.message_map.get(current_message_id)
                    if not message:
                        return CommandResult(
                            success=False,
                            output="",
                            error=f"cat: {path_arg}: Message not found",
                        )

                    # Get the requested metadata
                    if file_name == "text":
                        content_text = (
                            message.content.get_text()
                            if hasattr(message.content, "get_text")
                            else str(
                                message.content.text
                                if hasattr(message.content, "text")
                                else message.content
                            )
                        )
                        # Show helpful message if text is empty
                        if not content_text or content_text.strip() == "":
                            output_lines.append("[empty]")
                        else:
                            output_lines.append(content_text)
                    elif file_name == "role":
                        output_lines.append(
                            message.role.value if message.role else "user"
                        )
                    elif file_name == "timestamp":
                        output_lines.append(
                            str(message.timestamp) if message.timestamp else ""
                        )
                    elif file_name == "id":
                        output_lines.append(current_message_id)
                    else:
                        return CommandResult(
                            success=False,
                            output="",
                            error=f"cat: {path_arg}: Unknown metadata file: {file_name}",
                        )

                elif path_type == PathType.MESSAGE_NODE:
                    # Display message content
                    # Parse the path to get conversation ID and message path
                    parsed = VFSPathParser.parse(current_path)
                    conv_id = parsed.conversation_id
                    message_path = parsed.message_path

                    # Load conversation
                    conversation = self.db.load_conversation(conv_id)
                    if not conversation:
                        return CommandResult(
                            success=False,
                            output="",
                            error=f"cat: {path_arg}: Conversation not found",
                        )

                    # Navigate to the message
                    current_message_id = None
                    for node_name in message_path:
                        # Extract index from node name (m1 -> 1, m2 -> 2)
                        if not node_name.lower().startswith("m"):
                            return CommandResult(
                                success=False,
                                output="",
                                error=f"cat: {path_arg}: Invalid message node: {node_name}",
                            )

                        try:
                            node_index = int(node_name[1:])  # Remove 'm' prefix
                        except ValueError:
                            return CommandResult(
                                success=False,
                                output="",
                                error=f"cat: {path_arg}: Invalid message node: {node_name}",
                            )

                        # Get available children at this level
                        if current_message_id is None:
                            # At root level
                            available_ids = conversation.root_message_ids
                        else:
                            # Get children of current message
                            children = conversation.get_children(current_message_id)
                            available_ids = [child.id for child in children]

                        # Map index to message ID (1-indexed)
                        if node_index < 1 or node_index > len(available_ids):
                            return CommandResult(
                                success=False,
                                output="",
                                error=f"cat: {path_arg}: Message node {node_name} out of range",
                            )

                        current_message_id = available_ids[node_index - 1]

                    # Get the message from the message_map
                    message = conversation.message_map.get(current_message_id)

                    if message:
                        # Format message content
                        role_label = message.role.value.title()
                        content_text = (
                            message.content.get_text()
                            if hasattr(message.content, "get_text")
                            else str(
                                message.content.text
                                if hasattr(message.content, "text")
                                else message.content
                            )
                        )
                        output_lines.append(f"{role_label}: {content_text}")
                    else:
                        return CommandResult(
                            success=False,
                            output="",
                            error=f"cat: {path_arg}: Message not found",
                        )

                elif path_type == PathType.CONVERSATION:
                    # Display all messages in conversation
                    # Get conversation
                    parsed = VFSPathParser.parse(current_path)
                    conv_id = parsed.conversation_id
                    conversation = self.db.load_conversation(conv_id)

                    if not conversation:
                        return CommandResult(
                            success=False,
                            output="",
                            error=f"cat: {path_arg}: Conversation not found",
                        )

                    # Display all messages on the longest path
                    path = conversation.get_longest_path()
                    for msg in path:
                        role_label = msg.role.value.title()
                        output_lines.append(f"{role_label}: {msg.content.text}")
                        output_lines.append("")  # Blank line between messages

                else:
                    return CommandResult(
                        success=False,
                        output="",
                        error=f"cat: {path_arg}: Not a message or conversation",
                    )

            except Exception as e:
                return CommandResult(
                    success=False, output="", error=f"cat: {path_arg}: {str(e)}"
                )

        output = "\n".join(output_lines) + "\n" if output_lines else ""
        return CommandResult(success=True, output=output)

    def cmd_head(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Display first n lines

        Usage:
            head [n]        - Display first n lines from stdin (default 10)
            head <path> [n] - Display first n lines from path
            cat m1 | head 5 - Display first 5 lines of message 1

        Args:
            args: Command arguments
            stdin: Standard input

        Returns:
            CommandResult with first n lines
        """
        # Parse arguments
        n = 10  # default
        path = None

        if args:
            if args[0].isdigit():
                n = int(args[0])
            else:
                path = args[0]
                if len(args) > 1 and args[1].isdigit():
                    n = int(args[1])

        # Get content
        if path:
            # Read from path using cat
            result = self.cmd_cat([path])
            if not result.success:
                return result
            content = result.output
        else:
            # Read from stdin
            content = stdin

        if not content:
            return CommandResult(success=True, output="")

        # Take first n lines
        lines = content.split("\n")
        output = "\n".join(lines[:n])
        if output and not output.endswith("\n"):
            output += "\n"

        return CommandResult(success=True, output=output)

    def cmd_tail(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Display last n lines

        Usage:
            tail [n]        - Display last n lines from stdin (default 10)
            tail <path> [n] - Display last n lines from path
            cat m1 | tail 5 - Display last 5 lines of message 1

        Args:
            args: Command arguments
            stdin: Standard input

        Returns:
            CommandResult with last n lines
        """
        # Parse arguments
        n = 10  # default
        path = None

        if args:
            if args[0].isdigit():
                n = int(args[0])
            else:
                path = args[0]
                if len(args) > 1 and args[1].isdigit():
                    n = int(args[1])

        # Get content
        if path:
            # Read from path using cat
            result = self.cmd_cat([path])
            if not result.success:
                return result
            content = result.output
        else:
            # Read from stdin
            content = stdin

        if not content:
            return CommandResult(success=True, output="")

        # Take last n lines
        lines = content.split("\n")
        # Remove trailing empty line if present
        if lines and not lines[-1]:
            lines = lines[:-1]

        output = "\n".join(lines[-n:])
        if output and not output.endswith("\n"):
            output += "\n"

        return CommandResult(success=True, output=output)

    def cmd_echo(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Echo arguments or environment variables

        Usage:
            echo <text>     - Print text
            echo $VAR       - Print environment variable (handled by parser)
            echo "hello"    - Print with quotes removed

        Args:
            args: Command arguments (variables already expanded by parser)
            stdin: Standard input (ignored)

        Returns:
            CommandResult with echoed text
        """
        output = " ".join(args) + "\n" if args else "\n"
        return CommandResult(success=True, output=output)

    def cmd_grep(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Search for pattern in input

        Usage:
            grep <pattern>          - Search stdin for pattern
            grep <pattern> <path>   - Search file for pattern
            cat m1 | grep "error"   - Search message for "error"

        Options:
            -i  Case insensitive search
            -n  Show line numbers
            -v  Invert match (show non-matching lines)
            -c  Count matching lines only
            -l  List matching paths only (files mode)

        Args:
            args: Command arguments
            stdin: Standard input

        Returns:
            CommandResult with matching lines
        """
        if not args:
            return CommandResult(
                success=False, output="", error="grep: no pattern specified"
            )

        # Parse options
        case_insensitive = False
        show_line_numbers = False
        invert_match = False
        count_only = False
        list_files_only = False
        pattern = None
        paths: List[str] = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith("-") and len(arg) > 1 and not arg.startswith("--"):
                # Parse combined options (e.g., -inv)
                for char in arg[1:]:
                    if char == "i":
                        case_insensitive = True
                    elif char == "n":
                        show_line_numbers = True
                    elif char == "v":
                        invert_match = True
                    elif char == "c":
                        count_only = True
                    elif char == "l":
                        list_files_only = True
                    else:
                        return CommandResult(
                            success=False,
                            output="",
                            error=f"grep: invalid option: -{char}",
                        )
            elif pattern is None:
                pattern = arg
            else:
                paths.append(arg)
            i += 1

        if not pattern:
            return CommandResult(
                success=False, output="", error="grep: no pattern specified"
            )

        # Compile regex
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return CommandResult(
                success=False, output="", error=f"grep: invalid pattern: {e}"
            )

        # Get content source(s)
        if paths:
            # Process multiple paths
            all_output = []
            total_count = 0
            multiple_files = len(paths) > 1

            for path in paths:
                result = self.cmd_cat([path])
                if not result.success:
                    # For single file, propagate error
                    # For multiple files, skip files that can't be read
                    if not multiple_files:
                        return result
                    continue
                content = result.output

                match_count, file_matches = self._grep_content(
                    content, regex, invert_match, show_line_numbers
                )
                total_count += match_count

                if list_files_only:
                    if match_count > 0:
                        all_output.append(path)
                elif count_only:
                    if multiple_files:
                        all_output.append(f"{path}:{match_count}")
                    else:
                        all_output.append(str(match_count))
                else:
                    if multiple_files:
                        # Prefix each line with filename
                        for line in file_matches:
                            all_output.append(f"{path}:{line}")
                    else:
                        all_output.extend(file_matches)

            output = "\n".join(all_output)
        else:
            # Read from stdin
            content = stdin

            if not content:
                if count_only:
                    return CommandResult(success=True, output="0\n")
                return CommandResult(success=True, output="")

            match_count, matching = self._grep_content(
                content, regex, invert_match, show_line_numbers
            )

            if count_only:
                output = str(match_count)
            elif list_files_only:
                # -l doesn't make sense without files, return empty
                output = ""
            else:
                output = "\n".join(matching)

        if output and not output.endswith("\n"):
            output += "\n"

        return CommandResult(success=True, output=output)

    def _grep_content(
        self,
        content: str,
        regex: re.Pattern,
        invert_match: bool,
        show_line_numbers: bool,
    ) -> tuple:
        """
        Search content for regex matches.

        Args:
            content: Text content to search
            regex: Compiled regex pattern
            invert_match: If True, return non-matching lines
            show_line_numbers: If True, prefix with line numbers

        Returns:
            Tuple of (match_count, list of matching/non-matching lines)
        """
        lines = content.split("\n")
        matching = []
        match_count = 0

        for line_num, line in enumerate(lines, start=1):
            has_match = bool(regex.search(line))

            # Apply inversion if requested
            if invert_match:
                should_include = not has_match
            else:
                should_include = has_match

            if should_include:
                match_count += 1
                if show_line_numbers:
                    matching.append(f"{line_num}:{line}")
                else:
                    matching.append(line)

        return match_count, matching


def register_commands() -> Dict[str, Callable]:
    """
    Register Unix command handlers

    Note: This returns a factory function that creates handlers
    with proper db and navigator instances.

    Returns:
        Dictionary of command handlers
    """
    # This is a placeholder - actual registration will happen
    # when the TUI initializes with a db and navigator instance
    return {}


def create_unix_commands(
    db: ConversationDB, navigator: VFSNavigator, tui_instance=None
) -> Dict[str, Callable]:
    """
    Create Unix command handlers with database and navigator

    Args:
        db: Database instance
        navigator: VFS navigator
        tui_instance: Optional TUI instance for current path state

    Returns:
        Dictionary mapping command names to handlers
    """
    unix = UnixCommands(db, navigator, tui_instance)

    return {
        "cat": unix.cmd_cat,
        "head": unix.cmd_head,
        "tail": unix.cmd_tail,
        "echo": unix.cmd_echo,
        "grep": unix.cmd_grep,
    }
