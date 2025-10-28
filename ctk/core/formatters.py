"""
Output formatters for CTK commands.

Provides abstract interface for formatting command outputs.
Different interfaces (CLI, TUI, REST API) implement their own formatters.

Design:
- Formatters are pure output - they only render, never execute logic
- Each formatter method corresponds to a command output
- Formatters can be stateful (e.g., maintain console instance)
"""

from abc import ABC, abstractmethod
from typing import List, Any, Optional
from datetime import datetime

from ctk.core.models import ConversationTree


class OutputFormatter(ABC):
    """Abstract base class for output formatters"""

    @abstractmethod
    def format_conversation_list(self, conversations: List[Any], title: Optional[str] = None):
        """Format and output a list of conversations"""
        pass

    @abstractmethod
    def format_search_results(self, results: List[Any], query: str):
        """Format and output search results"""
        pass

    @abstractmethod
    def format_conversation_detail(self, tree: ConversationTree):
        """Format and output detailed conversation view"""
        pass

    @abstractmethod
    def format_error(self, message: str):
        """Format and output error message"""
        pass

    @abstractmethod
    def format_success(self, message: str):
        """Format and output success message"""
        pass

    @abstractmethod
    def format_warning(self, message: str):
        """Format and output warning message"""
        pass

    @abstractmethod
    def format_info(self, message: str):
        """Format and output info message"""
        pass

    @abstractmethod
    def confirm(self, message: str) -> bool:
        """Prompt user for confirmation, return True if confirmed"""
        pass


class CLIFormatter(OutputFormatter):
    """
    CLI formatter using simple print statements.

    Designed for command-line interface with table-based output.
    """

    def __init__(self, json_output: bool = False):
        """
        Initialize CLI formatter.

        Args:
            json_output: If True, format output as JSON
        """
        self.json_output = json_output

    def format_conversation_list(self, conversations: List[Any], title: Optional[str] = None):
        """Format conversation list as table or JSON"""
        if not conversations:
            print("No conversations found")
            return

        if self.json_output:
            import json
            conv_dicts = [c.to_dict() if hasattr(c, 'to_dict') else c for c in conversations]
            print(json.dumps(conv_dicts, indent=2, default=str))
        else:
            if title:
                print(f"\n{title}")
            # Table format with flags
            print(f"{'F':<3} {'ID':<40} {'Title':<45} {'Model':<20} {'Updated'}")
            print("-" * 130)
            for conv in conversations:
                conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv

                # Build flags
                flags = ""
                if conv_dict.get('pinned_at'):
                    flags += "📌"
                if conv_dict.get('starred_at'):
                    flags += "⭐"
                if conv_dict.get('archived_at'):
                    flags += "📦"

                title = conv_dict.get('title') or 'Untitled'
                if len(title) > 42:
                    title = title[:42] + '...'
                model = conv_dict.get('model') or 'Unknown'
                if len(model) > 17:
                    model = model[:17] + '...'
                updated = conv_dict.get('updated_at') or 'Unknown'
                if len(updated) > 19:
                    updated = updated[:19]

                print(f"{flags:<3} {conv_dict['id']:<40} {title:<45} {model:<20} {updated}")

    def format_search_results(self, results: List[Any], query: str):
        """Format search results as table or JSON"""
        if not results:
            print(f"No conversations found matching '{query}'")
            return

        if self.json_output:
            import json
            print(json.dumps(results, indent=2, default=str))
        else:
            print(f"Found {len(results)} conversation(s):\n")
            print(f"{'F':<3} {'ID':<40} {'Title':<45} {'Msgs':<6} {'Source':<10} {'Model':<15}")
            print("-" * 130)
            for conv in results:
                conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv

                # Build flags
                flags = ""
                if conv_dict.get('pinned_at'):
                    flags += "📌"
                if conv_dict.get('starred_at'):
                    flags += "⭐"
                if conv_dict.get('archived_at'):
                    flags += "📦"

                title = conv_dict.get('title', 'Untitled')
                if len(title) > 42:
                    title = title[:42] + '...'

                print(f"{flags:<3} {conv_dict['id']:<40} {title:<45} {conv_dict.get('message_count', 0):<6} "
                      f"{conv_dict.get('source', ''):<10} {conv_dict.get('model', '')[:15]:<15}")

    def format_conversation_detail(self, tree: ConversationTree):
        """Format detailed conversation view"""
        print(f"\nConversation: {tree.title}")
        print(f"ID: {tree.id}")
        if tree.metadata:
            print(f"Source: {tree.metadata.source or 'unknown'}")
            print(f"Model: {tree.metadata.model or 'unknown'}")
            if tree.metadata.created_at:
                print(f"Created: {tree.metadata.created_at}")
            if tree.metadata.tags:
                print(f"Tags: {', '.join(tree.metadata.tags)}")
        print(f"Total messages: {len(tree.message_map)}")
        print()

        # Get path to display
        path = tree.get_longest_path()
        if not path:
            print("No messages in conversation")
            return

        print(f"Messages (longest path, {len(path)} messages):")
        print("=" * 80)

        for i, msg in enumerate(path):
            role_name = msg.role.value.upper()
            print(f"\n[{i}] {role_name}")
            print("-" * 80)
            print(msg.content.text or "")

        print("=" * 80)

        # Show tree info if conversation has branches
        if len(tree.message_map) > len(path):
            print(f"\nNote: This conversation has branches ({len(tree.message_map)} total messages)")
            print(f"Use 'ctk tree {tree.id}' to see the full tree structure")

    def format_error(self, message: str):
        """Format error message"""
        print(f"Error: {message}")

    def format_success(self, message: str):
        """Format success message"""
        print(f"✓ {message}")

    def format_warning(self, message: str):
        """Format warning message"""
        print(f"⚠ Warning: {message}")

    def format_info(self, message: str):
        """Format info message"""
        print(f"ℹ {message}")

    def confirm(self, message: str) -> bool:
        """Prompt for confirmation"""
        response = input(f"{message} (yes/no): ").strip().lower()
        return response == 'yes'


class TUIFormatter(OutputFormatter):
    """
    TUI formatter using Rich library for beautiful terminal output.

    Designed for interactive chat interface.
    """

    def __init__(self, console=None):
        """
        Initialize TUI formatter.

        Args:
            console: Rich Console instance (creates new one if None)
        """
        if console:
            self.console = console
        else:
            from rich.console import Console
            self.console = Console()

    def format_conversation_list(self, conversations: List[Any], title: Optional[str] = None):
        """Format conversation list for TUI"""
        if not conversations:
            self.console.print("[yellow]No conversations found in database[/yellow]")
            return

        title_text = title or f"Recent conversations ({len(conversations)})"
        self.console.print(f"\n[bold cyan]{title_text}[/bold cyan]")
        self.console.print("=" * 60)

        for conv in conversations:
            conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv

            conv_id = conv_dict['id']
            title = conv_dict.get('title') or 'Untitled'
            created = conv_dict.get('created_at')

            # Format timestamp
            if isinstance(created, datetime):
                created = created.strftime('%Y-%m-%d %H:%M')
            elif isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created).strftime('%Y-%m-%d %H:%M')
                except:
                    pass

            model = conv_dict.get('model') or 'unknown'
            message_count = conv_dict.get('message_count', 0)

            self.console.print(f"\n  [bold][{conv_id[:8]}...][/bold] {title}")
            self.console.print(f"  Created: {created} | Model: {model} | Messages: {message_count}")

        self.console.print("=" * 60)
        self.console.print("[dim]Use '/load <id>' to continue a conversation[/dim]\n")

    def format_search_results(self, results: List[Any], query: str):
        """Format search results for TUI"""
        if not results:
            self.console.print(f"[yellow]No conversations found matching '{query}'[/yellow]")
            return

        self.console.print(f"\n[bold cyan]Found {len(results)} conversation(s) matching '{query}':[/bold cyan]")
        self.console.print("-" * 60)

        for conv in results:
            conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv

            conv_id = conv_dict['id']
            title = conv_dict.get('title') or 'Untitled'
            created = conv_dict.get('created_at')

            # Format timestamp
            if isinstance(created, datetime):
                created = created.strftime('%Y-%m-%d %H:%M')
            elif isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created).strftime('%Y-%m-%d %H:%M')
                except:
                    pass

            model = conv_dict.get('model') or 'unknown'
            message_count = conv_dict.get('message_count', 0)

            self.console.print(f"\n  [bold]ID:[/bold] {conv_id[:8]}...")
            self.console.print(f"  [bold]Title:[/bold] {title}")
            self.console.print(f"  [bold]Created:[/bold] {created}")
            self.console.print(f"  [bold]Model:[/bold] {model}")
            self.console.print(f"  [bold]Messages:[/bold] {message_count}")

        self.console.print("-" * 60)
        self.console.print("[dim]Use '/load <id>' to load a conversation[/dim]\n")

    def format_conversation_detail(self, tree: ConversationTree):
        """Format detailed conversation view for TUI"""
        self.console.print(f"\n[bold cyan]Conversation:[/bold cyan] {tree.title}")
        self.console.print(f"[dim]ID: {tree.id[:8]}...[/dim]")
        if tree.metadata:
            self.console.print(f"[dim]Source: {tree.metadata.source or 'unknown'}[/dim]")
            self.console.print(f"[dim]Model: {tree.metadata.model or 'unknown'}[/dim]")
        self.console.print(f"[dim]Messages: {len(tree.message_map)}[/dim]\n")

    def format_error(self, message: str):
        """Format error message with Rich"""
        self.console.print(f"[red]✗ Error:[/red] {message}")

    def format_success(self, message: str):
        """Format success message with Rich"""
        self.console.print(f"[green]✓[/green] {message}")

    def format_warning(self, message: str):
        """Format warning message with Rich"""
        self.console.print(f"[yellow]⚠ Warning:[/yellow] {message}")

    def format_info(self, message: str):
        """Format info message with Rich"""
        self.console.print(f"[cyan]ℹ[/cyan] {message}")

    def confirm(self, message: str) -> bool:
        """Prompt for confirmation"""
        response = input(f"{message} (yes/no): ").strip().lower()
        return response == 'yes'


def format_datetime(dt: Any) -> str:
    """Helper to format datetime consistently"""
    if isinstance(dt, datetime):
        return dt.strftime('%Y-%m-%d %H:%M')
    elif isinstance(dt, str):
        try:
            return datetime.fromisoformat(dt).strftime('%Y-%m-%d %H:%M')
        except:
            return dt
    return str(dt) if dt else 'Unknown'
