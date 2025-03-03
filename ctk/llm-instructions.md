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

## Structure of `$libdir/conversations.json`

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

```