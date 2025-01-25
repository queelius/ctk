# Project Directory: ctk

## Documentation Files


### README.md


'''markdown
# `ctk`: Conversation Tree Toolkit

Purpose: Process, filter, LLM-engage, etc. conversation logs (JSON) compatible with the data export format of OpenAI (e.g., chatgpt conversation histories).
'''

### src2md-ctk.md


'''markdown
# Project Directory: ctk

## Documentation Files


### README.md


'''markdown
# `ctk`: Conversation Tree Toolkit

Purpose: Process, filter, LLM-engage, etc. conversation logs (JSON) compatible with the data export format of OpenAI (e.g., chatgpt conversation histories).
'''

### src2md-ctk.md


'''markdown
# Project Directory: ctk

## Documentation Files


### README.md


'''markdown
# `ctk`: Conversation Tree Toolkit

Purpose: Process, filter, LLM-engage, etc. conversation logs (JSON) compatible with the data export format of OpenAI (e.g., chatgpt conversation histories).
'''

### ctk/llm-instructions.md


'''markdown
'''

### Source Files

#### Source File: `ctk/__init__.py`

```python

```

#### Source File: `ctk/cli.py`

```python
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
import time
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown
from rich.json import JSON

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

def query_conversations_regex(libdir, expression, field_paths):
    """
    @brief Query the conversations with a regex expression.

    @param libdir Path to the conversation library directory.
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

def union_conversation_libs(libdirs, output_dir, conflict_resolution="skip"):
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

    # Subcommand: regex
    regex_parser = subparsers.add_parser("regex", help="Run a regex query on the ctk lib")
    regex_parser.add_argument("libdir", help="Path to the conversation library directory")
    regex_parser.add_argument("expression", help="Regex expression")
    regex_parser.add_argument("field_paths", nargs="+", help="Field paths to apply the regex")

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
    llm_parser = subparsers.add_parser("llm", help="Run a language model on the ctk lib")
    llm_parser.add_argument("libdir", help="Path to the conversation library directory")
    llm_parser.add_argument("query", help="Query to run")

    args = parser.parse_args()

    if args.command == "list":
        list_conversations(args.libdir, args.fields, args.indices) 

    elif args.command == "regex":
        results = query_conversations_regex(args.libdir, args.expression, args.field_paths)
        print(json.dumps(results, indent=2))

    elif args.command == "remove":
        conversations = load_conversations(args.libdir)
        for index in sorted(args.indices, reverse=True):
            del conversations[index]
        save_conversations(args.libdir, conversations)
        print(f"Removed {len(args.indices)} conversations")

    elif args.command == "export":
        print("TODO: Implement export command")

    elif args.command == "llm":
        print("TODO: Implement llm command")

    elif args.command == "jmespath":
        result = query_conversations_jmespath(args.libdir, args.query)
        print(json.dumps(result, indent=2))

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

```

#### Source File: `ctk/llm.py`

```python
import os
import requests
import configparser
from string import Template

def load_ctkrc_config():
    """
    Loads configuration from ~/.ctkrc.

    Expects a section [llm] with at least 'endpoint' and 'api_key'.
    """
    config_path = os.path.expanduser("~/.ctkrc")
    parser = configparser.ConfigParser()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not find config file at {config_path}")

    parser.read(config_path)

    if "llm" not in parser:
        raise ValueError(
            "Config file ~/.ctkrc is missing the [llm] section. "
            "Please add it with 'endpoint' and 'api_key' keys."
        )

    endpoint = parser["llm"].get("endpoint", "")
    api_key = parser["llm"].get("api_key", "")
    model = parser["llm"].get("model", "gpt-3.5-turbo")

    if not endpoint or not api_key or not model:
        raise ValueError(
            "Please make sure your [llm] section in ~/.ctkrc "
            "includes 'endpoint', 'api_key', and 'model' keys."
        )
    
    return endpoint, api_key, model

def query_llm(lib_dir, prompt):
    """
    Queries an OpenAI-compatible LLM endpoint with the given prompt.

    :param prompt: The user query or conversation prompt text.
    :param model: The OpenAI model name to use, defaults to gpt-3.5-turbo.
    :param temperature: Sampling temperature, defaults to 0.7.
    :return: The JSON response from the endpoint.
    """
    endpoint, api_key, model = load_ctkrc_config()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # let's prefix the prompt with the contents of the file `llm-instructions.md`
    # however, since this is a ypi package, we need to find the path to the file
    # we can use the `__file__` variable to get the path to this file, and then
    # construct the path to the `llm-instructions.md` file
    file_instr_path = os.path.join(os.path.dirname(__file__), "llm-instructions.md")    

    # Read the markdown file
    with open(file_instr_path, "r") as f:
        template = Template(f.read())

    data = {
        "lib_dir": lib_dir
    }

    instructions = template.safe_substitute(data)
    prompt = instructions + "\n\nQuestion: " + prompt

    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemError(f"Error calling LLM endpoint: {e}")

    return response.json()
```

'''

### ctk/llm-instructions.md


'''markdown
'''

### Source Files

#### Source File: `ctk/__init__.py`

```python

```

#### Source File: `ctk/cli.py`

```python
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
import time
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown
from rich.json import JSON

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

def query_conversations_regex(libdir, expression, field_paths):
    """
    @brief Query the conversations with a regex expression.

    @param libdir Path to the conversation library directory.
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

def union_conversation_libs(libdirs, output_dir, conflict_resolution="skip"):
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

    # Subcommand: regex
    regex_parser = subparsers.add_parser("regex", help="Run a regex query on the ctk lib")
    regex_parser.add_argument("libdir", help="Path to the conversation library directory")
    regex_parser.add_argument("expression", help="Regex expression")
    regex_parser.add_argument("field_paths", nargs="+", help="Field paths to apply the regex")

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
    llm_parser = subparsers.add_parser("llm", help="Run a language model on the ctk lib")
    llm_parser.add_argument("libdir", help="Path to the conversation library directory")
    llm_parser.add_argument("query", help="Query to run")

    args = parser.parse_args()

    if args.command == "list":
        list_conversations(args.libdir, args.fields, args.indices) 

    elif args.command == "regex":
        results = query_conversations_regex(args.libdir, args.expression, args.field_paths)
        print(json.dumps(results, indent=2))

    elif args.command == "remove":
        conversations = load_conversations(args.libdir)
        for index in sorted(args.indices, reverse=True):
            del conversations[index]
        save_conversations(args.libdir, conversations)
        print(f"Removed {len(args.indices)} conversations")

    elif args.command == "export":
        print("TODO: Implement export command")

    elif args.command == "llm":
        print("TODO: Implement llm command")

    elif args.command == "jmespath":
        result = query_conversations_jmespath(args.libdir, args.query)
        print(json.dumps(result, indent=2))

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

```

#### Source File: `ctk/llm.py`

```python
import os
import requests
import configparser
from string import Template

def load_ctkrc_config():
    """
    Loads configuration from ~/.ctkrc.

    Expects a section [llm] with at least 'endpoint' and 'api_key'.
    """
    config_path = os.path.expanduser("~/.ctkrc")
    parser = configparser.ConfigParser()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not find config file at {config_path}")

    parser.read(config_path)

    if "llm" not in parser:
        raise ValueError(
            "Config file ~/.ctkrc is missing the [llm] section. "
            "Please add it with 'endpoint' and 'api_key' keys."
        )

    endpoint = parser["llm"].get("endpoint", "")
    api_key = parser["llm"].get("api_key", "")
    model = parser["llm"].get("model", "gpt-3.5-turbo")

    if not endpoint or not api_key or not model:
        raise ValueError(
            "Please make sure your [llm] section in ~/.ctkrc "
            "includes 'endpoint', 'api_key', and 'model' keys."
        )
    
    return endpoint, api_key, model

def query_llm(lib_dir, prompt):
    """
    Queries an OpenAI-compatible LLM endpoint with the given prompt.

    :param prompt: The user query or conversation prompt text.
    :param model: The OpenAI model name to use, defaults to gpt-3.5-turbo.
    :param temperature: Sampling temperature, defaults to 0.7.
    :return: The JSON response from the endpoint.
    """
    endpoint, api_key, model = load_ctkrc_config()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # let's prefix the prompt with the contents of the file `llm-instructions.md`
    # however, since this is a ypi package, we need to find the path to the file
    # we can use the `__file__` variable to get the path to this file, and then
    # construct the path to the `llm-instructions.md` file
    file_instr_path = os.path.join(os.path.dirname(__file__), "llm-instructions.md")    

    # Read the markdown file
    with open(file_instr_path, "r") as f:
        template = Template(f.read())

    data = {
        "lib_dir": lib_dir
    }

    instructions = template.safe_substitute(data)
    prompt = instructions + "\n\nQuestion: " + prompt

    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemError(f"Error calling LLM endpoint: {e}")

    return response.json()
```

'''

### ctk/llm-instructions.md


'''markdown
```markdown
# Instructions for Using the `ctk` Command-Line Tool

The `ctk` (Conversation Tree Toolkit) is a powerful command-line tool designed to manage and analyze conversation logs compatible with OpenAI's data export format (e.g., ChatGPT conversation histories). These instructions will guide you on how to effectively utilize the `ctk` tool to perform various operations such as listing conversations, querying data, merging libraries, exporting conversations, and leveraging language models for advanced analysis.

## Basic Usage

The general syntax for using `ctk` is as follows:

```bash
ctk <command> [options] <arguments>
```

Replace `<command>` with one of the available commands listed below, and provide the necessary `[options]` and `<arguments>` as required by each command.

---

## Available Commands

### 1. `list`

**Description:**  
Lists all conversations in the specified library directory.

**Usage:**

```bash
ctk list $libdir [--indices <indices>] [--fields <fields>]
```

**Options:**
- `--indices`: Specify the indices of conversations to list. If omitted, all conversations are listed.
- `--fields`: Specify which fields to include in the output (default: `title`, `update_time`).

**Example:**

```bash
ctk list $libdir --fields title update_time
```

---

### 2. `search`

**Description:**  
Runs a regex query on the conversations to filter results based on specified patterns.

**Usage:**

```bash
ctk search $libdir <expression> --fields <fields>
```

**Arguments:**
- `<expression>`: The regex pattern to search for.
- `<fields>`: One or more JMESPath expressions specifying the fields to apply the regex to.

**Example:**

```bash
ctk search $libdir testing
```

---

### 3. `jmespath`

**Description:**  
Executes a JMESPath query on the conversations for advanced data retrieval.

**Usage:**

```bash
ctk jmespath $libdir <query>
```

**Arguments:**
- `<query>`: The JMESPath expression to execute.

**Example:**

```bash
ctk jmespath $libdir "conversations[?status=='active']"
```

---

### 4. `conversation`

**Description:**  
Prints detailed conversation information based on conversation indices or specific node IDs.

**Usage:**

```bash
ctk conversation $libdir <indices> [--node <node_id>] [--json]
```

**Arguments:**
- `<indices>`: One or more indices of conversations to display.

**Options:**
- `--node`: Specify the node ID to indicate the terminal node of a conversation path.
- `--json`: Output the conversation in JSON format instead of a formatted table.

**Example:**

```bash
ctk conversation $libdir 0 1 2 --node node123 --json
```

---

### 5. `merge`

**Description:**  
Merges multiple `ctk` libraries into a single library using specified operations.

**Usage:**

```bash
ctk merge <operation> <libdirs> -o <output_dir>
```

**Arguments:**
- `<operation>`: Type of merge operation (`union`, `intersection`, `difference`).
- `<libdirs>`: List of library directories to merge.

**Options:**
- `-o, --output`: Specify the output library directory.

**Example:**

```bash
ctk merge union ./lib1 ./lib2 -o ./merged_lib
```

---

### 6. `export`

**Description:**  
Exports conversations from the library in specified formats.

**Usage:**

```bash
ctk export $libdir <indices> [--format <format>]
```

**Arguments:**
- `<indices>`: One or more indices of conversations to export. If omitted, all conversations are exported.

**Options:**
- `--format`: Output format (`json`, `markdown`, `hugo`). Default is `json`.

**Example:**

```bash
ctk export $libdir 0 1 --format markdown
```

---

### 7. `dash`

**Description:**  
Launches a Streamlit-based dashboard for interactive exploration of the conversation library.

**Usage:**

```bash
ctk dash $libdirlib
```

---

## Examples

1. **Listing All Conversations:**

   ```bash
   ctk list $libdir
   ```

2. **Listing Specific Fields:**

   ```bash
   ctk list $libdir --fields title update_time model
   ```

3. **Filtering Conversations with Regex Search:**

   ```bash
   ctk sarch $libdir "who are you"
   ```

4. **Running a JMESPath Query:**

   ```bash
   ctk jmespath $libdir "conversations[?status=='active']"
   ```

5. **Merging Two Libraries with Union Operation:**

   ```bash
   ctk merge union ./lib1 ./lib2 -o ./merged_lib
   ```

6. **Exporting Conversations to Markdown:**

   ```bash
   ctk export $libdir 0 1 --format markdown
   ```

7. **Launching the Dashboard:**

   ```bash
   ctk dash $libdir
   ```

8. **Running a Language Model Query:**

   ```bash
   ctk llm $libdir "Provide a summary of conversation 0."
   ```

---

## Notes

- **Indices**: Conversation indices start at `0`. Use the `list` command to view available indices before performing operations on specific conversations.
  
- **Conflict Resolution in Merges**: When merging libraries, be mindful of duplicate conversation IDs. Choose the appropriate conflict resolution strategy (`skip`, `overwrite-old`, `error`) based on your requirements.
  
- **JSON Output**: Utilize the `--json` flag in commands like `list` and `conversation` for machine-readable output, which is useful for further processing or integration with other tools.
  
- **Error Handling**: The tool provides informative error messages. Ensure to read them carefully to troubleshoot issues related to missing files, incorrect indices, or invalid configurations.

---

## Getting Help

For more information on using the `ctk` tool, you can access the help documentation for each command by using the `--help` flag. For example:

```bash
ctk list --help
```

This command will display detailed information about the `list` command, including its usage, arguments, and options.

---

## Structure of `{libdir}/conversations.json`

In the ctk library stored in the directory `$libdir`, we have a number of files, but the main file of interest is `converseations.json`.
The `converations.json` file contains structured data for ChatGPT chat sessions (conversation trees).

### Example `conversations.json`:

```json
```

## Response Format for LLM Queries

When you are prompted with a query, respond in JSON. The JSON should take the following general format:

```json
{
  "command": "command_name",
  "args": ["$libdir", "<args>"]
}
```

### Example 1

Suppose the query is "Find conversations that are starred."
Then, you might respond with the output:

```json
{
  "command": "jmespath",
  "args": ["$libdir", "conversations[?starred]"]
}
```

### Example 2

If the prompt was slightly different, for example "Find conversations that are starred and only show me the title and URL", the response might be:

```json
{
  "command": "jmespath",
  "args": ["$libdir", "conversations[?starred].[title, url]"]
}
```

A full list of commands is give by:

- `search`: Search (using regex) conversations by query
- `list`: List the converations with the given indices
- `remove`: Remove a conversation by its ID
- `merge`: Perform merge (set) operations on converation libraries
- `cloud`: Generate a URL mention graph from bookmarks
- `export`:  Export ctk library to a different format
- `jmespath`: Query conversations using JMESPath
- `llm`: Query the ctk library using a Large Language Model

```'''

### Source Files

#### Source File: `ctk/__init__.py`

```python

```

#### Source File: `ctk/cli.py`

```python
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
    show_tree_parser = subparsers.add_parser("show-conversation-tree", help="Conversation tree visualization")
    show_tree_parser.add_argument("libdir", help="Path to the conversation library directory")
    show_tree_parser.add_argument("index", type=int, help="Index of conversation tree to visualize")
    show_tree_parser.add_argument("--label-fields", nargs="+", 
                                  type=str, default=['id'], help="When showing the tree, use this field as the node's label")
    show_tree_parser.add_argument("--truncate", type=int, default=10, help="Truncate the label of a node to this length. Default: 10")


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
        conv = conversations[args.index]
        tree_map = conv.get("mapping", {})
        t = AlgoTree.FlatForest(tree_map)

        # a label field can be something like message.author.name
        # so we need to split it by '.' and then recursively search for the value
        paths = []
        
        for field in args.label_fields:
            paths.append(field.split('.'))

        def path_value(data, path):
            for p in path:
                data = data.get(p)
                if data is None:
                    break
            
            last = path[-1].lower()
            if last == "create_time":
                return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data))
            elif isinstance(data, (int, float)):
                return str(data)
            elif isinstance(data, (list, dict)):
                return json.dumps(data)
            elif data is None:
                return "N/A"
            else:
                return data
 
        def get_label(node):
            results = []
            for path in paths:
                value = path_value(node.payload, path)
                value = value[:args.truncate]
                results.append(value)

            label = " ".join(results)
            return label


        console.print(AlgoTree.pretty_tree(t, node_name=get_label))

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

```

#### Source File: `ctk/cloud.py`

```python
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
import logging
import networkx as nx
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import matplotlib.pyplot as plt
from urllib.parse import urlparse
from pyvis.network import Network
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.table import Table
from rich.console import Console
from colorama import init as colorama_init, Fore, Style

# Initialize colorama and rich console
colorama_init(autoreset=True)
console = Console()

def extract_urls(html_content, base_url, bookmark_urls=None, max_mentions=50):
    """Extract a limited number of absolute URLs from the HTML content.
    
    If bookmark_urls is provided, only include URLs present in this set.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')  # Use 'lxml' parser for robustness
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme in ('http', 'https'):
            if bookmark_urls is None or full_url in bookmark_urls:
                if full_url != base_url:  # Prevent self-loop by excluding the bookmark's own URL
                    urls.add(full_url)
                    if len(urls) >= max_mentions:
                        break
    return urls


def extract_urls2(html_content, base_url, bookmark_urls=None):
    """Extract all absolute URLs from the HTML content.
    
    If bookmark_urls is provided, only include URLs present in this set.
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')  # Try 'lxml' parser first
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme in ('http', 'https'):
            if bookmark_urls is None or full_url in bookmark_urls:
                urls.add(full_url)
    return urls

def get_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    """Configure a requests Session with retry strategy."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def fetch_html(url, verify_ssl=True, session=None):
    """Fetch HTML content from a URL with optional SSL verification."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; BookmarkTool/1.0)'
        }
        if session:
            response = session.get(url, headers=headers, timeout=10, verify=verify_ssl)
        else:
            response = requests.get(url, headers=headers, timeout=10, verify=verify_ssl)
        response.raise_for_status()
        return response.text
    except requests.exceptions.SSLError as ssl_err:
        logging.error(f"SSL error fetching {url}: {ssl_err}")
        return None
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error fetching {url}: {http_err}")
        return None
    except requests.exceptions.RequestException as req_err:
        logging.error(f"Error fetching {url}: {req_err}")
        return None
    
def is_valid_url(url):
    """Check if the URL has a valid scheme and netloc."""
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

def generate_url_graph(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()  # Assuming get_session is defined elsewhere
    
    success_count = 0
    failure_count = 0
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark 
                for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                if not is_valid_url(bookmark['url']):
                    logging.error(f"Invalid URL '{bookmark['url']}' for bookmark ID {bookmark['id']}. Skipping.")
                    failure_count += 1
                    progress.advance(task)
                    continue
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        # Prevent self-loops by ensuring mentioned_url is different from bookmark['url']
                        if mentioned_url != bookmark['url']:
                            if only_in_library:
                                if mentioned_url in bookmark_urls:
                                    G.add_edge(bookmark['url'], mentioned_url)
                            else:
                                G.add_edge(bookmark['url'], mentioned_url)
                    success_count += 1
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                    failure_count += 1
                progress.advance(task)
    
    # Additional Safety: Remove any accidental self-loops
    self_loops = list(nx.selfloop_edges(G))
    if self_loops:
        logging.warning(f"Detected {len(self_loops)} self-loop(s). Removing them.")
        G.remove_edges_from(self_loops)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    logging.info(f"Successfully processed {success_count} bookmarks.")
    logging.info(f"Failed to process {failure_count} bookmarks.")
    return G

def generate_url_graph0(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()  # Assuming get_session is defined elsewhere
    
    success_count = 0
    failure_count = 0
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark 
                for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                if not is_valid_url(bookmark['url']):
                    logging.error(f"Invalid URL '{bookmark['url']}' for bookmark ID {bookmark['id']}. Skipping.")
                    failure_count += 1
                    progress.advance(task)
                    continue
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        # Prevent self-loops by ensuring mentioned_url is different from bookmark['url']
                        if mentioned_url != bookmark['url']:
                            if only_in_library:
                                if mentioned_url in bookmark_urls:
                                    G.add_edge(bookmark['url'], mentioned_url)
                            else:
                                G.add_edge(bookmark['url'], mentioned_url)
                    success_count += 1
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                    failure_count += 1
                progress.advance(task)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    logging.info(f"Successfully processed {success_count} bookmarks.")
    logging.info(f"Failed to process {failure_count} bookmarks.")
    return G

def generate_url_graph2(bookmarks, max_bookmarks=100, only_in_library=True, ignore_ssl=False):
    """Generate a NetworkX graph based on URL mentions in bookmarks."""
    G = nx.DiGraph()
    total = min(len(bookmarks), max_bookmarks)
    logging.info(f"Generating graph from {total} bookmarks.")
    
    # Create a set of all bookmark URLs for quick lookup
    bookmark_urls = set(b['url'] for b in bookmarks[:total])
    
    session = get_session()
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Processing bookmarks...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_bookmark = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark for bookmark in bookmarks[:total]
            }
            for future in as_completed(future_to_bookmark):
                bookmark = future_to_bookmark[future]
                html_content = future.result()
                if html_content:
                    if only_in_library:
                        mentioned_urls = extract_urls(html_content, bookmark['url'], bookmark_urls=bookmark_urls)
                    else:
                        mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        if only_in_library:
                            # Since extract_urls already filters, just add the edge
                            G.add_edge(bookmark['url'], mentioned_url)
                        else:
                            if mentioned_url != bookmark['url']:
                                G.add_edge(bookmark['url'], mentioned_url)
                else:
                    logging.warning(f"Skipping bookmark ID {bookmark['id']} due to fetch failure.")
                progress.advance(task)
    
    logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    return G

def visualize_graph_pyvis(graph, output_file):
    """Visualize the graph using pyvis and save as an HTML file."""
    net = Network(height='750px', width='100%', directed=True)
    net.from_nx(graph)
    net.show_buttons(filter_=['physics'])

    try:
        # Use write_html to save the HTML file without attempting to open it
        net.write_html(output_file)
        logging.info(f"Interactive graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save interactive graph visualization: {e}")

def visualize_graph_png(graph, output_file):
    # Fallback to matplotlib if not HTML
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(graph, k=0.05, iterations=30)
    nx.draw_networkx_nodes(graph, pos, node_size=10, node_color='blue', alpha=0.5)
    nx.draw_networkx_edges(graph, pos, arrows=False, alpha=0.75)
    plt.title("Bookmark URL Mention Graph")
    plt.axis('off')
    plt.tight_layout()
    try:
        plt.savefig(output_file, format='PNG')
        logging.info(f"Graph visualization saved to '{output_file}'.")
    except Exception as e:
        logging.error(f"Failed to save graph visualization: {e}")
    plt.close()

def display_graph_stats(graph, top_n=5):
    """Compute and display detailed statistics of the NetworkX graph."""
    stats = {}
    stats['Number of Nodes'] = graph.number_of_nodes()
    stats['Number of Edges'] = graph.number_of_edges()
    stats['Density'] = nx.density(graph)
    stats['Average Degree'] = sum(dict(graph.degree()).values()) / graph.number_of_nodes() if graph.number_of_nodes() > 0 else 0
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
        stats['Top Degree Centrality'] = ', '.join([f"{url} ({centrality:.4f})" for url, centrality in top_degree])
    except:
        stats['Top Degree Centrality'] = 'N/A'
    
    # Identify top N nodes by Betweenness Centrality
    try:
        top_betweenness = sorted(betweenness_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Top Betweenness Centrality'] = ', '.join([f"{url} ({centrality:.4f})" for url, centrality in top_betweenness])
    except:
        stats['Top Betweenness Centrality'] = 'N/A'
    
    # Display the statistics using Rich
    table = Table(title="Graph Statistics", show_header=True, header_style="bold magenta")
    table.add_column("Statistic", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")
    
    for key, value in stats.items():
        table.add_row(key, str(value))
    
    console.print(table)

```

#### Source File: `ctk/llm.py`

```python
import os
import requests
import configparser
from string import Template

def load_ctkrc_config():
    """
    Loads configuration from ~/.ctkrc.

    Expects a section [llm] with at least 'endpoint' and 'api_key'.
    """
    config_path = os.path.expanduser("~/.ctkrc")
    parser = configparser.ConfigParser()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not find config file at {config_path}")

    parser.read(config_path)

    if "llm" not in parser:
        raise ValueError(
            "Config file ~/.ctkrc is missing the [llm] section. "
            "Please add it with 'endpoint' and 'api_key' keys."
        )

    endpoint = parser["llm"].get("endpoint", "")
    api_key = parser["llm"].get("api_key", "")
    model = parser["llm"].get("model", "gpt-3.5-turbo")

    if not endpoint or not api_key or not model:
        raise ValueError(
            "Please make sure your [llm] section in ~/.ctkrc "
            "includes 'endpoint', 'api_key', and 'model' keys."
        )
    
    return endpoint, api_key, model

def query_llm(lib_dir, prompt):
    """
    Queries an OpenAI-compatible LLM endpoint with the given prompt.

    :param lib_dir: The directory where the library is located.
    :param prompt: The user query or conversation prompt text.
    :return: The JSON response from the endpoint.
    """
    endpoint, api_key, model = load_ctkrc_config()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    file_instr_path = os.path.join(os.path.dirname(__file__), "llm-instructions.md")    

    from string import Template
    
    # Read the markdown file
    with open(file_instr_path, "r") as f:
        template = Template(f.read())

    data = {
        "libdir": lib_dir
    }

    instructions = template.safe_substitute(data)
    prompt = instructions + "\n\nQuestion: " + prompt

    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    try:
        response = requests.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemError(f"Error calling LLM endpoint: {e}")

    return response.json()
```

