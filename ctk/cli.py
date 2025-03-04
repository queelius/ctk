"""
@file cli.py
@brief ctk command-line tool for managing and analyzing chat logs.

This script provides subcommands to import, list, merge, run jmespath queries,
launch a Streamlit dashboard, etc. It uses the CTKContext pattern to maintain state
and avoid redundant I/O operations.
"""

import argparse
import json
import os
import sys
import AlgoTree
import subprocess
import logging
import zipfile
import traceback
from rich.console import Console
from rich.json import JSON
from rich.table import Table
from importlib.metadata import version
import webbrowser
from rich.prompt import Confirm
import traceback
from .context import CTKContext
from .cli_handlers import (handle_semantic_network, handle_bridges, handle_clusters, handle_extrapolate)
from .utils import (ensure_libdir_structure, print_json_as_table,
                    generate_unique_filename, pretty_print_conversation)
from .operations import (list_conversations, search_conversations, 
                      execute_jmespath_query, get_conversation_details,
                      export_conversations, merge_libraries,
                      analyze_semantic_network, find_bridge_conversations,
                      find_conversation_clusters)
from .merge import union_libs, intersect_libs, diff_libs
from .llm import query_llm, chat_llm
from .vis import generate_url_graph, visualize_graph_pyvis, visualize_graph_png
from .stats import graph_stats


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

console = Console()


def launch_streamlit_dashboard(lib_dir):
    """
    @brief Launch a Streamlit-based dashboard for exploring the ctx lib.
    @param lib_dir Path to the conversation library directory.
    @return None
    @details This function just outlines how you'd call Streamlit. 
    """
    dash_cmd = [
        "streamlit", "run",
        "streamlit/app.py",
        # "--",  # pass CLI arguments to the Streamlit app
        f"--libdir={lib_dir}"
    ]
    subprocess.run(dash_cmd, check=True)


################################################################################
# COMMAND-LINE INTERFACE (argparse)
################################################################################

def main():
    """
    @brief Main entry point for the ctk CLI.
    @return None
    """
    parser = argparse.ArgumentParser(
        description="ctk: A command-line tool for chat log management and analysis."
    )
    parser.add_argument("--version", action="version",
                        version=version("conversation-tk"))

    subparsers = parser.add_subparsers(
        dest="command", help="Subcommand to run")

    # Subcommand: search
    regex_parser = subparsers.add_parser(
        "search", help="Run a search using regex against the ctk lib on the specified fields")
    regex_parser.add_argument(
        "libdir", help="Path to the conversation library directory")
    regex_parser.add_argument("expression", help="Regex expression")
    regex_parser.add_argument(
        "--fields", nargs="+", help="Field paths to apply the regex", default=["title"])
    regex_parser.add_argument(
        "--json", action="store_true", help="Output as JSON. Default: False")

    # Subcommand: conv-stats
    tree_parser = subparsers.add_parser(
        "conv-stats", help="Compute conversation tree statistics")
    tree_parser.add_argument(
        "libdir", help="Path to the conversation library directory")
    tree_parser.add_argument(
        "index", type=int, help="Index of conversation tree")
    tree_parser.add_argument(
        "--json", action="store_true", help="Output as JSON. Default: False")
    tree_parser.add_argument("--no-payload", action="store_true",
                             help="Do not show payload in the output. Default: False")

    # Subcommand: tree
    tree_parser = subparsers.add_parser(
        "tree", help="Conversation tree visualization")
    tree_parser.add_argument(
        "libdir", help="Path to the conversation library directory")
    tree_parser.add_argument(
        "index", type=int, help="Index of conversation tree to visualize")
    tree_parser.add_argument("--label-fields", nargs="+",
                             type=str, default=['id', 'message.content.parts'],
                             help="When showing the tree, use this field as the node's label")
    tree_parser.add_argument("--label-lambda", type=str, default=None,
                             help="Lambda function to apply to a node to determine its label")

    tree_parser.add_argument(
        "--truncate", type=int, default=8, help="Truncate each field to this length. Default: 8")

    # Subcommand: conv
    conv_parser = subparsers.add_parser(
        "conv", help="Print conversation based on a particular node id. Defaults to using `current_node` for the corresponding conversation tree.")
    conv_parser.add_argument(
        "libdir", help="Path to the conversation library directory")
    conv_parser.add_argument(
        "indices", nargs="+", type=int, help="Indices of conversations to print")
    conv_parser.add_argument(
        "--node", default=None, help="Node id that indicates the terminal node of a conversation path")
    conv_parser.add_argument(
        "--json", action="store_true", help="Output as JSON")
    conv_parser.add_argument("--msg-limit", type=int, default=1000,
                             help="Limit the number of messages to display. Default: 1000")
    conv_parser.add_argument("--msg-roles", type=str, nargs="+", default=[
                             "user", "assistant"], help="Roles to include in message output")
    conv_parser.add_argument("--msg-start-index", type=int, default=0,
                             help="Start index for messages to display. Default: 0")
    conv_parser.add_argument("--msg-end-index", type=int, default=-1,
                             help="End index for messages to display. Default: -1 (end of list). Use negative values to count from the end.")

    # Subcommand: remove
    remove_parser = subparsers.add_parser(
        "remove", help="Remove a conversation from the ctk lib")
    remove_parser.add_argument(
        "libdir", help="Path to the conversation library directory")
    remove_parser.add_argument(
        "indices", type=int, nargs="+", help="Indices of conversations to remove")

    # Subcommand: share
    export_parser = subparsers.add_parser(
        "export", help="Export a conversation from the ctk lib")
    export_parser.add_argument(
        "libdir", help="Path to the conversation library directory")
    export_parser.add_argument("--indices", type=int, nargs="+", default=None,
                               help="Indices of conversations to export. Default: all")
    export_parser.add_argument(
        "--format", choices=["json", "markdown", "hugo", "zip"], default="json", help="Output format")

    # Subcommand: list
    list_parser = subparsers.add_parser(
        "list", help="List conversations in the ctk lib")
    list_parser.add_argument("libdir", help="Path to the ctk library")
    list_parser.add_argument("--indices", nargs="+", default=None,
                             type=int, help="Indices of conversations to list. Default: all")
    list_parser.add_argument("--fields", nargs="+", default=[
                             "title", "create_time"], help="Path fields to include in the output")

    # Subcommand: merge (union, intersection, difference)
    merge_parser = subparsers.add_parser(
        "merge", help="Merge multiple ctk libs into one")
    merge_parser.add_argument("operation", choices=["union", "intersection", "difference"],
                              help="Type of merge operation")
    merge_parser.add_argument("libdirs", nargs="+",
                              help="List of library directories")
    merge_parser.add_argument(
        "-o", "--output", required=True, help="Output library directory")

    # Subcommand: jmespath
    jmespath_parser = subparsers.add_parser(
        "jmespath", help="Run a JMESPath query on the ctk lib")
    jmespath_parser.add_argument(
        "libdir", help="Path to the conversation library directory")
    jmespath_parser.add_argument("query", help="JMESPath expression")

    # Subcommand: dash
    dash_parser = subparsers.add_parser(
        "dash", help="Launch Streamlit dashboard")
    dash_parser.add_argument(
        "libdir", help="Path to the conversation library directory")

    # Subcommand: llm
    llm_parser = subparsers.add_parser(
        'llm', help='Query the ctk library using a Large Language Model for natural language processing')
    llm_parser.add_argument('libdir', type=str,
                            help='Directory of the ctk library to query')
    llm_parser.add_argument('query', type=str, help='Query string')
    llm_parser.add_argument('--json', action='store_true',
                            help='Output in JSON format')

    # Subcommand: viz
    viz_parser = subparsers.add_parser(
        'viz', help='Visualize the conversation library as a complex network')
    viz_parser.add_argument(
        'libdir', type=str, help='Directory of the ctk library to visualize')
    viz_parser.add_argument('output_format', type=str,
                            help='Output format: html, png')
    viz_parser.add_argument('--limit', type=int, default=5000,
                            help='Limit the number of conversations to visualize')

    # Subcommand: graph-stats
    graph_stats_parser = subparsers.add_parser(
        'graph-stats', help='Display shared URL statistics about the ctk library')
    graph_stats_parser.add_argument(
        'libdir', type=str, help='Directory of the ctk library to analyze')
    graph_stats_parser.add_argument(
        '--output_format', type=str, help='Output format: json, table, markdown', default='table')
    graph_stats_parser.add_argument(
        '--limit', type=int, default=10000, help='Limit the number of conversations to analyze')
    graph_stats_parser.add_argument(
        '--top-n', type=int, default=10, help='Number of top nodes to display')

    # Subcommand: purge
    purge_parser = subparsers.add_parser(
        'purge', help='Purge dead links from the conversation library')
    purge_parser.add_argument(
        'libdir', type=str, help='Directory of the ctk library to purge')

    # Subcommand: web
    web_parser = subparsers.add_parser(
        'web', help='View a conversation in the OpenAI chat interface')
    web_parser.add_argument(
        'libdir', type=str, help='Directory of the ctk library to visit')
    web_parser.add_argument('index', type=int, nargs='+',
                            help='Indices of the conversations to view in the browser')

    # Subcommand: chat
    chat_parser = subparsers.add_parser(
        'chat', help='Chat with the ctk library')
    chat_parser.add_argument(
        'libdir', type=str, help='Directory of the ctk library to chat with')

    # Subcommand: about
    about_parser = subparsers.add_parser(
        'about', help='Print information about ctk')

    # Add semantic network subcommands
    add_semantic_commands(subparsers)

    args = parser.parse_args()

    try:
        if args.command == "list":
            # Create CTK context
            ctx = CTKContext(lib_dir=args.libdir)
            
            # Get and display conversation list
            results = list_conversations(ctx, args.fields, args.indices)
            
            # Display results in tabular format
            display_list_results(results, args.fields)
            
        elif args.command == "search":
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

        elif args.command == "remove":
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

        elif args.command == "export":
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

        elif args.command == 'llm':
            # This uses the new CTKContext internally
            query_llm(args.libdir, args.query)

        elif args.command == "jmespath":
            # Create CTK context
            ctx = CTKContext(lib_dir=args.libdir)
            
            # Execute JMESPath query
            result = execute_jmespath_query(ctx, args.query)
            
            # Output result as formatted JSON
            console.print(JSON(json.dumps(result, indent=2)))

        elif args.command == "conv-stats":
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

        elif args.command == "tree":
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
                    from .utils import path_value
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
        elif args.command == "purge":
            print("TODO: Implement purge command. This swill remove any local files that are dead links in the library.")

        elif args.command == "chat":
            # Uses the CTKContext internally
            chat_llm(args.libdir)

        elif args.command == "conv":
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

        elif args.command == "about":
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

        elif args.command == "web":
            # Create CTK context
            ctx = CTKContext(lib_dir=args.libdir)
            
            for idx in args.index:
                conv = ctx.get_conversation(idx)
                if not conv:
                    console.print(f"[red]Error: Index {idx} out of range.[/red]. Skipping.")
                    continue

                link = f"https://chat.openai.com/c/{conv['id']}"
                webbrowser.open_new_tab(link)

        elif args.command == "merge":
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

        elif args.command == "dash":
            launch_streamlit_dashboard(args.libdir)

        elif args.command == "viz":
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

        elif args.command == "graph-stats":
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

        elif args.command == "semantic-network":
            # Handle semantic network command
            handle_semantic_network(args)
            
        elif args.command == "bridges":
            # Handle bridges command
            handle_bridges(args)
            
        elif args.command == "clusters":
            # Handle clusters command
            handle_clusters(args)
            
        elif args.command == "extrapolate":
            # Handle extrapolate command
            handle_extrapolate(args)
            
        else:
            parser.print_help()
            
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if os.environ.get("CTK_DEBUG"):
            console.print(traceback.format_exc())
        sys.exit(1)

def display_list_results(results, fields):
    """Display list results in tabular format"""
    from rich.table import Table
    
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

def add_semantic_commands(subparsers):
    """Add semantic network commands to the CLI parser"""
    
    # Subcommand: semantic-network
    semantic_parser = subparsers.add_parser(
        'semantic-network', help='Build and analyze a semantic network of conversations')
    semantic_parser.add_argument(
        'libdir', type=str, help='Directory of the CTK library to analyze')
    semantic_parser.add_argument(
        '--limit', type=int, default=1000, help='Limit the number of conversations to analyze')
    semantic_parser.add_argument(
        '--threshold', type=float, default=0.5, help='Similarity threshold for creating edges')
    semantic_parser.add_argument(
        '--model', type=str, default='text-embedding-ada-002', 
        help='API embedding model to use')
    semantic_parser.add_argument(
        '--algorithm', type=str, default='louvain',
        choices=['louvain', 'leiden', 'spectral'], help='Clustering algorithm')
    semantic_parser.add_argument(
        '--output-format', type=str, default='html', choices=['html', 'png', 'graphml'],
        help='Output format for the network visualization')
    semantic_parser.add_argument(
        '--no-cache', action='store_true', help='Do not use cached embeddings')
    
    # Subcommand: recommend
    recommend_parser = subparsers.add_parser(
        'recommend', help='Recommend similar conversations based on semantic similarity')
    recommend_parser.add_argument(
        'libdir', type=str, help='Directory of the CTK library')
    recommend_parser.add_argument(
        'index', type=int, help='Index of the conversation to get recommendations for')
    recommend_parser.add_argument(
        '--num', type=int, default=5, help='Number of recommendations to return')
    recommend_parser.add_argument(
        '--model', type=str, default='text-embedding-ada-002', 
        help='API embedding model to use')
    recommend_parser.add_argument(
        '--no-cache', action='store_true', help='Do not use cached embeddings')
    
    # Subcommand: bridges
    bridges_parser = subparsers.add_parser(
        'bridges', help='Find bridge conversations that connect different topic clusters')
    bridges_parser.add_argument(
        'libdir', type=str, help='Directory of the CTK library')
    bridges_parser.add_argument(
        '--threshold', type=float, default=0.5, help='Similarity threshold for creating edges')
    bridges_parser.add_argument(
        '--top-n', type=int, default=10, help='Number of top bridge conversations to return')
    bridges_parser.add_argument(
        '--model', type=str, default='text-embedding-ada-002', 
        help='API embedding model to use')
    bridges_parser.add_argument(
        '--no-cache', action='store_true', help='Do not use cached embeddings')
    
    # Subcommand: clusters
    clusters_parser = subparsers.add_parser(
        'clusters', help='Find clusters of related conversations')
    clusters_parser.add_argument(
        'libdir', type=str, help='Directory of the CTK library')
    clusters_parser.add_argument(
        '--threshold', type=float, default=0.5, help='Similarity threshold for creating edges')
    clusters_parser.add_argument(
        '--algorithm', type=str, default='louvain',
        choices=['louvain', 'leiden', 'spectral'], help='Clustering algorithm')
    clusters_parser.add_argument(
        '--resolution', type=float, default=1.0, help='Resolution parameter for community detection')
    clusters_parser.add_argument(
        '--model', type=str, default='text-embedding-ada-002', 
        help='API embedding model to use')
    clusters_parser.add_argument(
        '--no-cache', action='store_true', help='Do not use cached embeddings')
    
    # Subcommand: extrapolate
    extrapolate_parser = subparsers.add_parser(
        'extrapolate', help='Suggest new conversation topics by exploring embedding space')
    extrapolate_parser.add_argument(
        'libdir', type=str, help='Directory of the CTK library')
    extrapolate_parser.add_argument(
        '--num', type=int, default=5, help='Number of topics to suggest')
    extrapolate_parser.ad