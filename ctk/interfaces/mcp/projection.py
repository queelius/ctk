"""
MCP tool projection layer.

Projects a curated subset of the tool registry as ``mcp.types.Tool`` objects,
applying a thin alias map for backward compatibility with old MCP parameter names.

The seven canonical names in ``_CURATED_MCP_TOOLS`` are the only tools the MCP
server exposes.  Everything else in the registry (the full ~28 builtin tools +
network tools) is available to the TUI but NOT over MCP, keeping the MCP surface
minimal and stable.

Backward-compatibility alias map (one-release shim):
  - ``find_similar`` is a legacy MCP tool name; dispatches to
    ``find_similar_conversations``.
  - Several parameter names differ between the old MCP schemas and the canonical
    registry schemas.  The alias map rewrites incoming argument keys so callers
    using old names keep working.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import mcp.types as types

from ctk.core import (
    builtin_tools,
    network_tools,
)  # noqa: F401 -- ensure providers register
from ctk.core.tools_registry import all_tools, provider_for_tool

# ---------------------------------------------------------------------------
# Curated canonical names
# ---------------------------------------------------------------------------

_CURATED_MCP_TOOLS = {
    "search_conversations",
    "get_conversation",
    "update_conversation",
    "get_statistics",
    "find_similar_conversations",
    "semantic_search",
    "execute_sql",
}

# ---------------------------------------------------------------------------
# Alias map
#
# Structure: {legacy_name: {"_canonical": canonical_name, old_param: new_param, ...}}
#
# ``_canonical`` maps the legacy tool name to the canonical registry name.
# All other keys map old MCP parameter names to canonical registry parameter names.
# ---------------------------------------------------------------------------

_ALIAS: Dict[str, Dict[str, str]] = {
    "find_similar": {
        "_canonical": "find_similar_conversations",
        "id": "conversation_id",
        "top_k": "limit",
        "threshold": "min_similarity",
    },
    "get_conversation": {
        "id": "conversation_id",
        "include_content": "show_messages",
    },
    "update_conversation": {
        "id": "conversation_id",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def canonical_name(name: str) -> str:
    """Return the canonical registry name for ``name`` (handles legacy aliases)."""
    return _ALIAS.get(name, {}).get("_canonical", name)


def normalize_aliases(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Rewrite argument keys for ``name`` according to the alias map.

    Only renames keys that are present in ``args``; skips ``_canonical``.
    Returns a new dict; does not mutate the input.
    """
    mapping = _ALIAS.get(name, {})
    if not mapping:
        return args
    result: Dict[str, Any] = {}
    for k, v in args.items():
        canonical_k = mapping.get(k, k) if k != "_canonical" else k
        result[canonical_k] = v
    return result


def _registry_tool_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Return the registry tool dict for the given canonical name, or None."""
    for t in all_tools():
        if t.get("name") == name:
            return t
    return None


def _to_mcp_tool(
    tool_dict: Dict[str, Any], override_name: Optional[str] = None
) -> types.Tool:
    """Convert a registry tool dict to a ``types.Tool``.

    Drops ``pass_through`` (a registry-only key).  Uses ``override_name`` when
    building the legacy alias tool definition.
    """
    return types.Tool(
        name=override_name or tool_dict["name"],
        description=tool_dict["description"],
        inputSchema=tool_dict["input_schema"],
    )


def _synthesize_find_similar_alias(canonical: Dict[str, Any]) -> types.Tool:
    """Synthesize the legacy ``find_similar`` tool from the canonical schema.

    Renames the canonical parameter keys back to the old MCP names
    (``conversation_id`` -> ``id``, ``limit`` -> ``top_k``,
    ``min_similarity`` -> ``threshold``) so old clients still see the legacy
    schema during the deprecation window.
    """
    schema = copy.deepcopy(canonical["input_schema"])
    props = schema.get("properties", {})
    required = schema.get("required", [])

    # Rename canonical param keys to legacy names
    renames = {
        "conversation_id": "id",
        "limit": "top_k",
        "min_similarity": "threshold",
    }

    new_props: Dict[str, Any] = {}
    for k, v in props.items():
        new_props[renames.get(k, k)] = v
    schema["properties"] = new_props

    # Rename required entries
    schema["required"] = [renames.get(r, r) for r in required]

    return types.Tool(
        name="find_similar",
        description=canonical["description"],
        inputSchema=schema,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def project_tools() -> List[types.Tool]:
    """Return the curated MCP tool list derived from the registry.

    Includes:
    - One ``types.Tool`` for each name in ``_CURATED_MCP_TOOLS``, sourced from
      the registry.
    - One legacy ``find_similar`` alias tool (synthesized from the canonical
      ``find_similar_conversations`` schema with parameter names reverted to the
      old MCP names).

    The list is sorted by name for stable output.
    """
    result: List[types.Tool] = []
    find_similar_canonical: Optional[Dict[str, Any]] = None

    for t in all_tools():
        name = t.get("name")
        if name not in _CURATED_MCP_TOOLS:
            continue
        result.append(_to_mcp_tool(t))
        if name == "find_similar_conversations":
            find_similar_canonical = t

    # Append the legacy alias
    if find_similar_canonical is not None:
        result.append(_synthesize_find_similar_alias(find_similar_canonical))

    result.sort(key=lambda t: t.name)
    return result


async def handle_tool(
    name: str,
    arguments: Dict[str, Any],
    db: Any,
) -> List[types.TextContent]:
    """Dispatch an MCP tool call through the registry.

    Accepts both canonical names and the legacy ``find_similar`` alias.
    Returns ``[TextContent(type="text", text="Unknown tool: <name>")]`` for
    any name not in the curated set and not an alias.
    """
    if name not in _CURATED_MCP_TOOLS and name not in _ALIAS:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    args = normalize_aliases(name, arguments)
    cname = canonical_name(name)

    provider = provider_for_tool(cname)
    if provider == "ctk.network":
        result_str = network_tools.execute_network_tool(db, cname, args)
    else:
        result_str = builtin_tools.execute_builtin_tool(db, cname, args)

    return [types.TextContent(type="text", text=result_str)]
