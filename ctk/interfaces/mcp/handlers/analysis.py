"""MCP handlers for semantic search and network analysis operations."""

import logging
from typing import Any, Dict, List

import mcp.types as types
import numpy as np

from ctk.core.constants import MAX_ID_LENGTH, MAX_QUERY_LENGTH
from ctk.interfaces.mcp.validation import validate_integer, validate_string

logger = logging.getLogger(__name__)


# --- Helper Functions ---


def _check_embeddings_exist(db) -> List[Dict[str, Any]]:
    """Check if embeddings exist in the database."""
    return db.get_all_embeddings()


def _no_embeddings_error() -> list[types.TextContent]:
    """Return standard error message when no embeddings are found."""
    return [
        types.TextContent(
            type="text",
            text="No embeddings found. Generate them first with: ctk net embeddings --db <path>",
        )
    ]


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    if vec_a.shape != vec_b.shape:
        return 0.0
    dot = float(np.dot(vec_a, vec_b))
    n1 = float(np.linalg.norm(vec_a))
    n2 = float(np.linalg.norm(vec_b))
    return dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0


def _get_conversation_title(db, conversation_id: str, max_len: int = 50) -> str:
    """Safely get a conversation title, returning 'Unknown' on failure."""
    try:
        conv = db.load_conversation(conversation_id)
        return (conv.title or "Untitled")[:max_len] if conv else "Unknown"
    except Exception:
        return "Unknown"


# --- Tool Definitions ---

TOOLS: List[types.Tool] = [
    types.Tool(
        name="find_similar",
        description=(
            "Find conversations similar to a given conversation using cached embeddings. "
            "Requires embeddings to have been generated first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Conversation ID (full or partial prefix)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10)",
                    "default": 10,
                },
                "threshold": {
                    "type": "number",
                    "description": "Minimum similarity score 0.0-1.0 (default: 0.1)",
                    "default": 0.1,
                },
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="semantic_search",
        description=(
            "Search conversations by meaning using embeddings. Unlike text search, "
            "this finds conceptually similar conversations even without keyword matches. "
            "Requires embeddings to have been generated first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search by meaning",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_network_summary",
        description=(
            "Get summary statistics of the conversation similarity network: "
            "number of clusters, density, most central conversations."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number",
                    "description": "Minimum similarity for graph edges (default: 0.3)",
                    "default": 0.3,
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_clusters",
        description=(
            "Detect topic clusters among conversations using community detection "
            "on the similarity graph."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "algorithm": {
                    "type": "string",
                    "description": "Community detection algorithm (default: label_propagation)",
                    "enum": ["label_propagation", "greedy_modularity"],
                    "default": "label_propagation",
                },
            },
            "required": [],
        },
    ),
]


# --- Handler Functions ---


async def handle_find_similar(arguments: dict, db) -> list[types.TextContent]:
    """Handle find_similar tool call."""
    conv_id_input = validate_string(
        arguments.get("id"), "id", MAX_ID_LENGTH, required=True
    )
    top_k = (
        validate_integer(arguments.get("top_k"), "top_k", min_val=1, max_val=100) or 10
    )
    threshold = arguments.get("threshold", 0.1)
    if isinstance(threshold, str):
        threshold = float(threshold)

    # Resolve partial ID
    resolved = db.resolve_identifier(conv_id_input)
    if not resolved:
        return [
            types.TextContent(
                type="text",
                text=f"Error: Could not find conversation '{conv_id_input}'",
            )
        ]
    full_id = resolved[0]

    # Check embeddings exist
    all_embs = _check_embeddings_exist(db)
    if not all_embs:
        return _no_embeddings_error()

    # Use cached similarities from DB first
    similar = db.get_similar_conversations(
        full_id, metric="cosine", top_k=top_k, threshold=threshold
    )

    if not similar:
        # Try computing on the fly from cached embeddings
        target_emb = None
        candidate_embs = {}
        for emb_record in all_embs:
            if emb_record["conversation_id"] == full_id:
                target_emb = np.array(emb_record["embedding"])
            else:
                candidate_embs[emb_record["conversation_id"]] = np.array(
                    emb_record["embedding"]
                )

        if target_emb is None:
            return [
                types.TextContent(
                    type="text",
                    text=f"No embedding found for conversation {full_id[:8]}. Re-run embeddings.",
                )
            ]

        # Compute cosine similarities
        results = []
        for cid, cemb in candidate_embs.items():
            sim = _cosine_similarity(target_emb, cemb)
            if sim >= threshold:
                results.append({"conversation_id": cid, "similarity": sim})

        results.sort(key=lambda x: x["similarity"], reverse=True)
        similar = results[:top_k]

    if not similar:
        return [
            types.TextContent(
                type="text",
                text=f"No similar conversations found for {full_id[:8]}.",
            )
        ]

    # Format output
    lines = [f"Conversations similar to {full_id[:8]}:\n"]
    for i, s in enumerate(similar, 1):
        cid = s["conversation_id"]
        sim = s["similarity"]
        title = _get_conversation_title(db, cid)
        lines.append(f"[{i}] {cid[:8]} ({sim:.2f}) {title}")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_semantic_search(arguments: dict, db) -> list[types.TextContent]:
    """Handle semantic_search tool call."""
    query = validate_string(
        arguments.get("query"), "query", MAX_QUERY_LENGTH, required=True
    )
    top_k = (
        validate_integer(arguments.get("top_k"), "top_k", min_val=1, max_val=100) or 10
    )

    all_embs = _check_embeddings_exist(db)
    if not all_embs:
        return _no_embeddings_error()

    # Embed the query text using same provider as stored embeddings
    provider_name = all_embs[0].get("provider", "tfidf")

    try:
        from ctk.core.similarity import (ConversationEmbedder,
                                         ConversationEmbeddingConfig)
        from ctk.integrations.embeddings.base import (AggregationStrategy,
                                                      ChunkingStrategy)

        config = ConversationEmbeddingConfig(
            provider=provider_name,
            chunking=ChunkingStrategy.WHOLE,
            aggregation=AggregationStrategy.MEAN,
        )

        # For TF-IDF, we need a fitted vectorizer
        if provider_name == "tfidf":
            from ctk.integrations.embeddings.tfidf import TFIDFEmbedding

            tfidf = TFIDFEmbedding(config.provider_config)

            # Gather texts from conversations that have embeddings
            texts = []
            for emb_record in all_embs:
                try:
                    conv = db.load_conversation(emb_record["conversation_id"])
                    if conv:
                        path = conv.get_longest_path()
                        text_parts = [conv.title or ""]
                        for msg in path:
                            if hasattr(msg.content, "get_text"):
                                text_parts.append(msg.content.get_text())
                            elif hasattr(msg.content, "text"):
                                text_parts.append(msg.content.text or "")
                        texts.append(" ".join(text_parts))
                except Exception:
                    continue

            if not texts:
                return [
                    types.TextContent(
                        type="text",
                        text="Error: Could not load conversation texts for TF-IDF fitting.",
                    )
                ]

            tfidf.fit(texts + [query])
            query_resp = tfidf.embed(query)
            query_vec = np.array(query_resp.embedding)
        else:
            embedder = ConversationEmbedder(config)
            query_resp = embedder.provider.embed(query)
            query_vec = np.array(query_resp.embedding)

    except Exception as e:
        logger.error(f"Failed to embed query: {e}")
        return [types.TextContent(type="text", text=f"Error embedding query: {e}")]

    # Compare against all stored embeddings
    results = []
    for emb_record in all_embs:
        stored_vec = np.array(emb_record["embedding"])
        sim = _cosine_similarity(query_vec, stored_vec)
        if sim > 0:
            results.append(
                {
                    "conversation_id": emb_record["conversation_id"],
                    "similarity": sim,
                }
            )

    results.sort(key=lambda x: x["similarity"], reverse=True)
    results = results[:top_k]

    if not results:
        return [
            types.TextContent(
                type="text",
                text="No semantically similar conversations found.",
            )
        ]

    lines = [f'Semantic search results for "{query}":\n']
    for i, r in enumerate(results, 1):
        cid = r["conversation_id"]
        sim = r["similarity"]
        title = _get_conversation_title(db, cid)
        lines.append(f"[{i}] {cid[:8]} ({sim:.2f}) {title}")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_get_network_summary(arguments: dict, db) -> list[types.TextContent]:
    """Handle get_network_summary tool call."""
    threshold = arguments.get("threshold", 0.3)
    if isinstance(threshold, str):
        threshold = float(threshold)

    all_embs = _check_embeddings_exist(db)
    if not all_embs:
        return _no_embeddings_error()

    # Build similarity graph from cached embeddings
    n = len(all_embs)
    ids = [e["conversation_id"] for e in all_embs]
    vecs = [np.array(e["embedding"]) for e in all_embs]

    edge_count = 0
    degrees = {cid: 0 for cid in ids}

    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(vecs[i], vecs[j])
            if sim >= threshold:
                edge_count += 1
                degrees[ids[i]] += 1
                degrees[ids[j]] += 1

    max_edges = n * (n - 1) / 2 if n > 1 else 1
    density = edge_count / max_edges if max_edges > 0 else 0

    # Find most central (highest degree)
    central = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:5]

    lines = [
        "Conversation Network Summary",
        "=" * 40,
        f"Nodes: {n}",
        f"Edges: {edge_count} (threshold: {threshold})",
        f"Density: {density:.3f}",
    ]
    if n > 0:
        lines.append(f"Avg degree: {sum(degrees.values()) / n:.1f}")

    if central and central[0][1] > 0:
        lines.append("\nMost connected conversations:")
        for cid, deg in central:
            if deg == 0:
                break
            title = _get_conversation_title(db, cid, max_len=40)
            lines.append(f"  {cid[:8]} (degree {deg}) {title}")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_get_clusters(arguments: dict, db) -> list[types.TextContent]:
    """Handle get_clusters tool call."""
    algorithm = arguments.get("algorithm", "label_propagation")

    all_embs = _check_embeddings_exist(db)
    if not all_embs:
        return _no_embeddings_error()

    try:
        import networkx as nx
        import networkx.algorithms.community as nx_comm
    except ImportError:
        return [
            types.TextContent(
                type="text",
                text="Error: NetworkX required for clustering. Install with: pip install networkx",
            )
        ]

    # Build graph
    n = len(all_embs)
    ids = [e["conversation_id"] for e in all_embs]
    vecs = [np.array(e["embedding"]) for e in all_embs]

    G = nx.Graph()
    G.add_nodes_from(ids)

    threshold = 0.3
    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(vecs[i], vecs[j])
            if sim >= threshold:
                G.add_edge(ids[i], ids[j], weight=sim)

    # Detect communities
    if algorithm == "label_propagation":
        communities_iter = nx_comm.label_propagation_communities(G)
    elif algorithm == "greedy_modularity":
        communities_iter = nx_comm.greedy_modularity_communities(G)
    else:
        return [
            types.TextContent(
                type="text",
                text=f"Unknown algorithm: {algorithm}",
            )
        ]

    # Format output
    clusters = {}
    for idx, comm in enumerate(communities_iter):
        clusters[idx] = list(comm)

    lines = [f"Found {len(clusters)} cluster(s):\n"]
    for cluster_id, members in sorted(clusters.items(), key=lambda x: -len(x[1])):
        lines.append(f"Cluster {cluster_id + 1} ({len(members)} conversations):")
        for cid in members[:5]:  # Show first 5
            title = _get_conversation_title(db, cid, max_len=40)
            lines.append(f"  {cid[:8]} {title}")
        if len(members) > 5:
            lines.append(f"  ... and {len(members) - 5} more")
        lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]


# --- Handler Dispatch Map ---

HANDLERS: Dict[str, callable] = {
    "find_similar": handle_find_similar,
    "semantic_search": handle_semantic_search,
    "get_network_summary": handle_get_network_summary,
    "get_clusters": handle_get_clusters,
}
