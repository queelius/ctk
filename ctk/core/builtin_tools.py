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


_BUILTIN_TOOLS: List[BuiltinTool] = []
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
