#!/usr/bin/env python3
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
import jmespath
import subprocess



################################################################################
# LIBRARY FUNCTIONS
################################################################################

def load_metadata(libdir):
    """
    @brief Load library metadata from `<libdir>/metadata.json`.
    @param libdir Path to the context library directory.
    @return A dictionary containing metadata fields.
    """
    meta_path = os.path.join(libdir, "metadata.json")
    if not os.path.isfile(meta_path):
        # Return an empty dict or raise an error if you require metadata.json
        return {}

    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_metadata(libdir, metadata):
    """
    @brief Save the library metadata to `<libdir>/metadata.json`.
    @param libdir Path to the context library directory.
    @param metadata A dictionary with metadata fields to write.
    """
    meta_path = os.path.join(libdir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def load_conversations(libdir):
    """
    @brief Load all conversations from `<libdir>/conversations.json`.
    @param libdir Path to the context library directory.
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
    @param libdir Path to the context library directory.
    @param conversations Python list/dict containing conversation data.
    """
    conv_path = os.path.join(libdir, "conversations.json")
    with open(conv_path, "w", encoding="utf-8") as f:
        json.dump(conversations, f, indent=2)

def create_empty_lib(libdir):
    """
    @brief Create an empty context library structure.
    @param libdir Path to the context library directory.
    @return None
    """
    ensure_libdir_structure(libdir)
    save_metadata(libdir, {})
    save_conversations(libdir, [])

def ensure_libdir_structure(libdir):
    """
    @brief Ensure that the specified library directory contains expected structure.
    @param libdir Path to the context library directory.
    @details Creates the directory if it doesn't exist, as well as placeholders.
    """
    if not os.path.isdir(libdir):
        os.makedirs(libdir)

    # Create attachments/ and raw/ if desired
    attachments_dir = os.path.join(libdir, "attachments")
    raw_dir = os.path.join(libdir, "raw")

    for d in [attachments_dir, raw_dir]:
        if not os.path.isdir(d):
            os.makedirs(d)


def import_data(libdir, source_file, keep_raw=True):
    """
    @brief Import an external JSON chat export into the ctx lib.
    @param libdir Path to the context library directory.
    @param source_file Path to the external JSON file to import.
    @param keep_raw Whether to store a copy of the raw file in `raw/`.
    @return None
    """
    ensure_libdir_structure(libdir)

    # Optionally store original raw file
    if keep_raw:
        filename = os.path.basename(source_file)
        raw_dest = os.path.join(libdir, "raw", filename)
        shutil.copyfile(source_file, raw_dest)

    # Parse the input JSON
    with open(source_file, "r", encoding="utf-8") as f:
        new_data = json.load(f)

    # Merge it into existing conversations
    existing_data = load_conversations(libdir)
    merged_data = merge_data(existing_data, new_data)

    # Save back
    save_conversations(libdir, merged_data)

    # Update metadata (optional)
    metadata = load_metadata(libdir)
    metadata["imported_files"] = metadata.get("imported_files", [])
    metadata["imported_files"].append(os.path.basename(source_file))
    save_metadata(libdir, metadata)

def list_conversations(libdir):
    """
    @brief List all conversations found in `<libdir>/conversations.json`.

    @param libdir Path to the context library directory.
    @return None
    @details Prints titles/IDs to stdout.
    """
    conversations = load_conversations(libdir)
    if not conversations:
        print("(No conversations found.)")
        return

    for idx, conv in enumerate(conversations, start=1):
        # If you have a known field like `title` or `id`, show it
        conv_id = conv.get("id", f"Unknown-{idx}")
        title = conv.get("title", "(no title)")
        print(f"{idx}. {title} ({conv_id})")


def query_conversations_jmespath(libdir, expression):
    """
    @brief Query the conversations with a JMESPath expression.

    @param libdir Path to the context library directory.
    @param expression A JMESPath query string.
    @return The result of the JMESPath query.
    """
    conversations = load_conversations(libdir)
    return jmespath.search(expression, conversations)

def query_conversations_regex(libdir, expression, field_paths):
    """
    @brief Query the conversations with a regex expression.

    @param libdir Path to the context library directory.
    @param expression A regex expression.
    @param field_path A JMESPath query string to the field to apply the regex to.
    @return A list of conversations that satisfy the regex expression.
    """
    conversations = load_conversations(libdir)
    results = []
    for conv in conversations:
        for field_path in field_paths:
            field = jmespath.search(field_path, conv)
            if field and re.search(expression, field):
                results.append(conv)
                break

    return results

def launch_streamlit_dashboard(libdir):
    """
    @brief Launch a Streamlit-based dashboard for exploring the ctx lib.
    @param libdir Path to the context library directory.
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

def union_data(existing, new_data):
    """
    @brief Merge new conversation data with existing data.
    @param existing Existing conversation data (list or dict).
    @param new_data Newly imported conversation data (list or dict).
    @return Merged conversation data (list or dict).
    @details This skeleton merges two top-level arrays by naive concatenation.
    In reality, you might implement deduplication or advanced merging logic.
    """
    # Simple approach: assume both are lists
    if not isinstance(existing, list):
        existing = []
    if not isinstance(new_data, list):
        new_data = [new_data]
    return existing + new_data

def intersect_data(existing, new_data):
    """
    @brief Merge new conversation data with existing data.
    @param existing Existing conversation data (list or dict).
    @param new_data Newly imported conversation data (list or dict).
    @return Merged conversation data (list or dict).
    @details This skeleton merges two top-level arrays by naive concatenation.
    In reality, you might implement deduplication or advanced merging logic.
    """
    # Simple approach: assume both are lists
    if not isinstance(existing, list):
        existing = []
    if not isinstance(new_data, list):
        new_data = [new_data]
    return existing + new_data


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

    # Subcommand: init
    init_parser = subparsers.add_parser("init", help="Initialize a new conversation library")
    init_parser.add_argument("libdir", help="Path to the context library directory")
    init_parser.add_argument("--force", action="store_true", help="Overwrite if exists")

    # Subcommand: add
    add_parser = subparsers.add_parser("add", help="Add a single conversation into the ctx lib")
    add_parser.add_argument("libdir", help="Path to the context library directory")
    add_parser.add_argument("source_file", help="Path to the JSON export file") 

    # Subcommand: regex
    regex_parser = subparsers.add_parser("regex", help="Run a regex query on the ctx lib")
    regex_parser.add_argument("libdir", help="Path to the context library directory")
    regex_parser.add_argument("expression", help="Regex expression")
    regex_parser.add_argument("field_paths", nargs="+", help="Field paths to apply the regex")

    # Subcommand: conversation-tree
    tree_parser = subparsers.add_parser("conversation-tree", help="Print conversation tree")
    tree_parser.add_argument("libdir", help="Path to the context library directory")
    tree_parser.add_argument("indices", nargs="+", type=int, help="Indices of conversations to print")

    # Subcommand: remove
    remove_parser = subparsers.add_parser("remove", help="Remove a conversation from the ctx lib")
    remove_parser.add_argument("libdir", help="Path to the context library directory")
    remove_parser.add_argument("indices", type=int, nargs="+", help="Indices of conversations to remove")

    # Subcommand: share
    share_parser = subparsers.add_parser("share", help="Share a conversation from the ctx lib")
    share_parser.add_argument("libdir", help="Path to the context library directory")
    share_parser.add_argument("indices", type=int, nargs="+", help="Indices of conversations to share")
    share_parser.add_argument("--format", choices=["json", "html", "markdown", "hugo"], default="json", help="Output format")

    # Subcommand: import
    import_parser = subparsers.add_parser("import", help="Import a JSON export into the ctx lib")
    import_parser.add_argument("libdir", help="Path to the context library directory")
    import_parser.add_argument("source_file", help="Path to the JSON export file")
    import_parser.add_argument("--no-raw", action="store_true", help="Do not keep a copy in raw")

    # Subcommand: list
    list_parser = subparsers.add_parser("list", help="List all conversations in the ctx lib")
    list_parser.add_argument("libdir", help="Path to the context library directory")

    # Subcommand: merge (union, diff, etc. For now, just union.)
    merge_parser = subparsers.add_parser("merge", help="Merge multiple ctx libs into one")
    merge_parser.add_argument("operation", choices=["union", "intersection", "difference"],
                              help="Type of merge operation")
    merge_parser.add_argument("libdirs", nargs="+", help="List of library directories")
    merge_parser.add_argument("-o", "--output", required=True, help="Output library directory")

    # Subcommand: jmespath
    jmespath_parser = subparsers.add_parser("jmespath", help="Run a JMESPath query on the ctx lib")
    jmespath_parser.add_argument("libdir", help="Path to the context library directory")
    jmespath_parser.add_argument("query", help="JMESPath expression")

    # Subcommand: dash
    dash_parser = subparsers.add_parser("dash", help="Launch Streamlit dashboard")
    dash_parser.add_argument("libdir", help="Path to the context library directory")

    # Subcommand: llm
    llm_parser = subparsers.add_parser("llm", help="Run a language model on the ctx lib")
    llm_parser.add_argument("libdir", help="Path to the context library directory")
    llm_parser.add_argument("model", help="Language model to use")
    llm_parser.add_argument("query", help="Query to run")

    # Subcommand: share
    share_parser = subparsers.add_parser("share", help="Share a conversation from the ctx lib")
    share_parser.add_argument("libdir", help="Path to the context library directory")
    share_parser.add_argument("indices", type=int, nargs="+", help="Indices of conversations to share")
    share_parser.add_argument("--format", choices=["json", "html", "markdown", "hugo"], default="json", help="Output format")

    args = parser.parse_args()

    if args.command == "import":
        import_data(args.libdir, args.source_file, keep_raw=not args.no_raw)

    elif args.command == "init":
        if os.path.exists(args.libdir) and not args.force:
            print(f"Directory already exists: {args.libdir}. Use --force to overwrite.")
            sys.exit(1)
        create_empty_lib(args.libdir)

    elif args.command == "list":
        list_conversations(args.libdir)

    elif args.command == "regex":
        results = query_conversations_regex(args.libdir, args.expression, args.field_paths)
        print(json.dumps(results, indent=2))

    elif args.command == "remove":
        conversations = load_conversations(args.libdir)
        for index in sorted(args.indices, reverse=True):
            del conversations[index]
        save_conversations(args.libdir, conversations)
        print(f"Removed {len(args.indices)} conversations")

    elif args.command == "share":
        print("TODO: Implement share command")

    elif args.command == "llm":
        print("TODO: Implement llm command")

    elif args.command == "jmespath":
        result = query_conversations_jmespath(args.libdir, args.query)
        print(json.dumps(result, indent=2))

    elif args.command == "conversation-tree":
        conversations = load_conversations(args.libdir)
        for index in args.indices:
            conv = conversations[index]
            # print the non-tree metadata fields
            for key, value in conv.items():
                if key != "mapping":
                    print(f"{key}: {value}")
            print(AlgoTree.pretty_tree(conv["mapping"]))

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
