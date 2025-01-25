# Project Directory: ctk

## Documentation Files


### README.md


'''markdown
# `ctk`: Conversation Tree Toolkit

**`ctk`** (Conversation Tree Toolkit) is a powerful command-line tool designed to manage, analyze, and engage with conversation logs exported from OpenAI's platforms (e.g., ChatGPT). Whether you're looking to filter conversations, perform advanced queries, merge multiple conversation libraries, or leverage Large Language Models (LLMs) for deeper insights, `ctk` provides a comprehensive suite of tools to streamline your workflow.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Available Commands](#available-commands)
    - [`list`](#1-list)
    - [`search`](#2-search)
    - [`jmespath`](#3-jmespath)
    - [`conversation`](#4-conversation)
    - [`merge`](#5-merge)
    - [`export`](#6-export)
    - [`dash`](#7-dash)
    - [`llm`](#8-llm)
- [Examples](#examples)
- [Structure of `conversations.json`](#structure-of-conversationsjson)
- [Response Format for LLM Queries](#response-format-for-llm-queries)
- [Notes](#notes)
- [Getting Help](#getting-help)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **List Conversations**: Display a list of all conversations with selected fields.
- **Search with Regex**: Filter conversations based on regex patterns applied to specific fields.
- **Advanced Queries with JMESPath**: Perform complex queries for data retrieval.
- **Conversation Details**: View detailed information about specific conversations.
- **Merge Libraries**: Combine multiple conversation libraries using set operations.
- **Export Conversations**: Export conversations in various formats like JSON, Markdown, or Hugo.
- **Interactive Dashboard**: Launch a Streamlit-based dashboard for visual exploration.
- **LLM Integration**: Engage with Large Language Models to perform tasks like summarization or analysis on your conversation data.

---

## Installation

### Prerequisites

- **Python 3.7+**
- **pip** (Python package installer)

### Local Development Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/queelius/ctk.git
   cd ctk
   ```

2. **Create a Virtual Environment (Optional but Recommended)**

   Using `venv`:

   ```bash
   python3 -m venv ctk-env
   source ctk-env/bin/activate
   ```

   Using `conda`:

   ```bash
    conda create --name ctk-env python=3.8
    conda activate ctk-env
   ```

3. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Make the `ctk` Command Accessible**

   Ensure that the `ctk` script is executable and added to your PATH. You can achieve this by installing the package or setting up an alias.

   ```bash
   chmod +x ctk/cli.py
   ln -s $(pwd)/ctk/cli.py /usr/local/bin/ctk
   ```

   *Alternatively, you can install `ctk` as a package if a `setup.py` is provided.*

---

### End-User Installation Using `pypi`:

1. **Install the Package**

   ```bash
   pip install ctk
   ```

## Configuration

Before using the `llm` command, you need to configure the LLM settings.

1. **Create Configuration File**

   Create a file named `.ctkrc` in your home directory:

   ```bash
   touch ~/.ctkrc
   ```

2. **Add LLM Configuration**

   Open `.ctkrc` with your preferred text editor and add the following:

   ```ini
   [llm]
   endpoint = https://api.openai.com/v1/engines/davinci/completions
   api_key = YOUR_API_KEY
   model = gpt-3.5-turbo
   ```

   - **endpoint**: The API endpoint for the language model service.
   - **api_key**: Your API key for authenticating with the language model service.
   - **model**: The specific language model to use (e.g., `gpt-3.5-turbo`).

   **Note:** Replace `YOUR_API_KEY` with your actual API key.

---

## Usage

The `ctk` tool offers various subcommands to perform different operations on your conversation libraries. The general syntax is:

```bash
ctk <command> [options] <arguments>
```

### Available Commands

#### 1. `list`

**Description:**  
Lists all conversations in the specified library directory.

**Usage:**

```bash
ctk list <libdir> [--indices <indices>] [--fields <fields>]
```

**Arguments:**
- `<libdir>`: Path to the conversation library directory.

**Options:**
- `--indices`: Specify the indices of conversations to list. If omitted, all conversations are listed.
- `--fields`: Specify which fields to include in the output (default: `title`, `update_time`).

**Example:**

```bash
ctk list ./conversations --fields title update_time model
```

---

#### 2. `search`

**Description:**  
Runs a regex query on the conversations to filter results based on specified patterns.

**Usage:**

```bash
ctk search <libdir> <expression> --fields <fields>
```

**Arguments:**
- `<libdir>`: Path to the conversation library directory.
- `<expression>`: The regex pattern to search for.

**Options:**
- `--fields`: One or more JMESPath expressions specifying the fields to apply the regex to (default: `title`).
- `--json`: Output the results in JSON format.

**Example:**

```bash
ctk search ./conversations "C\+\+" --fields title --json
```

*Note: To search for the literal string "C++", ensure you escape the plus signs as shown.*

---

#### 3. `jmespath`

**Description:**  
Executes a JMESPath query on the conversations for advanced data retrieval.

**Usage:**

```bash
ctk jmespath <libdir> <query>
```

**Arguments:**
- `<libdir>`: Path to the conversation library directory.
- `<query>`: The JMESPath expression to execute.

**Example:**

```bash
ctk jmespath ./conversations "conversations[?status=='active']"
```

---

#### 4. `conversation`

**Description:**  
Prints detailed conversation information based on conversation indices or specific node IDs.

**Usage:**

```bash
ctk conversation <libdir> <indices> [--node <node_id>] [--json]
```

**Arguments:**
- `<libdir>`: Path to the conversation library directory.
- `<indices>`: One or more indices of conversations to display.

**Options:**
- `--node`: Specify the node ID to indicate the terminal node of a conversation path.
- `--json`: Output the conversation in JSON format instead of a formatted table.

**Example:**

```bash
ctk conversation ./conversations 0 1 2 --node node123 --json
```

---

#### 5. `merge`

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

#### 6. `export`

**Description:**  
Exports conversations from the library in specified formats.

**Usage:**

```bash
ctk export <libdir> <indices> [--format <format>]
```

**Arguments:**
- `<libdir>`: Path to the conversation library directory.
- `<indices>`: One or more indices of conversations to export. If omitted, all conversations are exported.

**Options:**
- `--format`: Output format (`json`, `markdown`, `hugo`). Default is `json`.

**Example:**

```bash
ctk export ./conversations 0 1 --format markdown
```

---

#### 7. `dash`

**Description:**  
Launches a Streamlit-based dashboard for interactive exploration of the conversation library.

**Usage:**

```bash
ctk dash <libdir>
```

**Arguments:**
- `<libdir>`: Path to the conversation library directory.

**Example:**

```bash
ctk dash ./conversations
```

---

#### 8. `llm`

**Description:**  
Runs a language model query on the conversation library to perform tasks like summarization, analysis, or generating insights.

**Usage:**

```bash
ctk llm <libdir> <query> [--json]
```

**Arguments:**
- `<libdir>`: Path to the conversation library directory.
- `<query>`: The query or prompt to send to the language model.

**Options:**
- `--json`: Output the results in JSON format.

**Example:**

```bash
ctk llm ./conversations "Provide a summary of conversation 0."
```

*Note: Ensure that the `.ctkrc` configuration file is properly set up with your LLM API credentials.*

---

## Examples

1. **Listing All Conversations:**

   ```bash
   ctk list ./conversations
   ```

2. **Listing Specific Fields:**

   ```bash
   ctk list ./conversations --fields title update_time model
   ```

3. **Filtering Conversations with Regex Search:**

   ```bash
   ctk search ./conversations "C\+\+" --fields title --json
   ```

4. **Running a JMESPath Query:**

   ```bash
   ctk jmespath ./conversations "conversations[?status=='active']"
   ```

5. **Merging Two Libraries with Union Operation:**

   ```bash
   ctk merge union ./lib1 ./lib2 -o ./merged_lib
   ```

6. **Exporting Conversations to Markdown:**

   ```bash
   ctk export ./conversations 0 1 --format markdown
   ```

7. **Launching the Dashboard:**

   ```bash
   ctk dash ./conversations
   ```

8. **Running a Language Model Query:**

   ```bash
   ctk llm ./conversations "Provide a summary of conversation 0."
   ```

---

## Structure of `conversations.json`

The `ctk` library stores conversation data in a JSON file named `conversations.json` located within your specified library directory (`libdir`). This file contains structured data representing ChatGPT chat sessions, organized as conversation trees.

### Example `conversations.json`:

```json
[
  {
    "id": "conversation_1",
    "title": "Project Discussion",
    "create_time": 1633072800,
    "update_time": 1633076400,
    "default_model_slug": "gpt-3.5-turbo",
    "safe_urls": ["https://example.com"],
    "mapping": {
      "node_1": {
        "text": "Hello, how can I assist you today?",
        "payload": {
          "message": {
            "content": {
              "content_type": "text",
              "parts": ["Hello, how can I assist you today?"]
            },
            "author": {
              "role": "assistant",
              "name": "ChatGPT"
            },
            "create_time": 1633072800
          }
        }
      },
      "node_2": {
        "text": "I need help with my project.",
        "payload": {
          "message": {
            "content": {
              "content_type": "text",
              "parts": ["I need help with my project."]
            },
            "author": {
              "role": "user",
              "name": "Alice"
            },
            "create_time": 1633072860
          }
        }
      }
    },
    "current_node": "node_2"
  }
]
```

*This is a simplified example. The actual structure may vary based on your specific data.*

---

## Response Format for LLM Queries

When using the `llm` command to interact with a Large Language Model, the expected response format is JSON. This structured format ensures that the `ctk` tool can parse and execute the appropriate commands based on your query.

### General Format:

```json
{
  "command": "command_name",
  "args": ["<libdir>", "<args>"]
}
```

### Examples

**Example 1: Finding Starred Conversations**

*Query: "Find conversations that are starred."*

**Response:**

```json
{
  "command": "jmespath",
  "args": ["./conversations", "conversations[?starred]"]
}
```

**Example 2: Listing Titles and URLs of Starred Conversations**

*Query: "Find conversations that are starred and only show me the title and URL."*

**Response:**

```json
{
  "command": "jmespath",
  "args": ["./conversations", "conversations[?starred].[title, url]"]
}
```

---

## Notes

- **Library Directory (`libdir`)**: Ensure that the specified library directory exists and contains a valid `conversations.json` file before performing operations.

- **Indices**: Conversation indices start at `0`. Use the `list` command to view available indices before performing operations on specific conversations.

- **Regex Patterns**: When using regex patterns, escape special characters as needed. For example, to search for "C++", use `C\+\+`.

- **Conflict Resolution in Merges**: When merging libraries, duplicate conversation IDs can be handled using strategies like `skip`, `overwrite-old`, or `error` based on your requirements.

- **JSON Output**: Utilize the `--json` flag in commands like `list` and `conversation` for machine-readable output, which is useful for further processing or integration with other tools.

- **Error Handling**: The tool provides informative error messages. Ensure to read them carefully to troubleshoot issues related to missing files, incorrect indices, or invalid configurations.

- **Performance**: For large libraries, some operations might take longer. Consider optimizing your queries and using efficient patterns to enhance performance.

---

## Getting Help

For more information on using the `ctk` tool, access the help documentation for each command using the `--help` flag. For example:

```bash
ctk list --help
```

This command will display detailed information about the `list` command, including its usage, arguments, and options.

---

## Contributing

Contributions are welcome! If you'd like to contribute to the `ctk` project, please follow these steps:

1. **Fork the Repository**

   Click the "Fork" button at the top right of the repository page to create your own fork.

2. **Clone Your Fork**

   ```bash
   git clone https://github.com/yourusername/ctk.git
   cd ctk
   ```

3. **Create a New Branch**

   ```bash
   git checkout -b feature/YourFeatureName
   ```

4. **Make Your Changes**

   Implement your feature or bug fix.

5. **Commit Your Changes**

   ```bash
   git commit -m "Add feature: YourFeatureName"
   ```

6. **Push to Your Fork**

   ```bash
   git push origin feature/YourFeatureName
   ```

7. **Create a Pull Request**

   Navigate to the original repository and click the "New Pull Request" button. Provide a clear description of your changes.

**Please ensure that your contributions adhere to the project's coding standards and include appropriate tests where applicable.**

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgements

- Developed using Python and leveraging powerful libraries like `argparse`, `jmespath`, `rich`, `requests`, `networkx`, and `pyvis`.
- Inspired by the need to efficiently manage and analyze conversation logs from AI platforms.

---

## Contact

For questions, suggestions, or support, please open an issue on the [GitHub repository](https://github.com/queelius/ctk/issues) or contact the maintainer at [your.email@example.com](mailto:lex@metafunctor.com).
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
import sys
import AlgoTree
import subprocess
from rich.console import Console
from rich.json import JSON
from  .utils import ( load_conversations, save_conversations, pretty_print_conversation, 
                    query_conversations_search, query_conversations_jmespath, path_value,
                    list_conversations, ensure_libdir_structure, print_json_as_table)
from .merge import union_libs, intersect_libs, diff_libs
from importlib.metadata import version
import webbrowser

from .llm import query_llm
from .vis import generate_url_graph, visualize_graph_pyvis, visualize_graph_png
from .stats import graph_stats
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

console = Console()

def launch_streamlit_dashboard(libdir):
    """
    @brief Launch a Streamlit-based dashboard for exploring the ctx lib.
    @param libdir Path to the conversation library directory.
    @return None
    @details This function just outlines how you'd call Streamlit. 
    """
    dash_cmd = [
        "streamlit", "run",
        "streamlit/app.py",
        #"--",  # pass CLI arguments to the Streamlit app
        f"--libdir={libdir}"
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
    parser.add_argument("--version", action="version", version=version("conversation-tk"))

    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    # Subcommand: search
    regex_parser = subparsers.add_parser("search", help="Run a search using regex against the ctk lib on the specified fields")
    regex_parser.add_argument("libdir", help="Path to the conversation library directory")
    regex_parser.add_argument("expression", help="Regex expression")
    regex_parser.add_argument("--fields", nargs="+", help="Field paths to apply the regex", default=["title"])
    regex_parser.add_argument("--json", action="store_true", help="Output as JSON. Default: False")

    # Subcommand: conversation-tree
    tree_parser = subparsers.add_parser("conv-stats", help="Compute conversation tree statistics")
    tree_parser.add_argument("libdir", help="Path to the conversation library directory")
    tree_parser.add_argument("index", type=int, help="Index of conversation tree")
    tree_parser.add_argument("--json", action="store_true", help="Output as JSON. Default: False")
    tree_parser.add_argument("--no-payload", action="store_true", help="Do not show payload in the output. Default: False")

    # Subcommand: show-conversation-tree
    show_tree_parser = subparsers.add_parser("tree", help="Conversation tree visualization")
    show_tree_parser.add_argument("libdir", help="Path to the conversation library directory")
    show_tree_parser.add_argument("index", type=int, help="Index of conversation tree to visualize")
    show_tree_parser.add_argument("--label-fields", nargs="+", 
                                  type=str, default=['id', 'message.content.parts'], help="When showing the tree, use this field as the node's label")
    show_tree_parser.add_argument("--truncate", type=int, default=8, help="Truncate each field to this length. Default: 8")

    # Subcommand: conversation
    conv_parser = subparsers.add_parser("conv", help="Print conversation based on a particular node id. Defaults to using `current_node` for the corresponding conversation tree.")
    conv_parser.add_argument("libdir", help="Path to the conversation library directory")
    conv_parser.add_argument("indices", nargs="+", type=int, help="Indices of conversations to print")
    conv_parser.add_argument("--node", default=None, help="Node id that indicates the terminal node of a conversation path")
    conv_parser.add_argument("--json", action="store_true", help="Output as JSON")
    conv_parser.add_argument("--msg-limit", type=int, default=1000, help="Limit the number of messages to display. Default: 1000")
    conv_parser.add_argument("--msg-roles", type=str, nargs="+", default=["user", "assistant"], help="Roles to include in message output")
    conv_parser.add_argument("--msg-start-index", type=int, default=0, help="Start index for messages to display. Default: 0")
    conv_parser.add_argument("--msg-end-index", type=int, default=-1, help="End index for messages to display. Default: -1 (end of list). Use negative values to count from the end.")

    # Subcommand: remove
    remove_parser = subparsers.add_parser("remove", help="Remove a conversation from the ctk lib")
    remove_parser.add_argument("libdir", help="Path to the conversation library directory")
    remove_parser.add_argument("indices", type=int, nargs="+", help="Indices of conversations to remove")

    # Subcommand: share
    share_parser = subparsers.add_parser("export", help="Export a conversation from the ctk lib")
    share_parser.add_argument("libdir", help="Path to the conversation library directory")
    share_parser.add_argument("--indices", type=int, nargs="+", default=None, help="Indices of conversations to export. Default: all")
    share_parser.add_argument("--format", choices=["json", "markdown", "hugo", "zip"], default="json", help="Output format")

    # Subcommand: list
    list_parser = subparsers.add_parser("list", help="List conversations in the ctk lib")
    list_parser.add_argument("libdir", help="Path to the ctk library")
    list_parser.add_argument("--indices", nargs="+", default=None, type=int, help="Indices of conversations to list. Default: all")
    list_parser.add_argument("--fields", nargs="+", default=["title", "create_time"], help="Path fields to include in the output")

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

    # Subcommand: viz
    viz_parser = subparsers.add_parser('viz', help='Visualize the conversation library as a complex network')
    viz_parser.add_argument('libdir', type=str, help='Directory of the ctk library to visualize')
    viz_parser.add_argument('output_format', type=str, help='Output format: html, png')
    viz_parser.add_argument('--limit', type=int, default=5000, help='Limit the number of conversations to visualize')

    # Subcommand: graph-stats
    graph_stats_parser = subparsers.add_parser('graph-stats', help='Display shared URL statistics about the ctk library')
    graph_stats_parser.add_argument('libdir', type=str, help='Directory of the ctk library to analyze')
    graph_stats_parser.add_argument('output_format', type=str, help='Output format: json, table')
    graph_stats_parser.add_argument('--limit', type=int, default=10000, help='Limit the number of conversations to analyze')
    graph_stats_parser.add_argument('--top-n', type=int, default=10, help='Number of top nodes to display')

    # Subcommand: purge
    purge_parser = subparsers.add_parser('purge', help='Purge dead links from the conversation library')
    purge_parser.add_argument('libdir', type=str, help='Directory of the ctk library to purge')

    # Subcommand: visit
    visit_parser = subparsers.add_parser('web', help='View a conversation in the OpenAI chat interface')
    visit_parser.add_argument('libdir', type=str, help='Directory of the ctk library to visit')
    visit_parser.add_argument('index', type=int, nargs='+', help='Indices of the conversations to view in the browser')
    
    # Subcommand: about
    about_parser = subparsers.add_parser('about', help='Print information about ctk')

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
        logger.debug(f"Removed {len(args.indices)} conversations")

    elif args.command == "export":
        conversations = load_conversations(args.libdir)
        if args.indices is None:
            indices = range(len(conversations))
        else:
            indices = args.indices
        conversations = [conversations[i] for i in indices if i < len(conversations)]

        if args.format == "zip":
            import zipfile
            with zipfile.ZipFile("conversations.zip", "w") as zf:
                # write all conversations to the zip file in a single json file
                zf.writestr("conversations.json", json.dumps(conversations, indent=2))
                # now we copy the directory of the libdir, which contains the conversations.json, with the exception of copying the conversations.json file
                for root, dirs, files in os.walk(args.libdir):
                    for file in files:
                        if file == "conversations.json":
                            continue
                        # write the file to the zip file in the zip file, replicating the same structure
                        arcname = os.path.relpath(os.path.join(root, file), start=args.libdir)
                        zf.write(os.path.join(root, file), arcname=arcname)

    elif args.command == 'llm':
        lib_dir = args.lib_dir
        if not os.path.isdir(lib_dir):
            logging.error(f"The specified library directory '{lib_dir}' does not exist or is not a directory.")
            sys.exit(1)
        conversations = load_conversations(lib_dir)

        while True:
            try:
                results = query_llm(lib_dir, args.query)
                results = json.loads(results['response'])

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


    elif args.command == "conv-stats":
        conversations = load_conversations(args.libdir)
        if args.index >= len(conversations):
            console.debug(f"[red]Error: Index {index} out of range.[/red]")
        conv = conversations[args.index]

        cur_node_name = conv.get("current_node")
        
        tree_map = conv.get("mapping")
        t = AlgoTree.FlatForest(tree_map)
        cur_node = t.node(cur_node_name)
        ancestors = AlgoTree.utils.ancestors(cur_node)
        cur_conv_ids = [node.name for node in ancestors] + [cur_node_name]

        stats = {}
        metadata = conv
        metadata.pop("mapping", None)

        stats['metadata'] = metadata
        stats["num_paths"] = len(AlgoTree.utils.leaves(t.root))
        stats["num_nodes"] = AlgoTree.utils.size(t.root)
        stats["max_path"] = AlgoTree.utils.height(t.root)

        def walk(node):
            node_dict = {}
            siblings = AlgoTree.utils.siblings(node)
            node_dict["num_siblings"] = len(siblings)
            node_dict["is_leaf"] = AlgoTree.utils.is_leaf(node)
            node_dict["is_root"] = AlgoTree.utils.is_root(node)
            node_dict["is_current"] = node.name in cur_conv_ids
            node_dict["num_children"] = len(node.children)
            node_dict["depth"] = AlgoTree.utils.depth(node)
            node_dict["num_descendants"] = AlgoTree.utils.size(node)
            node_dict["num_ancestors"] = len(AlgoTree.utils.ancestors(node))
            if not args.no_payload:
               node_dict['payload'] = node.payload
            
            # let id be the enumaration of the nodes
            id = len(stats)
            stats[id] = node_dict

            for child in node.children:
                walk(child)

        walk(t.root)
        if args.json:
            console.print(JSON(json.dumps(stats, indent=2)))
        else:
            print_json_as_table(stats, table_title=conv['title'])

    elif args.command == "tree":
        convs = load_conversations(args.libdir)
        if args.index >= len(convs):
            console.debug(f"[red]Error: Index {index} out of range.[/red]")
            sys.exit(1)
        conv = convs[args.index]
        tree_map = conv.get("mapping", {})
        t = AlgoTree.FlatForest(tree_map)

        paths = []
        for field in args.label_fields:
            paths.append(field.split('.'))

        def get_label(node):
            results = []
            for path in paths:
                value = path_value(node.payload, path)
                value = value[:args.truncate]
                results.append(value)

            label = " ".join(results)
            return label\

        console.print(AlgoTree.pretty_tree(t, node_name=get_label))

    elif args.command == "purge":
        print("TODO: Implement purge command. This swill remove any local files that are dead links in the library.")

    elif args.command == "conv":

        if args.node is not None and len(args.indices) >1:
            console.print("[red]Error: If you specify a node, you can only print one conversation at a time.[/red]")
            sys.exit(1)

        convs = load_conversations(args.libdir)
        json_obj = []

        for idx in args.indices:                
            if idx >= len(convs):
                console.debug(f"[red]Error: Index {idx} in indices out of range.[/red]. Skipping.")
                continue

            if args.json:
                json_obj.append(convs[idx])
            else:
                pretty_print_conversation(
                    convs[idx],
                    terminal_node = args.node,
                    msg_limit = args.msg_limit,
                    msg_roles = args.msg_roles,
                    msg_start_index = args.msg_start_index,
                    msg_end_index = args.msg_end_index)

        if args.json:
            console.print(JSON(json.dumps(json_obj, indent=2)))

    elif args.command == "about":
        console.print("[bold cyan]ctk[/bold cyan]: A command-line toolkit for working with conversation trees, "
                    "typically derived from exported LLM interaction data.\n")
        console.print("[dim]Developed by:[/dim] [bold white]Alex Towell[/bold white]  \n"
                    "[dim]Contact:[/dim] [link=mailto:lex@metafunctor.com]lex@metafunctor.com[/link]  \n"
                    "[dim]Source Code:[/dim] [link=https://github.com/queelius/ctk]https://github.com/queelius/ctk[/link]\n")
        console.print("[bold]Features:[/bold]")
        console.print("• Parse and analyze LLM conversation trees.")
        console.print("• Export, transform, and query structured conversation data.")
        console.print("• Visualize conversation trees and relationships.")
        console.print("• Query conversation trees using JMESPath.")
        console.print("• Query conversation trees using an LLM.")
        console.print("• Launch a Streamlit dashboard for interactive exploration.")
        console.print("• Lightweight and designed for command-line efficiency.")
        console.print("\n[bold green]Usage:[/bold green] Run `ctk --help` for available commands.")


    elif args.command == "web":
        convs = load_conversations(args.libdir)
        for idx in args.index:
            if idx < 0 or idx >= len(convs):
                console.debug(f"[red]Error: Index {idx} out of range.[/red]. Skipping.")
                continue
        
            conv = convs[idx]
            link = f"https://chat.openai.com/c/{conv['id']}"
            webbrowser.open_new_tab(link)

    elif args.command == "merge":
        ensure_libdir_structure(args.output)
        if args.operation == "union":
            union_libs(args.libdirs, args.output)
            logger.debug(f"Merged {len(args.libdirs)} libs into {args.output}")
        elif args.operation == "intersection":
            intersect_libs(args.libdirs, args.output)
            logger.debug(f"Merged {len(args.libdirs)} libs into {args.output}")
        elif args.operation == "difference":
            diff_libs(args.libdirs, args.output)
            logger.debug(f"Merged {len(args.libdirs)} libs into {args.output}")
        logger.debug(f"Merged {len(args.libdirs)} libs into {args.output}")

    elif args.command == "dash":
        launch_streamlit_dashboard(args.libdir)

    elif args.command == "viz":
        convs = load_conversations(args.libdir)
        net = generate_url_graph(convs, args.limit)
        if args.output_format == 'png':
            visualize_graph_png(net, 'graph.png')
        elif args.output_format == 'html':
            visualize_graph_pyvis(net, 'graph.html')
        else:
            print("Invalid output format. Please choose 'png' or 'html'.")
            sys.exit(1)

    elif args.command == "graph-stats":
        convs = load_conversations(args.libdir)
        net = generate_url_graph(convs, args.limit)
        stats = graph_stats(net, args.top_n)
        if args.output_format == 'json':
            console.print(JSON(json.dumps(stats, indent=2)))
        elif args.output_format == 'table':
            print_json_as_table(stats)
        else:
            print("Invalid output format. Please choose 'json' or 'table'.")
            sys.exit(1)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()

```

#### Source File: `ctk/config.py`

```python
import configparser
import os

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

```

#### Source File: `ctk/link_tools.py`

```python
from urllib.parse import urlparse
import logging
import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from rich.progress import Progress, SpinnerColumn, BarColumn, TimeElapsedColumn
import logging
import networkx as nx
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def extract_urls_from_markdown(content):
    """
    Extract URLs from Markdown content.
    :param content: The Markdown content to extract URLs from.
    :return: A set of URLs extracted from the content.
    """
    urls = set()
    lines = content.split('\n')
    for line in lines:
        if line.startswith('http://') or line.startswith('https://'):
            urls.add(line.strip())
        elif '](' in line:
            url = line.split('](')[1].split(')')[0]
            if url.startswith(('http://', 'https://')):
                urls.add(url)
    return urls

def extract_urls_from_html(content):
    """
    Extract a URLs from the HTML content.
    :param html_content: The HTML content to extract URLs from.
    :return: A set of URLs extracted from the content.
    """
    try:
        soup = BeautifulSoup(content, 'lxml')
    except Exception as e:
        logging.warning(f"lxml parser failed: {e}. Falling back to 'html.parser'.")
        try:
            soup = BeautifulSoup(content, 'html.parser')
        except Exception as e:
            logging.error(f"html.parser also failed: {e}. Skipping this content.")
            return set()
    
    urls = set()
    for link in soup.find_all('a', href=True):
        url = link['href']
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            urls.add(url)
    return urls

def get_session(retries=3, backoff_factor=0.3, status_forcelist=(500, 502, 504)):
    """
    Configure a requests Session with retry strategy.

    :param retries: Number of retries for transient errors.
    :param backoff_factor: Factor by which to back off between retries.
    :param status_forcelist: HTTP status codes to force a retry on.
    :return: A configured requests Session object.
    """
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
    """
    Fetch HTML content from a URL with optional SSL verification.

    :param url: The URL to fetch.
    :param verify_ssl: Whether to verify SSL certificates.
    :param session: An optional requests Session object.
    :return: The HTML content as a string, or None if an error occurred.
    """
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

def generate_url_graph(convs, limit, ignore_ssl=False):
    """
    Generate a NetworkX graph based on URL mentions in conversation trees.
    """
    G = nx.DiGraph()
    total = min(len(convs), limit)
    logging.debug(f"Generating graph from {total} conversations.")
    
    # Create a set of all URLs for quick lookup
    urls = set(c['safe_urls'] for c in convs[:total])
    
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
        task = progress.add_task("Processing conversations...", total=total)
        
        # Use ThreadPoolExecutor for concurrent fetching
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {
                executor.submit(fetch_html, bookmark['url'], verify_ssl=not ignore_ssl, session=session): bookmark 
                for url in urls[:total]
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
                    mentioned_urls = extract_urls(html_content, bookmark['url'])
                    
                    for mentioned_url in mentioned_urls:
                        # Prevent self-loops by ensuring mentioned_url is different from bookmark['url']
                        if mentioned_url != bookmark['url']:
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
    
    # logging.info(f"Graph generated with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
    # logging.info(f"Successfully processed {success_count} bookmarks.")
    # logging.info(f"Failed to process {failure_count} bookmarks.")
    return G

```

#### Source File: `ctk/llm.py`

```python
import os
import requests
from string import Template
from .config import load_ctkrc_config

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

#### Source File: `ctk/merge.py`

```python
from .utils import load_conversations, save_conversations
from rich.console import Console

console = Console()

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

def intersect_libs(libdirs, output_dir, conflict_resolution="skip"):
    """
    @brief Take the intersection of multiple conversation libraries.
    @param libdirs List of library directories to merge.
    @param conflict_resolution How to handle duplicate conversation ids. Options: "skip", "overwrite-old", "error"
    @param output_dir Output library directory.
    """

    intersection_lib = []
    for d in libdirs:
        lib = load_conversations(d)
        if not lib:
            continue
        for conv in lib:
            if conv["id"] in [c["id"] for c in intersection_lib]:
                union_conv = lib[conv["id"]]
                if conflict_resolution == "skip":
                    console.print(f"Skipping duplicate id {conv['id']}")
                    continue
                elif conflict_resolution == "overwrite-old":
                    # keep the one with the newest update_time or if that doesn't exist, the newest create_time
                    latest_time_lib = max(conv.get("update_time", 0), conv.get("create_time", 0))
                    latest_time_union = max(union_conv.get("update_time", 0), union_conv.get("create_time", 0))
                    if latest_time_lib > latest_time_union:
                        intersection_lib[conv["id"]] = conv
                        console.print(f"Overwriting with newer id {conv['id']}")
                    else:
                        console.print(f"Keeping existing id {conv['id']}")
                elif conflict_resolution == "error":
                    raise ValueError(f"Duplicate id {conv['id']} found in libraries")
            else:
                intersection_lib.append(conv)

    save_conversations(output_dir, intersection_lib)

def diff_libs(libdirs, output_dir):
    """
    @brief Find the difference between the first lib (libdirs[0]) and the union of the remaining libs.
    @param libdirs List of library directories to take the difference of.
    @param output_dir Output library directory.
    """

    diff_lib = load_conversations(libdirs[0])
    for d in libdirs[1:]:
        lib = load_conversations(d)
        for conv in lib:
            if conv["id"] in [c["id"] for c in diff_lib]:
                diff_lib.remove(conv)

    save_conversations(output_dir, diff_lib)
```

#### Source File: `ctk/stats.py`

```python
import networkx as nx
import logging

logger = logging.getLogger(__name__)

def graph_stats(graph, top_n=10):
    """Compute and display detailed statistics of the NetworkX graph."""
    stats = {}
    stats['Number of Nodes'] = graph.number_of_nodes()
    stats['Number of Edges'] = graph.number_of_edges()
    stats['Density'] = nx.density(graph)
    connected = nx.is_connected(graph.to_undirected())
    stats['Connected'] = connected
    if connected:
        stats['Average Shortest Path Length'] = nx.average_shortest_path_length(graph.to_undirected())
        stats['Graph Diameter'] = nx.diameter(graph.to_undirected())
    try:
        stats['Degree'] = {}
        stats['Degree']['Average'] = sum(dict(graph.degree()).values()) / graph.number_of_nodes() if graph.number_of_nodes() > 0 else 0
        stats['Degree']['Max'] = max(dict(graph.degree()).values()) if dict(graph.degree()) else 0
        stats['Degree']['Min'] = min(dict(graph.degree()).values()) if dict(graph.degree()) else 0
        top_degree = sorted(dict(graph.degree()).items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Degree'][f'Top {top_n}'] = [f"{url} ({degree})" for url, degree in top_degree]
    except Exception as e:
        logging.warning(f"Could not compute degree measures: {e}")
    
    try:
        degree_centrality = nx.degree_centrality(graph)
        stats['Degree Centrality'] = {}
        stats['Degree Centrality']['Min'] = min(degree_centrality.values()) if degree_centrality else 0
        stats['Degree Centrality']['Max'] = max(degree_centrality.values()) if degree_centrality else 0
        stats['Degree Centrality']['Average'] = sum(degree_centrality.values()) / len(degree_centrality) if degree_centrality else 0
        top_degree_cent = sorted(degree_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Degree Centrality'][f'Top {top_n}'] = [f"{url} ({centrality:.4f})" for url, centrality in top_degree_cent]
    except Exception as e:
        logging.warning(f"Could not compute centrality measures: {e}")

    try:
        betweenness_centrality = nx.betweenness_centrality(graph)
        stats['Betweenness Centrality'] = {}
        stats['Betweenness Centrality']['Min'] = min(betweenness_centrality.values()) if betweenness_centrality else 0
        stats['Betweenness Centrality']['Max'] = max(betweenness_centrality.values()) if betweenness_centrality else 0
        stats['Betweenness Centrality']['Average'] = sum(betweenness_centrality.values()) / len(betweenness_centrality) if betweenness_centrality else 0
        top_betweenness = sorted(betweenness_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Betweenness Centrality'][f'Top {top_n}'] = [f"{url} ({centrality:.4f})" for url, centrality in top_betweenness]
    except Exception as e:
        logging.warning(f"Could not compute betweenness centrality measures: {e}")

    try:
        closeness_centrality = nx.closeness_centrality(graph)
        stats['Closeness Centrality'] = {}
        stats['Closeness Centrality']['Min'] = min(closeness_centrality.values()) if closeness_centrality else 0
        stats['Closeness Centrality']['Max'] = max(closeness_centrality.values()) if closeness_centrality else 0
        stats['Closeness Centrality']['Average'] = sum(closeness_centrality.values()) / len(closeness_centrality) if closeness_centrality else 0
        top_closeness = sorted(closeness_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Closeness Centrality'][f'Top {top_n}'] = [f"{url} ({centrality:.4f})" for url, centrality in top_closeness]
    except Exception as e:
        logging.warning(f"Could not compute closeness centrality measures: {e}")

    try:
        eigenvector_centrality = nx.eigenvector_centrality(graph)
        stats['Eigenvector Centrality'] = {}
        stats['Eigenvector Centrality']['Min'] = min(eigenvector_centrality.values()) if eigenvector_centrality else 0
        stats['Eigenvector Centrality']['Max'] = max(eigenvector_centrality.values()) if eigenvector_centrality else 0
        stats['Eigenvector Centrality']['Average'] = sum(eigenvector_centrality.values()) / len(eigenvector_centrality) if eigenvector_centrality else 0
        top_eigenvector = sorted(eigenvector_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Eigenvector Centrality'][f'Top {top_n}'] = [f"{url} ({centrality:.4f})" for url, centrality in top_eigenvector]
    except Exception as e:
        logging.warning(f"Could not compute eigenvector centrality measures: {e}")

    try:
        pagerank_centrality = nx.pagerank(graph)
        stats['PageRank Centrality'] = {}
        stats['PageRank Centrality']['Min'] = min(pagerank_centrality.values()) if pagerank_centrality else 0
        stats['PageRank Centrality']['Max'] = max(pagerank_centrality.values()) if pagerank_centrality else 0
        stats['PageRank Centrality']['Average'] = sum(pagerank_centrality.values()) / len(pagerank_centrality) if pagerank_centrality else 0
        top_pagerank = sorted(pagerank_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['PageRank Centrality'][f'Top {top_n}'] = [f"{url} ({centrality:.4f})" for url, centrality in top_pagerank]
    except Exception as e:
        logging.warning(f"Could not compute PageRank centrality measures: {e}")

    try:
        harmonic_centrality = nx.harmonic_centrality(graph)
        stats['Harmonic Centrality'] = {}
        stats['Harmonic Centrality']['Min'] = min(harmonic_centrality.values()) if harmonic_centrality else 0
        stats['Harmonic Centrality']['Max'] = max(harmonic_centrality.values()) if harmonic_centrality else 0
        stats['Harmonic Centrality']['Average'] = sum(harmonic_centrality.values()) / len(harmonic_centrality) if harmonic_centrality else 0
        top_harmonic = sorted(harmonic_centrality.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Harmonic Centrality'][f'Top {top_n}'] = [f"{url} ({centrality:.4f})" for url, centrality in top_harmonic]
    except Exception as e:
        logging.warning(f"Could not compute harmonic centrality measures: {e}")

    try:
        comps = nx.connected_components(graph.to_undirected())
        comps_sizes = [len(c) for c in comps]
        stats['Connected Components'] = {}
        stats['Connected Components']['Average'] = sum(comps_sizes) / len(comps_sizes) if comps_sizes else 0
        stats['Connected Components']['Number'] = nx.number_connected_components(graph.to_undirected())
        stats['Connected Components'][f'Top {top_n} Sizes'] = sorted(comps_sizes, reverse=True)[:top_n]
    except Exception as e:
        logging.warning(f"Could not compute graph components measures: {e}")

    try:
        clustering_coeffs = nx.clustering(graph.to_undirected())
        stats['Clustering Coefficients'] = {}
        stats['Clustering Coefficients']['Min'] = min(clustering_coeffs.values()) if clustering_coeffs else 0
        stats['Clustering Coefficients']['Max'] = max(clustering_coeffs.values()) if clustering_coeffs else 0
        stats['Clustering Coefficients']['Average'] = sum(clustering_coeffs.values()) / len(clustering_coeffs) if clustering_coeffs else 0
        top_clustering = sorted(clustering_coeffs.items(), key=lambda x: x[1], reverse=True)[:top_n]
        stats['Clustering Coefficients'][f'Top {top_n}'] = [f"{url} ({coeff:.4f})" for url, coeff in top_clustering]
    except Exception as e:
        logging.warning(f"Could not compute clustering coefficients measures: {e}")

    return stats

```

#### Source File: `ctk/utils.py`

```python
import json
import os
import jmespath
import re
import AlgoTree
import time
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown
from rich.text import Text

console = Console()

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

def load_conversations(libdir):
    """
    @brief Load all conversations from `<libdir>/conversations.json`.
    @param libdir Path to the conversation library directory.
    @return A Python object (usually a list) of conversations.
    """
    conv_path = os.path.join(libdir, "conversations.json")
    if not os.path.isfile(conv_path):
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

def pretty_print_conversation(conv, terminal_node=None, msg_limit=None, msg_roles=['user', 'assistant'], msg_start_index=0, msg_end_index=-1):
    # Basic metadata
    title = conv.get("title", "Untitled")
    created = conv.get("create_time")
    #updated = conv.get("update_time")
    model = conv.get("default_model_slug")
    safe_urls = conv.get("safe_urls", [])
    conversation_id = conv.get("id")
    openai_link = f"https://chat.openai.com/c/{conversation_id}"
    safe_urls.append(openai_link)


    print(f"args: {msg_limit=}, {msg_roles=}, {msg_start_index=}, {msg_end_index=}")

    if created is not None:
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created))
    #if updated is not None:
    #    updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(updated))

    # Create a table for overall conversation metadata
    table = Table(title=f"[bold green]{title}[/bold green]")
    table.add_column("Created", justify="right")
    #table.add_column("Updated", justify="right")
    table.add_column("Model", justify="right")
    table.add_column("Links", justify="right")

    # Build a clickable list of safe URLs
    pretty_safe_urls = "\n".join(f"[bold blue][link={url}]{url}[/link][/bold blue]" for url in safe_urls)
    table.add_row(
        created or "N/A",
        #updated or "N/A",
        f"[purple]{model}[/purple]" if model else "N/A",
        pretty_safe_urls if safe_urls else "N/A",
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
    msgs = [node.payload.get('message') for node in ancestors] + [n.payload.get('message')]
    if msg_end_index < 0:
        msg_end_index += len(msgs)
    if msg_start_index < 0:
        msg_start_index += len(msgs)
    msgs = [msg for i, msg in enumerate(msgs) if i >= msg_start_index and i < msg_end_index and msg is not None]
    msgs = [msg for msg in msgs if msg.get("author", {}).get("role", "") in msg_roles]
    msgs = [msg for msg in msgs if msg.get("content", {}).get("content_type") == "text"]
    msgs = [msg for msg in msgs if "".join(msg.get("content", {}).get("parts", [])).strip() != ""]
    msgs = msgs[:msg_limit]

    for i, msg in enumerate(msgs):
        try:
            author = msg.get("author", {})
            role = author.get("role")
            name = author.get("name")
            create_time = msg.get("create_time")

            subtitle = ""
            if create_time is not None:
                created_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(create_time))
                subtitle = f"{subtitle} - Created: {created_str}"
            if name is not None:
                subtitle = f"{name}, {subtitle}"

            message_table = Table(
                title=f"{i+1}/{len(msgs)} [bold purple]{role}[/bold purple] :: [dim]{subtitle}[/dim]",
                title_justify="center",
                show_header=False,
                show_lines=True,
                show_edge=True,
                highlight=True
            )
            combined_text = "".join([part for part in msg.get('content', {}).get("parts", [])])
            message_table.add_row(Markdown(combined_text))
            console.print(message_table)
            console.print()

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            continue

def print_json_as_table(data, table_title=None, indent=0):
    """
    Pretty print JSON data as a table using Rich, handling nested objects.

    Args:
        data: JSON data to print (dict, list, or other)
        table_title: Optional title for the table
        indent: Indentation level for nested tables
    """
    if isinstance(data, dict):
        table = Table(show_header=True, header_style="bold magenta", show_lines=True)
        table.add_column("Field", style="dim", no_wrap=True)
        table.add_column("Value")
        
        if table_title:
            console.print(Text(table_title, style="bold underline"), end="\n\n")
        
        for key, value in data.items():
            if isinstance(value, dict):
                # Create an inner table for the nested dictionary
                nested_table = create_nested_table(value, key)
                table.add_row(str(key), nested_table)
            elif isinstance(value, list):
                # Handle lists by creating a bullet list or another suitable representation
                list_text = "\n".join(f"- {item}" if not isinstance(item, dict) else f"- {create_nested_table(item, key='')}" for item in value)
                table.add_row(str(key), list_text)
            else:
                table.add_row(str(key), str(value))
        
        console.print(table)
    elif isinstance(data, list):
        for index, item in enumerate(data, start=1):
            print_json_as_table(item, table_title=f"Item {index}", indent=indent)
    else:
        console.print(data)

def create_nested_table(data, title=""):
    """
    Create a Rich Table for nested dictionary data.

    Args:
        data: Nested dictionary
        title: Optional title for the nested table

    Returns:
        A Renderable object representing the nested table
    """
    if not isinstance(data, dict):
        return str(data)
    
    table = Table(show_header=True, header_style="bold green", show_lines=True)
    table.add_column("Field", style="dim", no_wrap=True)
    table.add_column("Value")
    
    for key, value in data.items():
        if isinstance(value, dict):
            nested_table = create_nested_table(value, key)
            table.add_row(str(key), nested_table)
        elif isinstance(value, list):
            list_text = "\n".join(f"- {item}" if not isinstance(item, dict) else f"- {create_nested_table(item, key='')}" for item in value)
            table.add_row(str(key), list_text)
        else:
            table.add_row(str(key), str(value))
    
    return table


```

#### Source File: `ctk/vis.py`

```python
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


```

##### Source File: `ctk/streamlit/__init__.py`

```python

```

##### Source File: `ctk/streamlit/app.py`

```python
import streamlit as st
import pandas as pd
import os
import logging
from utils import load_metadata, extract_zip
from filters import sanitize_dataframe, create_filters
from display import display_conversation_tab, display_statistics_tab

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def display_dashboard(convs: list):
    """
    Displays the main dashboard with advanced filtering and a compact UI layout using tabs.
    """
    df = pd.DataFrame(convs)
    df = sanitize_dataframe(df)
    filtered_df = create_filters(df)

    # Create Tabs
    tabs = st.tabs(["📚 Conversations", "Advanced Search", "📖 Table", "📝 Instructions"])

    with tabs[0]:
        display_conversation_tab(filtered_df)

    with tabs[1]:
        # Display Advanced Search
        display_advanced_search_tab(convs)

    with tabs[2]:
        # Display Table
        display_table_view_tab(filtered_df)

    with tabs[3]:
        # Display Instructions
        st.header("📝 Instructions")
        st.markdown("""
        **Export** the ctk library: `ctk export <ctk-library> --output-format zip`
        **Upload** the zip file using the uploader below.
        **Interact** with the ctk library using the tabs in the main window.
        """)

    # Display Footer
    # display_footer()

def main():
    st.set_page_config(page_title="ctk Dashboard", layout="wide")
    st.title("📚 ctk Dashoard")
    st.write("""Upload a **zip** file of the ctk library.""")

    # File uploader for ZIP archive
    st.subheader("📁 Upload ZIP Archive")
    zip_file = st.file_uploader(
        label="Upload a ZIP file of your ctk library",
        type=["zip"],
        key="zip_upload"
    )

    MAX_ZIP_SIZE = 8 * 1024 * 1024 * 1024  # 1 GB

    if zip_file:
        print("Uploaded ZIP file:", zip_file.name)
        print("🔄 File size:", zip_file.size)
        if zip_file.size > MAX_ZIP_SIZE:
            st.error(f"❌ Uploaded ZIP file is {zip_file.size / 1024 / 1024 / 1024:.2f} GB, which exceeds the size limit of 1 GB.")
            logger.error("Uploaded ZIP file exceeds the size limit.")
            st.stop()

        with st.spinner("🔄 Extracting and processing ZIP archive..."):
            extracted_files = extract_zip(zip_file)
        if not extracted_files:
            logger.error("No files extracted from the ZIP archive.")
            st.stop()  # Stop if extraction failed

        import json
        with open("conversations.json", "r", encoding="utf-8") as f:
            return json.load(f)

        display_dashboard(convs)
    else:
        st.info("📥 Please upload a ZIP archive to get started.")
        logger.debug("No ZIP archive uploaded yet.")

def display_table_view_tab(filtered_df: pd.DataFrame):
    """
    Displays the Table tab with a searchable table of metadata.
    """
    st.header("📖 Table")
    st.write("Explore the conversation trees of your library using the interactive table below.")
    st.dataframe(filtered_df)

def display_advanced_search_tab(convs: list):
    """
    Using JMESPath to search the conversations. 
    """
    import jmespath

    st.header("Advanced Search")
    st.write("Use JMESPath queries to search the metadata list.")
    query = st.text_input("Enter a JMESPath query", "[].[?created > `2020-01-01`]")
    try:
        result = jmespath.search(query, convs)
        st.write("Search Results:")
        st.write(result)
    except Exception as e:
        st.error(f"An error occurred: {e}")
        logger.error(f"JMESPath search error: {e}")

if __name__ == "__main__":
    main()

```

##### Source File: `ctk/streamlit/display.py`

```python
import streamlit as st
from PIL import Image
import pandas as pd
import altair as alt
import logging
import os

logger = logging.getLogger(__name__)

def display_conversation_tab(filtered_df: pd.DataFrame):
    """
    Displays the Books tab with book entries and download/view links.
    """
    total_size = len(filtered_df)
    st.subheader(f"📚 Conversations (Total: {total_size})")
    if not filtered_df.empty:
        for idx, row in filtered_df.iterrows():
            with st.expander(f"**{row.get('title', 'No Title')}**"):
                # show title in a header style
                title = row.get("title", "No Title")
                st.markdown(f"# 📖 {title}")

                metadata_details = {
                    "🔑 **Unique ID**": row.get("id", "NA"),
                }

                for key, value in metadata_details.items():
                    st.markdown(f"{key}: {value}")

                else:
                    st.info("📄 No conversation trees.")
                    logger.debug("No conversation trees.")
    else:
        st.info("📚 No conversation trees match the current filter criteria.")
        logger.debug("No conversation trees match the current filter criteria.")

```

##### Source File: `ctk/streamlit/filters.py`

```python
import pandas as pd
import streamlit as st
import logging

logger = logging.getLogger(__name__)

def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitizes the DataFrame by ensuring correct data types and handling missing values.
    """
    # Sanitize string fields: 'title', 'description'
    string_fields = ['title']
    for field in string_fields:
        df[field] = df[field].apply(lambda x: x if isinstance(x, str) else '').fillna('').astype(str)
    
    df['created'] = pd.to_numeric(df['date'], errors='coerce')
    return df

def create_filters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Creates and applies advanced filters to the DataFrame based on user inputs.
    Returns the filtered DataFrame.
    """
    # Sidebar for Filters
    st.sidebar.header("🔍 Filters")
    
    # Title Search
    title_search = st.sidebar.text_input("🔎 Search by Title")
    
    # Created Date Filter (Range Slider)
    selected_years = None
    if 'created' in df.columns and pd.api.types.is_numeric_dtype(df['created']):
        min_year = int(df['created'].min()) if pd.notna(df['created'].min()) else 0
        max_year = int(df['created'].max()) if pd.notna(df['created'].max()) else 0
        if min_year and max_year:
            selected_years = st.sidebar.slider("📅 Created Year Range", min_year, max_year, (min_year, max_year))
        else:
            st.sidebar.info("📅 No valid creation year data available.")
    else:
        st.sidebar.info("📅 Created data is not available.")
    
    # Apply Filters
    filtered_df = df.copy()
    
    if title_search:
        filtered_df = filtered_df[filtered_df['title'].str.contains(title_search, case=False, na=False)]
    
    if selected_years:
        filtered_df = filtered_df[(filtered_df['created'] >= selected_years[0]) & (filtered_df['created'] <= selected_years[1])]
    
    return filtered_df

```

##### Source File: `ctk/streamlit/utils.py`

```python
import json
import os
import zipfile
from io import BytesIO
import streamlit as st
import streamlit as st
from typing import List, Dict

def extract_zip(zip_bytes: BytesIO) -> dict:
    """
    Extracts a ZIP file in-memory and returns a dictionary of its contents.
    Keys are file names, and values are BytesIO objects containing the file data.
    """
    extracted_files = {}
    try:
        with zipfile.ZipFile(zip_bytes) as z:
            for file_info in z.infolist():
                if not file_info.is_dir():
                    with z.open(file_info) as f:
                        normalized_path = os.path.normpath(file_info.filename)
                        # Prevent path traversal
                        if os.path.commonprefix([normalized_path, os.path.basename(normalized_path)]) != "":
                            extracted_files[normalized_path] = BytesIO(f.read())
        return extracted_files
    except zipfile.BadZipFile:
        st.error("The uploaded file is not a valid ZIP archive.")
        return {}
    except Exception as e:
        st.error(f"Error extracting ZIP file: {e}")
        return {}


```

