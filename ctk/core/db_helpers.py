"""
Database helper functions for CLI and TUI.

These helpers wrap common database operations with formatting and filtering.
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from .formatting import format_conversations_table

if TYPE_CHECKING:
    from .database import ConversationDB


def list_conversations_helper(
    db: "ConversationDB",
    limit: Optional[int] = None,
    json_output: bool = False,
    archived: bool = False,
    starred: bool = False,
    pinned: bool = False,
    include_archived: bool = False,
    source: Optional[str] = None,
    project: Optional[str] = None,
    model: Optional[str] = None,
    tags: Optional[str] = None,
) -> int:
    """
    List conversations with filtering.

    Args:
        db: Database instance
        limit: Maximum results
        json_output: Output as JSON
        archived: Show only archived
        starred: Show only starred
        pinned: Show only pinned
        include_archived: Include archived in results
        source: Filter by source
        project: Filter by project
        model: Filter by model
        tags: Comma-separated tags

    Returns:
        0 on success, 1 on error
    """
    # Build filter args
    filter_args = {
        "limit": limit,
        "source": source,
        "project": project,
        "model": model,
        "include_archived": include_archived,
    }

    # Handle tags
    if tags:
        filter_args["tags"] = [t.strip() for t in tags.split(",")]

    # Handle archive/star/pin flags
    if archived:
        filter_args["archived"] = True
    if starred:
        filter_args["starred"] = True
    if pinned:
        filter_args["pinned"] = True

    conversations = db.list_conversations(**filter_args)

    if not conversations:
        print("No conversations found")
        return 0

    # Display format
    if json_output:
        # Convert to dicts
        conv_dicts = [
            c.to_dict() if hasattr(c, "to_dict") else c for c in conversations
        ]
        print(json.dumps(conv_dicts, indent=2, default=str))
    else:
        format_conversations_table(conversations, show_message_count=False)

    return 0


def search_conversations_helper(
    db: "ConversationDB",
    query: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    title_only: bool = False,
    content_only: bool = False,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    source: Optional[str] = None,
    project: Optional[str] = None,
    model: Optional[str] = None,
    tags: Optional[str] = None,
    min_messages: Optional[int] = None,
    max_messages: Optional[int] = None,
    has_branches: bool = False,
    archived: bool = False,
    starred: bool = False,
    pinned: bool = False,
    include_archived: bool = False,
    order_by: str = "updated_at",
    ascending: bool = False,
    output_format: str = "table",
) -> int:
    """
    Search conversations with filtering.

    Args:
        db: Database instance
        query: Search query text
        limit: Maximum results
        offset: Skip N results
        title_only: Search only titles
        content_only: Search only content
        date_from: Created after date
        date_to: Created before date
        source: Filter by source
        project: Filter by project
        model: Filter by model
        tags: Comma-separated tags
        min_messages: Minimum message count
        max_messages: Maximum message count
        has_branches: Filter branching conversations
        archived: Show only archived
        starred: Show only starred
        pinned: Show only pinned
        include_archived: Include archived in results
        order_by: Sort field
        ascending: Sort direction
        output_format: 'table', 'json', or 'csv'

    Returns:
        0 on success, 1 on error
    """
    # Parse tags
    tags_list = tags.split(",") if tags else None

    # Build search args
    search_args = {
        "query_text": query,
        "limit": limit,
        "offset": offset,
        "title_only": title_only,
        "content_only": content_only,
        "date_from": date_from,
        "date_to": date_to,
        "source": source,
        "project": project,
        "model": model,
        "tags": tags_list,
        "min_messages": min_messages,
        "max_messages": max_messages,
        "has_branches": has_branches,
        "order_by": order_by,
        "ascending": ascending,
        "include_archived": include_archived,
    }

    # Handle archive/star/pin flags
    if archived:
        search_args["archived"] = True
    if starred:
        search_args["starred"] = True
    if pinned:
        search_args["pinned"] = True

    results = db.search_conversations(**search_args)

    if not results:
        print("No conversations found matching criteria")
        return 0

    # Display results
    if output_format == "json":
        conv_dicts = [c.to_dict() if hasattr(c, "to_dict") else c for c in results]
        print(json.dumps(conv_dicts, indent=2, default=str))
    elif output_format == "csv":
        print("ID,Title,Messages,Source,Model,Created,Updated")
        for conv in results:
            conv_dict = conv.to_dict() if hasattr(conv, "to_dict") else conv
            print(
                f"{conv_dict['id']},{conv_dict.get('title', 'Untitled')},{conv_dict.get('message_count', 0)},"
                f"{conv_dict.get('source', '')},{conv_dict.get('model', '')},"
                f"{conv_dict.get('created_at', '')},{conv_dict.get('updated_at', '')}"
            )
    else:  # default table format
        format_conversations_table(results, show_message_count=True)

    return 0
