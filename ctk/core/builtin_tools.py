"""Self-dispatching builtin tools for the ctk.builtin provider.

Each tool co-locates its JSON schema and a handler callable, mirroring
ctk/core/network_tools.py. This replaces the former 832-line execute_ask_tool
if/elif dispatcher with a dict-dispatched, behavior-preserving registry.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ctk.core.database import ConversationDB

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db: ConversationDB
    args: Dict[str, Any]
    use_rich: bool = True
    debug: bool = False
    shell_executor: Optional[Callable[..., Any]] = None


@dataclass
class ToolResult:
    text: str
    data: Any = None
    rich_renderable: bool = False

    @classmethod
    def message(cls, text: str) -> "ToolResult":
        return cls(text=text)


@dataclass(frozen=True)
class BuiltinTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[["ToolContext"], "ToolResult"]
    pass_through: bool = False

    def as_schema_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        if self.pass_through:
            d["pass_through"] = True
        return d


def _resolve_conversation_id(db: ConversationDB, conv_id: str) -> str:
    """Resolve a partial id or slug to a full conversation id.

    Returns the full id on success, or an ``Error:``-prefixed string on
    miss/ambiguity (the sentinel contract the ask-tool branches check with
    ``conv_id.startswith("Error:")``). Reuses ``ConversationDB.resolve_conversation``
    rather than re-implementing a prefix scan.
    """
    full = db.resolve_conversation(conv_id)
    if full is None:
        return f"Error: No conversation found matching '{conv_id}'"
    return full


def _do_star_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    # Resolve prefix
    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    ctx.db.star_conversation(conv_id)
    return ToolResult.message(f"Starred conversation {conv_id[:8]}...")


def _do_unstar_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    ctx.db.star_conversation(conv_id, star=False)
    return ToolResult.message(f"Unstarred conversation {conv_id[:8]}...")


def _do_pin_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    ctx.db.pin_conversation(conv_id)
    return ToolResult.message(f"Pinned conversation {conv_id[:8]}...")


def _do_unpin_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    ctx.db.pin_conversation(conv_id, pin=False)
    return ToolResult.message(f"Unpinned conversation {conv_id[:8]}...")


def _do_archive_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    ctx.db.archive_conversation(conv_id)
    return ToolResult.message(f"Archived conversation {conv_id[:8]}...")


def _do_unarchive_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    ctx.db.archive_conversation(conv_id, archive=False)
    return ToolResult.message(f"Unarchived conversation {conv_id[:8]}...")


def _do_rename_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    title = ctx.args.get("title", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")
    if not title:
        return ToolResult.message("Error: title required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    ctx.db.update_conversation_metadata(conv_id, title=title)
    return ToolResult.message(f"Renamed conversation {conv_id[:8]}... to '{title}'")


def _do_delete_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    # Get title before deletion for confirmation message
    tree = ctx.db.load_conversation(conv_id)
    title = tree.title if tree else "Unknown"

    ctx.db.delete_conversation(conv_id)
    return ToolResult.message(f"Deleted conversation '{title}' ({conv_id[:8]}...)")


def _do_tag_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    tags = ctx.args.get("tags", [])
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")
    if not tags:
        return ToolResult.message("Error: tags required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    tree = ctx.db.load_conversation(conv_id)
    if not tree:
        return ToolResult.message(f"Conversation {conv_id} not found")

    # Add tags
    existing_tags = tree.metadata.tags if tree.metadata and tree.metadata.tags else []
    new_tags = [t for t in tags if t not in existing_tags]
    tree.metadata.tags = existing_tags + new_tags
    ctx.db.save_conversation(tree)

    return ToolResult.message(f"Added tags to {conv_id[:8]}...: {', '.join(new_tags)}")


def _do_list_tags(ctx: ToolContext) -> ToolResult:
    # Get all tags with counts
    stats = ctx.db.get_statistics()
    tags_data = stats.get("by_tag", {})

    if not tags_data:
        return ToolResult.message("No tags found in database.")

    result_str = "Tags in database:\n\n"
    # Sort by count descending
    sorted_tags = sorted(tags_data.items(), key=lambda x: x[1], reverse=True)
    for tag, count in sorted_tags:
        result_str += f"  {tag}: {count} conversation(s)\n"

    result_str += f"\nTotal: {len(tags_data)} unique tags"
    return ToolResult.message(result_str)


def _do_remove_tag(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    tag = ctx.args.get("tag", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")
    if not tag:
        return ToolResult.message("Error: tag required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    tree = ctx.db.load_conversation(conv_id)
    if not tree:
        return ToolResult.message(f"Conversation {conv_id} not found")

    if not tree.metadata or not tree.metadata.tags:
        return ToolResult.message("Conversation has no tags")

    if tag not in tree.metadata.tags:
        return ToolResult.message(f"Tag '{tag}' not found on conversation")

    tree.metadata.tags = [t for t in tree.metadata.tags if t != tag]
    ctx.db.save_conversation(tree)
    return ToolResult.message(f"Removed tag '{tag}' from {conv_id[:8]}...")


def _do_auto_tag_conversation(ctx: ToolContext) -> ToolResult:
    conv_id_arg = ctx.args.get("conversation_id", "")
    if not conv_id_arg:
        return ToolResult.message("Error: conversation_id required")
    conv_id = _resolve_conversation_id(ctx.db, conv_id_arg)
    if conv_id.startswith("Error:"):
        return ToolResult.message(f"Conversation not found: {conv_id_arg}")

    conversation = ctx.db.load_conversation(conv_id)
    if not conversation:
        return ToolResult.message(f"Conversation not found: {conv_id}")

    # Auto-tagging requires LLM - check if we have one in context
    # This is a simplified version - the full implementation would use the TUI's provider
    # For now, return a message suggesting manual tagging
    return ToolResult.message(
        f"Auto-tagging requires an LLM provider."
        f" Use `ctk auto-tag {conv_id[:8]}` from the command line,"
        " or manually add tags with `tag_conversation`."
    )


def _do_get_statistics(ctx: ToolContext) -> ToolResult:
    stats = ctx.db.get_statistics()

    result_str = "Database Statistics:\n\n"
    result_str += f"Total conversations: {stats.get('total_conversations', 0)}\n"
    result_str += f"Total messages: {stats.get('total_messages', 0)}\n"

    if stats.get("by_source"):
        result_str += "\nBy source:\n"
        for source, count in stats["by_source"].items():
            result_str += f"  - {source}: {count}\n"

    if stats.get("by_model"):
        result_str += "\nTop models:\n"
        for model, count in list(stats["by_model"].items())[:5]:
            result_str += f"  - {model}: {count}\n"

    return ToolResult.message(result_str)


def _do_list_sources(ctx: ToolContext) -> ToolResult:
    stats = ctx.db.get_statistics()
    sources_data = stats.get("by_source", {})

    if not sources_data:
        return ToolResult.message("No sources found in database.")

    result_str = "Sources in database:\n\n"
    sorted_sources = sorted(sources_data.items(), key=lambda x: x[1], reverse=True)
    for source, count in sorted_sources:
        result_str += f"  {source}: {count} conversation(s)\n"

    result_str += f"\nTotal: {len(sources_data)} sources"
    return ToolResult.message(result_str)


def _do_list_models(ctx: ToolContext) -> ToolResult:
    stats = ctx.db.get_statistics()
    models_data = stats.get("by_model", {})

    if not models_data:
        return ToolResult.message("No models found in database.")

    result_str = "Models in database:\n\n"
    sorted_models = sorted(models_data.items(), key=lambda x: x[1], reverse=True)
    for model, count in sorted_models[:20]:  # Limit to top 20
        result_str += f"  {model}: {count} conversation(s)\n"

    if len(models_data) > 20:
        result_str += f"\n  ... and {len(models_data) - 20} more models"

    result_str += f"\nTotal: {len(models_data)} unique models"
    return ToolResult.message(result_str)


def _do_get_recent_conversations(ctx: ToolContext) -> ToolResult:
    limit = ctx.args.get("limit", 10)
    if not isinstance(limit, int):
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 10

    conversations = ctx.db.list_conversations(limit=limit)

    if not conversations:
        return ToolResult.message("No conversations found.")

    result_str = f"Recent conversations (last {len(conversations)}):\n\n"
    for i, conv in enumerate(conversations, 1):
        conv_dict = conv.to_dict() if hasattr(conv, "to_dict") else conv
        flags = ""
        if conv_dict.get("starred_at"):
            flags += "⭐"
        if conv_dict.get("pinned_at"):
            flags += "📌"

        title = conv_dict.get("title", "Untitled")[:50]
        updated = conv_dict.get("updated_at", "Unknown")[:19]

        result_str += f"{i}. {flags}{conv_dict['id'][:8]}... {title}\n"
        result_str += f"   Updated: {updated}\n"

    result_str += "\nType `show <id>` to view any conversation."
    return ToolResult.message(result_str)


def _do_list_conversations(ctx: ToolContext) -> ToolResult:
    # Get filter parameters
    starred = ctx.args.get("starred")
    pinned = ctx.args.get("pinned")
    archived = ctx.args.get("archived")
    limit = ctx.args.get("limit", 20)
    source = ctx.args.get("source")
    model = ctx.args.get("model")

    if not isinstance(limit, int):
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 20

    # Build kwargs for list_conversations
    kwargs: Dict[str, Any] = {"limit": limit}
    if starred is not None:
        kwargs["starred"] = starred
    if pinned is not None:
        kwargs["pinned"] = pinned
    if archived is not None:
        kwargs["archived"] = archived
    if source:
        kwargs["source"] = source
    if model:
        kwargs["model"] = model

    conversations = ctx.db.list_conversations(**kwargs)

    if not conversations:
        filters_desc = []
        if starred:
            filters_desc.append("starred")
        if pinned:
            filters_desc.append("pinned")
        if archived:
            filters_desc.append("archived")
        if source:
            filters_desc.append(f"source={source}")
        if model:
            filters_desc.append(f"model={model}")
        filter_str = f" ({', '.join(filters_desc)})" if filters_desc else ""
        return ToolResult.message(f"No conversations found{filter_str}.")

    result_str = f"Conversations ({len(conversations)} results):\n\n"
    for i, conv in enumerate(conversations, 1):
        conv_dict = conv.to_dict() if hasattr(conv, "to_dict") else conv
        flags = ""
        if conv_dict.get("starred_at"):
            flags += "⭐"
        if conv_dict.get("pinned_at"):
            flags += "📌"
        if conv_dict.get("archived_at"):
            flags += "📦"

        title = conv_dict.get("title", "Untitled")[:50]
        source_str = conv_dict.get("metadata", {}).get("source", "") or ""
        model_str = conv_dict.get("metadata", {}).get("model", "") or ""

        result_str += f"{i}. {flags}{conv_dict['id'][:8]}... {title}\n"
        if source_str or model_str:
            result_str += f"   {source_str} | {model_str}\n"

    return ToolResult.message(result_str)


_BUILTIN_TOOLS: List[BuiltinTool] = [
    BuiltinTool(
        name="star_conversation",
        description="""Star a conversation to mark it as important.

USE THIS TOOL WHEN: user says "star this", "mark as important", "favorite this conversation".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to star",
                }
            },
            "required": ["conversation_id"],
        },
        handler=_do_star_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="unstar_conversation",
        description="""Remove star from a conversation.

USE THIS TOOL WHEN: user says "unstar this", "remove from favorites".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to unstar",
                }
            },
            "required": ["conversation_id"],
        },
        handler=_do_unstar_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="pin_conversation",
        description="""Pin a conversation to keep it at the top.

USE THIS TOOL WHEN: user says "pin this", "keep at top".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to pin",
                }
            },
            "required": ["conversation_id"],
        },
        handler=_do_pin_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="unpin_conversation",
        description="""Remove pin from a conversation.

USE THIS TOOL WHEN: user says "unpin this".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to unpin",
                }
            },
            "required": ["conversation_id"],
        },
        handler=_do_unpin_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="archive_conversation",
        description="""Archive a conversation to hide it from default listings.

USE THIS TOOL WHEN: user says "archive this", "hide this conversation".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to archive",
                }
            },
            "required": ["conversation_id"],
        },
        handler=_do_archive_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="unarchive_conversation",
        description="""Unarchive a conversation to make it visible again.

USE THIS TOOL WHEN: user says "unarchive this", "restore this conversation".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to unarchive",
                }
            },
            "required": ["conversation_id"],
        },
        handler=_do_unarchive_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="rename_conversation",
        description="""Rename a conversation by setting its title.

USE THIS TOOL WHEN: user says "rename this to...", "change title to...", "call this...".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to rename",
                },
                "title": {
                    "type": "string",
                    "description": "New title for the conversation",
                },
            },
            "required": ["conversation_id", "title"],
        },
        handler=_do_rename_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="delete_conversation",
        description="""Delete a conversation from the database. This is IRREVERSIBLE.

USE THIS TOOL WHEN: user explicitly says "delete this conversation", "remove this chat".

IMPORTANT: Ask for confirmation before deleting.""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to delete",
                }
            },
            "required": ["conversation_id"],
        },
        handler=_do_delete_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="tag_conversation",
        description="""Add tags to a conversation for categorization.

USE THIS TOOL WHEN: user says "tag this as...", "add tag...", "categorize as...".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to add to the conversation",
                },
            },
            "required": ["conversation_id", "tags"],
        },
        handler=_do_tag_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="list_tags",
        description="""List all tags in the database with counts.

USE THIS TOOL WHEN: user says "show all tags", "what tags exist", "list tags".""",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_do_list_tags,
        pass_through=False,
    ),
    BuiltinTool(
        name="remove_tag",
        description="""Remove a tag from a conversation.

USE THIS TOOL WHEN: user says "remove tag", "untag", "delete tag from...".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                },
                "tag": {"type": "string", "description": "Tag to remove"},
            },
            "required": ["conversation_id", "tag"],
        },
        handler=_do_remove_tag,
        pass_through=False,
    ),
    BuiltinTool(
        name="auto_tag_conversation",
        description="""Automatically tag a conversation using LLM analysis.

USE THIS TOOL WHEN: user says "auto-tag", "suggest tags", "analyze and tag".

Uses LLM to analyze conversation content and suggest relevant tags.""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or prefix of conversation ID",
                }
            },
            "required": ["conversation_id"],
        },
        handler=_do_auto_tag_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="get_statistics",
        description="""Get database statistics (counts, sources, models).

DO NOT USE THIS TOOL FOR: greetings, chitchat, or general questions.

USE THIS TOOL WHEN: user asks "how many conversations", "what are the stats", "show statistics".""",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_do_get_statistics,
        pass_through=True,
    ),
    BuiltinTool(
        name="list_sources",
        description="""List all conversation sources (openai, anthropic, etc.) with counts.

USE THIS TOOL WHEN: user says "what sources", "show sources", "where are conversations from".""",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_do_list_sources,
        pass_through=False,
    ),
    BuiltinTool(
        name="list_models",
        description="""List all models used in conversations with counts.

USE THIS TOOL WHEN: user says "what models", "show models", "which models were used".""",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_do_list_models,
        pass_through=False,
    ),
    BuiltinTool(
        name="get_recent_conversations",
        description="""Get the N most recently updated conversations.

USE THIS TOOL WHEN: user says "recent conversations", "latest chats",
"what did I work on recently".""",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of conversations to return (default: 10)",
                }
            },
            "required": [],
        },
        handler=_do_get_recent_conversations,
        pass_through=False,
    ),
    BuiltinTool(
        name="list_conversations",
        description="""List conversations with optional filters.

USE THIS TOOL WHEN: user asks to "list conversations", "show all chats",
"list starred", "show pinned", "what's archived".

Returns a formatted table of conversations matching the criteria.""",
        input_schema={
            "type": "object",
            "properties": {
                "starred": {
                    "type": "boolean",
                    "description": "Filter to starred conversations only",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Filter to pinned conversations only",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Filter to archived conversations only",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 20)",
                },
                "source": {
                    "type": "string",
                    "description": "Filter by source (e.g., 'anthropic', 'openai')",
                },
                "model": {"type": "string", "description": "Filter by model name"},
            },
            "required": [],
        },
        handler=_do_list_conversations,
        pass_through=True,
    ),
]
_HANDLERS: Dict[str, BuiltinTool] = {}


def _rebuild_handlers() -> None:
    _HANDLERS.clear()
    _HANDLERS.update({t.name: t for t in _BUILTIN_TOOLS})


def builtin_tool_names() -> set:
    return set(_HANDLERS)


def execute_builtin_tool(
    db: ConversationDB,
    name: str,
    args: Dict[str, Any],
    *,
    use_rich: bool = True,
    debug: bool = False,
    shell_executor: Optional[Callable[..., Any]] = None,
) -> str:
    tool = _HANDLERS.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    ctx = ToolContext(
        db=db, args=args, use_rich=use_rich, debug=debug, shell_executor=shell_executor
    )
    try:
        result = tool.handler(ctx)
    except Exception as e:  # mirrors the original broad wrapper, behavior-preserving
        return f"Error executing {name}: {e}"
    return result.text


_rebuild_handlers()
