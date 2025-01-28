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
        # path_values = [jmespath.search(p, conv) for p in path_fields]
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
    # updated = conv.get("update_time")
    model = conv.get("default_model_slug")
    safe_urls = conv.get("safe_urls", [])
    conversation_id = conv.get("id")
    openai_link = f"https://chat.openai.com/c/{conversation_id}"
    safe_urls.append(openai_link)

    print(
        f"args: {msg_limit=}, {msg_roles=}, {msg_start_index=}, {msg_end_index=}")

    if created is not None:
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created))
    # if updated is not None:
    #    updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(updated))

    # Create a table for overall conversation metadata
    table = Table(title=f"[bold green]{title}[/bold green]")
    table.add_column("Created", justify="right")
    # table.add_column("Updated", justify="right")
    table.add_column("Model", justify="right")
    table.add_column("Links", justify="right")

    # Build a clickable list of safe URLs
    pretty_safe_urls = "\n".join(
        f"[bold blue][link={url}]{url}[/link][/bold blue]" for url in safe_urls)
    table.add_row(
        created or "N/A",
        # updated or "N/A",
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
    msgs = [node.payload.get('message')
            for node in ancestors] + [n.payload.get('message')]
    if msg_end_index < 0:
        msg_end_index += len(msgs)
    if msg_start_index < 0:
        msg_start_index += len(msgs)
    msgs = [msg for i, msg in enumerate(
        msgs) if i >= msg_start_index and i < msg_end_index and msg is not None]
    msgs = [msg for msg in msgs if msg.get(
        "author", {}).get("role", "") in msg_roles]
    msgs = [msg for msg in msgs if msg.get(
        "content", {}).get("content_type") == "text"]
    msgs = [msg for msg in msgs if "".join(
        msg.get("content", {}).get("parts", [])).strip() != ""]
    msgs = msgs[:msg_limit]

    for i, msg in enumerate(msgs):
        try:
            author = msg.get("author", {})
            role = author.get("role")
            name = author.get("name")
            create_time = msg.get("create_time")

            subtitle = ""
            if create_time is not None:
                created_str = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(create_time))
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
            combined_text = "".join(
                [part for part in msg.get('content', {}).get("parts", [])])
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
        table = Table(show_header=True,
                      header_style="bold magenta", show_lines=True)
        table.add_column("Field", style="dim", no_wrap=True)
        table.add_column("Value")

        if table_title:
            console.print(
                Text(table_title, style="bold underline"), end="\n\n")

        for key, value in data.items():
            if isinstance(value, dict):
                # Create an inner table for the nested dictionary
                nested_table = create_nested_table(value, key)
                table.add_row(str(key), nested_table)
            elif isinstance(value, list):
                # Handle lists by creating a bullet list or another suitable representation
                list_text = "\n".join(f"- {item}" if not isinstance(
                    item, dict) else f"- {create_nested_table(item, key='')}" for item in value)
                table.add_row(str(key), list_text)
            else:
                table.add_row(str(key), str(value))

        console.print(table)
    elif isinstance(data, list):
        for index, item in enumerate(data, start=1):
            print_json_as_table(
                item, table_title=f"Item {index}", indent=indent)
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
            list_text = "\n".join(f"- {item}" if not isinstance(item, dict)
                                  else f"- {create_nested_table(item, key='')}" for item in value)
            table.add_row(str(key), list_text)
        else:
            table.add_row(str(key), str(value))

    return table


def generate_unique_filename(preferred_name):
    """
    Generate a unique filename by appending an integer suffix if the file already exists
    such that `preferred_name_n` is used if `preferred_name`, `preferred_name_2`, ...,
    `preferred_name_{n-1}` already exist.
    """
    base, ext = os.path.splitext(preferred_name)
    n = 1
    while os.path.exists(preferred_name):
        preferred_name = f"{base}_{n}{ext}"
        n += 1
    return preferred_name