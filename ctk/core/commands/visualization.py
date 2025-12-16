"""
Visualization command handlers

Implements: tree, paths, show
"""

from typing import List, Dict, Callable
from ctk.core.command_dispatcher import CommandResult
from ctk.core.vfs_navigator import VFSNavigator
from ctk.core.vfs import VFSPathParser, PathType
from ctk.core.database import ConversationDB


class VisualizationCommands:
    """Handler for visualization commands"""

    def __init__(self, db: ConversationDB, navigator: VFSNavigator, tui_instance=None):
        """
        Initialize visualization command handlers

        Args:
            db: Database instance
            navigator: VFS navigator
            tui_instance: Optional TUI instance for current path state
        """
        self.db = db
        self.navigator = navigator
        self.tui = tui_instance

    def cmd_tree(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Display conversation tree structure

        Usage:
            tree                - Show tree for current conversation
            tree <conv_id>      - Show tree for specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with tree visualization
        """
        # Determine conversation ID
        if args:
            # Explicit conversation ID provided
            conv_id_or_path = args[0]

            # Parse as path
            try:
                if conv_id_or_path.startswith('/'):
                    parsed = VFSPathParser.parse(conv_id_or_path)
                    conv_id = parsed.conversation_id
                else:
                    # Try as direct ID or prefix
                    if self.tui:
                        current_path = self.tui.vfs_cwd
                        parsed_current = VFSPathParser.parse(current_path)
                        # Try prefix resolution in /chats
                        chats_path = VFSPathParser.parse('/chats')
                        try:
                            conv_id = self.navigator.resolve_prefix(conv_id_or_path, chats_path)
                            if not conv_id:
                                conv_id = conv_id_or_path  # Use as-is
                        except ValueError:
                            conv_id = conv_id_or_path
                    else:
                        conv_id = conv_id_or_path
            except Exception as e:
                return CommandResult(success=False, output="", error=f"tree: Invalid path: {e}")
        else:
            # Use current path
            if not self.tui:
                return CommandResult(success=False, output="", error="tree: No conversation in current context")

            current_path = self.tui.vfs_cwd
            parsed = VFSPathParser.parse(current_path)

            if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                conv_id = parsed.conversation_id
            else:
                return CommandResult(success=False, output="", error="tree: Not in a conversation directory")

        # Load conversation
        conversation = self.db.load_conversation(conv_id)
        if not conversation:
            return CommandResult(success=False, output="", error=f"tree: Conversation not found: {conv_id}")

        # Build tree visualization
        output_lines = []
        output_lines.append("\nConversation Tree:")
        output_lines.append("=" * 80)

        # Get all paths
        paths = conversation.get_all_paths()

        if not paths:
            output_lines.append("(empty conversation)")
        else:
            # Show tree structure
            output_lines.append(self._format_tree(conversation))

        output_lines.append("=" * 80)
        output_lines.append(f"\nTotal messages: {len(conversation.message_map)}")
        output_lines.append(f"Total paths: {len(paths)}")
        output_lines.append(f"Title: {conversation.title or '(untitled)'}")

        output = '\n'.join(output_lines) + '\n'
        return CommandResult(success=True, output=output)

    def _format_tree(self, conversation) -> str:
        """Format conversation tree as text"""
        output_lines = []

        def print_tree_node(message_ids: List[str], prefix: str = "", is_last: bool = True, visited=None):
            """Recursively print tree structure"""
            if visited is None:
                visited = set()

            for i, msg_id in enumerate(message_ids):
                if msg_id in visited:
                    continue
                visited.add(msg_id)

                message = conversation.message_map.get(msg_id)
                if not message:
                    continue

                # Determine connector
                is_last_item = (i == len(message_ids) - 1)
                connector = "└─" if is_last_item else "├─"

                # Show message info
                role_emoji = {"system": "⚙", "user": "U", "assistant": "A", "tool": "T"}
                emoji = role_emoji.get(message.role.value if message.role else "user", "?")

                # Content preview
                content_text = message.content.get_text() if hasattr(message.content, 'get_text') else str(message.content.text if hasattr(message.content, 'text') else message.content)
                content_preview = content_text[:40].replace('\n', ' ').strip() if content_text else ""
                if len(content_text) > 40:
                    content_preview += "..."

                # Format line
                output_lines.append(f"{prefix}{connector}{emoji} {msg_id[:8]} {content_preview}")

                # Print children
                children = conversation.get_children(msg_id)
                if children:
                    # Update prefix for children
                    extension = "  " if is_last_item else "│ "
                    new_prefix = prefix + extension
                    child_ids = [child.id for child in children]
                    print_tree_node(child_ids, new_prefix, True, visited)

        # Start with root messages
        print_tree_node(conversation.root_message_ids)

        return '\n'.join(output_lines)

    def cmd_paths(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        List all paths in conversation tree

        Usage:
            paths               - Show all paths in current conversation
            paths <conv_id>     - Show all paths in specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with path listing
        """
        # Use same conversation resolution logic as tree
        if args:
            conv_id_or_path = args[0]
            try:
                if conv_id_or_path.startswith('/'):
                    parsed = VFSPathParser.parse(conv_id_or_path)
                    conv_id = parsed.conversation_id
                else:
                    if self.tui:
                        chats_path = VFSPathParser.parse('/chats')
                        try:
                            conv_id = self.navigator.resolve_prefix(conv_id_or_path, chats_path)
                            if not conv_id:
                                conv_id = conv_id_or_path
                        except ValueError:
                            conv_id = conv_id_or_path
                    else:
                        conv_id = conv_id_or_path
            except Exception as e:
                return CommandResult(success=False, output="", error=f"paths: Invalid path: {e}")
        else:
            if not self.tui:
                return CommandResult(success=False, output="", error="paths: No conversation in current context")

            current_path = self.tui.vfs_cwd
            parsed = VFSPathParser.parse(current_path)

            if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                conv_id = parsed.conversation_id
            else:
                return CommandResult(success=False, output="", error="paths: Not in a conversation directory")

        # Load conversation
        conversation = self.db.load_conversation(conv_id)
        if not conversation:
            return CommandResult(success=False, output="", error=f"paths: Conversation not found: {conv_id}")

        # Get all paths
        paths = conversation.get_all_paths()

        output_lines = []
        output_lines.append(f"\nAll paths in conversation ({len(paths)} total):")
        output_lines.append("=" * 80)

        for i, path in enumerate(paths, 1):
            output_lines.append(f"\nPath {i} ({len(path)} messages):")
            for msg in path:
                role_label = msg.role.value.title() if msg.role else "User"
                content_text = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content.text if hasattr(msg.content, 'text') else msg.content)
                preview = content_text[:50].replace('\n', ' ').strip() if content_text else ""
                if len(content_text) > 50:
                    preview += "..."
                output_lines.append(f"  {role_label}: {preview}")

        output_lines.append("=" * 80)

        output = '\n'.join(output_lines) + '\n'
        return CommandResult(success=True, output=output)

    def cmd_show(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Show conversation content

        Usage:
            show <conv_id>          - Show conversation by ID (prefix allowed)
            show <conv_id> --path N - Show specific path (0-indexed)
            show <conv_id> -l       - Show longest path (default)
            show <conv_id> -L       - Show latest path

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with conversation display
        """
        from ctk.core.helpers import show_conversation_helper

        # Determine conversation ID
        if not args:
            # Try current conversation
            if not self.tui:
                return CommandResult(success=False, output="", error="show: Conversation ID required")

            current_path = self.tui.vfs_cwd
            parsed = VFSPathParser.parse(current_path)

            if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                conv_id = parsed.conversation_id
            else:
                return CommandResult(success=False, output="", error="show: Not in a conversation. Usage: show <conv_id>")
            path_selection = 'longest'
        else:
            # Parse arguments
            conv_id_arg = None
            path_selection = 'longest'

            i = 0
            while i < len(args):
                arg = args[i]
                if arg == '--path' and i + 1 < len(args):
                    path_selection = args[i + 1]
                    i += 2
                elif arg == '-l':
                    path_selection = 'longest'
                    i += 1
                elif arg == '-L':
                    path_selection = 'latest'
                    i += 1
                elif arg.startswith('-'):
                    return CommandResult(success=False, output="", error=f"show: Unknown option: {arg}")
                else:
                    if conv_id_arg is None:
                        conv_id_arg = arg
                    i += 1

            if not conv_id_arg:
                return CommandResult(success=False, output="", error="show: Conversation ID required")

            # Resolve conversation ID (with prefix support via VFS)
            conv_id_or_path = conv_id_arg

            try:
                if conv_id_or_path.startswith('/'):
                    parsed = VFSPathParser.parse(conv_id_or_path)
                    conv_id = parsed.conversation_id
                else:
                    # Try prefix resolution
                    chats_path = VFSPathParser.parse('/chats')
                    try:
                        resolved = self.navigator.resolve_prefix(conv_id_or_path, chats_path)
                        conv_id = resolved if resolved else conv_id_or_path
                    except ValueError:
                        conv_id = conv_id_or_path
            except Exception as e:
                return CommandResult(success=False, output="", error=f"show: Invalid path: {e}")

        # Use shared helper
        result = show_conversation_helper(
            db=self.db,
            conv_id=conv_id,
            path_selection=path_selection,
            plain_output=True,
            show_metadata=True
        )

        if not result['success']:
            return CommandResult(success=False, output="", error=f"show: {result['error']}")

        # Use Rich formatting if we have a TUI with console
        conversation = result['conversation']
        nav = result['navigator']
        path = result['path']
        path_count = result['path_count']

        if self.tui and hasattr(self.tui, 'console'):
            from io import StringIO
            from rich.console import Console

            # Create a string buffer to capture Rich output
            string_io = StringIO()
            console = Console(file=string_io, force_terminal=True)

            # Metadata header
            console.print(f"\n[bold]Conversation:[/bold] {conversation.title or '(untitled)'}")
            console.print(f"[dim]ID:[/dim] {conversation.id}")
            if conversation.metadata:
                if conversation.metadata.source:
                    console.print(f"[dim]Source:[/dim] {conversation.metadata.source}")
                if conversation.metadata.model:
                    console.print(f"[dim]Model:[/dim] {conversation.metadata.model}")
                if conversation.metadata.created_at:
                    console.print(f"[dim]Created:[/dim] {conversation.metadata.created_at}")
                if conversation.metadata.tags:
                    console.print(f"[dim]Tags:[/dim] {', '.join(conversation.metadata.tags)}")
            console.print(f"[dim]Total messages:[/dim] {len(conversation.message_map)}")
            console.print(f"[dim]Paths:[/dim] {path_count}")
            console.print()

            if not path:
                console.print("[italic](no messages)[/italic]")
            else:
                console.print(f"[bold]Messages (path: {path_selection}, {len(path)} messages):[/bold]")
                console.print("=" * 80)

                for msg in path:
                    role_label = msg.role.value.title() if msg.role else "User"
                    role_color = {"User": "cyan", "Assistant": "magenta", "System": "yellow", "Tool": "green"}.get(role_label, "white")
                    content_text = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)
                    console.print(f"\n[bold {role_color}][{role_label}][/bold {role_color}]")
                    console.print(content_text)

                console.print("=" * 80)

            if path_count > 1:
                console.print(f"\n[italic]Note: This conversation has {path_count} paths[/italic]")
                console.print("[dim]Use 'show <id> --path N' or '-L' for latest path[/dim]")

            return CommandResult(success=True, output=string_io.getvalue())
        else:
            # Plain text output
            return CommandResult(success=True, output=result['output'])

    def cmd_help(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Show help for shell commands

        Usage:
            help              - Show all available commands
            help <command>    - Show help for specific command

        Args:
            args: Command arguments (optional command name)
            stdin: Standard input (ignored)

        Returns:
            CommandResult with help text
        """
        help_text = """
CTK Shell Commands
==================

Navigation:
  cd [path]         - Change directory (supports prefixes like cd abc12)
  ls [-l] [path]    - List directory contents (-l for long format)
  pwd               - Print working directory

Search:
  find [path] [options]  - Find conversations
    -name "pattern"      - Match title (wildcards: * ?)
    -content "text"      - Match message content
    -role <role>         - Filter by role (user/assistant/system)
    -type <type>         - Filter by type (conversation/message/etc)
    -i                   - Case insensitive
    -limit N             - Max results
    -l                   - Long format (shows table with metadata)

View:
  show <id>         - Show conversation content (supports prefix)
  show <id> -L      - Show latest path
  show <id> --path N - Show specific path number
  tree [id]         - Show conversation tree structure
  paths [id]        - List all paths in conversation
  cat <file>        - View content (when in message node: cat text)

Organization:
  star [id]         - Star conversation (current if no ID)
  unstar [id]       - Remove star
  pin [id]          - Pin conversation
  unpin [id]        - Remove pin
  archive [id]      - Archive conversation
  unarchive [id]    - Unarchive
  title "new title" - Rename conversation

Chat:
  say <message>     - Send message to LLM (one-shot)
  chat [message]    - Enter chat mode (optionally with first message)

Network:
  net embeddings    - Generate conversation embeddings
  net similar [id]  - Find similar conversations (uses current if no ID)
  net links         - Build similarity graph
  net network       - Show network statistics

System:
  help              - Show this help
  exit              - Exit shell (returns to previous mode)

Virtual Filesystem Structure:
  /                 - Root
  /chats/           - All conversations
  /starred/         - Starred conversations
  /pinned/          - Pinned conversations
  /archived/        - Archived conversations
  /tags/<tag>/      - Conversations with tag
  /source/<src>/    - Conversations by source
  /model/<model>/   - Conversations by model
  /recent/          - Recently updated

Examples:
  find -content "python" -l       Find conversations mentioning python
  show abc12                      Show conversation starting with abc12
  cd /starred && ls               List starred conversations
  tree                            Show current conversation structure
"""
        return CommandResult(success=True, output=help_text)


def create_visualization_commands(db: ConversationDB, navigator: VFSNavigator, tui_instance=None) -> Dict[str, Callable]:
    """
    Create visualization command handlers

    Args:
        db: Database instance
        navigator: VFS navigator
        tui_instance: Optional TUI instance for current path state

    Returns:
        Dictionary mapping command names to handlers
    """
    viz = VisualizationCommands(db, navigator, tui_instance)

    return {
        'tree': viz.cmd_tree,
        'paths': viz.cmd_paths,
        'show': viz.cmd_show,
        'help': viz.cmd_help,
    }
