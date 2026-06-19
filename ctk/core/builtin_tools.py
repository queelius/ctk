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
