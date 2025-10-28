"""
Network analysis utilities for conversation graphs.

This module provides functions to compute network statistics and metrics
for conversation similarity graphs.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


def load_graph_from_file(graph_path: str):
    """
    Load graph from JSON file and convert to NetworkX.

    Args:
        graph_path: Path to graph JSON file

    Returns:
        NetworkX graph object
    """
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("NetworkX required: pip install networkx")

    with open(graph_path, 'r') as f:
        graph_data = json.load(f)

    G = nx.Graph()
    G.add_nodes_from(graph_data['nodes'])

    for link in graph_data['links']:
        G.add_edge(
            link['source_id'],
            link['target_id'],
            weight=link.get('weight', 1.0)
        )

    return G


def compute_global_metrics(G) -> Dict[str, Any]:
    """
    Compute global network metrics.

    Args:
        G: NetworkX graph

    Returns:
        Dictionary with global metrics
    """
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("NetworkX required: pip install networkx")

    metrics = {}

    # Basic structure
    metrics['num_nodes'] = G.number_of_nodes()
    metrics['num_edges'] = G.number_of_edges()

    if metrics['num_nodes'] == 0:
        return metrics

    # Density
    metrics['density'] = nx.density(G)

    # Degree statistics
    degrees = [d for n, d in G.degree()]
    if degrees:
        metrics['avg_degree'] = sum(degrees) / len(degrees)
        metrics['max_degree'] = max(degrees)
        metrics['min_degree'] = min(degrees)

    # Connected components
    components = list(nx.connected_components(G))
    metrics['num_components'] = len(components)

    if components:
        # Giant component
        giant = max(components, key=len)
        metrics['giant_component_size'] = len(giant)
        metrics['giant_component_fraction'] = len(giant) / metrics['num_nodes']

        # Diameter and average path length (only for connected graphs)
        if len(components) == 1:
            # Fully connected
            try:
                metrics['diameter'] = nx.diameter(G)
                metrics['avg_path_length'] = nx.average_shortest_path_length(G)
            except nx.NetworkXError as e:
                logger.warning(f"Could not compute diameter/path length: {e}")
                metrics['diameter'] = None
                metrics['avg_path_length'] = None
        else:
            # Multiple components - compute for giant component
            giant_subgraph = G.subgraph(giant)
            try:
                metrics['diameter'] = nx.diameter(giant_subgraph)
                metrics['avg_path_length'] = nx.average_shortest_path_length(giant_subgraph)
            except nx.NetworkXError as e:
                logger.warning(f"Could not compute diameter/path length for giant component: {e}")
                metrics['diameter'] = None
                metrics['avg_path_length'] = None

    # Clustering
    try:
        metrics['global_clustering'] = nx.transitivity(G)
        metrics['avg_local_clustering'] = nx.average_clustering(G)
    except Exception as e:
        logger.warning(f"Could not compute clustering: {e}")
        metrics['global_clustering'] = None
        metrics['avg_local_clustering'] = None

    return metrics


def format_network_stats(graph_metadata: Dict[str, Any], G=None) -> str:
    """
    Format network statistics for display.

    Args:
        graph_metadata: Graph metadata from database
        G: Optional NetworkX graph (will compute additional metrics)

    Returns:
        Formatted string for display
    """
    from datetime import datetime

    lines = []

    # Header
    created = graph_metadata.get('created_at')
    if isinstance(created, datetime):
        created_str = created.strftime('%Y-%m-%d %H:%M')
    else:
        created_str = str(created)

    lines.append(f"\nNetwork Statistics (Graph built: {created_str})")
    lines.append("━" * 50)

    # Basic structure
    lines.append("\nStructure:")
    lines.append(f"  Nodes: {graph_metadata.get('num_nodes', 'N/A')}")
    lines.append(f"  Edges: {graph_metadata.get('num_edges', 'N/A')}")

    density = graph_metadata.get('density')
    if density is not None:
        lines.append(f"  Density: {density:.3f}")

    avg_degree = graph_metadata.get('avg_degree')
    if avg_degree is not None:
        lines.append(f"  Avg degree: {avg_degree:.1f}")

    # Connectivity
    num_components = graph_metadata.get('num_components')
    if num_components is not None:
        lines.append("\nConnectivity:")
        lines.append(f"  Components: {num_components}")

        giant_size = graph_metadata.get('giant_component_size')
        num_nodes = graph_metadata.get('num_nodes', 1)
        if giant_size is not None and num_nodes:
            pct = (giant_size / num_nodes) * 100
            lines.append(f"  Giant component: {giant_size} nodes ({pct:.0f}%)")

        diameter = graph_metadata.get('diameter')
        if diameter is not None:
            lines.append(f"  Diameter: {diameter}")

        avg_path = graph_metadata.get('avg_path_length')
        if avg_path is not None:
            lines.append(f"  Avg path length: {avg_path:.2f}")

    # Clustering
    global_clustering = graph_metadata.get('global_clustering')
    local_clustering = graph_metadata.get('avg_local_clustering')

    if global_clustering is not None or local_clustering is not None:
        lines.append("\nClustering:")
        if global_clustering is not None:
            lines.append(f"  Global clustering: {global_clustering:.3f}")
        if local_clustering is not None:
            lines.append(f"  Avg local clustering: {local_clustering:.3f}")

    # Communities (if detected)
    num_communities = graph_metadata.get('num_communities')
    modularity = graph_metadata.get('modularity')
    algorithm = graph_metadata.get('communities_algorithm')

    if num_communities is not None:
        lines.append("\nCommunities:")
        lines.append(f"  Communities: {num_communities}")
        if modularity is not None:
            lines.append(f"  Modularity: {modularity:.3f}")
        if algorithm:
            lines.append(f"  Algorithm: {algorithm}")

    # Graph parameters
    lines.append("\nParameters:")
    threshold = graph_metadata.get('threshold')
    if threshold is not None:
        lines.append(f"  Similarity threshold: {threshold}")

    max_links = graph_metadata.get('max_links_per_node')
    if max_links is not None:
        lines.append(f"  Max links per node: {max_links}")

    # File reference
    graph_file = graph_metadata.get('graph_file_path')
    if graph_file:
        lines.append(f"\nSource: {graph_file}")

    return '\n'.join(lines)


def save_network_metrics_to_db(db, metrics: Dict[str, Any]):
    """
    Save computed network metrics to database.

    Args:
        db: ConversationDB instance
        metrics: Dictionary of computed metrics
    """
    # Get current graph
    current_graph = db.get_current_graph()
    if not current_graph:
        raise ValueError("No current graph exists")

    # Update graph with metrics
    db.save_current_graph(
        graph_file_path=current_graph['graph_file_path'],
        threshold=current_graph['threshold'],
        max_links_per_node=current_graph['max_links_per_node'],
        embedding_session_id=current_graph['embedding_session_id'],
        num_nodes=metrics.get('num_nodes'),
        num_edges=metrics.get('num_edges'),
        density=metrics.get('density'),
        avg_degree=metrics.get('avg_degree'),
        num_components=metrics.get('num_components'),
        giant_component_size=metrics.get('giant_component_size'),
        diameter=metrics.get('diameter'),
        avg_path_length=metrics.get('avg_path_length'),
        global_clustering=metrics.get('global_clustering'),
        avg_local_clustering=metrics.get('avg_local_clustering')
    )

    logger.info("Saved network metrics to database")
