import networkx as nx
from networkx.readwrite import json_graph


def generate_network(libdir, method, threshold, output, format="json"):
    """
    Generate network data from conversations using the specified method and save it in the chosen format.

    Args:
        libdir (str): Path to the conversation library directory.
        method (str): Method to generate the network ("url" or "embedding").
        threshold (float): Similarity threshold for the embedding method.
        output (str): Output file path.
        format (str): Output format ("json", "graphml", or "gml").
    """
    conversations = load_conversations(libdir)
    G = nx.Graph()

    if method == "url":
        # URL-based method: link conversations sharing URLs
        for i, conv in enumerate(conversations):
            G.add_node(i, label=conv["title"], id=conv["id"])
        for i in range(len(conversations)):
            for j in range(i + 1, len(conversations)):
                common_urls = set(conversations[i].get("safe_urls", [])) & set(conversations[j].get("safe_urls", []))
                if common_urls:
                    G.add_edge(i, j, weight=len(common_urls))

    elif method == "embedding":
        # Embedding-based method: link conversations based on cosine similarity
        embeddings_path = os.path.join(libdir, "embeddings.json")
        if not os.path.exists(embeddings_path):
            console.print("[red]Error: Embeddings not found. Run 'ctk embed' first.[/red]")
            sys.exit(1)
        with open(embeddings_path, "r") as f:
            embeddings_data = json.load(f)
        id_to_embedding = {item["id"]: item["embedding"] for item in embeddings_data}
        embeddings = [id_to_embedding[conv["id"]] for conv in conversations if conv["id"] in id_to_embedding]
        if len(embeddings) != len(conversations):
            console.print("[yellow]Warning: Some conversations lack embeddings.[/yellow]")
        embeddings = np.array(embeddings)
        similarities = cosine_similarity(embeddings)
        for i, conv in enumerate(conversations):
            G.add_node(i, label=conv["title"], id=conv["id"])
        for i in range(len(conversations)):
            for j in range(i + 1, len(conversations)):
                sim = similarities[i, j]
                if sim > threshold:
                    G.add_edge(i, j, weight=sim)

    # Output the network data in the specified format
    if format == "json":
        data = json_graph.node_link_data(G)
        with open(output, "w") as f:
            json.dump(data, f)
    elif format == "graphml":
        nx.write_graphml(G, output)
    elif format == "gml":
        nx.write_gml(G, output)
    else:
        console.print("[red]Invalid format specified.[/red]")
        sys.exit(1)

    console.print(f"[green]Network data saved to {output} in {format} format.[/green]")

def network_command():
    """
    Parse command-line arguments and generate network data.
    """
    parser = argparse.ArgumentParser(description="Generate network data from conversations.")
    parser.add_argument("libdir", help="Path to the conversation library directory")
    parser.add_argument("--method", choices=["url", "embedding"], default="url", help="Method to generate the network")
    parser.add_argument("--threshold", type=float, default=0.8, help="Similarity threshold for embedding method")
    parser.add_argument("--output", default="network.json", help="Output file path")
    parser.add_argument("--format", choices=["json", "graphml", "gml"], default="json", help="Output format")
    args = parser.parse_args()
    generate_network(args.libdir, args.method, args.threshold, args.output, args.format)

def generate_network(libdir, method, threshold, output, format="json"):
    G = nx.Graph()  # Build your network here
    # ... (add nodes and edges based on method)

    if format == "json":
        data = json_graph.node_link_data(G)
        with open(output, "w") as f:
            json.dump(data, f)
    elif format == "graphml":
        nx.write_graphml(G, output)
    elif format == "gml":
        nx.write_gml(G, output)


import argparse
import json
import sys
import networkx as nx
from networkx.readwrite import json_graph
import matplotlib.pyplot as plt
from pyvis.network import Network
from rich.console import Console

console = Console()

def visualize_network(input_file, format, output):
    """
    Visualize network data from the input file and save it in the specified format.

    Args:
        input_file (str): Input file path for network data (in JSON format).
        format (str): Output format for visualization ("png" or "html").
        output (str): Output file path for visualization.
    """
    # Load network data from input file
    with open(input_file, "r") as f:
        data = json.load(f)
    G = json_graph.node_link_graph(data)

    if format == "png":
        plt.figure(figsize=(12, 12))
        pos = nx.spring_layout(G, k=0.01, iterations=30, weight="weight")
        nx.draw_networkx_nodes(G, pos, node_size=5, node_color='green', alpha=0.5)
        nx.draw_networkx_edges(G, pos, arrows=False, alpha=0.95)
        plt.title("Conversation Network")
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output, format='PNG')
        console.print(f"[green]Visualization saved to {output}.[/green]")
        plt.close()
    elif format == "html":
        net = Network(height='1000px', width='100%', directed=False)
        net.from_nx(G)
        net.show_buttons(filter_=['physics'])
        net.write_html(output)
        console.print(f"[green]Interactive visualization saved to {output}.[/green]")
    else:
        console.print("[red]Invalid format specified.[/red]")
        sys.exit(1)

def viz_command():
    """
    Parse command-line arguments and visualize network data.
    """
    parser = argparse.ArgumentParser(description="Visualize network data.")
    parser.add_argument("--input", default="network.json", help="Input file path for network data")
    parser.add_argument("--format", choices=["png", "html"], default="png", help="Output format for visualization")
    parser.add_argument("--output", default="network.png", help="Output file path for visualization")
    args = parser.parse_args()
    visualize_network(args.input, args.format, args.output)

# Update viz parser
viz_parser.add_argument("--method", choices=["url", "embedding"], default="url", help="Graph generation method")
viz_parser.add_argument("--threshold", type=float, default=0.8, help="Similarity threshold for embedding method")

# In main()
elif args.command == "viz":
    convs = load_conversations(args.libdir)
    if args.method == "url":
        net = generate_url_graph(convs, args.limit)
    elif args.method == "embedding":
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        embeddings_path = os.path.join(args.libdir, "embeddings.json")
        if not os.path.exists(embeddings_path):
            console.print("[red]Error: Embeddings not found. Run 'ctk embed' first.[/red]")
            sys.exit(1)
        with open(embeddings_path, "r") as f:
            embeddings_data = json.load(f)
        id_to_embedding = {item["id"]: item["embedding"] for item in embeddings_data}
        embeddings = [id_to_embedding[conv["id"]] for conv in convs if conv["id"] in id_to_embedding]
        if len(embeddings) != len(convs):
            console.print("[yellow]Warning: Some conversations lack embeddings.[/yellow]")
        embeddings = np.array(embeddings)
        similarities = cosine_similarity(embeddings)
        net = nx.Graph()  # Undirected graph for similarity
        for i, conv in enumerate(convs):
            net.add_node(i, label=conv["title"])
        for i in range(len(convs)):
            for j in range(i + 1, len(convs)):
                sim = similarities[i, j]
                if sim > args.threshold:
                    net.add_edge(i, j, weight=sim)
    if args.output_format == "png":
        visualize_graph_png(net, "graph.png")
    elif args.output_format == "html":
        visualize_graph_pyvis(net, "graph.html")
    else:
        console.print("[red]Invalid output format.[/red]")
        sys.exit(1)




def load_network(file):
    # not complete of course, just intermediate outputs from grok
    import networkx as nx
    import json
    with open("network.json", "r") as f:
        data = json.load(f)
    G = nx.node_link_graph(data)
