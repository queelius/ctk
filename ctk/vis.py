import logging
import networkx as nx
import matplotlib.pyplot as plt
from pyvis.network import Network
from math import exp

def generate_url_graph(convs, limit=1000, link_types=["safe_urls"], min_weight=0, digraph=False, **kwargs):
    """
    Generate a NetworkX graph based where nodes are conversation trees and
    link weights are based on the linear combination of `link-types`. Two combination
    trees are linked if they have weight greater than `min_weight`. The command `link-types`
    supports the following link type arguments:

    - `safe-urls`: URLs designated as safe. Each conversation tree is associated with the key `safe_urls` that maps to a list of safe URLs.
    - `urls`: All URLs. We extract all URLs from the messages in each conversation tree. A keyword argument `roles` can be used to specify which
    roles to include in the messages.
    - `tf-idf`: We compute the TF-IDF of the set of conversation trees. Kwargs may optionally include `roles`, which species which roles to include
    in the messages used to compute the TF-IDF. Defaulty: all roles.
    - `keywords`: Two conversation trees have a link weight given by the number of keywords they have in common. Kwargs must include a `keyword-list` to
    specify the list of keywords to use.
    - `link-fn-name`: The name of a function that takes two conversation trees and returns a weight. Kwargs must include a `link-fn-name-value` to specify
    the function to use
    - `link-fn-lambda`: The function as a serialization of a lambda function. (We evaluate the lambda string using `eval`). The
    e possibilities:
        - To duplicate `safe-urls`: `lambda c1, c2: len(set(c1['safe_urls']) & set(c2['safe_urls']))`
        - To base links on the difference of the longest conversation in the trees:
            `lambda c1, c2: abs(AlgoTree.utils.depth(AlgoTree.FlatTree(c1)) - AlgoTree.utils.depth(AlgoTree.FlatTree(c2)))`  

    @param convs List of conversation trees.
    @param limit Maximum number of conversation trees to consider.
    @param link_types List of link types to use for computing weights.
    @param min_weight Minimum weight for links.
    @param kwargs Additional keyword arguments for link types.
    :return: The generated graph.

    """
    G = nx.DiGraph() if digraph else nx.Graph()

    total = min(len(convs), limit)
    for conv in convs[:total]:
        G.add_node(conv['id'], label=conv['title'], type='tree')

    for c1 in convs[:total]:
        for c2 in convs[:total]:
            if c1 == c2:
                continue

            weight = 0
            for link_type in link_types:
                if link_type == "safe_urls":
                    common_urls = set(c1['safe_urls']) & set(c2['safe_urls'])
                    weight += len(common_urls)
                elif link_type == "urls":
                    pass
                elif link_type == 'tf-idf':
                    pass
                elif link_type == 'keywords':
                    keywords = kwargs.get('keyword-list', [])
                    pass
                elif link_type == 'link-fn-name':
                    pass
                elif link_type == 'link-fn-lambda':
                    pass
                elif link_type == 'bm25':
                    pass
                elif link_type == 'cosine':
                    pass

            if 'normalize-weights' in kwargs:
                weight = 1 - exp(-weight)

            if weight > min_weight:
                G.add_edge(c1['id'], c2['id'], weight=weight)


    return G


def visualize_graph_pyvis(G, output_file):
    """Visualize the graph using pyvis and save as an HTML file."""
    net = Network(height='3000px', width='100%', directed=False)
    net.from_nx(G)
    # net.show_buttons(filter_=['physics'])

    try:
        # Use write_html to save the HTML file without attempting to open it
        net.write_html(output_file)
        logging.info(
            f"Interactive graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save interactive graph visualization: {e}")


def visualize_graph_png(G, output_file):
    plt.figure(figsize=(12, 12))
    pos = nx.spring_layout(G, k=0.01, iterations=30, weight="weight")
    nx.draw_networkx_nodes(G, pos, node_size=5,
                           node_color='green', alpha=0.5)
    nx.draw_networkx_edges(G, pos, arrows=False, alpha=0.95)
    plt.title("Conversations - Shared URLs")
    plt.axis('off')
    plt.tight_layout()
    try:
        plt.savefig(output_file, format='PNG')
        logging.info(f"Graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save graph visualization: {e}")
    plt.close()


def json_graph_stats(G, top_n=10):
    """Compute and display detailed statistics of the NetworkX graph."""

    stats = {}
    stats['Graph'] = {}
    stats['Graph']['# Nodes'] = G.number_of_nodes()
    stats['Graph']['# Edges'] = G.number_of_edges()
    stats['Graph']['Density'] = nx.density(G)
    stats['Graph']['Diameter'] = nx.diameter(G) if nx.is_connected(G) else 'N/A'

    stats['Degree'] = {}
    stats['Degree']['Average'] = sum(dict(G.degree()).values()) / G.number_of_nodes()
    stats['Degree']['Max'] = max(dict(G.degree()).values())
    stats['Degree']['Min'] = min(dict(G.degree()).values())
    stats['Degree'][f'Top {top_n}'] = sorted(
        dict(G.degree()).items(), key=lambda x: x[1], reverse=True)[:top_n]
    
    stats['Connected Components'] = {}
    stats['Connected Components']['Number'] = nx.number_connected_components(G)

    stats['Clustering'] = {}
    stats['Clustering']['Coefficient'] = nx.average_clustering(G)

    stats['Centrality'] = {}
    deg_centrality = nx.degree_centrality(G)
    stats['Centrality']['Average Degree'] = sum(deg_centrality.values()) / len(deg_centrality)
    betweenness = nx.betweenness_centrality(G)
    stats['Centrality']['Average Betweenness'] = sum(betweenness.values()) / len(betweenness)

    top_degree = sorted(deg_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
    stats['Centrality'][f'Top {top_n} Degree'] = [
            f"{url} ({centrality:.4f})" for url, centrality in top_degree]
 
    top_betweenness = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)[:top_n]
    stats['Centrality'][f'Top {top_n} Betweenness'] = [
        f"{url} ({centrality:.4f})" for url, centrality in top_betweenness]

    graph_comps_sizes = [len(c) for c in nx.connected_components(G)]

    stats['Graph Components'] = {}
    stats['Graph Components'][f'Top {top_n}'] = sorted(
        graph_comps_sizes, reverse=True)[:10]
    stats['Graph Components']['Max'] = max(graph_comps_sizes)
    stats['Graph Components']['Min'] = min(graph_comps_sizes)
    stats['Graph Components']['Average'] = sum(
        graph_comps_sizes) / len(graph_comps_sizes) if graph_comps_sizes else 0
    
    return stats