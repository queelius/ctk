"""
Conversation display helpers for CLI and TUI.

Provides formatted output for viewing conversation content.
"""

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from .database import ConversationDB


def show_conversation_helper(
    db: "ConversationDB",
    conv_id: str,
    path_selection: str = "longest",
    plain_output: bool = True,
    show_metadata: bool = True,
    render_markdown: bool = False,
) -> Dict[str, Any]:
    """
    Load and format a conversation for display.

    This is a shared helper used by both CLI `ctk show` and shell `show` commands.

    Args:
        db: Database instance
        conv_id: Conversation ID or prefix
        path_selection: 'longest', 'latest', or path number as string
        plain_output: If True, return plain text; if False, return Rich-formatted
        show_metadata: Include metadata in output
        render_markdown: Render markdown in messages (for Rich output)

    Returns:
        Dict with keys:
            'success': bool
            'conversation': ConversationTree if found
            'output': formatted string output
            'error': error message if failed
    """
    from ctk.core.tree import ConversationTreeNavigator

    # Load conversation (with prefix matching)
    conversation = db.load_conversation(conv_id)

    if not conversation:
        # Try partial ID match
        all_convs = db.list_conversations(limit=None, include_archived=True)
        matches = [c for c in all_convs if c.id.startswith(conv_id)]

        if len(matches) == 0:
            return {
                "success": False,
                "conversation": None,
                "output": "",
                "error": f"No conversation found matching '{conv_id}'",
            }
        elif len(matches) > 1:
            match_list = "\n".join(f"  {m.id[:12]}... {m.title}" for m in matches[:5])
            return {
                "success": False,
                "conversation": None,
                "output": "",
                "error": f"Multiple conversations match '{conv_id}':\n{match_list}",
            }
        else:
            conversation = db.load_conversation(matches[0].id)

    if not conversation:
        return {
            "success": False,
            "conversation": None,
            "output": "",
            "error": f"Failed to load conversation: {conv_id}",
        }

    # Create navigator
    nav = ConversationTreeNavigator(conversation)
    path_count = nav.get_path_count()

    # Select path
    if path_selection == "longest":
        path = nav.get_longest_path()
    elif path_selection == "latest":
        path = nav.get_latest_path()
    elif path_selection.isdigit():
        path_num = int(path_selection)
        path = nav.get_path(path_num)
        if not path:
            return {
                "success": False,
                "conversation": conversation,
                "output": "",
                "error": f"Path {path_num} not found (available: 0-{path_count-1})",
            }
    else:
        path = nav.get_longest_path()

    # Build output
    output_lines = []

    if show_metadata:
        output_lines.append(f"\nConversation: {conversation.title or '(untitled)'}")
        output_lines.append(f"ID: {conversation.id}")
        if conversation.metadata:
            if conversation.metadata.source:
                output_lines.append(f"Source: {conversation.metadata.source}")
            if conversation.metadata.model:
                output_lines.append(f"Model: {conversation.metadata.model}")
            if conversation.metadata.created_at:
                output_lines.append(f"Created: {conversation.metadata.created_at}")
            if conversation.metadata.tags:
                output_lines.append(f"Tags: {', '.join(conversation.metadata.tags)}")
        output_lines.append(f"Total messages: {len(conversation.message_map)}")
        output_lines.append(f"Paths: {path_count}")
        output_lines.append("")

    if not path:
        output_lines.append("(no messages)")
    else:
        output_lines.append(f"Messages (path: {path_selection}, {len(path)} messages):")
        output_lines.append("=" * 80)

        for msg in path:
            role_label = msg.role.value.title() if msg.role else "User"
            content_text = (
                msg.content.get_text()
                if hasattr(msg.content, "get_text")
                else str(msg.content)
            )
            output_lines.append(f"\n[{role_label}]")
            output_lines.append(content_text)

        output_lines.append("=" * 80)

    if path_count > 1:
        output_lines.append(f"\nNote: This conversation has {path_count} paths")
        output_lines.append("Use --path N or -L for different path views")

    return {
        "success": True,
        "conversation": conversation,
        "navigator": nav,
        "path": path,
        "path_count": path_count,
        "output": "\n".join(output_lines) + "\n",
        "error": "",
    }
