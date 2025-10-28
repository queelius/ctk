"""
Unix-like command handlers

Implements: cat, head, tail, echo, grep
"""

import re
from typing import List, Dict, Callable, Optional
from ctk.core.command_dispatcher import CommandResult
from ctk.core.vfs_navigator import VFSNavigator
from ctk.core.vfs import PathType
from ctk.core.database import ConversationDB


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

    def cmd_cat(self, args: List[str], stdin: str = '') -> CommandResult:
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

                if path_arg == '.':
                    # Current location
                    current_path = current_vfs_path
                else:
                    # Resolve path relative to current location
                    if not path_arg.startswith('/'):
                        # Relative path - combine with current
                        if current_vfs_path.endswith('/'):
                            full_path = current_vfs_path + path_arg
                        else:
                            full_path = current_vfs_path + '/' + path_arg
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
                        return CommandResult(success=False, output="", error=f"cat: {path_arg}: Conversation not found")

                    # Navigate to the message
                    current_message_id = None
                    for node_name in message_path:
                        # Extract index from node name (m1 -> 1, m2 -> 2)
                        if not node_name.lower().startswith('m'):
                            return CommandResult(success=False, output="", error=f"cat: {path_arg}: Invalid message node: {node_name}")

                        try:
                            node_index = int(node_name[1:])  # Remove 'm' prefix
                        except ValueError:
                            return CommandResult(success=False, output="", error=f"cat: {path_arg}: Invalid message node: {node_name}")

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
                            return CommandResult(success=False, output="", error=f"cat: {path_arg}: Message node {node_name} out of range")

                        current_message_id = available_ids[node_index - 1]

                    # Get the message
                    message = conversation.message_map.get(current_message_id)
                    if not message:
                        return CommandResult(success=False, output="", error=f"cat: {path_arg}: Message not found")

                    # Get the requested metadata
                    if file_name == 'text':
                        content_text = message.content.get_text() if hasattr(message.content, 'get_text') else str(message.content.text if hasattr(message.content, 'text') else message.content)
                        # Show helpful message if text is empty
                        if not content_text or content_text.strip() == '':
                            output_lines.append("[empty]")
                        else:
                            output_lines.append(content_text)
                    elif file_name == 'role':
                        output_lines.append(message.role.value if message.role else "user")
                    elif file_name == 'timestamp':
                        output_lines.append(str(message.timestamp) if message.timestamp else "")
                    elif file_name == 'id':
                        output_lines.append(current_message_id)
                    else:
                        return CommandResult(success=False, output="", error=f"cat: {path_arg}: Unknown metadata file: {file_name}")

                elif path_type == PathType.MESSAGE_NODE:
                    # Display message content
                    # Parse the path to get conversation ID and message path
                    parsed = VFSPathParser.parse(current_path)
                    conv_id = parsed.conversation_id
                    message_path = parsed.message_path

                    # Load conversation
                    conversation = self.db.load_conversation(conv_id)
                    if not conversation:
                        return CommandResult(success=False, output="", error=f"cat: {path_arg}: Conversation not found")

                    # Navigate to the message
                    current_message_id = None
                    for node_name in message_path:
                        # Extract index from node name (m1 -> 1, m2 -> 2)
                        if not node_name.lower().startswith('m'):
                            return CommandResult(success=False, output="", error=f"cat: {path_arg}: Invalid message node: {node_name}")

                        try:
                            node_index = int(node_name[1:])  # Remove 'm' prefix
                        except ValueError:
                            return CommandResult(success=False, output="", error=f"cat: {path_arg}: Invalid message node: {node_name}")

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
                            return CommandResult(success=False, output="", error=f"cat: {path_arg}: Message node {node_name} out of range")

                        current_message_id = available_ids[node_index - 1]

                    # Get the message from the message_map
                    message = conversation.message_map.get(current_message_id)

                    if message:
                        # Format message content
                        role_label = message.role.value.title()
                        content_text = message.content.get_text() if hasattr(message.content, 'get_text') else str(message.content.text if hasattr(message.content, 'text') else message.content)
                        output_lines.append(f"{role_label}: {content_text}")
                    else:
                        return CommandResult(success=False, output="", error=f"cat: {path_arg}: Message not found")

                elif path_type == PathType.CONVERSATION:
                    # Display all messages in conversation
                    # Get conversation
                    parsed = VFSPathParser.parse(current_path)
                    conv_id = parsed.conversation_id
                    conversation = self.db.load_conversation(conv_id)

                    if not conversation:
                        return CommandResult(success=False, output="", error=f"cat: {path_arg}: Conversation not found")

                    # Display all messages on the longest path
                    path = conversation.get_longest_path()
                    for msg in path:
                        role_label = msg.role.value.title()
                        output_lines.append(f"{role_label}: {msg.content.text}")
                        output_lines.append("")  # Blank line between messages

                else:
                    return CommandResult(success=False, output="", error=f"cat: {path_arg}: Not a message or conversation")

            except Exception as e:
                return CommandResult(success=False, output="", error=f"cat: {path_arg}: {str(e)}")

        output = '\n'.join(output_lines) + '\n' if output_lines else ''
        return CommandResult(success=True, output=output)

    def cmd_head(self, args: List[str], stdin: str = '') -> CommandResult:
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
            return CommandResult(success=True, output='')

        # Take first n lines
        lines = content.split('\n')
        output = '\n'.join(lines[:n])
        if output and not output.endswith('\n'):
            output += '\n'

        return CommandResult(success=True, output=output)

    def cmd_tail(self, args: List[str], stdin: str = '') -> CommandResult:
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
            return CommandResult(success=True, output='')

        # Take last n lines
        lines = content.split('\n')
        # Remove trailing empty line if present
        if lines and not lines[-1]:
            lines = lines[:-1]

        output = '\n'.join(lines[-n:])
        if output and not output.endswith('\n'):
            output += '\n'

        return CommandResult(success=True, output=output)

    def cmd_echo(self, args: List[str], stdin: str = '') -> CommandResult:
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
        output = ' '.join(args) + '\n' if args else '\n'
        return CommandResult(success=True, output=output)

    def cmd_grep(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Search for pattern in input

        Usage:
            grep <pattern>          - Search stdin for pattern
            grep <pattern> <path>   - Search file for pattern
            cat m1 | grep "error"   - Search message for "error"

        Options:
            -i  Case insensitive search
            -n  Show line numbers

        Args:
            args: Command arguments
            stdin: Standard input

        Returns:
            CommandResult with matching lines
        """
        if not args:
            return CommandResult(success=False, output="", error="grep: no pattern specified")

        # Parse options
        case_insensitive = False
        show_line_numbers = False
        pattern = None
        path = None

        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith('-'):
                if 'i' in arg:
                    case_insensitive = True
                if 'n' in arg:
                    show_line_numbers = True
            elif pattern is None:
                pattern = arg
            else:
                path = arg
            i += 1

        if not pattern:
            return CommandResult(success=False, output="", error="grep: no pattern specified")

        # Get content
        if path:
            # Read from path
            result = self.cmd_cat([path])
            if not result.success:
                return result
            content = result.output
        else:
            # Read from stdin
            content = stdin

        if not content:
            return CommandResult(success=True, output='')

        # Search for pattern
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return CommandResult(success=False, output="", error=f"grep: invalid pattern: {e}")

        lines = content.split('\n')
        matching = []

        for line_num, line in enumerate(lines, start=1):
            if regex.search(line):
                if show_line_numbers:
                    matching.append(f"{line_num}:{line}")
                else:
                    matching.append(line)

        output = '\n'.join(matching)
        if output and not output.endswith('\n'):
            output += '\n'

        return CommandResult(success=True, output=output)


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


def create_unix_commands(db: ConversationDB, navigator: VFSNavigator, tui_instance=None) -> Dict[str, Callable]:
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
        'cat': unix.cmd_cat,
        'head': unix.cmd_head,
        'tail': unix.cmd_tail,
        'echo': unix.cmd_echo,
        'grep': unix.cmd_grep,
    }
