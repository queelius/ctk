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


def _do_get_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args["conversation_id"]

    # Handle prefix matching (own inline scan, NOT _resolve_conversation_id)
    if len(conv_id) < 36:
        all_convs = ctx.db.list_conversations(limit=None, include_archived=True)
        matches = [c for c in all_convs if c.id.startswith(conv_id)]

        if len(matches) == 0:
            return ToolResult.message(f"No conversation found matching '{conv_id}'")
        elif len(matches) > 1:
            return ToolResult.message(
                f"Multiple conversations match '{conv_id}' - please be more specific"
            )
        else:
            conv_id = matches[0].id

    # Load conversation
    tree = ctx.db.load_conversation(conv_id)
    if not tree:
        return ToolResult.message(f"Conversation {conv_id} not found")

    result_str = f"Conversation: {tree.title or 'Untitled'}\n"
    result_str += f"ID: {tree.id}\n"
    if tree.metadata:
        if tree.metadata.source:
            result_str += f"Source: {tree.metadata.source}\n"
        if tree.metadata.model:
            result_str += f"Model: {tree.metadata.model}\n"
        if tree.metadata.project:
            result_str += f"Project: {tree.metadata.project}\n"
        if tree.metadata.tags:
            result_str += f"Tags: {', '.join(tree.metadata.tags)}\n"

    # Count messages
    msg_count = len(tree.message_map)
    result_str += f"Messages: {msg_count}\n"

    # Show messages if requested
    if ctx.args.get("show_messages", False):
        result_str += "\nMessages:\n"
        path = tree.get_longest_path()
        for i, msg in enumerate(path[:5], 1):
            # Handle both MessageContent objects and plain strings
            if hasattr(msg.content, "get_text"):
                text = msg.content.get_text()
            else:
                text = str(msg.content) if msg.content else ""
            content = text[:100] if text else "(no content)"
            role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            result_str += f"\n{i}. {role}: {content}...\n"
        if len(path) > 5:
            result_str += f"\n... and {len(path) - 5} more messages\n"

    return ToolResult.message(result_str)


def _do_show_conversation_content(ctx: ToolContext) -> ToolResult:
    from ctk.core.conversation_display import show_conversation_helper

    conv_id = ctx.args.get("conversation_id", "")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    path_selection = ctx.args.get("path_selection", "longest")

    result = show_conversation_helper(
        db=ctx.db,
        conv_id=conv_id,
        path_selection=path_selection,
        plain_output=True,
        show_metadata=True,
    )

    if result["success"]:
        return ToolResult.message(result["output"])
    else:
        return ToolResult.message(f"Error: {result['error']}")


def _do_list_conversation_paths(ctx: ToolContext) -> ToolResult:
    conv_id_arg = ctx.args.get("conversation_id", "")
    if not conv_id_arg:
        return ToolResult.message("Error: conversation_id required")
    conv_id = _resolve_conversation_id(ctx.db, conv_id_arg)
    if conv_id.startswith("Error:"):
        return ToolResult.message(f"Conversation not found: {conv_id_arg}")

    conversation = ctx.db.load_conversation(conv_id)
    if not conversation:
        return ToolResult.message(f"Conversation not found: {conv_id}")

    paths = conversation.get_all_paths()

    if not paths:
        return ToolResult.message(f"No paths found in conversation {conv_id[:8]}...")

    result_str = f"Paths in conversation {conv_id[:8]}... ({len(paths)} total):\n\n"
    for i, path in enumerate(paths, 1):
        result_str += f"Path {i} ({len(path)} messages):\n"
        for msg in path:
            role_label = msg.role.value.title() if msg.role else "User"
            content_text = (
                msg.content.get_text()
                if hasattr(msg.content, "get_text")
                else str(msg.content)
            )
            preview = (
                content_text[:50].replace("\n", " ").strip() if content_text else ""
            )
            if len(content_text) > 50:
                preview += "..."
            result_str += f"  {role_label}: {preview}\n"
        result_str += "\n"

    return ToolResult.message(result_str)


def _do_duplicate_conversation(ctx: ToolContext) -> ToolResult:
    import copy
    import uuid

    conv_id = ctx.args.get("conversation_id", "")
    new_title = ctx.args.get("new_title", None)
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    tree = ctx.db.load_conversation(conv_id)
    if not tree:
        return ToolResult.message(f"Conversation {conv_id} not found")

    # Create a deep copy with new ID
    new_tree = copy.deepcopy(tree)
    new_tree.id = str(uuid.uuid4())
    new_tree.title = new_title or f"Copy of {tree.title}"

    # Update message IDs
    old_to_new = {}
    for old_id, msg in list(new_tree.message_map.items()):
        new_id = str(uuid.uuid4())
        old_to_new[old_id] = new_id
        msg.id = new_id

    # Update message_map keys and parent references
    new_message_map = {}
    for old_id, msg in new_tree.message_map.items():
        new_id = old_to_new.get(old_id, old_id)
        if msg.parent_id and msg.parent_id in old_to_new:
            msg.parent_id = old_to_new[msg.parent_id]
        new_message_map[new_id] = msg
    new_tree.message_map = new_message_map

    # Update root_message_ids
    new_tree.root_message_ids = [
        old_to_new.get(rid, rid) for rid in new_tree.root_message_ids
    ]

    ctx.db.save_conversation(new_tree)
    return ToolResult.message(
        f"Created copy: '{new_tree.title}' ({new_tree.id[:8]}...)"
    )


def _do_list_plugins(ctx: ToolContext) -> ToolResult:
    from ctk.core.plugin import PluginRegistry

    manager = PluginRegistry()
    importers = manager.list_importers()
    exporters = manager.list_exporters()

    result_str = "Available Plugins:\n\n"

    result_str += "Importers:\n"
    if importers:
        for name in sorted(importers):
            result_str += f"  - {name}\n"
    else:
        result_str += "  (none)\n"

    result_str += "\nExporters:\n"
    if exporters:
        for name in sorted(exporters):
            result_str += f"  - {name}\n"
    else:
        result_str += "  (none)\n"

    return ToolResult.message(result_str)


def _do_export_conversation(ctx: ToolContext) -> ToolResult:
    conv_id = ctx.args.get("conversation_id", "")
    export_format = ctx.args.get("format", "markdown")
    if not conv_id:
        return ToolResult.message("Error: conversation_id required")

    conv_id = _resolve_conversation_id(ctx.db, conv_id)
    if conv_id.startswith("Error:"):
        return ToolResult.message(conv_id)

    tree = ctx.db.load_conversation(conv_id)
    if not tree:
        return ToolResult.message(f"Conversation {conv_id} not found")

    if export_format == "markdown":
        from ctk.exporters.markdown import MarkdownExporter

        exporter = MarkdownExporter()
        output = exporter.export_data([tree])
        return ToolResult.message(f"Markdown export of '{tree.title}':\n\n{output}")

    elif export_format == "json":
        import json

        # Convert to dict
        conv_dict = {
            "id": tree.id,
            "title": tree.title,
            "messages": [
                {
                    "role": msg.role.value if msg.role else "user",
                    "content": (
                        msg.content.get_text()
                        if hasattr(msg.content, "get_text")
                        else str(msg.content)
                    ),
                }
                for msg in tree.get_longest_path()
            ],
        }
        return ToolResult.message(f"JSON export:\n{json.dumps(conv_dict, indent=2)}")

    elif export_format == "jsonl":
        messages = tree.get_longest_path()
        lines = []
        for msg in messages:
            import json

            line = json.dumps(
                {
                    "role": msg.role.value if msg.role else "user",
                    "content": (
                        msg.content.get_text()
                        if hasattr(msg.content, "get_text")
                        else str(msg.content)
                    ),
                }
            )
            lines.append(line)
        return ToolResult.message(
            f"JSONL export ({len(lines)} messages):\n" + "\n".join(lines)
        )

    else:
        return ToolResult.message(
            f"Unknown format: {export_format}. Use markdown, json, or jsonl."
        )


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
        description=(
            "Get the N most recently updated conversations.\n\n"
            'USE THIS TOOL WHEN: user says "recent conversations", "latest chats",'
            ' "what did I work on recently".'
        ),
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
        description=(
            "List conversations with optional filters.\n\n"
            'USE THIS TOOL WHEN: user asks to "list conversations", "show all chats",'
            ' "list starred", "show pinned", "what\'s archived".\n\n'
            "Returns a formatted table of conversations matching the criteria."
        ),
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
    BuiltinTool(
        name="get_conversation",
        description=(
            "Get details of a specific conversation by its ID.\n\n"
            "DO NOT USE THIS TOOL FOR: greetings, chitchat, or questions that"
            " don't mention a specific conversation ID.\n\n"
            "USE THIS TOOL WHEN: user provides a conversation ID and wants details about it."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                },
                "show_messages": {
                    "type": "boolean",
                    "description": "Include message content (default: false)",
                },
            },
            "required": ["conversation_id"],
        },
        handler=_do_get_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="show_conversation_content",
        description=(
            "Show the full content of a conversation.\n\n"
            'USE THIS TOOL WHEN: user says "show me the conversation",'
            ' "display the chat", "what was said in...".'
        ),
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to show",
                },
                "path_selection": {
                    "type": "string",
                    "description": (
                        "Which path to show: 'longest' (default), 'latest',"
                        " or a path number like '0', '1'"
                    ),
                },
            },
            "required": ["conversation_id"],
        },
        handler=_do_show_conversation_content,
        pass_through=False,
    ),
    BuiltinTool(
        name="list_conversation_paths",
        description=(
            "List all paths in a branching conversation tree.\n\n"
            'USE THIS TOOL WHEN: user asks "show paths", "list branches",'
            ' "how many paths", "conversation branches".\n\n'
            "Returns all distinct paths from root to leaf in the conversation tree."
        ),
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
        handler=_do_list_conversation_paths,
        pass_through=False,
    ),
    BuiltinTool(
        name="duplicate_conversation",
        description="""Create a copy of a conversation with a new ID.

USE THIS TOOL WHEN: user says "duplicate", "copy conversation", "clone this".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID to duplicate",
                },
                "new_title": {
                    "type": "string",
                    "description": "Optional title for the copy",
                },
            },
            "required": ["conversation_id"],
        },
        handler=_do_duplicate_conversation,
        pass_through=False,
    ),
    BuiltinTool(
        name="list_plugins",
        description=(
            'List available importer and exporter plugins.\n\n'
            'USE THIS TOOL WHEN: user asks "what plugins", "list importers",'
            ' "list exporters", "supported formats".'
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_do_list_plugins,
        pass_through=False,
    ),
    BuiltinTool(
        name="export_conversation",
        description="""Export a conversation to a specific format.

USE THIS TOOL WHEN: user says "export to markdown", "save as json", "export conversation".""",
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or partial conversation ID",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json", "jsonl"],
                    "description": "Export format (default: markdown)",
                },
            },
            "required": ["conversation_id"],
        },
        handler=_do_export_conversation,
        pass_through=False,
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
