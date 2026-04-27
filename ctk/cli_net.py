#!/usr/bin/env python3
"""Network/similarity CLI commands.

As of 2.12.0 the analytical surface (similar, neighbors, clusters,
centrality, paths) moved into the ``ctk.network`` virtual MCP — the
LLM calls those tools during chat, no CLI subcommands needed. What
remains here are the two batch operations the user explicitly drives:

* ``ctk net embeddings`` — compute embeddings for the corpus
* ``ctk net links`` — build the similarity graph from those embeddings

Both write to the SQLite database; the MCP tools then read from it.
Run them once after import, again whenever the corpus changes.
"""

import logging

from ctk.core.database import ConversationDB

logger = logging.getLogger(__name__)


def add_net_commands(subparsers):
    """Register the slim ``ctk net`` subcommand group."""

    net_parser = subparsers.add_parser(
        "net",
        help="Build embeddings and similarity graph (analytical queries are tools)",
    )
    net_subparsers = net_parser.add_subparsers(
        dest="net_command", help="Operation"
    )

    embeddings_parser = net_subparsers.add_parser(
        "embeddings", help="Generate embeddings for conversations"
    )
    embeddings_parser.add_argument("--db", "-d", required=True, help="Database path")
    embeddings_parser.add_argument(
        "--provider", default="tfidf", help="Embedding provider (default: tfidf)"
    )
    embeddings_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed all conversations, ignoring cache",
    )
    embeddings_parser.add_argument(
        "--limit", type=int, help="Limit number of conversations to embed"
    )
    embeddings_parser.add_argument(
        "--search", help="Filter by keyword search in title/content"
    )
    embeddings_parser.add_argument(
        "--starred", action="store_true", help="Only starred conversations"
    )
    embeddings_parser.add_argument(
        "--pinned", action="store_true", help="Only pinned conversations"
    )
    embeddings_parser.add_argument(
        "--archived", action="store_true", help="Only archived conversations"
    )
    embeddings_parser.add_argument("--tags", help="Filter by tags (comma-separated)")
    embeddings_parser.add_argument(
        "--source", help="Filter by source (e.g., openai, anthropic)"
    )
    embeddings_parser.add_argument("--model", help="Filter by model name")

    links_parser = net_subparsers.add_parser(
        "links", help="Build a similarity graph from existing embeddings"
    )
    links_parser.add_argument("--db", "-d", required=True, help="Database path")
    links_parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.3,
        help="Minimum similarity for an edge (default: 0.3)",
    )
    links_parser.add_argument(
        "--max-links", type=int, default=10, help="Max edges per node (default: 10)"
    )
    links_parser.add_argument(
        "--rebuild", action="store_true", help="Force rebuild even if a graph exists"
    )


def cmd_embeddings(args):
    """Generate embeddings for conversations and persist them."""
    from rich.console import Console

    from ctk.core.similarity import (AggregationStrategy, ChunkingStrategy,
                                     ConversationEmbedder,
                                     ConversationEmbeddingConfig)

    console = Console()

    with ConversationDB(args.db) as db:
        filter_kwargs = {}
        if args.limit:
            filter_kwargs["limit"] = args.limit
        if args.starred:
            filter_kwargs["starred"] = True
        if args.pinned:
            filter_kwargs["pinned"] = True
        if args.archived:
            filter_kwargs["archived"] = True
        if args.source:
            filter_kwargs["source"] = args.source
        if args.model:
            filter_kwargs["model"] = args.model

        if args.search:
            conversations = db.search_conversations(args.search, **filter_kwargs)
        else:
            conversations = db.list_conversations(**filter_kwargs)

        if args.tags:
            tag_list = [t.strip() for t in args.tags.split(",")]
            conversations = [
                c
                for c in conversations
                if c.metadata
                and c.metadata.tags
                and any(tag in c.metadata.tags for tag in tag_list)
            ]

        console.print(f"Generating embeddings using {args.provider}...")
        console.print(f"Found {len(conversations)} conversations")

        if not conversations:
            console.print("[yellow]No conversations to embed[/yellow]")
            return 0

        config = ConversationEmbeddingConfig(
            provider=args.provider,
            chunking=ChunkingStrategy.MESSAGE,
            aggregation=AggregationStrategy.WEIGHTED_MEAN,
            role_weights={"user": 2.0, "assistant": 1.0, "system": 0.5},
            include_title=True,
            include_tags=True,
        )
        embedder = ConversationEmbedder(config)

        if args.provider == "tfidf":
            from ctk.core.similarity import extract_conversation_text

            console.print("Fitting TF-IDF on corpus...")
            corpus = [extract_conversation_text(conv) for conv in conversations]
            embedder.provider.fit(corpus)
            console.print(
                f"[green]✓[/green] Fitted with "
                f"{embedder.provider.vectorizer.max_features} features"
            )

        console.print("Embedding conversations...")
        embedded_count = 0
        model_name = config.model or config.provider

        for conv in conversations:
            if not args.force:
                cached = db.get_embedding(
                    conv.id, provider=config.provider, model=model_name
                )
                if cached is not None:
                    continue

            try:
                emb = embedder.embed_conversation(conv)
                db.save_embedding(
                    conversation_id=conv.id,
                    embedding=emb,
                    provider=config.provider,
                    model=model_name,
                    chunking_strategy=config.chunking.value,
                    aggregation_strategy=config.aggregation.value,
                    aggregation_weights=config.role_weights,
                )
                embedded_count += 1
            except Exception as e:
                console.print(f"[red]Error embedding {conv.id[:8]}: {e}[/red]")

        console.print(f"[green]✓[/green] Embedded {embedded_count} conversations")

        filters_dict = {
            k: v
            for k, v in {
                "search": args.search,
                "starred": args.starred,
                "pinned": args.pinned,
                "archived": args.archived,
                "tags": args.tags,
                "source": args.source,
                "model": args.model,
                "limit": args.limit,
            }.items()
            if v
        }

        session_id = db.save_embedding_session(
            provider=config.provider,
            chunking_strategy=config.chunking.value,
            aggregation_strategy=config.aggregation.value,
            num_conversations=len(conversations),
            model=model_name,
            role_weights=config.role_weights,
            filters=filters_dict if filters_dict else None,
            mark_current=True,
        )
        console.print(f"[green]✓[/green] Saved embedding session (ID: {session_id})")

    return 0


def cmd_links(args):
    """Build a similarity graph from existing embeddings."""
    from rich.console import Console

    from ctk.core.similarity import (AggregationStrategy, ChunkingStrategy,
                                     ConversationEmbedder,
                                     ConversationEmbeddingConfig,
                                     ConversationGraphBuilder,
                                     SimilarityComputer)

    console = Console()

    with ConversationDB(args.db) as db:
        existing_graph = db.get_current_graph()
        if existing_graph and not args.rebuild:
            console.print("Graph already exists:")
            console.print(f"  Created: {existing_graph['created_at']}")
            console.print(f"  Nodes: {existing_graph['num_nodes']}")
            console.print(f"  Edges: {existing_graph['num_edges']}")
            console.print(f"  Threshold: {existing_graph['threshold']}")
            console.print("\nUse --rebuild to force rebuild")
            return 0

        session = db.get_current_embedding_session()
        if not session:
            console.print(
                "[red]Error: No embedding session. Run 'ctk net embeddings' first.[/red]"
            )
            return 1

        console.print(f"Building graph from embedding session {session['id']}...")

        filters = session.get("filters") or {}
        filter_kwargs = {}
        if filters.get("starred"):
            filter_kwargs["starred"] = True
        if filters.get("pinned"):
            filter_kwargs["pinned"] = True
        if filters.get("archived"):
            filter_kwargs["archived"] = True
        if filters.get("source"):
            filter_kwargs["source"] = filters["source"]
        if filters.get("model"):
            filter_kwargs["model"] = filters["model"]
        if filters.get("limit"):
            filter_kwargs["limit"] = filters["limit"]

        if filters.get("search"):
            conversations = db.search_conversations(
                filters["search"], **filter_kwargs
            )
        else:
            conversations = db.list_conversations(**filter_kwargs)

        if filters.get("tags"):
            tag_list = [t.strip() for t in filters["tags"].split(",")]
            conversations = [
                c
                for c in conversations
                if c.metadata
                and c.metadata.tags
                and any(tag in c.metadata.tags for tag in tag_list)
            ]

        console.print(f"Found {len(conversations)} conversations")
        if len(conversations) < 2:
            console.print("[yellow]Need at least 2 conversations to build a graph[/yellow]")
            return 0

        console.print(
            f"Computing pairwise similarities (threshold={args.threshold})..."
        )

        config = ConversationEmbeddingConfig(
            provider=session["provider"],
            chunking=ChunkingStrategy.MESSAGE,
            aggregation=AggregationStrategy.WEIGHTED_MEAN,
            role_weights=session.get("role_weights") or {"user": 2.0, "assistant": 1.0},
            include_title=True,
            include_tags=True,
        )
        embedder = ConversationEmbedder(config)
        sim_computer = SimilarityComputer(embedder, db=db)
        graph_builder = ConversationGraphBuilder(sim_computer)

        conversation_ids = [c.id for c in conversations]
        graph = graph_builder.build_graph(
            conversations=conversation_ids,
            threshold=args.threshold,
            max_links_per_node=args.max_links,
            use_cache=True,
            show_progress=True,
        )

        console.print(
            f"[green]✓[/green] Built graph with {len(graph.nodes)} nodes "
            f"and {len(graph.links)} edges"
        )

        import json
        import os
        from datetime import datetime

        db_dir = os.path.dirname(os.path.abspath(args.db))
        graph_dir = os.path.join(db_dir, ".ctk_graphs")
        os.makedirs(graph_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        graph_file = os.path.join(graph_dir, f"graph_{timestamp}.json")
        with open(graph_file, "w") as f:
            json.dump(graph.to_dict(), f, indent=2)
        console.print(f"[green]✓[/green] Saved graph to {graph_file}")

        relative_path = os.path.relpath(graph_file, db_dir)
        db.save_current_graph(
            graph_file_path=relative_path,
            threshold=args.threshold,
            max_links_per_node=args.max_links,
            embedding_session_id=session["id"],
            num_nodes=len(graph.nodes),
            num_edges=len(graph.links),
        )
        console.print("[green]✓[/green] Graph metadata saved to database")
        console.print(
            "\nIn the TUI, you can now ask the model questions like "
            "'find conversations similar to this one'."
        )

    return 0
