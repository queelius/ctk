#!/usr/bin/env python3
"""
Network/similarity CLI commands for CTK
Implements conversation embedding, similarity search, and graph analysis
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, List
import logging

from ctk.core.database import ConversationDB

logger = logging.getLogger(__name__)


def add_net_commands(subparsers):
    """Add network/similarity commands to CLI"""

    net_parser = subparsers.add_parser(
        'net',
        help='Network and similarity operations (embeddings, similar, links, network)'
    )

    net_subparsers = net_parser.add_subparsers(
        dest='net_command',
        help='Network operation to perform'
    )

    # EMBEDDINGS command
    embeddings_parser = net_subparsers.add_parser(
        'embeddings',
        help='Generate embeddings for conversations'
    )
    embeddings_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )
    embeddings_parser.add_argument(
        '--provider',
        default='tfidf',
        help='Embedding provider (default: tfidf)'
    )
    embeddings_parser.add_argument(
        '--force',
        action='store_true',
        help='Re-embed all conversations, ignoring cache'
    )
    embeddings_parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of conversations to embed'
    )
    embeddings_parser.add_argument(
        '--search',
        help='Filter by keyword search in title/content'
    )
    embeddings_parser.add_argument(
        '--starred',
        action='store_true',
        help='Only starred conversations'
    )
    embeddings_parser.add_argument(
        '--pinned',
        action='store_true',
        help='Only pinned conversations'
    )
    embeddings_parser.add_argument(
        '--archived',
        action='store_true',
        help='Only archived conversations'
    )
    embeddings_parser.add_argument(
        '--tags',
        help='Filter by tags (comma-separated)'
    )
    embeddings_parser.add_argument(
        '--source',
        help='Filter by source (e.g., openai, anthropic)'
    )
    embeddings_parser.add_argument(
        '--model',
        help='Filter by model name'
    )

    # SIMILAR command
    similar_parser = net_subparsers.add_parser(
        'similar',
        help='Find conversations similar to a given conversation'
    )
    similar_parser.add_argument(
        'id',
        nargs='?',
        help='Conversation ID (full or partial)'
    )
    similar_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )
    similar_parser.add_argument(
        '--top-k', '-k',
        type=int,
        default=10,
        help='Number of results (default: 10)'
    )
    similar_parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.0,
        help='Minimum similarity score (default: 0.0)'
    )
    similar_parser.add_argument(
        '--provider',
        default='tfidf',
        help='Embedding provider (default: tfidf)'
    )

    # LINKS command
    links_parser = net_subparsers.add_parser(
        'links',
        help='Build a graph of conversation relationships'
    )
    links_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )
    links_parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.3,
        help='Minimum similarity for edge (default: 0.3)'
    )
    links_parser.add_argument(
        '--max-links',
        type=int,
        default=10,
        help='Max edges per node (default: 10)'
    )
    links_parser.add_argument(
        '--rebuild',
        action='store_true',
        help='Force rebuild even if graph exists'
    )

    # NETWORK command
    network_parser = net_subparsers.add_parser(
        'network',
        help='Display network statistics for current graph'
    )
    network_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )
    network_parser.add_argument(
        '--rebuild',
        action='store_true',
        help='Recompute metrics even if cached'
    )

    # CLUSTERS command (community detection)
    clusters_parser = net_subparsers.add_parser(
        'clusters',
        help='Detect conversation communities/clusters'
    )
    clusters_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )
    clusters_parser.add_argument(
        '--algorithm',
        choices=['louvain', 'label_propagation', 'greedy'],
        default='louvain',
        help='Community detection algorithm (default: louvain)'
    )
    clusters_parser.add_argument(
        '--min-size',
        type=int,
        default=2,
        help='Minimum cluster size to report (default: 2)'
    )

    # NEIGHBORS command
    neighbors_parser = net_subparsers.add_parser(
        'neighbors',
        help='Show neighbors of a conversation in the graph'
    )
    neighbors_parser.add_argument(
        'id',
        help='Conversation ID (full or partial)'
    )
    neighbors_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )
    neighbors_parser.add_argument(
        '--depth',
        type=int,
        default=1,
        help='Depth of neighbors to show (default: 1)'
    )

    # PATH command
    path_parser = net_subparsers.add_parser(
        'path',
        help='Find shortest path between two conversations'
    )
    path_parser.add_argument(
        'source',
        help='Source conversation ID'
    )
    path_parser.add_argument(
        'target',
        help='Target conversation ID'
    )
    path_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )

    # CENTRAL command
    central_parser = net_subparsers.add_parser(
        'central',
        help='Find most central/connected conversations'
    )
    central_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )
    central_parser.add_argument(
        '--metric',
        choices=['degree', 'betweenness', 'pagerank', 'eigenvector'],
        default='degree',
        help='Centrality metric (default: degree)'
    )
    central_parser.add_argument(
        '--top-k', '-k',
        type=int,
        default=10,
        help='Number of top conversations to show (default: 10)'
    )

    # OUTLIERS command
    outliers_parser = net_subparsers.add_parser(
        'outliers',
        help='Find least connected/isolated conversations'
    )
    outliers_parser.add_argument(
        '--db', '-d',
        required=True,
        help='Database path'
    )
    outliers_parser.add_argument(
        '--top-k', '-k',
        type=int,
        default=10,
        help='Number of outliers to show (default: 10)'
    )


def cmd_embeddings(args):
    """Generate embeddings for conversations"""
    from rich.console import Console
    from ctk.core.similarity import (
        ConversationEmbedder,
        ConversationEmbeddingConfig,
        ChunkingStrategy,
        AggregationStrategy,
    )

    console = Console()

    with ConversationDB(args.db) as db:
        # Build filter kwargs
        filter_kwargs = {}
        if args.limit:
            filter_kwargs['limit'] = args.limit
        if args.starred:
            filter_kwargs['starred'] = True
        if args.pinned:
            filter_kwargs['pinned'] = True
        if args.archived:
            filter_kwargs['archived'] = True
        if args.source:
            filter_kwargs['source'] = args.source
        if args.model:
            filter_kwargs['model'] = args.model

        # Get conversations
        if args.search:
            conversations = db.search_conversations(args.search, **filter_kwargs)
        else:
            conversations = db.list_conversations(**filter_kwargs)

        if args.tags:
            tag_list = [t.strip() for t in args.tags.split(',')]
            conversations = [c for c in conversations
                          if c.metadata and c.metadata.tags
                          and any(tag in c.metadata.tags for tag in tag_list)]

        console.print(f"Generating embeddings using {args.provider}...")
        console.print(f"Found {len(conversations)} conversations")

        if not conversations:
            console.print("[yellow]No conversations to embed[/yellow]")
            return 0

        # Setup embedder
        config = ConversationEmbeddingConfig(
            provider=args.provider,
            chunking=ChunkingStrategy.MESSAGE,
            aggregation=AggregationStrategy.WEIGHTED_MEAN,
            role_weights={"user": 2.0, "assistant": 1.0, "system": 0.5},
            include_title=True,
            include_tags=True
        )

        embedder = ConversationEmbedder(config)

        # Fit TF-IDF if needed
        if args.provider == "tfidf":
            console.print("Fitting TF-IDF on corpus...")
            corpus = []
            for conv in conversations:
                text_parts = []
                if conv.title:
                    text_parts.append(conv.title)
                for msg in conv.message_map.values():
                    if hasattr(msg.content, 'get_text'):
                        text_parts.append(msg.content.get_text())
                    elif hasattr(msg.content, 'text'):
                        text_parts.append(msg.content.text)
                corpus.append(' '.join(text_parts))

            embedder.provider.fit(corpus)
            console.print(f"[green]✓[/green] Fitted with {embedder.provider.vectorizer.max_features} features")

        # Embed conversations
        console.print("Embedding conversations...")
        embedded_count = 0
        model_name = config.model or config.provider

        for conv in conversations:
            # Check cache unless force
            if not args.force:
                cached = db.get_embedding(
                    conv.id,
                    provider=config.provider,
                    model=model_name
                )
                if cached is not None:
                    continue

            # Embed and save
            try:
                emb = embedder.embed_conversation(conv)
                db.save_embedding(
                    conversation_id=conv.id,
                    embedding=emb,
                    provider=config.provider,
                    model=model_name,
                    chunking_strategy=config.chunking.value,
                    aggregation_strategy=config.aggregation.value,
                    aggregation_weights=config.role_weights
                )
                embedded_count += 1
            except Exception as e:
                console.print(f"[red]Error embedding {conv.id[:8]}: {e}[/red]")

        console.print(f"[green]✓[/green] Embedded {embedded_count} conversations")

        # Save embedding session
        filters_dict = {
            'search': args.search,
            'starred': args.starred,
            'pinned': args.pinned,
            'archived': args.archived,
            'tags': args.tags,
            'source': args.source,
            'model': args.model,
            'limit': args.limit,
        }
        filters_dict = {k: v for k, v in filters_dict.items() if v}

        session_id = db.save_embedding_session(
            provider=config.provider,
            chunking_strategy=config.chunking.value,
            aggregation_strategy=config.aggregation.value,
            num_conversations=len(conversations),
            model=model_name,
            role_weights=config.role_weights,
            filters=filters_dict if filters_dict else None,
            mark_current=True
        )

        console.print(f"[green]✓[/green] Saved embedding session (ID: {session_id})")

    return 0


def cmd_similar(args):
    """Find similar conversations"""
    from rich.console import Console
    from rich.table import Table
    from ctk.core.similarity import (
        ConversationEmbedder,
        ConversationEmbeddingConfig,
        SimilarityComputer,
        SimilarityMetric,
        ChunkingStrategy,
        AggregationStrategy,
    )

    console = Console()

    if not args.id:
        console.print("[red]Error: Conversation ID required[/red]")
        console.print("Usage: ctk net similar <id> [--top-k N]")
        return 1

    with ConversationDB(args.db) as db:
        # Resolve conversation ID (prefix matching)
        conv_id = args.id
        if len(conv_id) < 36:
            # Try prefix match
            all_convs = db.list_conversations(limit=10000)
            matches = [c for c in all_convs if c.id.startswith(conv_id)]
            if len(matches) == 1:
                conv_id = matches[0].id
            elif len(matches) > 1:
                console.print(f"[yellow]Ambiguous prefix '{conv_id}', matches:[/yellow]")
                for m in matches[:5]:
                    console.print(f"  {m.id[:12]}... {m.title or '(untitled)'}")
                return 1
            elif len(matches) == 0:
                console.print(f"[red]No conversation found with prefix: {conv_id}[/red]")
                return 1

        # Load query conversation
        query_conv = db.load_conversation(conv_id)
        if not query_conv:
            console.print(f"[red]Conversation not found: {conv_id}[/red]")
            return 1

        console.print(f"Finding conversations similar to: '{query_conv.title or '(untitled)'}'")

        # Setup embedder and similarity computer
        config = ConversationEmbeddingConfig(
            provider=args.provider,
            chunking=ChunkingStrategy.MESSAGE,
            aggregation=AggregationStrategy.WEIGHTED_MEAN,
            role_weights={"user": 2.0, "assistant": 1.0, "system": 0.5}
        )

        embedder = ConversationEmbedder(config)
        similarity = SimilarityComputer(embedder, metric=SimilarityMetric.COSINE, db=db)

        # Find similar
        try:
            results = similarity.find_similar(
                query_conv,
                top_k=args.top_k,
                threshold=args.threshold,
                use_cache=True
            )
        except Exception as e:
            if "not fitted" in str(e).lower():
                console.print("[red]Error: TF-IDF not fitted. Run 'ctk net embeddings' first.[/red]")
            else:
                console.print(f"[red]Error: {e}[/red]")
            return 1

        if not results:
            console.print("[yellow]No similar conversations found[/yellow]")
            return 0

        # Display results
        table = Table(title=f"Similar Conversations (top {len(results)})")
        table.add_column("Rank", style="dim", width=4)
        table.add_column("Score", style="cyan", width=6)
        table.add_column("ID", style="dim", width=10)
        table.add_column("Title", style="white")

        for i, (conv, score) in enumerate(results, 1):
            conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv
            title = conv_dict.get('title', '(untitled)')[:50]
            table.add_row(
                str(i),
                f"{score:.3f}",
                conv_dict['id'][:8] + "...",
                title
            )

        console.print(table)

    return 0


def cmd_links(args):
    """Build conversation similarity graph"""
    from rich.console import Console
    from ctk.core.similarity import (
        ConversationEmbedder,
        ConversationEmbeddingConfig,
        SimilarityComputer,
        ConversationGraphBuilder,
        ChunkingStrategy,
        AggregationStrategy,
    )

    console = Console()

    with ConversationDB(args.db) as db:
        # Check for existing graph
        existing_graph = db.get_current_graph()
        if existing_graph and not args.rebuild:
            console.print("Graph already exists:")
            console.print(f"  Created: {existing_graph['created_at']}")
            console.print(f"  Nodes: {existing_graph['num_nodes']}")
            console.print(f"  Edges: {existing_graph['num_edges']}")
            console.print(f"  Threshold: {existing_graph['threshold']}")
            console.print("\nUse --rebuild to force rebuild")
            return 0

        # Get current embedding session
        session = db.get_current_embedding_session()
        if not session:
            console.print("[red]Error: No embedding session found. Run 'ctk net embeddings' first.[/red]")
            return 1

        console.print(f"Building graph from embedding session {session['id']}...")

        # Get conversations based on session filters
        filters = session.get('filters') or {}
        filter_kwargs = {}
        if filters.get('starred'):
            filter_kwargs['starred'] = True
        if filters.get('pinned'):
            filter_kwargs['pinned'] = True
        if filters.get('archived'):
            filter_kwargs['archived'] = True
        if filters.get('source'):
            filter_kwargs['source'] = filters['source']
        if filters.get('model'):
            filter_kwargs['model'] = filters['model']
        if filters.get('limit'):
            filter_kwargs['limit'] = filters['limit']

        if filters.get('search'):
            conversations = db.search_conversations(filters['search'], **filter_kwargs)
        else:
            conversations = db.list_conversations(**filter_kwargs)

        if filters.get('tags'):
            tag_list = [t.strip() for t in filters['tags'].split(',')]
            conversations = [c for c in conversations
                          if c.metadata and c.metadata.tags
                          and any(tag in c.metadata.tags for tag in tag_list)]

        filter_desc = ', '.join(f"{k}={v}" for k, v in filters.items()) if filters else "none"
        console.print(f"Using filters: {filter_desc}")
        console.print(f"Found {len(conversations)} conversations")

        if len(conversations) < 2:
            console.print("[yellow]Need at least 2 conversations to build graph[/yellow]")
            return 0

        # Build graph
        console.print(f"Computing pairwise similarities (threshold={args.threshold})...")

        config = ConversationEmbeddingConfig(
            provider=session['provider'],
            chunking=ChunkingStrategy.MESSAGE,
            aggregation=AggregationStrategy.WEIGHTED_MEAN,
            role_weights=session.get('role_weights') or {"user": 2.0, "assistant": 1.0},
            include_title=True,
            include_tags=True
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
            show_progress=True
        )

        console.print(f"[green]✓[/green] Built graph with {len(graph.nodes)} nodes and {len(graph.links)} edges")

        # Save graph
        import tempfile
        import os
        graph_dir = os.path.join(os.path.dirname(args.db), '.ctk_graphs')
        os.makedirs(graph_dir, exist_ok=True)

        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        graph_file = os.path.join(graph_dir, f'graph_{timestamp}.json')

        graph.save(graph_file)
        console.print(f"[green]✓[/green] Saved graph to {graph_file}")

        # Save metadata to database
        db.save_graph_metadata(
            graph_file_path=graph_file,
            threshold=args.threshold,
            max_links_per_node=args.max_links,
            embedding_session_id=session['id'],
            num_nodes=len(graph.nodes),
            num_edges=len(graph.links)
        )

        console.print("[green]✓[/green] Graph metadata saved to database")
        console.print(f"\nUse 'ctk net network' to view global statistics")

    return 0


def cmd_network(args):
    """Display network statistics"""
    from rich.console import Console

    console = Console()

    with ConversationDB(args.db) as db:
        # Get current graph
        graph_metadata = db.get_current_graph()
        if not graph_metadata:
            console.print("[red]Error: No graph found. Run 'ctk net links' first to build a graph.[/red]")
            return 1

        # Check if metrics already computed
        if graph_metadata.get('density') is not None and not args.rebuild:
            from ctk.core.network_analysis import format_network_stats
            stats_str = format_network_stats(graph_metadata)
            console.print(stats_str)
            return 0

        # Need to compute metrics
        console.print("Computing network statistics...")

        from ctk.core.network_analysis import (
            load_graph_from_file,
            compute_global_metrics,
            save_network_metrics_to_db,
            format_network_stats
        )

        # Load graph from file
        graph_path = graph_metadata['graph_file_path']
        try:
            G = load_graph_from_file(graph_path)
        except FileNotFoundError:
            console.print(f"[red]Error: Graph file not found: {graph_path}[/red]")
            console.print("Run 'ctk net links --rebuild' to regenerate the graph")
            return 1
        except Exception as e:
            console.print(f"[red]Error loading graph: {e}[/red]")
            return 1

        # Compute metrics
        metrics = compute_global_metrics(G)

        # Save to database
        save_network_metrics_to_db(db, metrics)

        # Reload metadata (now with cached metrics)
        graph_metadata = db.get_current_graph()
        stats_str = format_network_stats(graph_metadata, G)
        console.print(stats_str)

    return 0


def _load_graph(db, console):
    """Helper to load graph from database"""
    from ctk.core.network_analysis import load_graph_from_file

    graph_metadata = db.get_current_graph()
    if not graph_metadata:
        console.print("[red]Error: No graph found. Run 'ctk net links' first.[/red]")
        return None, None

    graph_path = graph_metadata['graph_file_path']
    try:
        G = load_graph_from_file(graph_path)
        return G, graph_metadata
    except FileNotFoundError:
        console.print(f"[red]Error: Graph file not found: {graph_path}[/red]")
        console.print("Run 'ctk net links --rebuild' to regenerate")
        return None, None
    except Exception as e:
        console.print(f"[red]Error loading graph: {e}[/red]")
        return None, None


def _resolve_conv_id(db, conv_id_arg, console):
    """Helper to resolve conversation ID prefix"""
    if len(conv_id_arg) >= 36:
        return conv_id_arg

    all_convs = db.list_conversations(limit=10000)
    matches = [c for c in all_convs if c.id.startswith(conv_id_arg)]

    if len(matches) == 1:
        return matches[0].id
    elif len(matches) > 1:
        console.print(f"[yellow]Ambiguous prefix '{conv_id_arg}', matches:[/yellow]")
        for m in matches[:5]:
            console.print(f"  {m.id[:12]}... {m.title or '(untitled)'}")
        return None
    else:
        console.print(f"[red]No conversation found with prefix: {conv_id_arg}[/red]")
        return None


def cmd_clusters(args):
    """Detect conversation communities/clusters"""
    from rich.console import Console
    from rich.table import Table
    import networkx as nx

    console = Console()

    with ConversationDB(args.db) as db:
        G, graph_metadata = _load_graph(db, console)
        if G is None:
            return 1

        console.print(f"Detecting communities using {args.algorithm}...")

        # Community detection
        if args.algorithm == 'louvain':
            try:
                communities = nx.community.louvain_communities(G, seed=42)
            except AttributeError:
                # Older networkx versions
                from networkx.algorithms.community import greedy_modularity_communities
                communities = list(greedy_modularity_communities(G))
        elif args.algorithm == 'label_propagation':
            from networkx.algorithms.community import label_propagation_communities
            communities = list(label_propagation_communities(G))
        elif args.algorithm == 'greedy':
            from networkx.algorithms.community import greedy_modularity_communities
            communities = list(greedy_modularity_communities(G))

        # Filter by min size
        communities = [c for c in communities if len(c) >= args.min_size]
        communities = sorted(communities, key=len, reverse=True)

        if not communities:
            console.print("[yellow]No communities found with minimum size[/yellow]")
            return 0

        console.print(f"\n[green]Found {len(communities)} communities[/green]\n")

        # Display each community
        for i, community in enumerate(communities, 1):
            console.print(f"[bold]Community {i}[/bold] ({len(community)} conversations)")

            table = Table(show_header=True, header_style="dim")
            table.add_column("ID", width=10)
            table.add_column("Title", width=50)

            for conv_id in list(community)[:10]:  # Show max 10 per cluster
                conv = db.load_conversation(conv_id)
                if conv:
                    title = conv.title or "(untitled)"
                    table.add_row(conv_id[:8] + "...", title[:50])

            console.print(table)

            if len(community) > 10:
                console.print(f"  ... and {len(community) - 10} more\n")
            else:
                console.print()

    return 0


def cmd_neighbors(args):
    """Show neighbors of a conversation in the graph"""
    from rich.console import Console
    from rich.table import Table
    import networkx as nx

    console = Console()

    with ConversationDB(args.db) as db:
        G, graph_metadata = _load_graph(db, console)
        if G is None:
            return 1

        # Resolve conversation ID
        conv_id = _resolve_conv_id(db, args.id, console)
        if not conv_id:
            return 1

        if conv_id not in G:
            console.print(f"[red]Conversation {conv_id[:8]}... not in graph[/red]")
            return 1

        # Get neighbors at specified depth
        if args.depth == 1:
            neighbors = set(G.neighbors(conv_id))
        else:
            neighbors = set()
            current_level = {conv_id}
            for _ in range(args.depth):
                next_level = set()
                for node in current_level:
                    next_level.update(G.neighbors(node))
                neighbors.update(next_level)
                current_level = next_level - {conv_id}
            neighbors.discard(conv_id)

        # Get source conversation title
        source_conv = db.load_conversation(conv_id)
        source_title = source_conv.title if source_conv else "(untitled)"

        console.print(f"\nNeighbors of: [bold]{source_title}[/bold] ({conv_id[:8]}...)")
        console.print(f"Depth: {args.depth}, Found: {len(neighbors)}\n")

        if not neighbors:
            console.print("[yellow]No neighbors found[/yellow]")
            return 0

        # Display neighbors with edge weights
        table = Table(show_header=True)
        table.add_column("ID", width=10)
        table.add_column("Title", width=45)
        table.add_column("Similarity", width=10)

        neighbor_data = []
        for neighbor_id in neighbors:
            conv = db.load_conversation(neighbor_id)
            title = conv.title if conv else "(untitled)"

            # Get edge weight if direct neighbor
            weight = 0
            if G.has_edge(conv_id, neighbor_id):
                weight = G[conv_id][neighbor_id].get('weight', 0)

            neighbor_data.append((neighbor_id, title, weight))

        # Sort by weight descending
        neighbor_data.sort(key=lambda x: x[2], reverse=True)

        for nid, title, weight in neighbor_data[:20]:
            table.add_row(
                nid[:8] + "...",
                title[:45],
                f"{weight:.3f}" if weight > 0 else "-"
            )

        console.print(table)

        if len(neighbors) > 20:
            console.print(f"\n... and {len(neighbors) - 20} more neighbors")

    return 0


def cmd_path(args):
    """Find shortest path between two conversations"""
    from rich.console import Console
    import networkx as nx

    console = Console()

    with ConversationDB(args.db) as db:
        G, graph_metadata = _load_graph(db, console)
        if G is None:
            return 1

        # Resolve conversation IDs
        source_id = _resolve_conv_id(db, args.source, console)
        if not source_id:
            return 1

        target_id = _resolve_conv_id(db, args.target, console)
        if not target_id:
            return 1

        if source_id not in G:
            console.print(f"[red]Source {source_id[:8]}... not in graph[/red]")
            return 1

        if target_id not in G:
            console.print(f"[red]Target {target_id[:8]}... not in graph[/red]")
            return 1

        # Find shortest path
        try:
            path = nx.shortest_path(G, source_id, target_id)
        except nx.NetworkXNoPath:
            console.print("[yellow]No path exists between these conversations[/yellow]")
            return 0

        console.print(f"\n[green]Path found with {len(path)} steps:[/green]\n")

        for i, conv_id in enumerate(path):
            conv = db.load_conversation(conv_id)
            title = conv.title if conv else "(untitled)"

            prefix = "→ " if i > 0 else "  "
            marker = "[bold cyan]●[/bold cyan]" if i == 0 or i == len(path) - 1 else "[dim]○[/dim]"

            console.print(f"{prefix}{marker} {conv_id[:8]}... {title[:50]}")

            # Show edge weight to next node
            if i < len(path) - 1:
                next_id = path[i + 1]
                if G.has_edge(conv_id, next_id):
                    weight = G[conv_id][next_id].get('weight', 0)
                    console.print(f"     [dim]similarity: {weight:.3f}[/dim]")

    return 0


def cmd_central(args):
    """Find most central conversations"""
    from rich.console import Console
    from rich.table import Table
    import networkx as nx

    console = Console()

    with ConversationDB(args.db) as db:
        G, graph_metadata = _load_graph(db, console)
        if G is None:
            return 1

        console.print(f"Computing {args.metric} centrality...")

        # Compute centrality
        if args.metric == 'degree':
            centrality = nx.degree_centrality(G)
        elif args.metric == 'betweenness':
            centrality = nx.betweenness_centrality(G)
        elif args.metric == 'pagerank':
            centrality = nx.pagerank(G)
        elif args.metric == 'eigenvector':
            try:
                centrality = nx.eigenvector_centrality(G, max_iter=1000)
            except nx.PowerIterationFailedConvergence:
                console.print("[yellow]Eigenvector centrality failed to converge, using degree[/yellow]")
                centrality = nx.degree_centrality(G)

        # Sort by centrality
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)

        console.print(f"\n[bold]Top {args.top_k} by {args.metric} centrality:[/bold]\n")

        table = Table(show_header=True)
        table.add_column("Rank", width=5)
        table.add_column("Score", width=8)
        table.add_column("ID", width=10)
        table.add_column("Title", width=45)

        for i, (conv_id, score) in enumerate(sorted_nodes[:args.top_k], 1):
            conv = db.load_conversation(conv_id)
            title = conv.title if conv else "(untitled)"
            table.add_row(
                str(i),
                f"{score:.4f}",
                conv_id[:8] + "...",
                title[:45]
            )

        console.print(table)

    return 0


def cmd_outliers(args):
    """Find least connected/isolated conversations"""
    from rich.console import Console
    from rich.table import Table
    import networkx as nx

    console = Console()

    with ConversationDB(args.db) as db:
        G, graph_metadata = _load_graph(db, console)
        if G is None:
            return 1

        # Compute degree centrality (low degree = outlier)
        centrality = nx.degree_centrality(G)

        # Sort by centrality (ascending for outliers)
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1])

        console.print(f"\n[bold]Top {args.top_k} outliers (least connected):[/bold]\n")

        table = Table(show_header=True)
        table.add_column("Rank", width=5)
        table.add_column("Degree", width=8)
        table.add_column("ID", width=10)
        table.add_column("Title", width=45)

        for i, (conv_id, score) in enumerate(sorted_nodes[:args.top_k], 1):
            conv = db.load_conversation(conv_id)
            title = conv.title if conv else "(untitled)"
            degree = G.degree(conv_id)
            table.add_row(
                str(i),
                str(degree),
                conv_id[:8] + "...",
                title[:45]
            )

        console.print(table)

        # Also show isolated nodes (degree 0)
        isolated = list(nx.isolates(G))
        if isolated:
            console.print(f"\n[yellow]Found {len(isolated)} completely isolated nodes[/yellow]")

    return 0
