"""
Rich formatting utilities for CLI and TUI output.
"""

from typing import List, Optional

from rich.console import Console
from rich.table import Table


def format_conversations_table(
    conversations: List, show_message_count: bool = False, console: Optional[Console] = None
) -> None:
    """
    Format conversations as a Rich table.

    Args:
        conversations: List of conversation objects/dicts
        show_message_count: Whether to show message count column
        console: Optional Console instance (creates new one if not provided)
    """
    if console is None:
        console = Console()

    # Create table
    table = Table(
        title=f"[bold cyan]{len(conversations)} conversation(s) found[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", style="cyan", width=10)
    table.add_column("Title", style="white", width=50)
    if show_message_count:
        table.add_column("Msgs", style="blue", width=6)
    else:
        table.add_column("Model", style="blue", width=20)
    table.add_column("Updated", style="green", width=20)
    table.add_column("Tags", style="yellow")

    for i, conv in enumerate(conversations, 1):
        # Get dict representation
        conv_dict = conv.to_dict() if hasattr(conv, "to_dict") else conv

        # Build flags
        flags = ""
        if conv_dict.get("pinned_at"):
            flags += "📌 "
        if conv_dict.get("starred_at"):
            flags += "⭐ "
        if conv_dict.get("archived_at"):
            flags += "📦 "

        title = conv_dict.get("title") or "Untitled"
        if len(title) > 47:
            title = title[:47] + "..."
        title_with_flags = f"{flags}{title}" if flags else title

        updated = conv_dict.get("updated_at") or "Unknown"
        if len(updated) > 19:
            updated = updated[:19]

        # Build tags display
        tags_display = ""
        if conv_dict.get("tags"):
            tags_display = ", ".join(conv_dict["tags"][:3])
            if len(conv_dict["tags"]) > 3:
                tags_display += f" +{len(conv_dict['tags']) - 3}"

        # Build middle column (msgs or model)
        if show_message_count:
            middle_col = str(conv_dict.get("message_count", 0))
        else:
            model = conv_dict.get("model") or "Unknown"
            if len(model) > 17:
                model = model[:17] + "..."
            middle_col = model

        table.add_row(
            str(i),
            conv_dict["id"][:8] + "...",
            title_with_flags,
            middle_col,
            updated,
            tags_display,
        )

    console.print(table)
