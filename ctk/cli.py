"""
@file cli.py
@brief ctk command-line tool for managing and analyzing chat logs.

This script provides subcommands to import, list, merge, run jmespath queries,
launch a Streamlit dashboard, etc. It uses doxygen-style tags for documentation.
"""

import argparse
import json
import os
import shutil
import sys
import jmespath
import re
import AlgoTree
import subprocess
import time
from colorama import init as colorama_init, Fore, Style
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown
from rich.json import JSON

colorama_init(autoreset=True)
console = Console()

def load_conversations(libdir):
    """
    @brief Load all conversations from `<libdir>/conversations.json`.
    @param libdir Path to the conversation library directory.
    @return A Python object (usually a list) of conversations.
    """
    conv_path = os.path.join(libdir, "conversations.json")
    if not os.path.isfile(conv_path):
        # Return empty if missing
        return []

    with open(conv_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_conversations(libdir, conversations):
    """
    @brief Save conversation data to `<libdir>/conversations.json`.
    @param libdir Path to the conversation library directory.
    @param conversations Python list/dict containing conversation data.
    """
    conv_path = os.path.join(libdir, "conversations.json")
    with open(conv_path, "w", encoding="utf-8") as f:
        for conv in conversations:
            if "id" not in conv:
                raise ValueError("Conversation missing 'id' field")

def ensure_libdir_structure(libdir):
    """
    @brief Ensure that the specified library directory contains expected structure.
    @param libdir Path to the conversation library directory.
    @details Creates the directory if it doesn't exist, as well as placeholders.
    """
    if not os.path.isdir(libdir):
        os.makedirs(libdir)

def list_conversations(libdir, path_fields, indices=None, json_output=False):
    """
    @brief List all conversations found in `<libdir>/conversations.json`.

    @param libdir Path to the conversation library directory.
    @param path_fields A list of JMESPath query strings to include in the output.
    @param indices A list of indices to list. If None, list all.
    @param json_output If True, output as JSON instead of a table.
    @return None
    @details Prints a numbered list of conversation with the indicated fields.
    """

    conversations = load_conversations(libdir)
    if not conversations:
        console.print("[red]No conversations found.[/red]")
        return

    max_index = len(conversations)
    if indices is None:
        indices = range(max_index)

    table = Table(title="Conversations")
    color_cycle = ["cyan", "magenta", "green", "yellow", "blue"]
    color_idx = 0
    table.add_column("#", justify="right", style=color_cycle[color_idx])
    for pf in path_fields:
        color_idx += 1
        table.add_column(pf, style=color_cycle[color_idx % len(color_cycle)])

    import time

    for i, conv in enumerate(conversations):
        if i not in indices:
            continue
        #path_values = [jmespath.search(p, conv) for p in path_fields]
        path_values = [str(jmespath.search(p, conv)) if not isinstance(jmespath.search(p, conv), (int, float)) 
               else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(jmespath.search(p, conv)))
               for p in path_fields]

        table.add_row(str(i), *path_values)
    console.print(table)
        

def query_conversations_jmespath(libdir, expression):
    """
    @brief Query the conversations with a JMESPath expression.

    @param libdir Path to the conversation library directory.
    @param expression A JMESPath query string.
    @return The result of the JMESPath query.
    """
    conversations = load_conversations(libdir)
    return jmespath.search(expression, conversations)

def query_conversations_search(libdir, expression, fields):
    """
    @brief Query the conversations with a regex expression.

    @param libdir Path to the conversation library directory.
    @param expression A regex expression.
    @param fields A list of JMESPath query strings to apply the regex to.
    @param ignore_case If True, ignore case when matching.
    @return A list of conversations that satisfy the regex expression.

    """
    conversations = load_conversations(libdir)
    results = []
    pattern = re.compile(expression, re.IGNORECASE)

    for conv in conversations:
        for field in fields:
            out = jmespath.search(field, conv)
            if isinstance(out, (int, float)):
                out = str(out)
            elif isinstance(out, (list, dict)):
                out = json.dumps(out)  # Convert complex types to JSON string
            elif out is None:
                continue  # Skip if the field is None
            else:
                out = str(out)

            if pattern.search(out):
                results.append(conv)
                break  # Move to the next conversation after a match

    return results

def launch_streamlit_dashboard(libdir):
    """
    @brief Launch a Streamlit-based dashboard for exploring the ctx lib.
    @param libdir Path to the conversation library directory.
    @return None
    @details This function just outlines how you'd call Streamlit. 
    You might build an actual `.py` file for your dashboard with
    `streamlit run dash_app.py -- --libdir=...`.
    """
    dash_cmd = [
        "streamlit", "run",
        "dash_app.py",
        "--",  # pass CLI arguments to the Streamlit app
        f"--libdir={libdir}"
    ]
    subprocess.run(dash_cmd, check=True)

def union_libs(libdirs, output_dir, conflict_resolution="skip"):
    """
    @brief Take the union of multiple conversation libraries.
    @param libdirs List of library directories to merge.
    @param conflict_resolution How to handle duplicate conversation ids. Options: "skip", "overwrite-old", "error"
    @param output_dir Output library directory.
    """

    union_lib = load_conversations(libdirs[0])
    for d in libdirs[1:]:
        # check if unique ids conflict
        lib = load_conversations(d)
        if not lib:
            continue
        for conv in lib:
            if conv["id"] in [c["id"] for c in union_lib]:
                union_conv = lib[conv["id"]]
                if conflict_resolution == "skip":
                    console.print(f"Skipping duplicate id {conv['id']}")
                    continue
                elif conflict_resolution == "overwrite-old":
                    # keep the one with the newest update_time or if that doesn't exist, the newest create_time
                    latest_time_lib = max(conv.get("update_time", 0), conv.get("create_time", 0))
                    latest_time_union = max(union_conv.get("update_time", 0), union_conv.get("create_time", 0))
                    if latest_time_lib > latest_time_union:
                        union_lib[conv["id"]] = conv
                        console.print(f"Overwriting with newer id {conv['id']}")
                    else:
                        console.print(f"Keeping existing id {conv['id']}")
                elif conflict_resolution == "error":
                    raise ValueError(f"Duplicate id {conv['id']} found in libraries")
            else:
                union_lib.append(conv)

    save_conversations(output_dir, union_lib)

def pretty_print_conversation(conv, terminal_node=None):
    # Basic metadata
    title = conv.get("title", "Untitled Conversation")
    created = conv.get("create_time")
    updated = conv.get("update_time")
    model = conv.get("default_model_slug")
    safe_urls = conv.get("safe_urls", [])

    if created is not None:
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created))
    if updated is not None:
        updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(updated))

    # Create a table for overall conversation metadata
    table = Table(title=f"[bold green]{title}[/bold green]")
    table.add_column("Created", justify="right")
    table.add_column("Updated", justify="right")
    table.add_column("Model", justify="right")
    table.add_column("Safe URLs", justify="right")

    # Build a clickable list of safe URLs
    clickable_safe_urls = "\n".join(f"[bold blue][link={url}]{url}[/link][/bold blue]" for url in safe_urls)
    table.add_row(
        created or "N/A",
        updated or "N/A",
        f"[purple]{model}[/purple]" if model else "N/A",
        clickable_safe_urls if safe_urls else "N/A",
    )
    console.print(table)

    try:
        # Retrieve conversation mapping and pick the terminal node for the conversation path
        if terminal_node is None:
            terminal_node = conv.get("current_node")

        t = AlgoTree.FlatForest(conv.get("mapping", {}))
        n = t.node(terminal_node)
        ancestors = reversed(AlgoTree.ancestors(n))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    # Print out conversation messages
    for ancestor in ancestors:

        try:
            msg = ancestor.payload.get("message")
            if not msg:
                continue

            content = msg.get("content")
            if not content:
                continue

            content_type = content.get("content_type")
            if content_type != "text":
                continue

            author = msg.get("author", {})
            role = author.get("role")
            name = author.get("name")
            created_time = msg.get("create_time")

            subtitle = ""
            if created_time is not None:
                created_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_time))
                subtitle = f"Created: {created_str}"
            if name is not None:
                subtitle = f"{name}, {subtitle}"
            
            message_table = Table(
                title=f"[bold purple]{role}[/bold purple] :: [dim]{subtitle}[/dim]",
                title_justify="center",
                show_header=False,
                show_lines=True,
                show_edge=True,
                highlight=True
            )

            parts = content.get("parts", [])
            combined_text = "".join(parts)
            message_table.add_row(Markdown(combined_text))
            console.print(message_table)
            console.print()
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            continue





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
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # Subcommand: search
    regex_parser = subparsers.add_parser("search", help="Run a search using regex against the ctk lib on the specified fields")
    regex_parser.add_argument("libdir", help="Path to the conversation library directory")
    regex_parser.add_argument("expression", help="Regex expression")
    regex_parser.add_argument("--fields", nargs="+", help="Field paths to apply the regex", default=["title"])
    regex_parser.add_argument("--json", action="store_true", help="Output as JSON. Default: False")

    # Subcommand: conversation-tree
    tree_parser = subparsers.add_parser("tree-stats", help="Compute conversation tree statistics")
    tree_parser.add_argument("libdir", help="Path to the conversation library directory")
    tree_parser.add_argument("indices", nargs="+", default=None, type=int, help="Indices of conversation trees. Default: all")
    tree_parser.add_argument("--json", action="store_true", help="Output as JSON. Default: False")

    # Subcommand: show-conversation-tree
    show_tree_parser = subparsers.add_parser("conversation-tree", help="Conversation tree visualization")
    show_tree_parser.add_argument("libdir", help="Path to the conversation library directory")
    show_tree_parser.add_argument("index", type=int, help="Index of conversation tree to visualize")
    show_tree_parser.add_argument("--label-field", type=str, default="name", help="When showing the tree, use this field as the node name")
    # TODO AlgoTree to output image files

    # Subcommand: conversation
    linear_conv = subparsers.add_parser("conversation", help="Print conversation based on a particular node id. Defaults to using `current_node` for the corresponding conversation tree.")
    linear_conv.add_argument("libdir", help="Path to the conversation library directory")
    linear_conv.add_argument("indices", nargs="+", type=int, help="Indices of conversations to print")
    linear_conv.add_argument("--node", default=None, help="Node id that indicates the terminal node of a conversation path")
    linear_conv.add_argument("--json", action="store_true", help="Output as JSON")

    # Subcommand: remove
    remove_parser = subparsers.add_parser("remove", help="Remove a conversation from the ctk lib")
    remove_parser.add_argument("libdir", help="Path to the conversation library directory")
    remove_parser.add_argument("indices", type=int, nargs="+", help="Indices of conversations to remove")

    # Subcommand: share
    share_parser = subparsers.add_parser("export", help="Export a conversation from the ctk lib")
    share_parser.add_argument("libdir", help="Path to the conversation library directory")
    share_parser.add_argument("indices", type=int, nargs="+", default=None, help="Indices of conversations to export. Default: all")
    share_parser.add_argument("--format", choices=["json", "markdown", "hugo"], default="json", help="Output format")

    # Subcommand: list
    list_parser = subparsers.add_parser("list", help="List all conversations in the ctk lib")
    list_parser.add_argument("libdir", help="Path to the conversation library directory")
    list_parser.add_argument("--indices", nargs="+", default=None, type=int, help="Indices of conversations to list. Default: all")
    list_parser.add_argument("--fields", nargs="+", default=["title", "update_time"], help="Path fields to include in the output")

    # Subcommand: merge (union, intersection, difference)
    merge_parser = subparsers.add_parser("merge", help="Merge multiple ctk libs into one")
    merge_parser.add_argument("operation", choices=["union", "intersection", "difference"],
                              help="Type of merge operation")
    merge_parser.add_argument("libdirs", nargs="+", help="List of library directories")
    merge_parser.add_argument("-o", "--output", required=True, help="Output library directory")

    # Subcommand: jmespath
    jmespath_parser = subparsers.add_parser("jmespath", help="Run a JMESPath query on the ctk lib")
    jmespath_parser.add_argument("libdir", help="Path to the conversation library directory")
    jmespath_parser.add_argument("query", help="JMESPath expression")

    # Subcommand: dash
    dash_parser = subparsers.add_parser("dash", help="Launch Streamlit dashboard")
    dash_parser.add_argument("libdir", help="Path to the conversation library directory")

    # Subcommand: llm
    llm_parser = subparsers.add_parser('llm', help='Query the ctk library using a Large Language Model for natural language processing')
    llm_parser.add_argument('lib_dir', type=str, help='Directory of the ctk library to query')
    llm_parser.add_argument('query', type=str, help='Query string')
    llm_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    args = parser.parse_args()

    if args.command == "list":
        list_conversations(args.libdir, args.fields, args.indices) 

    elif args.command == "search":
        results = query_conversations_search(args.libdir, args.expression, args.fields)
        if args.json:
            # pretty JSON
            console.print(JSON(json.dumps(results, indent=2)))
        else:
            for conv in results:
                pretty_print_conversation(conv)

    elif args.command == "remove":
        conversations = load_conversations(args.libdir)
        for index in sorted(args.indices, reverse=True):
            del conversations[index]
        save_conversations(args.libdir, conversations)
        print(f"Removed {len(args.indices)} conversations")

    elif args.command == "export":
        print("TODO: Implement export command")

    elif args.command == 'llm':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            #logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        conversations = load_conversations(lib_dir)

        from ctk import llm
        while True:
            try:
                results = llm.query_llm(lib_dir, args.query)
                results = json.loads(results['response'])
                print(results)

                cmd = results["command"]
                arglist = results["args"]
                proc = ["ctk"] + [cmd] + arglist
                console.print(f"[bold green]Executing:[/bold green] {' '.join(proc)}")  
                subprocess.run(proc, check=True)
                break
            # catch any exceptions and continue
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
                continue

    elif args.command == "jmespath":
        result = query_conversations_jmespath(args.libdir, args.query)
        # pretty print
        console.print(JSON(json.dumps(result, indent=2)))

    elif args.command == "show-conversation-tree":
        conversations = load_conversations(args.libdir)
        for index in args.indices:
            conv = conversations[index]
            # print the non-tree metadata fields
            for key, value in conv.items():
                if key != "mapping":
                    print(f"{key}: {value}")
            tree_map = conv.get("mapping", {})
            t = AlgoTree.FlatForest(tree_map)
            console.print(AlgoTree.pretty_tree(t, node_name=lambda n: n['text']))

    elif args.command == "conversation":

        if args.node is not None and len(args.indices) >1:
            console.print("[red]Error: If you specify a node, you can only print one conversation at a time.[/red]")
            sys.exit(1)

        conversations = load_conversations(args.libdir)
        if args.json:
            obj = []
            for index in args.indices:
                if index >= len(conversations):
                    continue
                conv = conversations[index]
                obj.append(conv)
            console.print(JSON(json.dumps(obj, indent=2)))
        else:
            for index in args.indices:                
                if index >= len(conversations):
                    console.debug(f"[red]Error: Index {index} out of range.[/red]")
                    continue
                conv = conversations[index]
                pretty_print_conversation(conv, args.node)

    elif args.command == "merge":
        ensure_libdir_structure(args.output)
        result = load_conversations(args.libdirs[0])
        for d in args.libdirs:
            part = load_conversations(d)
            if args.operation == "union":
                result = union_data(result, part)
            elif args.operation == "intersection":
                result = intersect_data(result, part)
            elif args.operation == "difference":
                result = diff_data(result, part)
            else:
                raise ValueError(f"Unknown merge operation: {args.operation}")
        
        save_conversations(args.output, result)
        print(f"Merged {len(args.libdirs)} libs into {args.output}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
