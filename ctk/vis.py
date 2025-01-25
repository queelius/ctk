import logging
import networkx as nx
from urllib.parse import urljoin
import matplotlib.pyplot as plt
from urllib.parse import urlparse
from pyvis.network import Network
from rich.table import Table
from rich.console import Console

console = Console()

def generate_url_graph(conversations, limit=1000):
    """
    Generate a NetworkX graph based on URL mentions in conversation trees.
    """
    G = nx.DiGraph()
    total = min(len(conversations), limit)
    logging.debug(f"Generating graph from {total} conversations.")
    
    import json
    # Create a set of all bookmark URLs for quick lookup
    for conv in conversations[:total]:
        G.add_node(conv['id'], label=conv['title'], type='tree')
    
    # Create edges between converations. two nodes, c1 and c2, are linked if they
    # share common values c1['safe_urls'] and c2['safe_urls']. the weight is
    # the number of common values.

    for c1 in conversations[:total]:
        for c2 in conversations[:total]:
            if c1 == c2:
                continue
            common_urls = set(c1['safe_urls']) & set(c2['safe_urls'])
            if common_urls:
                G.add_edge(c1['title'], c2['title'], weight=len(common_urls)) 
    return G

def visualize_graph_pyvis(graph, output_file):
    """Visualize the graph using pyvis and save as an HTML file."""
    net = Network(height='3000px', width='100%', directed=False)
    net.from_nx(graph)
    #net.show_buttons(filter_=['physics'])

    try:
        # Use write_html to save the HTML file without attempting to open it
        net.write_html(output_file)
        logging.info(f"Interactive graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save interactive graph visualization: {e}")

def visualize_graph_png(graph, output_file):
    plt.figure(figsize=(12, 12))
    pos = nx.spring_layout(graph, k=0.01, iterations=30, weight="weight")
    nx.draw_networkx_nodes(graph, pos, node_size=5, node_color='green', alpha=0.5)
    nx.draw_networkx_edges(graph, pos, arrows=False, alpha=0.95)
    plt.title("Conversations - Shared URLs")
    plt.axis('off')
    plt.tight_layout()
    try:
        plt.savefig(output_file, format='PNG')
        logging.info(f"Graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save graph visualization: {e}")
    plt.close()

def json_graph_stats(graph):
    """Compute and display detailed statistics of the NetworkX graph."""
    stats = {}
    stats['Number of Nodes'] = graph.number_of_nodes()
    stats['Number of Edges'] = graph.number_of_edges()
    stats['Density'] = nx.density(graph)
    stats['Degree'] = {}
    stats['Degree']['Average'] = sum(dict(graph.degree()).values()) / graph.number_of_nodes() if graph.number_of_nodes() > 0 else 0
    stats['Degree']['Max'] = max(dict(graph.degree()).values()) if dict(graph.degree()) else 0
    stats['Degree']['Min'] = min(dict(graph.degree()).values()) if dict(graph.degree()) else 0
    stats['Degree']['Top 10'] = sorted(dict(graph.degree()).items(), key=lambda x: x[1], reverse=True)[:top_n]
    stats['Connected Components'] = nx.number_connected_components(graph.to_undirected())
    stats['Graph Diameter'] = nx.diameter(graph.to_undirected()) if nx.is_connected(graph.to_undirected()) else 'N/A'
    stats['Clustering Coefficient'] = nx.average_clustering(graph.to_undirected())
    
    # Calculate centrality measures
    try:
        degree_centrality = nx.degree_centrality(graph)
        betweenness_centrality = nx.betweenness_centrality(graph)
        stats['Degree Centrality (avg)'] = sum(degree_centrality.values()) / len(degree_centrality) if degree_centrality else 0
        stats['Betweenness Centrality (avg)'] = sum(betweenness_centrality.values()) / len(betweenness_centrality) if betweenness_centrality else 0
    except Exception as e:
        logging.warning(f"Could not compute centrality measures: {e}")
        stats['Degree Centrality (avg)'] = 'N/A'
        stats['Betweenness Centrality (avg)'] = 'N/A'
    
    # Identify top N nodes by Degree Centrality
    try:
        top_degree = sorted(degree_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Top Degree Centrality'] = [f"{url} ({centrality:.4f})" for url, centrality in top_degree]
    except:
        stats['Top Degree Centrality'] = 'N/A'
    
    top_betweenness = sorted(betweenness_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
    stats['Top Betweenness Centrality'] = [f"{url} ({centrality:.4f})" for url, centrality in top_betweenness]

    graph_comps_sizes = [len(c) for c in nx.connected_components(graph.to_undirected())]

    # more stats
    stats['Average Degree'] = sum(dict(graph.degree()).values()) / graph.number_of_nodes() if graph.number_of_nodes() > 0 else 0
    stats['Average Clustering Coefficient'] = nx.average_clustering(graph.to_undirected())
    stats['Average Shortest Path Length'] = nx.average_shortest_path_length(graph.to_undirected()) if nx.is_connected(graph.to_undirected()) else 'N/A'
    stats['Graph Components'] = {}
    stats['Graph Components']['Top 10'] = sorted(graph_comps_sizes, reverse=True)[:10]
    stats['Graph Components']['Max'] = max(graph_comps_sizes)
    stats['Graph Components']['Min'] = min(graph_comps_sizes)
    stats['Graph Components']['Average'] = sum(graph_comps_sizes) / len(graph_comps_sizes) if graph_comps_sizes else 0
    return stats

def table_stats(stats):        

    from .utils import print_json_as_table
    print_json_as_table(stats, "Conversation Graph Statistics")

