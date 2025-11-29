"""
Tree structure for conversations with branching support.

This module provides a lightweight in-memory tree representation
that's more convenient for navigation and display than the database
ConversationTree model.
"""

import uuid
from typing import List, Optional, Tuple, Any
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text

from .models import (
    ConversationTree,
    Message as DBMessage,
    MessageRole as DBMessageRole,
    MessageContent,
)


class TreeMessage:
    """
    Message node in conversation tree.

    Each message can have multiple children (branches).
    This is a lightweight structure for in-memory navigation.

    Note: role can be any enum-like object with a .value attribute.
    """
    def __init__(self, role: Any, content: str, parent: Optional['TreeMessage'] = None,
                 model: Optional[str] = None, user: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.role = role  # Can be DBMessageRole or LLMMessageRole
        self.content = content
        self.parent = parent
        self.children: List['TreeMessage'] = []
        self.timestamp = datetime.now()
        self.metadata: dict = {}

        # Track who/what created this message
        self.model = model  # Model that generated this (for assistant messages)
        self.user = user  # User who sent this (for user messages)

        # Add this message as child of parent
        if parent:
            parent.children.append(self)

    def get_path_to_root(self) -> List['TreeMessage']:
        """Get path from root to this message"""
        path = []
        current = self
        while current:
            path.append(current)
            current = current.parent
        return list(reversed(path))

    def get_depth(self) -> int:
        """Get depth in tree (root is 0)"""
        depth = 0
        current = self.parent
        while current:
            depth += 1
            current = current.parent
        return depth

    def is_leaf(self) -> bool:
        """Check if this is a leaf node (no children)"""
        return len(self.children) == 0

    def __repr__(self):
        return f"TreeMessage(id={self.id[:8]}..., role={self.role.value}, children={len(self.children)})"

    def format_tree(self, prefix="", is_last=True, max_content_length=30) -> str:
        """
        Format this message and its children as a tree structure.

        Args:
            prefix: Current line prefix for indentation
            is_last: Whether this is the last child of its parent
            max_content_length: Maximum characters to show from content

        Returns:
            String representation of tree
        """
        lines = []

        # Current message line
        connector = "└─" if is_last else "├─"
        role = self.role.value[0].upper()  # U, A, S, etc.
        content = self.content[:max_content_length].replace('\n', ' ') if self.content else ""
        if len(self.content) > max_content_length:
            content += "..."

        lines.append(f"{prefix}{connector}{role} {self.id[:6]} {content}")

        # Children
        if self.children:
            extension = "  " if is_last else "│ "
            new_prefix = prefix + extension
            for i, child in enumerate(self.children):
                is_last_child = (i == len(self.children) - 1)
                lines.append(child.format_tree(new_prefix, is_last_child, max_content_length))

        return '\n'.join(lines)

    def format_message(self, index: Optional[int] = None, show_metadata=False) -> str:
        """
        Format a single message for display.

        Args:
            index: Optional message index/number to display
            show_metadata: Whether to show model/user metadata

        Returns:
            Formatted message string
        """
        lines = []

        # Header
        role_name = self.role.value.upper()
        if index is not None:
            lines.append(f"[{index}] {role_name}")
        else:
            lines.append(role_name)

        # Metadata
        if show_metadata and (self.model or self.user):
            meta_parts = []
            if self.model:
                meta_parts.append(f"model: {self.model}")
            if self.user:
                meta_parts.append(f"user: {self.user}")
            lines.append(f"  ({', '.join(meta_parts)})")

        lines.append("-" * 80)
        lines.append(self.content)

        return '\n'.join(lines)

    def print_message(self, console: Console, index: Optional[int] = None,
                     show_metadata=False, render_markdown=True):
        """
        Pretty-print a single message using Rich.

        Args:
            console: Rich Console instance
            index: Optional message index/number to display
            show_metadata: Whether to show model/user metadata
            render_markdown: Whether to render markdown content
        """
        # Determine role color and icon
        if self.role.value.lower() == 'user':
            role_color = "green"
            role_icon = "👤"
        elif self.role.value.lower() == 'assistant':
            role_color = "magenta"
            role_icon = "🤖"
        elif self.role.value.lower() == 'system':
            role_color = "yellow"
            role_icon = "⚙️"
        else:
            role_color = "white"
            role_icon = "💬"

        # Build header
        header_text = Text()
        if index is not None:
            header_text.append(f"[{index}] ", style="dim")
        header_text.append(f"{role_icon} {self.role.value.upper()}", style=f"bold {role_color}")

        # Add metadata
        if show_metadata and (self.model or self.user):
            meta_parts = []
            if self.model:
                meta_parts.append(f"model: {self.model}")
            if self.user:
                meta_parts.append(f"user: {self.user}")
            header_text.append(f" ({', '.join(meta_parts)})", style="dim")

        console.print(header_text)
        console.print("─" * console.width, style="dim")

        # Content
        if render_markdown and self.content.strip():
            try:
                # Try to detect code blocks and render appropriately
                if "```" in self.content:
                    console.print(Markdown(self.content))
                else:
                    # Just regular text, print as-is for better formatting
                    console.print(self.content)
            except Exception:
                # Fallback to plain text
                console.print(self.content)
        else:
            console.print(self.content)

        console.print()


class ConversationTreeNavigator:
    """
    Navigator for conversation trees with path selection and display utilities.

    Converts database ConversationTree into TreeMessage structure for easier navigation.
    """

    def __init__(self, conversation: ConversationTree):
        """
        Initialize navigator from a database ConversationTree.

        Args:
            conversation: ConversationTree from database
        """
        self.conversation = conversation
        self.root: Optional[TreeMessage] = None
        self.message_map: dict[str, TreeMessage] = {}

        # Build tree structure
        self._build_tree()

    def _build_tree(self):
        """Build TreeMessage structure from ConversationTree"""
        # First pass: create all TreeMessage objects without parents
        for db_msg in self.conversation.message_map.values():
            # Extract metadata
            model = None
            user = None
            if db_msg.metadata:
                model = db_msg.metadata.get('model')
                user = db_msg.metadata.get('user')

            tree_msg = TreeMessage(
                role=db_msg.role,
                content=db_msg.content.text or "",
                parent=None,  # Will link in second pass
                model=model,
                user=user
            )
            tree_msg.id = db_msg.id  # Preserve original ID
            tree_msg.timestamp = db_msg.timestamp or datetime.now()
            tree_msg._parent_id = db_msg.parent_id  # Store for second pass

            self.message_map[tree_msg.id] = tree_msg

        # Second pass: link parents and children
        for tree_msg in self.message_map.values():
            parent_id = getattr(tree_msg, '_parent_id', None)
            if parent_id:
                parent = self.message_map.get(parent_id)
                if parent:
                    tree_msg.parent = parent
                    parent.children.append(tree_msg)

            # Set root (message with no parent)
            if not tree_msg.parent:
                self.root = tree_msg

            # Clean up temporary attribute
            if hasattr(tree_msg, '_parent_id'):
                delattr(tree_msg, '_parent_id')

    def get_all_paths(self) -> List[List[TreeMessage]]:
        """Get all paths from root to leaves"""
        if not self.root:
            return []

        def get_paths_from_node(node: TreeMessage) -> List[List[TreeMessage]]:
            if node.is_leaf():
                return [[node]]

            all_paths = []
            for child in node.children:
                child_paths = get_paths_from_node(child)
                for path in child_paths:
                    all_paths.append([node] + path)

            return all_paths

        return get_paths_from_node(self.root)

    def get_longest_path(self) -> List[TreeMessage]:
        """Get the longest path (most messages)"""
        paths = self.get_all_paths()
        if not paths:
            return []
        return max(paths, key=len)

    def get_latest_path(self) -> List[TreeMessage]:
        """Get path to most recently updated leaf"""
        if not self.root:
            return []

        # Find all leaf nodes
        leaves = [msg for msg in self.message_map.values() if msg.is_leaf()]

        if not leaves:
            return []

        # Find most recent leaf
        latest_leaf = max(leaves, key=lambda msg: msg.timestamp)
        return latest_leaf.get_path_to_root()

    def get_path(self, path_number: int) -> Optional[List[TreeMessage]]:
        """
        Get a specific path by number (0-indexed).

        Args:
            path_number: Index of path to retrieve

        Returns:
            List of messages in path, or None if invalid index
        """
        paths = self.get_all_paths()
        if 0 <= path_number < len(paths):
            return paths[path_number]
        return None

    def get_path_count(self) -> int:
        """Get total number of paths"""
        return len(self.get_all_paths())

    def get_all_leaves(self) -> List[TreeMessage]:
        """Get all leaf nodes"""
        return [msg for msg in self.message_map.values() if msg.is_leaf()]

    def has_branches(self) -> bool:
        """Check if conversation has any branches"""
        return any(len(msg.children) > 1 for msg in self.message_map.values())

    def format_path_summary(self) -> str:
        """Get summary of all paths for display"""
        paths = self.get_all_paths()

        if not paths:
            return "No paths found"

        lines = [f"Total paths: {len(paths)}\n"]

        for i, path in enumerate(paths):
            lines.append(f"Path {i}: {len(path)} messages")
            # Show last message preview
            if path:
                last_msg = path[-1]
                preview = last_msg.content[:50].replace('\n', ' ')
                if len(last_msg.content) > 50:
                    preview += "..."
                lines.append(f"  └─ {last_msg.role.value}: {preview}")

        return '\n'.join(lines)

    def format_path(self, path: List[TreeMessage], show_metadata=False) -> str:
        """
        Format a path (list of messages) for display.

        Args:
            path: List of TreeMessage objects
            show_metadata: Whether to show model/user metadata

        Returns:
            Formatted string with all messages
        """
        lines = ["=" * 80]

        for i, msg in enumerate(path):
            lines.append("")
            lines.append(msg.format_message(index=i, show_metadata=show_metadata))

        lines.append("")
        lines.append("=" * 80)

        return '\n'.join(lines)

    def format_tree(self, max_content_length=30) -> str:
        """
        Format entire conversation tree for display.

        Args:
            max_content_length: Maximum characters to show from message content

        Returns:
            Tree structure as string
        """
        if not self.root:
            return "No messages"

        lines = ["=" * 80]
        lines.append(self.root.format_tree(max_content_length=max_content_length))
        lines.append("=" * 80)
        lines.append("\nLegend: U=user, A=assistant, S=system")

        return '\n'.join(lines)

    def print_tree(self, console: Optional[Console] = None, max_content_length=30):
        """
        Pretty-print conversation tree structure using Rich.

        Args:
            console: Rich Console instance (creates new if None)
            max_content_length: Maximum characters to show from message content
        """
        if console is None:
            console = Console()

        if not self.root:
            console.print("[yellow]No messages[/yellow]")
            return

        # Print tree with color
        console.print("═" * console.width, style="cyan")

        def print_tree_node(msg: TreeMessage, prefix="", is_last=True):
            connector = "└─" if is_last else "├─"

            # Color based on role
            if msg.role.value.lower() == 'user':
                role_style = "bold green"
            elif msg.role.value.lower() == 'assistant':
                role_style = "bold magenta"
            elif msg.role.value.lower() == 'system':
                role_style = "bold yellow"
            else:
                role_style = "bold white"

            role = msg.role.value[0].upper()
            content = msg.content[:max_content_length].replace('\n', ' ') if msg.content else ""
            if len(msg.content) > max_content_length:
                content += "..."

            # Build line
            line = Text()
            line.append(prefix, style="dim")
            line.append(connector, style="cyan")
            line.append(f"{role} ", style=role_style)
            line.append(msg.id[:6], style="dim cyan")
            line.append(" ")
            line.append(content, style="dim")

            console.print(line)

            # Children
            if msg.children:
                extension = "  " if is_last else "│ "
                new_prefix = prefix + extension
                for i, child in enumerate(msg.children):
                    is_last_child = (i == len(msg.children) - 1)
                    print_tree_node(child, new_prefix, is_last_child)

        print_tree_node(self.root)
        console.print("═" * console.width, style="cyan")
        console.print("\n[dim]Legend: U=user, A=assistant, S=system[/dim]")

    def print_path(self, path: List[TreeMessage], console: Optional[Console] = None,
                  show_metadata=False, render_markdown=True):
        """
        Pretty-print a path (list of messages) using Rich.

        Args:
            path: List of TreeMessage objects
            console: Rich Console instance (creates new if None)
            show_metadata: Whether to show model/user metadata
            render_markdown: Whether to render markdown content
        """
        if console is None:
            console = Console()

        console.print("═" * console.width, style="cyan")

        for i, msg in enumerate(path):
            msg.print_message(console, index=i, show_metadata=show_metadata,
                            render_markdown=render_markdown)

        console.print("═" * console.width, style="cyan")

    def print_path_summary(self, console: Optional[Console] = None):
        """
        Pretty-print summary of all paths using Rich.

        Args:
            console: Rich Console instance (creates new if None)
        """
        if console is None:
            console = Console()

        paths = self.get_all_paths()

        if not paths:
            console.print("[yellow]No paths found[/yellow]")
            return

        console.print(f"\n[bold cyan]Total paths: {len(paths)}[/bold cyan]\n")

        for i, path in enumerate(paths):
            # Path header
            path_text = Text()
            path_text.append(f"Path {i}: ", style="bold")
            path_text.append(f"{len(path)} messages", style="cyan")
            console.print(path_text)

            # Show last message preview
            if path:
                last_msg = path[-1]
                preview = last_msg.content[:50].replace('\n', ' ')
                if len(last_msg.content) > 50:
                    preview += "..."

                # Color based on role
                if last_msg.role.value.lower() == 'user':
                    role_style = "green"
                elif last_msg.role.value.lower() == 'assistant':
                    role_style = "magenta"
                else:
                    role_style = "yellow"

                preview_text = Text()
                preview_text.append("  └─ ", style="dim")
                preview_text.append(f"{last_msg.role.value}: ", style=role_style)
                preview_text.append(preview, style="dim")
                console.print(preview_text)

    def to_conversation_tree(self) -> ConversationTree:
        """Convert back to database ConversationTree format"""
        tree = ConversationTree(
            id=self.conversation.id,
            title=self.conversation.title,
            metadata=self.conversation.metadata
        )

        # Convert all TreeMessages to DBMessages recursively
        def convert_node(tree_msg: TreeMessage, parent_id: Optional[str] = None):
            db_msg = DBMessage(
                id=tree_msg.id,
                role=tree_msg.role,
                content=MessageContent(text=tree_msg.content),
                timestamp=tree_msg.timestamp,
                parent_id=parent_id,
                metadata={'model': tree_msg.model, 'user': tree_msg.user} if (tree_msg.model or tree_msg.user) else None
            )
            tree.add_message(db_msg)

            # Recursively convert children
            for child in tree_msg.children:
                convert_node(child, tree_msg.id)

        if self.root:
            convert_node(self.root)

        return tree
