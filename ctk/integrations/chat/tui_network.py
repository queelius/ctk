"""Network/similarity commands extracted from ChatTUI."""

import json
from typing import Optional, Tuple

import networkx as nx


def handle_net_command(
    db, args, current_conversation_id=None, navigator=None, vfs_cwd=None
):
    """Handle network/similarity subcommands.

    Args:
        db: ConversationDB instance
        args: Raw argument string after 'net' command
        current_conversation_id: Currently loaded conversation ID (optional)
        navigator: VFS navigator for prefix resolution (optional)
        vfs_cwd: Current VFS working directory (optional)
    """
    from rich.console import Console
    from rich.table import Table

    from ctk.core.similarity import (AggregationStrategy, ChunkingStrategy,
                                     ConversationEmbedder,
                                     ConversationEmbeddingConfig,
                                     SimilarityComputer, SimilarityMetric)
    from ctk.integrations.embeddings.tfidf import TFIDFEmbedding

    if not db:
        print("Error: No database configured")
        return

    parts = args.split(maxsplit=1)
    if not parts or not parts[0].strip():
        print("Usage: net <subcommand>")
        print(
            "Available: embeddings, similar, links, network, clusters, neighbors, path, central, outliers"
        )
        return

    subcmd = parts[0].lower()
    subargs = parts[1] if len(parts) > 1 else ""

    console = Console()

    if subcmd == "embeddings":
        _handle_embeddings(db, subargs, console)

    elif subcmd == "similar":
        _handle_similar(
            db, subargs, console, current_conversation_id, navigator, vfs_cwd
        )

    elif subcmd == "links":
        _handle_links(db, subargs, console)

    elif subcmd == "network":
        _handle_network(db, subargs)

    elif subcmd == "clusters":
        _handle_clusters(db, subargs)

    elif subcmd == "neighbors":
        _handle_neighbors(db, subargs, current_conversation_id, navigator, vfs_cwd)

    elif subcmd == "path":
        _handle_path(db, subargs, navigator)

    elif subcmd == "central":
        _handle_central(db, subargs)

    elif subcmd == "outliers":
        _handle_outliers(db, subargs)

    else:
        print(f"Unknown net subcommand: {subcmd}")
        print(
            "Available: embeddings, similar, links, network, clusters, neighbors, path, central, outliers"
        )


def _load_graph(db) -> Optional[Tuple[nx.Graph, dict]]:
    """Load graph from database, handling missing files gracefully.

    Returns:
        (graph, metadata) tuple, or None if graph unavailable.
    """
    from ctk.core.network_analysis import load_graph_from_file, resolve_graph_path

    graph_metadata = db.get_current_graph()
    if not graph_metadata:
        print("Error: No graph found. Run 'net links' first.")
        return None

    db_dir = db.db_dir.resolve() if db.db_dir else None
    graph_path = resolve_graph_path(db_dir, graph_metadata["graph_file_path"])
    try:
        G = load_graph_from_file(graph_path)
        return G, graph_metadata
    except FileNotFoundError:
        print(f"Error: Graph file not found: {graph_path}")
        print("Run 'net links --rebuild' to regenerate the graph")
        return None
    except (IOError, OSError, json.JSONDecodeError) as e:
        print(f"Error loading graph: {e}")
        return None


def _handle_embeddings(db, subargs, console):
    """Handle 'net embeddings' subcommand."""
    from ctk.core.similarity import (AggregationStrategy, ChunkingStrategy,
                                     ConversationEmbedder,
                                     ConversationEmbeddingConfig)

    # Parse options
    provider = "tfidf"
    force = False
    limit = None  # None = all conversations
    starred = None
    pinned = None
    tags = None
    source = None
    project = None
    model = None
    search = None

    if subargs:
        arg_parts = subargs.split()
        i = 0
        while i < len(arg_parts):
            arg = arg_parts[i]

            if arg == "--provider":
                if i + 1 >= len(arg_parts):
                    print("Error: --provider requires a value")
                    return
                provider = arg_parts[i + 1]
                i += 2
            elif arg == "--limit":
                if i + 1 >= len(arg_parts):
                    print("Error: --limit requires a value")
                    return
                try:
                    limit = int(arg_parts[i + 1])
                except ValueError:
                    print(
                        f"Error: --limit must be an integer, got '{arg_parts[i + 1]}'"
                    )
                    return
                i += 2
            elif arg == "--force":
                force = True
                i += 1
            elif arg == "--starred":
                starred = True
                i += 1
            elif arg == "--pinned":
                pinned = True
                i += 1
            elif arg == "--tags":
                if i + 1 >= len(arg_parts):
                    print("Error: --tags requires a value")
                    return
                tags = [t.strip() for t in arg_parts[i + 1].split(",")]
                i += 2
            elif arg == "--source":
                if i + 1 >= len(arg_parts):
                    print("Error: --source requires a value")
                    return
                source = arg_parts[i + 1]
                i += 2
            elif arg == "--project":
                if i + 1 >= len(arg_parts):
                    print("Error: --project requires a value")
                    return
                project = arg_parts[i + 1]
                i += 2
            elif arg == "--model":
                if i + 1 >= len(arg_parts):
                    print("Error: --model requires a value")
                    return
                model = arg_parts[i + 1]
                i += 2
            elif arg == "--search":
                if i + 1 >= len(arg_parts):
                    print("Error: --search requires a value")
                    return
                search = arg_parts[i + 1]
                i += 2
            else:
                print(f"Error: Unknown option '{arg}'")
                print(
                    "Valid options: --provider, --limit, --force, --starred, --pinned, --tags, --source, --project, --model, --search"
                )
                return

    # Build filter description
    filter_desc = []
    if starred:
        filter_desc.append("starred")
    if pinned:
        filter_desc.append("pinned")
    if tags:
        filter_desc.append(f"tags={','.join(tags)}")
    if source:
        filter_desc.append(f"source={source}")
    if project:
        filter_desc.append(f"project={project}")
    if model:
        filter_desc.append(f"model={model}")
    if search:
        filter_desc.append(f"search='{search}'")

    filter_str = f" ({', '.join(filter_desc)})" if filter_desc else ""
    print(f"Generating embeddings using {provider}{filter_str}...")

    # Configure embedder
    config = ConversationEmbeddingConfig(
        provider=provider,
        chunking=ChunkingStrategy.MESSAGE,
        aggregation=AggregationStrategy.WEIGHTED_MEAN,
        role_weights={"user": 2.0, "assistant": 1.0, "system": 0.5},
        include_title=True,
        include_tags=True,
        provider_config={"max_features": 5000, "ngram_range": [1, 2]},
    )

    embedder = ConversationEmbedder(config)

    # Get conversations with filters
    if search:
        conversations = db.search_conversations(
            query_text=search,
            limit=limit,
            starred=starred,
            pinned=pinned,
            tags=tags,
            source=source,
            project=project,
            model=model,
        )
    else:
        conversations = db.list_conversations(
            limit=limit,
            starred=starred,
            pinned=pinned,
            tags=tags,
            source=source,
            project=project,
            model=model,
        )

    if not conversations:
        print("No conversations found matching filters")
        return

    print(f"Found {len(conversations)} conversations")

    # Fit TF-IDF if using that provider
    if provider == "tfidf":
        from ctk.core.similarity import extract_conversation_text

        print("Fitting TF-IDF on corpus...")
        corpus_texts = []
        for conv_summary in conversations:
            conv = db.load_conversation(conv_summary.id)
            if conv:
                corpus_texts.append(extract_conversation_text(conv))

        embedder.provider.fit(corpus_texts)
        print(f"Fitted with {embedder.provider.get_dimensions()} features")

    # Embed conversations
    print("Embedding conversations...")
    count = 0
    skipped = 0
    for conv_summary in conversations:
        conv = db.load_conversation(conv_summary.id)
        if conv:
            # Check if already embedded
            if not force:
                existing = db.get_embedding(
                    conv.id,
                    model=provider,
                    provider=provider,
                    chunking_strategy="message",
                    aggregation_strategy="weighted_mean",
                )
                if existing is not None:
                    skipped += 1
                    continue

            embedding = embedder.embed_conversation(conv)
            db.save_embedding(
                conversation_id=conv.id,
                embedding=embedding,
                provider=provider,
                model=provider,
                chunking_strategy="message",
                aggregation_strategy="weighted_mean",
                aggregation_weights=config.role_weights,
            )
            count += 1

    if skipped > 0:
        print(f"Embedded {count} new, skipped {skipped} already embedded. Use --force to re-embed.")
    else:
        print(f"Embedded {count} conversations")

    # Save embedding session metadata
    filters_dict = {}
    if starred is not None:
        filters_dict["starred"] = starred
    if pinned is not None:
        filters_dict["pinned"] = pinned
    if tags is not None:
        filters_dict["tags"] = tags
    if source is not None:
        filters_dict["source"] = source
    if project is not None:
        filters_dict["project"] = project
    if model is not None:
        filters_dict["model"] = model
    if search is not None:
        filters_dict["search"] = search
    if limit is not None:
        filters_dict["limit"] = limit

    session_id = db.save_embedding_session(
        provider=provider,
        model=provider,  # For TF-IDF, model == provider
        chunking_strategy="message",
        aggregation_strategy="weighted_mean",
        num_conversations=len(conversations),
        role_weights=config.role_weights,
        filters=filters_dict if filters_dict else None,
        mark_current=True,
    )
    print(f"Saved embedding session (ID: {session_id})")


def _handle_similar(
    db, subargs, console, current_conversation_id=None, navigator=None, vfs_cwd=None
):
    """Handle 'net similar' subcommand."""
    import shlex

    from rich.table import Table

    from ctk.core.similarity import (AggregationStrategy, ChunkingStrategy,
                                     ConversationEmbedder,
                                     ConversationEmbeddingConfig,
                                     SimilarityComputer, SimilarityMetric)

    try:
        arg_parts = shlex.split(subargs) if subargs else []
    except ValueError:
        arg_parts = subargs.split() if subargs else []

    conv_id = None
    top_k = 10
    threshold = 0.0
    provider = "tfidf"

    # Parse arguments
    i = 0
    while i < len(arg_parts):
        arg = arg_parts[i]
        if arg == "--top-k":
            if i + 1 < len(arg_parts):
                try:
                    top_k = int(arg_parts[i + 1])
                    i += 2
                    continue
                except ValueError:
                    print(f"Error: Invalid top-k value: {arg_parts[i + 1]}")
                    return
        elif arg == "--threshold":
            if i + 1 < len(arg_parts):
                try:
                    threshold = float(arg_parts[i + 1])
                    i += 2
                    continue
                except ValueError:
                    print(f"Error: Invalid threshold value: {arg_parts[i + 1]}")
                    return
        elif arg == "--provider":
            if i + 1 < len(arg_parts):
                provider = arg_parts[i + 1]
                i += 2
                continue
        elif not arg.startswith("--"):
            conv_id = arg
            i += 1
        else:
            i += 1

    # Use current conversation if none specified
    if not conv_id:
        conv_id = current_conversation_id
        # Also try to get from VFS path if in a conversation directory
        if not conv_id and vfs_cwd:
            from ctk.core.vfs import PathType, VFSPathParser

            try:
                parsed = VFSPathParser.parse(vfs_cwd)
                if parsed.path_type in [
                    PathType.CONVERSATION_ROOT,
                    PathType.MESSAGE_NODE,
                ]:
                    conv_id = parsed.conversation_id
            except Exception:
                pass
        if not conv_id:
            print(
                "Error: No conversation specified and not in a conversation directory"
            )
            print("Usage: /net similar [conv_id] [--top-k N] [--threshold N]")
            return

    # Resolve prefix if needed
    if conv_id and len(conv_id) < 36:
        from ctk.core.vfs import VFSPathParser

        try:
            chats_path = VFSPathParser.parse("/chats")
            resolved = navigator.resolve_prefix(conv_id, chats_path)
            if resolved:
                conv_id = resolved
        except Exception:
            pass  # Use original conv_id if resolution fails

    # Load conversation
    query_conv = db.load_conversation(conv_id)
    if not query_conv:
        print(f"Error: Conversation not found: {conv_id}")
        return

    print(f"Finding conversations similar to: '{query_conv.title}'")

    # Setup similarity computer
    config = ConversationEmbeddingConfig(
        provider=provider,
        chunking=ChunkingStrategy.MESSAGE,
        aggregation=AggregationStrategy.WEIGHTED_MEAN,
        role_weights={"user": 2.0, "assistant": 1.0, "system": 0.5},
        provider_config={"max_features": 5000, "ngram_range": [1, 2]},
    )

    embedder = ConversationEmbedder(config)

    # Load and fit TF-IDF if needed
    if provider == "tfidf" and not embedder.provider.is_fitted:
        from ctk.core.similarity import extract_conversation_text

        conversations = db.list_conversations()
        corpus_texts = []
        for conv_summary in conversations:
            conv = db.load_conversation(conv_summary.id)
            if conv:
                corpus_texts.append(extract_conversation_text(conv))

        embedder.provider.fit(corpus_texts)

    similarity = SimilarityComputer(embedder, metric=SimilarityMetric.COSINE, db=db)

    # Find similar
    results = similarity.find_similar(
        query_conv, top_k=top_k, threshold=threshold, use_cache=True
    )

    if not results:
        print(f"No similar conversations found (threshold={threshold})")
        return

    # Display results in table
    table = Table(title=f"Similar Conversations (top {len(results)})")
    table.add_column("Rank", style="cyan", width=6)
    table.add_column("Similarity", style="green", width=12)
    table.add_column("Title", style="white")
    table.add_column("Tags", style="yellow")
    table.add_column("ID", style="dim", width=15)

    for i, result in enumerate(results, 1):
        similar_conv = db.load_conversation(result.conversation2_id)
        if similar_conv:
            tags_str = (
                ", ".join(similar_conv.metadata.tags)
                if similar_conv.metadata.tags
                else ""
            )
            table.add_row(
                str(i),
                f"{result.similarity:.3f}",
                similar_conv.title or "(untitled)",
                tags_str,
                result.conversation2_id[:12] + "...",
            )

    console.print(table)


def _handle_links(db, subargs, console):
    """Handle 'net links' subcommand."""
    from ctk.core.similarity import (AggregationStrategy, ChunkingStrategy,
                                     ConversationEmbedder,
                                     ConversationEmbeddingConfig)

    # Parse options
    threshold = 0.3  # Default similarity threshold
    max_links = 10  # Default max links per node
    rebuild = False  # Force rebuild

    if subargs:
        arg_parts = subargs.split()
        i = 0
        while i < len(arg_parts):
            arg = arg_parts[i]

            if arg == "--threshold":
                if i + 1 >= len(arg_parts):
                    print("Error: --threshold requires a value")
                    return
                try:
                    threshold = float(arg_parts[i + 1])
                except ValueError:
                    print(
                        f"Error: --threshold must be a number, got '{arg_parts[i + 1]}'"
                    )
                    return
                i += 2
            elif arg == "--max-links":
                if i + 1 >= len(arg_parts):
                    print("Error: --max-links requires a value")
                    return
                try:
                    max_links = int(arg_parts[i + 1])
                except ValueError:
                    print(
                        f"Error: --max-links must be an integer, got '{arg_parts[i + 1]}'"
                    )
                    return
                i += 2
            elif arg == "--rebuild":
                rebuild = True
                i += 1
            else:
                print(f"Error: Unknown option '{arg}'")
                print("Valid options: --threshold, --max-links, --rebuild")
                return

    # Check if graph already exists
    existing_graph = db.get_current_graph()
    if existing_graph and not rebuild:
        print("Graph already exists:")
        print(f"  Created: {existing_graph['created_at']}")
        print(f"  Nodes: {existing_graph['num_nodes']}")
        print(f"  Edges: {existing_graph['num_edges']}")
        print(f"  Threshold: {existing_graph['threshold']}")
        print(f"  File: {existing_graph['graph_file_path']}")
        print("\nUse --rebuild to force rebuild")
        return

    # Get current embedding session
    session = db.get_current_embedding_session()
    if not session:
        print("Error: No embedding session found. Run /net embeddings first.")
        return

    print(f"Building graph from embedding session {session['id']}...")

    # Get conversations using same filters as embedding session
    filters = session.get("filters") or {}
    print(f"Using filters: {filters if filters else 'none'}")

    if filters.get("search"):
        conversations = db.search_conversations(
            query_text=filters.get("search"),
            limit=filters.get("limit"),
            starred=filters.get("starred"),
            pinned=filters.get("pinned"),
            tags=filters.get("tags"),
            source=filters.get("source"),
            project=filters.get("project"),
            model=filters.get("model"),
        )
    else:
        conversations = db.list_conversations(
            limit=filters.get("limit"),
            starred=filters.get("starred"),
            pinned=filters.get("pinned"),
            tags=filters.get("tags"),
            source=filters.get("source"),
            project=filters.get("project"),
            model=filters.get("model"),
        )

    if not conversations:
        print("Error: No conversations found with current filters")
        return

    print(f"Found {len(conversations)} conversations")

    # Build graph
    print(f"Computing pairwise similarities (threshold={threshold})...")
    from ctk.core.similarity import (ConversationGraphBuilder,
                                     SimilarityComputer)

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
        threshold=threshold,
        max_links_per_node=max_links,
        use_cache=True,
        show_progress=True,
    )

    print(f"Graph: {len(graph.nodes)} nodes, {len(graph.links)} edges")

    # Save graph to file
    from datetime import datetime
    from pathlib import Path

    # Create graphs directory in database directory
    if db.db_dir:
        db_dir = db.db_dir.resolve()
    else:
        db_dir = Path.cwd()

    graphs_dir = db_dir / "graphs"
    graphs_dir.mkdir(exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    graph_filename = f"graph_{timestamp}.json"
    graph_path = graphs_dir / graph_filename

    # Save graph
    with open(graph_path, "w") as f:
        json.dump(graph.to_dict(), f, indent=2)

    print(f"Saved to: {graph_path}")

    # Store path relative to db_dir so it survives directory moves
    relative_path = str(graph_path.relative_to(db_dir))

    # Save graph metadata to database
    db.save_current_graph(
        graph_file_path=relative_path,
        threshold=threshold,
        max_links_per_node=max_links,
        embedding_session_id=session["id"],
        num_nodes=len(graph.nodes),
        num_edges=len(graph.links),
    )

    print("Graph metadata saved to database")
    print(f"\nUse /net network to view global statistics")


def _handle_network(db, subargs):
    """Handle 'net network' subcommand."""
    rebuild = False

    if subargs:
        if "--rebuild" in subargs:
            rebuild = True

    # Get current graph
    graph_metadata = db.get_current_graph()
    if not graph_metadata:
        print("Error: No graph found. Run 'net links' first to build a graph.")
        return

    # Check if metrics already computed
    if graph_metadata.get("density") is not None and not rebuild:
        from ctk.core.network_analysis import format_network_stats

        stats_str = format_network_stats(graph_metadata)
        print(stats_str)
        return

    # Need to compute metrics
    print("Computing network statistics...")

    from ctk.core.network_analysis import (compute_global_metrics,
                                           format_network_stats,
                                           load_graph_from_file,
                                           resolve_graph_path,
                                           save_network_metrics_to_db)

    # Load graph from file
    db_dir = db.db_dir.resolve() if db.db_dir else None
    graph_path = resolve_graph_path(db_dir, graph_metadata["graph_file_path"])
    try:
        G = load_graph_from_file(graph_path)
    except FileNotFoundError:
        print(f"Error: Graph file not found: {graph_path}")
        print("Run 'net links --rebuild' to regenerate the graph")
        return
    except Exception as e:
        print(f"Error loading graph: {e}")
        return

    # Compute metrics
    metrics = compute_global_metrics(G)

    # Save to database
    save_network_metrics_to_db(db, metrics)

    # Reload metadata (now with cached metrics)
    graph_metadata = db.get_current_graph()

    # Display
    stats_str = format_network_stats(graph_metadata, G)
    print(stats_str)


def _handle_clusters(db, subargs):
    """Handle 'net clusters' subcommand."""
    # Parse options
    algorithm = "louvain"
    min_size = 2

    if subargs:
        arg_parts = subargs.split()
        i = 0
        while i < len(arg_parts):
            arg = arg_parts[i]
            if arg == "--algorithm" and i + 1 < len(arg_parts):
                algorithm = arg_parts[i + 1]
                i += 2
            elif arg == "--min-size" and i + 1 < len(arg_parts):
                try:
                    min_size = int(arg_parts[i + 1])
                except ValueError:
                    print(f"Error: --min-size must be an integer")
                    return
                i += 2
            else:
                i += 1

    # Load graph
    result = _load_graph(db)
    if result is None:
        return
    G, graph_metadata = result

    print(f"Detecting communities using {algorithm}...")

    if algorithm == "louvain":
        try:
            communities = nx.community.louvain_communities(G, seed=42)
        except AttributeError:
            from networkx.algorithms.community import \
                greedy_modularity_communities

            communities = list(greedy_modularity_communities(G))
    elif algorithm == "label_propagation":
        from networkx.algorithms.community import label_propagation_communities

        communities = list(label_propagation_communities(G))
    else:
        from networkx.algorithms.community import greedy_modularity_communities

        communities = list(greedy_modularity_communities(G))

    # Filter and sort
    communities = [c for c in communities if len(c) >= min_size]
    communities = sorted(communities, key=len, reverse=True)

    if not communities:
        print("No communities found with minimum size")
        return

    print(f"\nFound {len(communities)} communities\n")

    for i, community in enumerate(communities, 1):
        print(f"Community {i} ({len(community)} conversations)")
        for conv_id in list(community)[:5]:
            conv = db.load_conversation(conv_id)
            title = conv.title if conv else "(untitled)"
            print(f"  {conv_id[:8]}... {title[:50]}")
        if len(community) > 5:
            print(f"  ... and {len(community) - 5} more")
        print()


def _handle_neighbors(
    db, subargs, current_conversation_id=None, navigator=None, vfs_cwd=None
):
    """Handle 'net neighbors' subcommand."""
    # Parse options
    conv_id = None
    depth = 1

    if subargs:
        arg_parts = subargs.split()
        i = 0
        while i < len(arg_parts):
            arg = arg_parts[i]
            if arg == "--depth" and i + 1 < len(arg_parts):
                try:
                    depth = int(arg_parts[i + 1])
                except ValueError:
                    print("Error: --depth must be an integer")
                    return
                i += 2
            elif not arg.startswith("--"):
                conv_id = arg
                i += 1
            else:
                i += 1

    # Use current conversation if not specified
    if not conv_id:
        conv_id = current_conversation_id
        if not conv_id and vfs_cwd:
            from ctk.core.vfs import PathType, VFSPathParser

            try:
                parsed = VFSPathParser.parse(vfs_cwd)
                if parsed.path_type in [
                    PathType.CONVERSATION_ROOT,
                    PathType.MESSAGE_NODE,
                ]:
                    conv_id = parsed.conversation_id
            except Exception:
                pass
        if not conv_id:
            print("Error: No conversation specified")
            return

    # Resolve prefix
    if len(conv_id) < 36:
        from ctk.core.vfs import VFSPathParser

        try:
            chats_path = VFSPathParser.parse("/chats")
            resolved = navigator.resolve_prefix(conv_id, chats_path)
            if resolved:
                conv_id = resolved
            else:
                # Try direct DB lookup
                all_convs = db.list_conversations(limit=10000)
                matches = [c for c in all_convs if c.id.startswith(conv_id)]
                if len(matches) == 1:
                    conv_id = matches[0].id
                elif len(matches) > 1:
                    print(f"Ambiguous prefix '{conv_id}', matches:")
                    for m in matches[:5]:
                        print(f"  {m.id[:12]}... {m.title or '(untitled)'}")
                    return
                else:
                    print(f"No conversation found with prefix: {conv_id}")
                    return
        except Exception as e:
            # Fallback to direct DB lookup
            all_convs = db.list_conversations(limit=10000)
            matches = [c for c in all_convs if c.id.startswith(conv_id)]
            if len(matches) == 1:
                conv_id = matches[0].id
            elif len(matches) > 1:
                print(f"Ambiguous prefix '{conv_id}', matches:")
                for m in matches[:5]:
                    print(f"  {m.id[:12]}... {m.title or '(untitled)'}")
                return
            else:
                print(f"No conversation found with prefix: {conv_id}")
                return

    # Load graph
    result = _load_graph(db)
    if result is None:
        return
    G, graph_metadata = result

    if conv_id not in G:
        print(f"Conversation {conv_id[:8]}... not in graph")
        return

    # Get neighbors
    if depth == 1:
        neighbors = set(G.neighbors(conv_id))
    else:
        neighbors = set()
        current_level = {conv_id}
        for _ in range(depth):
            next_level = set()
            for node in current_level:
                next_level.update(G.neighbors(node))
            neighbors.update(next_level)
            current_level = next_level - {conv_id}
        neighbors.discard(conv_id)

    source_conv = db.load_conversation(conv_id)
    source_title = source_conv.title if source_conv else "(untitled)"

    print(f"\nNeighbors of: {source_title} ({conv_id[:8]}...)")
    print(f"Depth: {depth}, Found: {len(neighbors)}\n")

    if not neighbors:
        print("No neighbors found")
        return

    # Display with weights
    neighbor_data = []
    for nid in neighbors:
        conv = db.load_conversation(nid)
        title = conv.title if conv else "(untitled)"
        weight = G[conv_id][nid].get("weight", 0) if G.has_edge(conv_id, nid) else 0
        neighbor_data.append((nid, title, weight))

    neighbor_data.sort(key=lambda x: x[2], reverse=True)

    for nid, title, weight in neighbor_data[:20]:
        weight_str = f"{weight:.3f}" if weight > 0 else "-"
        print(f"  {nid[:8]}... [{weight_str}] {title[:45]}")

    if len(neighbors) > 20:
        print(f"\n... and {len(neighbors) - 20} more")


def _handle_path(db, subargs, navigator=None):
    """Handle 'net path' subcommand."""
    # Parse source and target
    if not subargs or len(subargs.split()) < 2:
        print("Error: path requires source and target IDs")
        print("Usage: net path <source> <target>")
        return

    parts = subargs.split()
    source_arg = parts[0]
    target_arg = parts[1]

    # Resolve prefixes
    from ctk.core.vfs import VFSPathParser

    chats_path = VFSPathParser.parse("/chats")

    source_id = source_arg
    if len(source_arg) < 36:
        try:
            resolved = navigator.resolve_prefix(source_arg, chats_path)
            if resolved:
                source_id = resolved
        except Exception:
            pass

    target_id = target_arg
    if len(target_arg) < 36:
        try:
            resolved = navigator.resolve_prefix(target_arg, chats_path)
            if resolved:
                target_id = resolved
        except Exception:
            pass

    # Load graph
    result = _load_graph(db)
    if result is None:
        return
    G, graph_metadata = result

    if source_id not in G:
        print(f"Source {source_id[:8]}... not in graph")
        return
    if target_id not in G:
        print(f"Target {target_id[:8]}... not in graph")
        return

    # Find path
    try:
        path = nx.shortest_path(G, source_id, target_id)
    except nx.NetworkXNoPath:
        print("No path exists between these conversations")
        return

    print(f"\nPath found with {len(path)} steps:\n")

    for i, cid in enumerate(path):
        conv = db.load_conversation(cid)
        title = conv.title if conv else "(untitled)"
        marker = "●" if i == 0 or i == len(path) - 1 else "○"
        prefix = "→ " if i > 0 else "  "
        print(f"{prefix}{marker} {cid[:8]}... {title[:50]}")

        if i < len(path) - 1:
            next_id = path[i + 1]
            if G.has_edge(cid, next_id):
                weight = G[cid][next_id].get("weight", 0)
                print(f"     similarity: {weight:.3f}")


def _handle_central(db, subargs):
    """Handle 'net central' subcommand."""
    # Parse options
    metric = "degree"
    top_k = 10

    if subargs:
        arg_parts = subargs.split()
        i = 0
        while i < len(arg_parts):
            arg = arg_parts[i]
            if arg == "--metric" and i + 1 < len(arg_parts):
                metric = arg_parts[i + 1]
                i += 2
            elif arg == "--top-k" and i + 1 < len(arg_parts):
                try:
                    top_k = int(arg_parts[i + 1])
                except ValueError:
                    print("Error: --top-k must be an integer")
                    return
                i += 2
            else:
                i += 1

    # Load graph
    result = _load_graph(db)
    if result is None:
        return
    G, graph_metadata = result

    print(f"Computing {metric} centrality...")

    if metric == "degree":
        centrality = nx.degree_centrality(G)
    elif metric == "betweenness":
        centrality = nx.betweenness_centrality(G)
    elif metric == "pagerank":
        centrality = nx.pagerank(G)
    elif metric == "eigenvector":
        try:
            centrality = nx.eigenvector_centrality(G, max_iter=1000)
        except nx.PowerIterationFailedConvergence:
            print("Eigenvector centrality failed, using degree")
            centrality = nx.degree_centrality(G)
    else:
        print(f"Unknown metric: {metric}")
        return

    sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)

    print(f"\nTop {top_k} by {metric} centrality:\n")

    for i, (cid, score) in enumerate(sorted_nodes[:top_k], 1):
        conv = db.load_conversation(cid)
        title = conv.title if conv else "(untitled)"
        print(f"  {i:2}. [{score:.4f}] {cid[:8]}... {title[:45]}")


def _handle_outliers(db, subargs):
    """Handle 'net outliers' subcommand."""
    # Parse options
    top_k = 10

    if subargs:
        arg_parts = subargs.split()
        i = 0
        while i < len(arg_parts):
            arg = arg_parts[i]
            if arg == "--top-k" and i + 1 < len(arg_parts):
                try:
                    top_k = int(arg_parts[i + 1])
                except ValueError:
                    print("Error: --top-k must be an integer")
                    return
                i += 2
            else:
                i += 1

    # Load graph
    result = _load_graph(db)
    if result is None:
        return
    G, graph_metadata = result

    centrality = nx.degree_centrality(G)
    sorted_nodes = sorted(centrality.items(), key=lambda x: x[1])

    print(f"\nTop {top_k} outliers (least connected):\n")

    for i, (cid, score) in enumerate(sorted_nodes[:top_k], 1):
        conv = db.load_conversation(cid)
        title = conv.title if conv else "(untitled)"
        degree = G.degree(cid)
        print(f"  {i:2}. [degree={degree}] {cid[:8]}... {title[:45]}")

    isolated = list(nx.isolates(G))
    if isolated:
        print(f"\nFound {len(isolated)} completely isolated nodes")
