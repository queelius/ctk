"""
Visualization command handlers

Implements: tree, paths
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
    }
