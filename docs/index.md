# Conversation Toolkit (CTK)

A plugin-based system for managing AI conversations from multiple providers. Import, store, search, branch, and export your conversations in a unified tree format while preserving provider-specific details.

## Quick Start

```bash
# Setup (one-time)
make install

# Import conversations from any supported provider
ctk import chatgpt_export.json --db my_chats
ctk import claude_export.json   --db my_chats --format anthropic

# Open the TUI on the database (primary interface)
ctk --db my_chats

# Bulk-export for fine-tuning, archiving, or sharing
ctk export training.jsonl --db my_chats --format jsonl
```

`ctk` with no subcommand opens the full-screen Textual TUI on the database in `~/.ctk/config.json`'s `database.default_path` (or the path passed via `--db`). Everything an interactive user does (chat, search, branch trees, organize, edit) lives in the TUI. The CLI subcommands are kept small and scriptable: import, export, query, sql, and a handful of admin operations.

## Key Features

- **Universal Tree Format**: every conversation is a tree. Linear chats are single-path trees, branching conversations (e.g., ChatGPT regenerations) preserve all paths.
- **Tree Primitive Algebra**: six primitives (delete, delete_subtree, prune_to, copy, copy_subtree, graft) compose into every higher-level operation: fork, branch, clone, snapshot, detach, promote.
- **Plugin Architecture**: importers and exporters auto-discover via Python imports. Adding a new format is one file.
- **Multiple LLM Backends**: named provider profiles for OpenAI, Azure, OpenRouter, vLLM, llama.cpp, LM Studio, Ollama, or any other OpenAI-compatible endpoint. Switch live via `/provider` in the TUI.
- **Inline Images**: terminal image rendering via `textual-image` (Sixel, Kitty TGP, or Halfcell), automatic protocol detection.
- **Tool Calling / MCP**: tools group under named virtual MCP providers (`ctk.builtin`, `ctk.network`). The LLM can search, list, find similar conversations, etc., directly during chat.
- **MCP Server**: ctk also runs as a real MCP server (`python -m ctk.mcp_server`) so external clients can use the same surface.
- **SQLite + FTS5**: local, fast, searchable. The "database" is a directory containing `conversations.db` and an associated `media/` folder for image attachments.

## Installation

```bash
git clone https://github.com/queelius/ctk.git
cd ctk
make install
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Pip install (when published):

```bash
pip install conversation-tk
```

## CLI Surface

The full top-level command list is intentionally small:

| Command | Purpose |
|---|---|
| `ctk` (no args) | Open the TUI on the configured DB |
| `ctk tui` | Same, alias for muscle memory |
| `ctk import` | Bulk import conversation exports |
| `ctk export` | Bulk export to file |
| `ctk query` | Filter / search with formatted output (table, json, csv) |
| `ctk sql` | Read-only SQL on the DB |
| `ctk db` | Maintenance: init, info, vacuum, backup, merge, diff, intersect, filter, split, dedupe, validate |
| `ctk net` | Build embeddings + similarity graph (analytical queries are MCP tools, used from the TUI) |
| `ctk auto-tag` | Bulk LLM-driven tagging |
| `ctk llm` | Provider config: providers, models, test |
| `ctk config` | Edit `~/.ctk/config.json` |

Per-conversation, per-library, chat-REPL, and ad-hoc network analysis subcommands all moved into the TUI as bindings, slash commands, or MCP tool calls.

## Importing Conversations

### ChatGPT / OpenAI

Export from [chatgpt.com/settings](https://chatgpt.com/settings) > Data Controls > Export.

```bash
ctk import conversations.json --db chats
ctk import chatgpt_export.json --db chats --format openai --tags "work,2024"
```

### Claude / Anthropic

Export from Claude's settings.

```bash
ctk import claude_export.json --db chats --format anthropic
```

### GitHub Copilot

```bash
ctk import ~/.vscode/workspaceStorage --db chats --format copilot
```

### Google Gemini

```bash
ctk import gemini_export.json --db chats --format gemini
```

### Generic JSONL (for fine-tuning datasets, local LLMs, etc.)

```bash
ctk import training_data.jsonl --db chats --format jsonl
for file in *.jsonl; do
  ctk import "$file" --db chats --format jsonl
done
```

### Filesystem-Based Coding Agents

```bash
# Auto-detect coding agent data (Copilot, Claude Code, Cursor, etc.)
ctk import ~/.local/share/agent-storage --db chats --format filesystem_coding
```

## Querying from the Shell

```bash
# List conversations as a Rich table
ctk query --db chats

# Filter and order
ctk query --db chats --starred --limit 10
ctk query --db chats --filter-source ChatGPT --filter-model gpt-4o

# JSON or CSV for piping
ctk query --db chats --format json | jq '.[].title'
ctk query --db chats --format csv > inventory.csv

# Read-only SQL when the query language isn't enough
ctk sql "SELECT source, COUNT(*) FROM conversations GROUP BY source" --db chats
```

## The TUI

```bash
ctk --db chats   # or just `ctk` if database.default_path is set
```

The TUI has a tabbed sidebar (All / Starred / Pinned / Recent / Archived) plus a main pane with focusable message bubbles and a multi-line chat input.

### Bindings

| Key | Action |
|---|---|
| `q` | Quit |
| `/` | Search overlay |
| `Esc` | Cancel search / dismiss modal |
| `Ctrl+R` | Refresh |
| `Ctrl+N` | New conversation |
| `Ctrl+H` | Help modal (bindings, slash commands, MCP providers) |
| `Ctrl+S` | Toggle star |
| `Ctrl+G` | System prompt modal |
| `Ctrl+O` | Attach file modal |
| `Ctrl+L` | Load more conversations into the sidebar |
| `Tab` / `Shift+Tab` | Move focus between message bubbles |
| `Ctrl+F` | Fork at focused message (truncate descendants and siblings) |
| `Ctrl+B` | Branch at focused message (preserve full tree, new id) |
| `Ctrl+D` | Delete subtree at focus (with confirm) |
| `Ctrl+E` | Extract subtree at focus into a new conversation |
| `Ctrl+P` | Promote focused path (drop sibling branches, with confirm) |
| `[` / `]` | Switch to previous / next sibling at focused message |

`Ctrl+H` opens a modal listing the live registry of bindings, slash commands, and MCP providers, so the canonical reference is always current.

### Slash Commands

Type any of these in the chat input. They route through the dispatcher before reaching the LLM.

| Command | Effect |
|---|---|
| `/help` | List all slash commands |
| `/mcp` | List MCP tool providers and their tools |
| `/model [name]` | Show or switch the chat model (also displays profile + base_url) |
| `/provider [name]` | List provider profiles or switch to one (rebuilds the active provider) |
| `/system [text]` | Show or set the system prompt |
| `/title <text>` | Rename the current conversation |
| `/star`, `/pin`, `/archive` | Toggle the corresponding flag |
| `/tag <name>...`, `/untag <name>` | Add or remove tags |
| `/clone` | Duplicate the current conversation as a sibling |
| `/snapshot` | Save a dated snapshot |
| `/delete` | Delete the current conversation entirely (with confirm) |
| `/delete-subtree` | Delete the focused subtree (with confirm) |
| `/extract` | Copy focused subtree as a new conversation |
| `/detach` | Move focused subtree out as a new conversation |
| `/promote` | Make the focused message's path the only path |
| `/graft <conv-id-or-prefix>` | Attach another conversation under the focused message |
| `/fork`, `/branch` | Same as Ctrl+F / Ctrl+B but at the path tail |
| `/attach <path>` | Attach a file as a system message |
| `/export <path> [format]` | Export the current conversation |
| `/sql <query>` | Read-only SQL query |
| `/clear` | Reset to a new empty conversation |
| `/quit` | Exit the TUI |

## Tree Operations: The Algebra

Every fork / branch / clone / snapshot / detach / promote operation in the TUI decomposes into one of six primitives. Five live on the in-memory `ConversationTree`, the sixth is DB-level.

| # | Primitive | Effect |
|---|---|---|
| 1 | `db.delete_conversation(id)` | Remove the conversation from the database |
| 2 | `tree.delete_subtree(n)` | Drop node `n` and all descendants |
| 3 | `tree.prune_to(n)` | Keep only the ancestor chain of `n` |
| 4 | `tree.copy()` | Full duplicate, new conversation id |
| 5 | `tree.copy_subtree(n)` | New conversation rooted at `n`'s subtree |
| 6 | `tree.graft(n, other)` | Attach a copy of `other` under `n`, fresh ids |

Derived operations are compositions: fork = `copy().prune_to(n)`, detach = `copy_subtree(n)` then `delete_subtree(n)`, promote = `prune_to(leaf_of_path)`, snapshot = `copy()` plus a dated title.

This algebra is the design contract: when you need a new tree-shape operation, write it as a composition rather than reaching into `message_map` directly. Tests in `tests/unit/test_tree_primitives.py` prove the primitives behave correctly under every shape (single message, deep chains, branching, missing nodes, root, leaf).

## LLM Backends and Provider Profiles

CTK ships one provider implementation, `OpenAIProvider`, wrapping the official `openai` SDK. It speaks the OpenAI chat-completions protocol, so any compatible endpoint works:

- The real OpenAI API
- Azure, OpenRouter
- Local: vLLM, llama.cpp server, LM Studio, Ollama (`http://localhost:11434/v1`)
- Custom remote inference rigs

### Named Profiles

Define multiple endpoints in `~/.ctk/config.json` and switch between them at startup or live in the TUI.

```json
{
  "providers": {
    "default": "muse",
    "openai":  {"base_url": "https://api.openai.com/v1", "default_model": "gpt-5"},
    "muse":    {"base_url": "http://muse.lan:8000/v1",   "default_model": "qwen3-omni"},
    "ollama":  {"base_url": "http://localhost:11434/v1", "default_model": "llama3.1:70b"}
  }
}
```

In the TUI:

```
/provider              # list profiles, marks the active one with *
/provider muse         # switch live; rebuilds the provider, refreshes status
/model                 # shows current model + profile + base_url
/model gpt-4o          # switch model on the active profile
```

CLI:

```bash
ctk --provider ollama --db chats         # open the TUI on a specific profile
ctk --provider muse --base-url http://x/v1   # ad-hoc override
ctk llm test --provider openai           # check connectivity
```

API keys read from `<PROFILE>_API_KEY` env var first (so `MUSE_API_KEY` works), falling back to `OPENAI_API_KEY`, then to the config file (with a warning).

## Exporting

### For Fine-Tuning (JSONL)

```bash
ctk export training.jsonl --db chats --format jsonl
ctk export selected.jsonl --db chats --format jsonl --ids conv1 conv2
ctk export filtered.jsonl --db chats --format jsonl --filter-source ChatGPT
ctk export sanitized.jsonl --db chats --format jsonl --sanitize
```

The `--sanitize` flag scrubs API keys, passwords, tokens, SSH keys, database URLs, and credit-card-like numbers before writing.

### Markdown

```bash
ctk export all.md       --db chats --format markdown   # single file
ctk export docs/        --db chats --format markdown   # one file per conversation
```

### Interactive HTML

```bash
ctk export archive.html --db chats --format html
ctk export archive.html --db chats --format html --media-dir media
```

The HTML export is a self-contained interactive app: branch navigation, search, image gallery, and tree-aware chat continuation against a local LLM endpoint (Ollama, LM Studio, etc.). Reply to any assistant message or continue at the end; new branches save to localStorage. Requires serving via HTTP for chat to work (`python -m http.server`).

### Hugo (Static Site)

```bash
ctk export content/conversations/ --db chats --format hugo
ctk export content/conversations/ --db chats --format hugo --starred
ctk export content/conversations/ --db chats --format hugo --hugo-organize tags
```

Each conversation becomes a Hugo page bundle with frontmatter and copied media files. `--hugo-organize` accepts `none`, `tags`, `source`, or `date`.

### Path Selection

For a tree with multiple paths (regenerations, branches), pick which one to export:

```bash
ctk export out.jsonl --db chats --path-selection longest   # default
ctk export out.jsonl --db chats --path-selection first
ctk export out.jsonl --db chats --path-selection last
```

## Tree Structure

CTK stores all conversations as trees. The flexibility this enables (forking to explore alternatives, regenerations as siblings, grafting context from other conversations) is the core of the model.

Linear conversation:

```
User: "What is Python?"
  Assistant: "Python is a programming language..."
    User: "How do I install it?"
      Assistant: "You can install Python by..."
```

Branching conversation (a regenerated assistant turn plus follow-ups on each):

```
User: "Write a poem"
  Assistant (v1): "Roses are red..."
  Assistant (v2): "In fields of gold..."
    User: "Make it longer"
      Assistant: "In fields of gold, where sunshine..."
```

In the TUI, branches are visible at every node with multiple children. `[` and `]` switch siblings.

## Database Operations

```bash
# Combine databases
ctk db merge source1 source2 --output merged

# Compare two databases
ctk db diff a b

# Filter into a new database
ctk db filter all_chats --output work_only --tags "work"
ctk db filter all_chats --output starred --starred

# Maintenance
ctk db init <dir>
ctk db info <dir>
ctk db vacuum <dir>
ctk db backup <dir> --output backup-2026-04.db
ctk db dedupe <dir>
ctk db validate <dir>
```

## Python API

```python
from ctk import ConversationDB, registry, Message, MessageContent, MessageRole

with ConversationDB("chats") as db:
    # Search
    results = db.search_conversations("python async", limit=20)

    # Load a tree
    conv = db.load_conversation("conv_id_123")

    # Tree primitives
    paths = conv.get_all_paths()
    longest = conv.get_longest_path()

    cloned = conv.copy()
    extracted = conv.copy_subtree(node_id="msg-abc")
    conv.delete_subtree("msg-xyz")
    conv.prune_to("msg-abc")

    # Add a new message
    msg = Message(
        role=MessageRole.USER,
        content=MessageContent(text="Follow-up question"),
        parent_id="previous-msg-id",
    )
    conv.add_message(msg)
    db.save_conversation(conv)
```

A fluent API is also available for query chains:

```python
from ctk import CTK

results = (
    CTK("chats")
    .search("python")
    .filter(source="ChatGPT")
    .limit(10)
    .get()
)
```

## Plugin System

Importers and exporters are auto-discovered via Python imports. To add a new format, drop a file in the right directory:

```python
# ctk/importers/my_format.py
from ctk.core.plugin import ImporterPlugin
from ctk.core.models import ConversationTree, Message, MessageContent, MessageRole

class MyFormatImporter(ImporterPlugin):
    name = "my_format"
    description = "Import from My Custom Format"
    version = "1.0.0"

    def validate(self, data):
        return "my_format_marker" in str(data)

    def import_data(self, data, **kwargs):
        tree = ConversationTree(title="Imported Conversation")
        tree.add_message(Message(
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
        ))
        return [tree]
```

The plugin is picked up the next time `ctk` runs.

### Built-in Importers

`openai`, `anthropic`, `gemini`, `copilot`, `jsonl`, `filesystem_coding`.

### Built-in Exporters

`json`, `jsonl`, `markdown`, `html`, `hugo`, `csv`, `echo`.

## Database Schema

The "database" is a directory:

```
my_chats/
  conversations.db       # SQLite file
  media/                 # image attachments referenced by relative URL
    <uuid>.webp
    ...
```

Tables (via SQLAlchemy ORM in `ctk/core/db_models.py`):

- `conversations`: metadata, title, timestamps, source, model, slug, starred / pinned / archived flags
- `messages`: content, role, parent / child relationships, namespaced ids (`<conv-id>::<msg-id>`)
- `tags`: searchable tags per conversation
- `paths`: cached path traversals for fast retrieval
- `embeddings`, `similarities`: TF-IDF vectors and pairwise similarity for `ctk net` analysis

FTS5 full-text search across message content (with a LIKE fallback when FTS5 is unavailable).

## Privacy

- 100% local for storage and search. Nothing leaves your machine unless you point a provider profile at a remote endpoint.
- No telemetry, no analytics.
- Optional sanitization removes API keys, passwords, tokens, SSH keys, database URLs, and similar patterns before sharing or exporting (`--sanitize`).

## Development

```bash
make install            # editable install + dev deps
make test               # run all tests
make test-unit          # unit tests only
make test-integration   # integration tests only
make coverage           # coverage report (htmlcov/, term-missing)
make format             # black + isort
make lint               # flake8 + mypy
make clean              # remove build artifacts and caches
```

Test count: ~1700 unit tests as of 2.14.x. The Textual TUI has a Pilot-driven harness in `tests/unit/test_textual_tui.py` covering modal lifecycles, slash commands, and tree-op actions.

## Citation

```bibtex
@software{towell_ctk_2026,
  author    = {Towell, Alex},
  title     = {{CTK}: Conversation Toolkit},
  year      = 2026,
  publisher = {GitHub},
  url       = {https://github.com/queelius/ctk},
  version   = {2.14.0}
}
```

Or use [CITATION.cff](CITATION.cff) for automatic citation in GitHub.

## License

MIT. See [LICENSE](LICENSE).

## Contributing

Contributions welcome. To add a new provider import format:

1. Create `ctk/importers/<name>.py` with an `ImporterPlugin` subclass.
2. Implement `validate()` and `import_data()`.
3. Add tests in `tests/unit/test_<name>_importer.py`.
4. Submit a PR.

The same pattern applies to exporters in `ctk/exporters/`. New TUI bindings, slash commands, and tool providers also welcome (see `ctk/tui/slash.py` and `ctk/core/tools_registry.py`).
