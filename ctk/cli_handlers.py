"""
@file cli_handlers.py
@brief Command handlers for the CTK CLI.

This module contains handlers for the various CTK commands,
separating the command logic from the CLI parsing in cli.py.
"""

import os
import json
import sys
import logging
import subprocess
import traceback
import webbrowser
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.json import JSON

from .context import CTKContext
from .utils import pretty_print_conversation, print_json_as_table

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

console = Console()

def handle_list(args):
    """Handle list command"""
    from .operations import list_conversations
    
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Get and display conversation list
    results = list_conversations(ctx, args.fields, args.indices)
    
    # Display results in tabular format
    display_list_results(results, args.fields)

def handle_search(args):
    """Handle search command"""
    from .operations import search_conversations
    
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Perform search
    results = search_conversations(ctx, args.expression, args.fields)
    
    # Display results
    if args.json:
        console.print(JSON(json.dumps(results, indent=2)))
    else:
        for result in results:
            pretty_print_conversation(result["conversation"])

def handle_remove(args):
    """Handle remove command"""
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Get all conversations
    conversations = ctx.conversations
    
    # Remove conversations by index
    for index in sorted(args.indices, reverse=True):
        if 0 <= index < len(conversations):
            del conversations[index]
        else:
            logger.warning(f"Index {index} out of range")
    
    # Update conversations and save to disk
    ctx.conversations = conversations
    ctx.save_conversations()
    
    logger.info(f"Removed {len(args.indices)} conversations")

def handle_export(args):
    """Handle export command"""
    import zipfile
    from .utils import generate_unique_filename
    from .operations import export_conversations
    
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Handle special case for zip format
    if args.format == "zip":
        zipfile_name = generate_unique_filename(args.libdir + ".zip") 
        with zipfile.ZipFile(zipfile_name, "w") as zf:
            # Get all or selected conversations
            if args.indices:
                conversations = ctx.get_conversations_by_indices(args.indices)
            else:
                conversations = ctx.conversations
                
            # Write conversations to zip file
            zf.writestr("conversations.json", json.dumps(conversations, indent=2))
            
            # Copy additional files from libdir
            for root, dirs, files in os.walk(args.libdir):
                for file in files:
                    if file == "conversations.json":
                        continue
                    # Write the file to the zip file, maintaining directory structure
                    arcname = os.path.relpath(os.path.join(root, file), start=args.libdir)
                    zf.write(os.path.join(root, file), arcname=arcname)
                    
        console.print(f"[green]Exported to {zipfile_name}[/green]")
    else:
        # Use standard export function
        result = export_conversations(
            ctx, 
            indices=args.indices, 
            format=args.format
        )
        
        # Output format-specific result
        if args.format == "json":
            console.print(result)
        elif args.format == "markdown":
            console.print(result)
        else:
            console.print(JSON(json.dumps(result, indent=2)))

def handle_jmespath(args):
    """Handle jmespath command"""
    from .operations import execute_jmespath_query
    
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Execute JMESPath query
    result = execute_jmespath_query(ctx, args.query)
    
    # Output result as formatted JSON
    console.print(JSON(json.dumps(result, indent=2)))

def handle_conv_stats(args):
    """Handle conv-stats command"""
    import AlgoTree
    
    # Create CTK context 
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Get conversation at index
    conv = ctx.get_conversation(args.index)
    if not conv:
        console.print(f"[red]Error: Index {args.index} out of range.[/red]")
        return
        
    # Compute tree statistics
    cur_node_name = conv.get("current_node")
    tree_map = conv.get("mapping")
    t = AlgoTree.FlatForest(tree_map)
    cur_node = t.node(cur_node_name)
    ancestors = AlgoTree.utils.ancestors(cur_node)
    cur_conv_ids = [node.name for node in ancestors] + [cur_node_name]

    stats = {}
    metadata = conv.copy()
    metadata.pop("mapping", None)

    stats['metadata'] = metadata
    stats["num_paths"] = len(AlgoTree.utils.leaves(t.root))
    stats["num_nodes"] = AlgoTree.utils.size(t.root)
    stats["max_path"] = AlgoTree.utils.height(t.root)

    def walk(node, the_id, the_parent_id):
        node_dict = {}
        node_dict["siblings"] = [
            node.name for node in AlgoTree.utils.siblings(node)]
        node_dict["children"] = [child.name for child in node.children]
        node_dict["is_leaf"] = AlgoTree.utils.is_leaf(node)
        node_dict["is_root"] = AlgoTree.utils.is_root(node)
        node_dict["is_current"] = node.name in cur_conv_ids
        node_dict["num_children"] = len(node.children)
        node_dict['num_siblings'] = len(node_dict['siblings'])
        node_dict["depth"] = AlgoTree.utils.depth(node)
        node_dict["num_descendants"] = AlgoTree.utils.size(node)
        node_dict["num_ancestors"] = len(AlgoTree.utils.ancestors(node))
        node_dict["parent_id"] = node.parent.name if node.parent else None
        if not args.no_payload:
            node_dict['payload'] = node.payload

        stats[(the_id, the_parent_id)] = node_dict

        the_parent_id = the_id
        the_id = the_id + 1
        for child in node.children:
            walk(child, the_id, the_parent_id)
            the_id += 1

    walk(t.root, 0, None)
    
    if args.json:
        console.print(JSON(json.dumps(stats, indent=2)))
    else:
        print_json_as_table(stats, table_title=conv['title'])

def handle_tree(args):
    """Handle tree command"""
    import AlgoTree
    from .utils import path_value
    
    # Create CTK context 
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Get conversation at index
    conv = ctx.get_conversation(args.index)
    if not conv:
        console.print(f"[red]Error: Index {args.index} out of range.[/red]")
        return
        
    # Visualize tree
    tree_map = conv.get("mapping", {})
    t = AlgoTree.FlatForest(tree_map)

    def generate_label_fn():
        paths = []
        for field in args.label_fields:
            paths.append(field.split('.'))

        def label_fn(node):
            results = []
            for path in paths:
                value = path_value(node.payload, path)
                value = value[:args.truncate]
                results.append(value)

            label = " ".join(results)
            return label

        return label_fn

    if args.label_lambda is None:
        label_fn = generate_label_fn()
        console.print(AlgoTree.pretty_tree(t, node_name=label_fn))
    else:
        label_fn = eval(args.label_lambda)
        label_fallback_fn = generate_label_fn()

        def wrapper_lambda(node):
            try:
                return label_fn(node)
            except Exception as e:
                print("Error in label_fn:", e)
                return label_fallback_fn(node)

        # label_fn should be a function that takes a conversation node and returns a string
        console.print(AlgoTree.pretty_tree(t, node_name=wrapper_lambda))

def handle_conv(args):
    """Handle conv command"""
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)

    if args.node is not None and len(args.indices) > 1:
        console.print(
            "[red]Error: If you specify a node, you can only print one conversation at a time.[/red]")
        sys.exit(1)

    # Get conversations by indices
    conversations = ctx.get_conversations_by_indices(args.indices)
    
    if args.json:
        console.print(JSON(json.dumps(conversations, indent=2)))
    else:
        for conv in conversations:
            pretty_print_conversation(
                conv,
                terminal_node=args.node,
                msg_limit=args.msg_limit,
                msg_roles=args.msg_roles,
                msg_start_index=args.msg_start_index,
                msg_end_index=args.msg_end_index)

def handle_merge(args):
    """Handle merge command"""
    from .operations import merge_libraries
    from .utils import ensure_libdir_structure
    
    # Create output context
    output_ctx = CTKContext(lib_dir=args.output)
    ensure_libdir_structure(args.output)
    
    # Create contexts for input libraries
    lib_contexts = [CTKContext(lib_dir=lib_dir) for lib_dir in args.libdirs]
    
    # Perform merge operation
    count = merge_libraries(args.operation, lib_contexts, output_ctx)
    
    # Save results
    output_ctx.save_conversations()
    
    logger.info(f"Merged {len(args.libdirs)} libraries into {args.output} with {count} conversations")

def handle_dash(args):
    """Handle dash command"""
    dash_cmd = [
        "streamlit", "run",
        "streamlit/app.py",
        f"--libdir={args.libdir}"
    ]
    subprocess.run(dash_cmd, check=True)

def handle_viz(args):
    """Handle viz command"""
    from .vis import generate_url_graph, visualize_graph_pyvis, visualize_graph_png
    
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Generate URL graph
    conversations = ctx.conversations[:args.limit]
    net = generate_url_graph(conversations, args.limit)
    
    # Visualize graph
    if args.output_format == 'png':
        visualize_graph_png(net, 'graph.png')
        console.print("[green]Graph visualization saved to graph.png[/green]")
    elif args.output_format == 'html':
        visualize_graph_pyvis(net, 'graph.html')
        console.print("[green]Graph visualization saved to graph.html[/green]")
    else:
        console.print("[red]Invalid output format. Please choose 'png' or 'html'.[/red]")

def handle_graph_stats(args):
    """Handle graph-stats command"""
    from .vis import generate_url_graph
    from .stats import graph_stats
    
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)
    
    # Generate URL graph
    conversations = ctx.conversations[:args.limit]
    net = generate_url_graph(conversations, args.limit)
    
    # Calculate graph statistics
    stats = graph_stats(net, args.top_n)
    
    # Display results
    if args.output_format == 'json':
        console.print(JSON(json.dumps(stats, indent=2)))
    elif args.output_format == 'table':
        print_json_as_table(stats)
    else:
        console.print("[red]Invalid output format. Please choose 'json' or 'table'.[/red]")

def handle_about(args):
    """Handle about command"""
    console.print("[bold cyan]ctk[/bold cyan]: A command-line toolkit for working with conversation trees, "
              "typically derived from exported LLM interaction data.\n")
    console.print("[dim]Developed by:[/dim] [bold white]Alex Towell[/bold white]  \n"
              "[dim]Contact:[/dim] [link=mailto:lex@metafunctor.com]lex@metafunctor.com[/link]  \n"
              "[dim]Source Code:[/dim] [link=https://github.com/queelius/ctk]https://github.com/queelius/ctk[/link]\n")
    console.print("[bold]Features:[/bold]")
    console.print("• Parse and analyze LLM conversation trees.")
    console.print(
        "• Export, transform, and query structured conversation data.")
    console.print("• Visualize conversation trees and relationships.")
    console.print("• Query conversation trees using JMESPath.")
    console.print("• Query conversation trees using an LLM.")
    console.print(
        "• Launch a Streamlit dashboard for interactive exploration.")
    console.print(
        "• Lightweight and designed for command-line efficiency.")
    console.print(
        "\n[bold green]Usage:[/bold green] Run `ctk --help` for available commands.")

def handle_web(args):
    """Handle web command"""
    # Create CTK context
    ctx = CTKContext(lib_dir=args.libdir)
    
    for idx in args.index:
        conv = ctx.get_conversation(idx)
        if not conv:
            console.print(f"[red]Error: Index {idx} out of range.[/red]. Skipping.")
            continue

        link = f"https://chat.openai.com/c/{conv['id']}"
        webbrowser.open_new_tab(link)

def handle_semantic_network(args):
    """Handle semantic-network command"""
    try:
        # Import semantic_network here to avoid circular imports
        from .semantic_network import generate_semantic_network
        
        # Create context
        ctx = CTKContext(lib_dir=args.libdir)
        
        console.print("[bold cyan]Building semantic network...[/bold cyan]")
        
        # Build the network
        graph, metrics, clusters, net = generate_semantic_network(
            args.libdir,
            limit=args.limit,
            threshold=args.threshold,
            embedding_model=args.model,
            algorithm=args.algorithm,
            use_cache=not args.no_cache
        )
        
        # Print basic metrics
        console.print(f"[bold]Semantic Network Analysis[/bold]")
        console.print(f"Number of nodes: {metrics['num_nodes']}")
        console.print(f"Number of edges: {metrics['num_edges']}")
        console.print(f"Network density: {metrics['density']:.4f}")
        
        # Visualize network
        if args.output_format == 'html':
            from .vis import visualize_graph_pyvis
            output_file = "semantic_network.html"
            visualize_graph_pyvis(graph, output_file)
            console.print(f"[green]Network visualization saved to {output_file}[/green]")
        elif args.output_format == 'png':
            from .vis import visualize_graph_png
            output_file = "semantic_network.png"
            visualize_graph_png(graph, output_file)
            console.print(f"[green]Network visualization saved to {output_file}[/green]")
        elif args.output_format == 'graphml':
            import networkx as nx
            output_file = "semantic_network.graphml"
            nx.write_graphml(graph, output_file)
            console.print(f"[green]Network saved to {output_file}[/green]")

        # Print top bridge nodes
        console.print("\n[bold]Top Bridge Conversations:[/bold]")
        bridges = net.find_bridge_conversations(top_n=10)
        
        bridge_table = Table(show_header=True)
        bridge_table.add_column("Conversation", style="cyan")
        bridge_table.add_column("Title", style="green")
        bridge_table.add_column("Betweenness", style="magenta")
        
        for conv_id, betweenness in bridges:
            title = next((c.get("title", "Untitled") for c in net.conversations 
                        if c.get("id") == conv_id), "Untitled")
            bridge_table.add_row(conv_id, title, f"{betweenness:.4f}")
            
        console.print(bridge_table)
        
        # Print clusters
        num_clusters = len(set(clusters.values()))
        console.print(f"\n[bold]Found {num_clusters} clusters of conversations[/bold]")
        console.print("Use 'ctk clusters' for detailed cluster analysis")
        
    except ImportError:
        console.print("[red]Error: Semantic network functionality requires additional dependencies.[/red]")
        console.print("Install with: pip install sentence-transformers scikit-learn networkx python-louvain")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if os.environ.get("CTK_DEBUG"):
            console.print(traceback.format_exc())

def handle_bridges(args):
    """Handle bridges command"""
    try:
        # Import semantic_network here to avoid circular imports
        from .semantic_network import generate_semantic_network
        
        # Create context
        ctx = CTKContext(lib_dir=args.libdir)
        
        console.print("[bold cyan]Finding bridge conversations...[/bold cyan]")
        
        # Build the network and find bridges
        graph, metrics, clusters, net = generate_semantic_network(
            args.libdir,
            threshold=args.threshold,
            embedding_model=args.model,
            use_cache=not args.no_cache
        )
        
        bridges = net.find_bridge_conversations(args.top_n)
        
        console.print("[bold]Bridge Conversations[/bold]")
        console.print("These conversations connect different topic clusters in your library.")
        
        bridge_table = Table(show_header=True)
        bridge_table.add_column("Index", style="cyan")
        bridge_table.add_column("Title", style="green")
        bridge_table.add_column("Betweenness", style="magenta")
        
        for conv_id, betweenness in bridges:
            title = next((c.get("title", "Untitled") for c in net.conversations 
                        if c.get("id") == conv_id), "Untitled")
            idx = next((i for i, c in enumerate(net.conversations) if c.get("id") == conv_id), None)
            if idx is not None:
                bridge_table.add_row(str(idx), title, f"{betweenness:.4f}")
        
        console.print(bridge_table)
        
    except ImportError:
        console.print("[red]Error: Semantic network functionality requires additional dependencies.[/red]")
        console.print("Install with: pip install sentence-transformers scikit-learn networkx python-louvain")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if os.environ.get("CTK_DEBUG"):
            console.print(traceback.format_exc())

def handle_clusters(args):
    """Handle clusters command"""
    try:
        # Import semantic_network here to avoid circular imports
        from .semantic_network import generate_semantic_network
        
        # Create context
        ctx = CTKContext(lib_dir=args.libdir)
        
        console.print("[bold cyan]Finding conversation clusters...[/bold cyan]")
        
        # Build the network and analyze clusters
        graph, metrics, clusters, net = generate_semantic_network(
            args.libdir,
            threshold=args.threshold,
            embedding_model=args.model,
            algorithm=args.algorithm,
            use_cache=not args.no_cache
        )
        
        # Count conversations in each cluster
        cluster_counts = {}
        for conv_id, cluster_id in clusters.items():
            if cluster_id not in cluster_counts:
                cluster_counts[cluster_id] = 0
            cluster_counts[cluster_id] += 1
            
        # Print cluster information
        console.print(f"[bold]Found {len(cluster_counts)} conversation clusters[/bold]")
        
        cluster_table = Table(show_header=True)
        cluster_table.add_column("Cluster", style="cyan")
        cluster_table.add_column("Size", style="magenta")
        cluster_table.add_column("Example Conversations", style="green")
        
        for cluster_id, count in sorted(cluster_counts.items(), key=lambda x: x[1], reverse=True):
            # Get example conversations from this cluster
            examples = []
            for i, conv in enumerate(net.conversations):
                conv_id = conv.get("id", "")
                if conv_id in clusters and clusters[conv_id] == cluster_id:
                    examples.append(conv.get("title", "Untitled"))
                    if len(examples) >= 3:  # Limit to 3 examples
                        break
                        
            example_str = ", ".join(examples)
            if len(examples) < count:
                example_str += f", ... ({count - len(examples)} more)"
                
            cluster_table.add_row(str(cluster_id), str(count), example_str)
            
        console.print(cluster_table)
        
    except ImportError:
        console.print("[red]Error: Semantic network functionality requires additional dependencies.[/red]")
        console.print("Install with: pip install sentence-transformers scikit-learn networkx python-louvain")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if os.environ.get("CTK_DEBUG"):
            console.print(traceback.format_exc())

def handle_extrapolate(args):
    """Handle extrapolate command"""
    try:
        # Import semantic_network here to avoid circular imports
        from .semantic_network import SemanticNetwork
        
        # Create context
        ctx = CTKContext(lib_dir=args.libdir)
        
        console.print("[bold cyan]Exploring conversation topics...[/bold cyan]")
        
        # Initialize semantic network
        net = SemanticNetwork(ctx.conversations, args.model)
        
        # Try to load cached embeddings
        cache_path = os.path.join(args.libdir, "embeddings.npz")
        cache_loaded = False
        
        if not args.no_cache and os.path.exists(cache_path):
            cache_loaded = net.load_embeddings(cache_path)
            
        if not cache_loaded:
            net.generate_embeddings()
            net.save_embeddings(cache_path)
            
        # Compute similarity matrix and create graph
        net.compute_similarity_matrix()
        
        # If LLM option is enabled, use the LLM to suggest topics
        if args.llm:
            try:
                from .llm import query_llm
                
                prompt = f"""
                I have a collection of {len(ctx.conversations)} AI conversations with the following themes:
                
                {', '.join([c.get('title', 'Untitled') for c in ctx.conversations[:20]])}
                
                Based on these themes and the gaps in my conversation library, suggest {args.num} new conversation topics that I should explore next. 
                Provide topics that would be interesting bridges between existing themes or entirely new territories.
                
                Format your response as a numbered list.
                """
                
                result = query_llm(args.libdir, prompt)
                console.print("[bold]Suggested new conversation topics:[/bold]")
                if "response" in result:
                    console.print(result["response"])
                else:
                    console.print("[yellow]No topics were generated. Try again or use embedding-based extrapolation.[/yellow]")
                
            except Exception as e:
                console.print(f"[red]Error using LLM for extrapolation: {e}[/red]")
                console.print("[yellow]Falling back to embedding-based extrapolation[/yellow]")
                extrapolate_using_embeddings(net, args.num)
                
        # Otherwise, use embedding space to find gaps and suggest topics
        else:
            extrapolate_using_embeddings(net, args.num)
            
    except ImportError:
        console.print("[red]Error: Semantic network functionality requires additional dependencies.[/red]")
        console.print("Install with: pip install sentence-transformers scikit-learn networkx python-louvain")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if os.environ.get("CTK_DEBUG"):
            console.print(traceback.format_exc())

def handle_recommend(args):
    """Handle recommend command"""
    try:
        # Import semantic_network here to avoid circular imports
        from .semantic_network import SemanticNetwork
        
        # Create context
        ctx = CTKContext(lib_dir=args.libdir)
        
        console.print(f"[bold cyan]Finding recommendations for conversation {args.index}...[/bold cyan]")
        
        # Get the conversation to recommend for
        conversation = ctx.get_conversation(args.index)
        if not conversation:
            console.print(f"[red]Error: Conversation index {args.index} not found.[/red]")
            return
            
        conversation_id = conversation.get("id")
        if not conversation_id:
            console.print(f"[red]Error: Conversation at index {args.index} has no ID.[/red]")
            return
        
        # Initialize semantic network
        net = SemanticNetwork(ctx.conversations, args.model)
        
        # Try to load cached embeddings
        cache_path = os.path.join(args.libdir, "embeddings.npz")
        cache_loaded = False
        
        if not args.no_cache and os.path.exists(cache_path):
            cache_loaded = net.load_embeddings(cache_path)
            
        if not cache_loaded:
            net.generate_embeddings()
            net.save_embeddings(cache_path)
            
        # Compute similarity matrix
        net.compute_similarity_matrix()
        
        # Get recommendations
        recommendations = net.recommend_conversations(conversation_id, args.num)
        
        if not recommendations:
            console.print("[red]No recommendations found.[/red]")
            return
            
        # Print recommendations
        console.print(f"[bold]Recommendations for:[/bold] {conversation.get('title', 'Untitled')}")
        
        rec_table = Table(show_header=True)
        rec_table.add_column("Index", style="cyan")
        rec_table.add_column("Title", style="green")
        rec_table.add_column("Similarity", style="magenta")
        
        for rec in recommendations:
            # Find the index of this conversation
            rec_idx = next((i for i, c in enumerate(ctx.conversations) if c.get("id") == rec["id"]), None)
            if rec_idx is not None:
                rec_table.add_row(str(rec_idx), rec["title"], f"{rec['similarity']:.4f}")
            
        console.print(rec_table)
        
    except ImportError:
        console.print("[red]Error: Semantic network functionality requires additional dependencies.[/red]")
        console.print("Install with: pip install sentence-transformers scikit-learn networkx python-louvain")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if os.environ.get("CTK_DEBUG"):
            console.print(traceback.format_exc())

def handle_purge(args):
    """Handle purge command"""
    console.print("[yellow]TODO: Implement purge command. This will remove any local files that are dead links in the library.[/yellow]")

# Helper functions

def display_list_results(results, fields):
    """Display list results in tabular format"""
    table = Table(title="Conversations")
    color_cycle = ["cyan", "magenta", "green", "yellow", "blue"]
    color_idx = 0
    
    # Add columns
    table.add_column("#", justify="right", style=color_cycle[color_idx])
    for field in fields:
        color_idx += 1
        table.add_column(field, style=color_cycle[color_idx % len(color_cycle)])
    
    # Add rows
    for result in results:
        row = [str(result["index"])]
        for field in fields:
            value = result.get(field, "N/A")
            row.append(str(value))
        table.add_row(*row)
        
    console.print(table)

def extrapolate_using_embeddings(net, num_topics):
    """Use embeddings to suggest new topics"""
    console.print("[bold]Topic Space Exploration[/bold]")
    console.print("Analyzing conversation embedding space to find interesting gaps...")
    
    # Create a basic table
    suggestion_table = Table(show_header=True)
    suggestion_table.add_column("#", style="cyan")
    suggestion_table.add_column("Suggested Topic", style="green")
    suggestion_table.add_column("Based On", style="magenta")
    
    # Get conversation pairs with low similarity
    for i in range(min(num_topics, 5)):
        # Find index of the pair with the lowest non-zero similarity
        min_sim = 1.0
        min_pair = (0, 0)
        
        for j in range(net.similarity_matrix.shape[0]):
            for k in range(j+1, net.similarity_matrix.shape[1]):
                sim = net.similarity_matrix[j, k]
                if 0.1 < sim < min_sim:  # Avoid completely unrelated pairs
                    min_sim = sim
                    min_pair = (j, k)
        
        # Get conversation titles
        conv1 = net.conversations[min_pair[0]].get("title", "Untitled")
        conv2 = net.conversations[min_pair[1]].get("title", "Untitled")
        
        # Suggest a topic that bridges these conversations
        suggestion = f"Exploring the connection between '{conv1}' and '{conv2}'"
        
        suggestion_table.add_row(str(i+1), suggestion, f"{conv1} + {conv2}")