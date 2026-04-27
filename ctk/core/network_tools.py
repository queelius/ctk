"""Network/similarity tools exposed as the ``ctk.network`` virtual MCP.

In the new "everything the LLM can do is a tool" model (2.12.0), the
graph/similarity analysis that used to live behind ``ctk net …``
subcommands becomes tools the model can invoke during chat. The model
is in a much better position to choose when to call them ("find
conversations like this one") than the user is to remember the exact
subcommand.

Scope for 2.12.0 — only the tools that can be answered directly from
the persisted ``SimilarityModel`` table ship as MCP tools:

* ``find_similar_conversations`` — top-k by stored similarity
* ``list_neighbors`` — graph adjacency for a given conversation

The richer graph analytics (clusters, centrality, paths) need a live
NetworkX graph that today gets rebuilt inside the CLI commands. They
will move to MCP tools in a follow-up once the graph-construction
machinery is factored out of cli_net.py into a reusable helper. Until
then, those operations are simply unavailable to the model — and that
is fine; the user can build the graph with ``ctk db links`` and then
ask "find similar to X" which IS a tool.

Read-only by intent: tools never mutate state. Embedding computation
and graph construction remain CLI batch operations because they don't
fit a chat turn (slow, big-memory).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from ctk.core.tools_registry import ToolProvider, register_provider

logger = logging.getLogger(__name__)


_NETWORK_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "find_similar_conversations",
        "pass_through": False,
        "description": (
            "Find conversations similar to a given one using precomputed "
            "embeddings. USE WHEN the user asks 'what other conversations "
            "are like this', 'find related threads', 'show me similar', "
            "etc. Requires that similarities have been computed first via "
            "`ctk db embeddings` and `ctk db links`. If no similarities "
            "are recorded for the seed, returns a message saying so — "
            "relay it to the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or prefix id of the seed conversation.",
                },
                "limit": {
                    "type": "integer",
                    "description": "How many similar conversations to return (default 10).",
                },
                "min_similarity": {
                    "type": "number",
                    "description": (
                        "Minimum similarity score in [0, 1] (default 0.0, "
                        "i.e., return whatever was stored)."
                    ),
                },
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "list_neighbors",
        "pass_through": False,
        "description": (
            "List the immediate graph neighbors of a conversation in the "
            "stored similarity graph. USE WHEN the user wants to see "
            "what's adjacent to a specific thread."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "Full or prefix id.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Cap on neighbors returned (default 20).",
                },
            },
            "required": ["conversation_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


def _resolve_id(db, prefix: str) -> Optional[str]:
    """Resolve a conv-id prefix to the full id, or return None."""
    if not prefix:
        return None
    # Cheapest path: try as a full id first.
    tree = db.load_conversation(prefix)
    if tree is not None:
        return tree.id
    # Fall back to a prefix scan over the conversation list.
    for conv in db.list_conversations(limit=10000):
        if conv.id.startswith(prefix):
            return conv.id
    return None


def _query_similarities(db, seed_id: str, limit: int, min_sim: float):
    """Return ``[(other_id, similarity)]`` for the seed, sorted desc.

    Reads the persisted ``SimilarityModel`` table; no graph
    reconstruction. Pairs are stored canonically with ``id1 < id2`` so
    we have to OR both columns in the filter and pick the "other"
    side explicitly.
    """
    from ctk.core.db_models import SimilarityModel

    with db.session_scope() as session:
        rows = (
            session.query(SimilarityModel)
            .filter(
                or_(
                    SimilarityModel.conversation1_id == seed_id,
                    SimilarityModel.conversation2_id == seed_id,
                )
            )
            .filter(SimilarityModel.similarity >= min_sim)
            .order_by(SimilarityModel.similarity.desc())
            .limit(limit)
            .all()
        )
        # Detach simple Python tuples so we don't return SQLAlchemy
        # objects bound to a session that's about to close.
        out = []
        for r in rows:
            other = (
                r.conversation2_id
                if r.conversation1_id == seed_id
                else r.conversation1_id
            )
            out.append((other, float(r.similarity)))
        return out


def _format_results(db, pairs) -> str:
    """Render ``[(conv_id, score)]`` as a list with titles for the model."""
    if not pairs:
        return "(no similar conversations found)"
    lines = []
    for conv_id, score in pairs:
        tree = db.load_conversation(conv_id)
        title = (tree.title if tree else "(missing)") or "(untitled)"
        lines.append(f"{conv_id[:8]}  {title}  ({score:.3f})")
    return "\n".join(lines)


def execute_network_tool(db, name: str, args: Dict[str, Any]) -> str:
    """Dispatch a ``ctk.network`` tool call to its implementation.

    Returns a string suitable for injecting back into the chat history
    as the tool's result. Errors surface as ``Error: ...`` so the
    model can relay them.
    """
    if name == "find_similar_conversations":
        return _do_find_similar(db, args)
    if name == "list_neighbors":
        return _do_neighbors(db, args)
    return f"Error: unknown ctk.network tool: {name}"


def _do_find_similar(db, args: Dict[str, Any]) -> str:
    seed_id = _resolve_id(db, args.get("conversation_id", ""))
    if seed_id is None:
        return f"Error: no conversation found matching '{args.get('conversation_id')}'"
    limit = int(args.get("limit", 10))
    min_sim = float(args.get("min_similarity", 0.0))
    try:
        pairs = _query_similarities(db, seed_id, limit, min_sim)
    except Exception as exc:
        return (
            f"Error: similarity query failed ({exc}). "
            "If you haven't yet, run `ctk db embeddings` then `ctk db links` "
            "to build the similarity graph."
        )
    if not pairs:
        return (
            "(no similarities recorded for that conversation — "
            "run `ctk db embeddings` and `ctk db links` to build them)"
        )
    return _format_results(db, pairs)


def _do_neighbors(db, args: Dict[str, Any]) -> str:
    """List neighbors. Identical to find-similar with no min threshold."""
    seed_id = _resolve_id(db, args.get("conversation_id", ""))
    if seed_id is None:
        return f"Error: no conversation found matching '{args.get('conversation_id')}'"
    limit = int(args.get("limit", 20))
    try:
        pairs = _query_similarities(db, seed_id, limit, min_sim=0.0)
    except Exception as exc:
        return f"Error: graph query failed ({exc})"
    if not pairs:
        return "(no neighbors found)"
    return _format_results(db, pairs)


# ---------------------------------------------------------------------------
# Provider registration (runs on import)
# ---------------------------------------------------------------------------


_NETWORK_PROVIDER = ToolProvider(
    name="ctk.network",
    description=(
        "Graph and similarity analysis over the conversation collection. "
        "Tools query the persisted similarity table; embedding computation "
        "and graph construction remain CLI operations "
        "(`ctk db embeddings`, `ctk db links`)."
    ),
    tools=_NETWORK_TOOLS,
)
register_provider(_NETWORK_PROVIDER)
