"""
Terminal UI for CTK chat.
"""

import json
import sys
import threading
import uuid
from datetime import datetime
from typing import List, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import DynamicCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown

from ctk.core.command_dispatcher import CommandDispatcher, CommandResult
from ctk.core.commands.unix import create_unix_commands
from ctk.core.database import ConversationDB
from ctk.core.models import ConversationMetadata, ConversationTree
from ctk.core.models import Message as DBMessage
from ctk.core.models import MessageContent
from ctk.core.models import MessageRole as DBMessageRole
from ctk.core.shell_completer import create_shell_completer
from ctk.core.shell_parser import ShellParser
from ctk.core.tree import ConversationTreeNavigator, TreeMessage
from ctk.integrations.llm.base import LLMProvider
from ctk.integrations.llm.base import Message as LLMMessage
from ctk.integrations.llm.base import MessageRole as LLMMessageRole
from ctk.integrations.llm.mcp_client import MCPClient, MCPServer


# Add to_llm_message method to TreeMessage for TUI use
def _tree_message_to_llm(self) -> LLMMessage:
    """Convert to LLM message format"""
    return LLMMessage(role=self.role, content=self.content)


TreeMessage.to_llm_message = _tree_message_to_llm


class ChatTUI:
    """
    Terminal UI for chatting with LLMs.

    Features:
    - Stream responses in real-time
    - Command system (/help, /exit, /clear, etc.)
    - Conversation history
    - Database integration
    """

    def __init__(
        self,
        provider: LLMProvider,
        db: Optional[ConversationDB] = None,
        render_markdown: bool = True,
        disable_tools: bool = False,
    ):
        """
        Initialize chat TUI.

        Args:
            provider: LLM provider to use
            db: Optional database for loading/saving conversations
            render_markdown: Whether to render markdown in messages (default: True)
            disable_tools: Disable tool calling (for models that don't support it)
        """
        self.provider = provider
        self.db = db
        self.tools_disabled = disable_tools  # Can be set to True on auto-detect failure

        # Tree structure for conversation
        self.root: Optional[TreeMessage] = None  # Root of conversation tree
        self.current_message: Optional[TreeMessage] = None  # Current position in tree
        self.message_map: dict[str, TreeMessage] = {}  # ID -> TreeMessage lookup

        self.current_conversation_id: Optional[str] = None
        self.conversation_title: Optional[str] = None
        self.conversation_project: Optional[str] = None  # Project name for organization
        self.current_user: Optional[str] = None  # Current user name (for tracking)
        self.conversation_model: str = (
            provider.model
        )  # Default model for this conversation
        self.render_markdown = render_markdown
        self.console = Console()  # Always use console for better formatting

        # LLM parameters
        self.temperature: float = 0.7
        self.max_tokens: Optional[int] = None
        self.num_ctx: Optional[int] = None  # Context window size

        # Display options
        self.streaming: bool = True  # Enable streaming by default

        # MCP integration
        self.mcp_client = MCPClient()

        # File system state
        import os

        self.cwd = os.getcwd()
        self.mcp_auto_tools: bool = False  # Auto-use tools when LLM requests them

        # Virtual filesystem state
        self.vfs_cwd: str = "/"  # Current VFS directory
        self.vfs_navigator = None  # Lazy init when db is available

        # Known commands (for slash-optional command routing)
        self.known_commands = {
            "help",
            "exit",
            "quit",
            "clear",
            "new-chat",
            "save",
            "load",
            "delete",
            "search",
            "list",
            "browse",
            "archive",
            "star",
            "pin",
            "title",
            "tag",
            "export",
            "show",
            "tree",
            "paths",
            "fork",
            "fork-id",
            "context",
            "mcp",
            "cd",
            "pwd",
            "ls",
            "ln",
            "cp",
            "mv",
            "rm",
            "mkdir",
            "net",
            "goto-longest",
            "goto-latest",
            "where",
            "alternatives",
            "history",
            "models",
            "model",
            "temp",
            "regenerate",
            "edit",
            "say",
            "find",
            "unstar",
            "unpin",
            "unarchive",
            "chat",
            "set",
            "get",
        }

        # Shell completer (created lazily to allow tui reference)
        self._shell_completer = None

        # Prompt toolkit setup with dynamic completer
        self.session = PromptSession(
            history=InMemoryHistory(),
            auto_suggest=AutoSuggestFromHistory(),
            completer=DynamicCompleter(self._get_completer),
        )

        # Style for prompt
        self.style = Style.from_dict(
            {
                "prompt": "#00aa00 bold",
                "user": "#00aaaa",
                "assistant": "#aa00aa",
                "system": "#888888",
                "error": "#aa0000 bold",
            }
        )

        # Shell settings (configurable via 'set' command)
        self.uuid_prefix_len = 8  # Default UUID prefix length for ls output

        # Shell mode support
        self.mode = "shell"  # 'shell' or 'chat'
        self.shell_parser = ShellParser()
        self.command_dispatcher = CommandDispatcher()
        self._register_shell_commands()

    def _register_shell_commands(self):
        """Register shell command handlers"""
        # Initialize VFS navigator if we have a database
        if self.db and not self.vfs_navigator:
            from ctk.core.vfs_navigator import VFSNavigator

            self.vfs_navigator = VFSNavigator(self.db)

        # Register commands if we have navigator
        if self.vfs_navigator:
            # Register Unix commands
            unix_commands = create_unix_commands(
                self.db, self.vfs_navigator, tui_instance=self
            )
            self.command_dispatcher.register_commands(unix_commands)

            # Register navigation commands
            from ctk.core.commands.navigation import create_navigation_commands

            nav_commands = create_navigation_commands(
                self.vfs_navigator, tui_instance=self
            )
            self.command_dispatcher.register_commands(nav_commands)

            # Register visualization commands
            from ctk.core.commands.visualization import \
                create_visualization_commands

            viz_commands = create_visualization_commands(
                self.db, self.vfs_navigator, tui_instance=self
            )
            self.command_dispatcher.register_commands(viz_commands)

            # Register organization commands
            from ctk.core.commands.organization import \
                create_organization_commands

            org_commands = create_organization_commands(
                self.db, self.vfs_navigator, tui_instance=self
            )
            self.command_dispatcher.register_commands(org_commands)

            # Register search commands
            from ctk.core.commands.search import create_search_commands

            search_commands = create_search_commands(
                self.db, self.vfs_navigator, tui_instance=self
            )
            self.command_dispatcher.register_commands(search_commands)

            # Register semantic search commands
            from ctk.core.commands.semantic import create_semantic_commands

            semantic_commands = create_semantic_commands(
                self.db, self.vfs_navigator, tui_instance=self
            )
            self.command_dispatcher.register_commands(semantic_commands)

        # Register chat commands (always available, even without db)
        from ctk.core.commands.chat import create_chat_commands

        chat_commands = create_chat_commands(tui_instance=self)
        self.command_dispatcher.register_commands(chat_commands)

        # Register settings commands (always available)
        from ctk.core.commands.settings import create_settings_commands

        settings_commands = create_settings_commands(tui_instance=self)
        self.command_dispatcher.register_commands(settings_commands)

        # Register database commands (save, load, search, list)
        from ctk.core.commands.database import create_database_commands

        db_commands = create_database_commands(db=self.db, tui_instance=self)
        self.command_dispatcher.register_commands(db_commands)

        # Register LLM control commands (temp, model, models, etc.)
        from ctk.core.commands.llm import create_llm_commands

        llm_commands = create_llm_commands(tui_instance=self)
        self.command_dispatcher.register_commands(llm_commands)

        # Register session commands (clear, new-chat, system, etc.)
        from ctk.core.commands.session import create_session_commands

        session_commands = create_session_commands(db=self.db, tui_instance=self)
        self.command_dispatcher.register_commands(session_commands)

        # Register tree navigation commands (fork, branch, merge, etc.)
        from ctk.core.commands.tree_nav import create_tree_nav_commands

        tree_nav_commands = create_tree_nav_commands(db=self.db, tui_instance=self)
        self.command_dispatcher.register_commands(tree_nav_commands)

        # Update environment variables
        self._update_environment()

        # Start background preloading of conversation index
        self._preload_conversation_index()

    def _update_environment(self):
        """Update shell environment variables"""
        env = {
            "CWD": self.vfs_cwd,
            "PWD": self.vfs_cwd,
            "MODEL": self.provider.model if self.provider else "",
            "PROVIDER": self.provider.name if self.provider else "",
        }

        # Add conversation-specific variables if in a conversation
        if self.current_conversation_id:
            env["CONV_ID"] = self.current_conversation_id

        if self.current_message:
            path = self.get_current_path()
            env["MSG_COUNT"] = str(len(path))

        self.shell_parser.set_environment(env)

    def _get_completer(self):
        """Get or create the shell completer (for DynamicCompleter)."""
        if self._shell_completer is None:
            self._shell_completer = create_shell_completer(tui_instance=self)
        return self._shell_completer

    def _preload_conversation_index(self):
        """
        Start background preloading of the ConversationIndex.

        This runs in a background thread so the TUI can start immediately
        while the index loads. The index takes ~0.5-2 seconds to load for
        100k conversations, but is then available for O(1) lookups.
        """
        if not self.vfs_navigator:
            return

        def _preload():
            try:
                # Access the index property to trigger lazy loading
                index = self.vfs_navigator.index
                index.ensure_loaded()
            except Exception:
                # Silently fail - index will load on first use if preload fails
                pass

        thread = threading.Thread(target=_preload, daemon=True)
        thread.start()

    def get_current_path(self) -> List[TreeMessage]:
        """Get path from root to current message"""
        if not self.current_message:
            return []
        return self.current_message.get_path_to_root()

    def get_messages_for_llm(self) -> List[LLMMessage]:
        """Get messages in current path as LLM message format"""
        return [msg.to_llm_message() for msg in self.get_current_path()]

    def tree_to_conversation_tree(self) -> ConversationTree:
        """Convert internal tree to database ConversationTree format"""
        if not self.root:
            raise ValueError("No messages to convert")

        tree = ConversationTree(
            id=self.current_conversation_id or str(uuid.uuid4()),
            title=self.conversation_title or self._generate_title(),
            metadata=ConversationMetadata(
                source=self.provider.name,
                model=self.provider.model,
                tags=[self.provider.name, "chat"],
            ),
        )

        # Convert all TreeMessages to DBMessages recursively
        def convert_node(tree_msg: TreeMessage, parent_id: Optional[str] = None):
            db_msg = DBMessage(
                id=tree_msg.id,
                role=DBMessageRole(tree_msg.role.value),
                content=MessageContent(text=tree_msg.content),
                timestamp=tree_msg.timestamp,
                parent_id=parent_id,
                metadata=(
                    {"model": tree_msg.model, "user": tree_msg.user}
                    if (tree_msg.model or tree_msg.user)
                    else None
                ),
            )
            tree.add_message(db_msg)

            # Recursively convert children
            for child in tree_msg.children:
                convert_node(child, tree_msg.id)

        convert_node(self.root)
        return tree

    def load_conversation_tree(self, tree: ConversationTree):
        """Load ConversationTree into internal tree structure"""
        # Clear current tree
        self.root = None
        self.current_message = None
        self.message_map = {}

        # Set conversation default model from metadata
        self.conversation_model = tree.metadata.model if tree.metadata else None

        # Use ConversationTreeNavigator to build the tree
        nav = ConversationTreeNavigator(tree)

        # Copy the built tree structure
        self.root = nav.root
        self.message_map = nav.message_map

        # Convert DBMessageRole to LLMMessageRole for all messages
        for msg in self.message_map.values():
            msg.role = LLMMessageRole(msg.role.value)

        # Set current position to most recent leaf node
        if self.root:
            leaves = nav.get_all_leaves()
            if leaves:
                # Find the leaf with the most recent timestamp
                most_recent_leaf = max(leaves, key=lambda msg: msg.timestamp)
                self.current_message = most_recent_leaf
            else:
                # No leaves yet (shouldn't happen), use root
                self.current_message = self.root

    def add_message(
        self, role: LLMMessageRole, content: str, parent: Optional[TreeMessage] = None
    ) -> TreeMessage:
        """
        Add a new message to the tree.

        Args:
            role: Message role
            content: Message content
            parent: Parent message (uses current_message if None)

        Returns:
            The created TreeMessage
        """
        if parent is None:
            parent = self.current_message

        # Track model for assistant messages, user for user messages
        model = self.provider.model if role == LLMMessageRole.ASSISTANT else None
        user = self.current_user if role == LLMMessageRole.USER else None

        msg = TreeMessage(
            role=role, content=content, parent=parent, model=model, user=user
        )
        self.message_map[msg.id] = msg

        # If this is the first message, set as root
        if self.root is None:
            self.root = msg

        # Move current position to new message
        self.current_message = msg

        return msg

    def print_header(self):
        """Print welcome header"""
        from rich.panel import Panel
        from rich.text import Text

        header_text = Text()
        header_text.append("CTK Chat", style="bold cyan")
        header_text.append(" - Conversation Toolkit\n", style="dim")
        header_text.append(f"Provider: ", style="dim")
        header_text.append(f"{self.provider.name}\n", style="bold")
        header_text.append(f"Model: ", style="dim")
        header_text.append(f"{self.provider.model}", style="bold magenta")

        self.console.print(Panel(header_text, border_style="cyan"))
        self.console.print("[dim]Type 'help' for commands, 'exit' to quit[/dim]\n")

    def print_success(self, message: str):
        """Print success message with rich formatting"""
        self.console.print(f"[green]✓[/green] {message}")

    def print_error(self, message: str):
        """Print error message with rich formatting"""
        self.console.print(f"[red]✗ Error:[/red] {message}")

    def print_warning(self, message: str):
        """Print warning message with rich formatting"""
        self.console.print(f"[yellow]⚠ Warning:[/yellow] {message}")

    def print_info(self, message: str):
        """Print info message with rich formatting"""
        self.console.print(f"[cyan]ℹ[/cyan] {message}")

    # Command help dictionary - detailed help for each command
    COMMAND_HELP = {
        "help": {
            "usage": "help [command]",
            "desc": "Show general help or detailed help for a specific command",
            "examples": ["help", "help fork", "help export"],
        },
        "save": {
            "usage": "save",
            "desc": "Save the current conversation to the database",
            "details": "Persists the entire conversation tree including all branches and metadata. Requires database to be configured.",
        },
        "load": {
            "usage": "load <id>",
            "desc": "Load a conversation from the database",
            "details": "Accepts full or partial conversation ID. Use /list or /search to find conversation IDs.",
            "examples": ["load abc123", "load abc"],
        },
        "delete": {
            "usage": "delete [id]",
            "desc": "Delete a conversation from the database",
            "details": "If no ID provided, deletes the currently loaded conversation. Requires confirmation.",
            "examples": ["delete", "delete abc123"],
        },
        "archive": {
            "usage": "archive",
            "desc": "Archive the current conversation",
            "details": "Archived conversations are hidden from default list/search results. Use --include-archived flag in CLI to see them.",
        },
        "unarchive": {
            "usage": "unarchive",
            "desc": "Unarchive the current conversation",
        },
        "star": {
            "usage": "star",
            "desc": "Star the current conversation for quick access",
            "details": "Starred conversations can be filtered with ctk list --starred",
        },
        "unstar": {"usage": "unstar", "desc": "Remove star from current conversation"},
        "pin": {
            "usage": "pin",
            "desc": "Pin the current conversation",
            "details": "Pinned conversations appear first in lists",
        },
        "unpin": {"usage": "unpin", "desc": "Unpin the current conversation"},
        "fork": {
            "usage": "fork <num>",
            "desc": "Fork conversation from a message number in current path",
            "details": "Creates a new conversation starting from the specified message. Use /history to see message numbers.",
            "examples": ["fork 5", "fork 0"],
        },
        "fork-id": {
            "usage": "fork-id <id>",
            "desc": "Fork conversation from a message by ID",
            "details": "Accepts full or partial message ID. Use /tree to see message IDs.",
            "examples": ["fork-id abc123"],
        },
        "duplicate": {
            "usage": "duplicate [title]",
            "desc": "Duplicate the current conversation",
            "details": 'Creates a complete copy with new ID. Optional custom title, otherwise prefixed with "Copy of".',
            "examples": ["duplicate", 'duplicate "My experiment"'],
        },
        "split": {
            "usage": "split <num>",
            "desc": "Split conversation at message number into new conversation",
            "details": "Creates a new conversation containing messages from the split point onwards.",
            "examples": ["split 10"],
        },
        "prune": {
            "usage": "prune <msg-id>",
            "desc": "Delete a message and all its descendants",
            "details": "Permanently removes the specified message and all child messages. Requires confirmation. Use /tree to find message IDs.",
            "examples": ["prune abc123"],
        },
        "keep-path": {
            "usage": "keep-path <num>",
            "desc": "Flatten tree by keeping only one path",
            "details": "Removes all branches except the specified path. Use /paths to see path numbers. Requires confirmation.",
            "examples": ["keep-path 0"],
        },
        "tag": {
            "usage": "tag [tag]",
            "desc": "Show current tags or add a tag to the conversation",
            "details": "Without arguments, displays current conversation tags. With an argument, adds the tag to the conversation. Tags help organize and filter conversations.",
            "examples": ["tag", "tag python", "tag machine-learning"],
        },
        "project": {
            "usage": "project [name]",
            "desc": "Show current project or set project for the conversation",
            "details": "Without arguments, displays current project. With an argument, sets the project name. Projects help organize related conversations.",
            "examples": ["project", "project research", "project ctk-dev"],
        },
        "auto-tag": {
            "usage": "auto-tag",
            "desc": "Use LLM to suggest and add tags automatically",
            "details": "Analyzes the conversation and suggests 3-5 relevant tags. You can approve or reject the suggestions.",
        },
        "export": {
            "usage": "export <format> [file]",
            "desc": "Export conversation to file",
            "details": "Formats: markdown, json, jsonl, html. If no file specified, generates default name.",
            "examples": [
                "export markdown",
                "export json output.json",
                "export html report.html",
            ],
        },
        "tree": {
            "usage": "tree",
            "desc": "Visualize conversation tree structure",
            "details": "Shows branching structure with message IDs, roles, and content previews. Current position marked with *.",
        },
        "paths": {
            "usage": "paths",
            "desc": "List all branches/paths through the conversation tree",
            "details": "Shows each possible path from root to leaf. Useful before /keep-path.",
        },
        "merge": {
            "usage": "merge <id> [num]",
            "desc": "Merge another conversation into this one",
            "details": "Inserts messages from another conversation. Optional message number specifies insertion point (default: end).",
            "examples": ["merge abc123", "merge abc123 5"],
        },
        "history": {
            "usage": "history [length]",
            "desc": "Show message history of current path",
            "details": "Optional length parameter truncates message content to N characters.",
            "examples": ["history", "history 100"],
        },
        "temp": {
            "usage": "temp [value]",
            "desc": "Set or show temperature (0.0-2.0)",
            "details": "Controls randomness of responses. Lower = more focused, higher = more creative. Default: 0.7",
            "examples": ["temp", "temp 0.9"],
        },
        "model": {
            "usage": "model [name]",
            "desc": "Switch model or show current model",
            "examples": ["model", "model llama3.2", "model gpt-4"],
        },
        "search": {
            "usage": "search <query> [options]",
            "desc": "Search conversations in the database",
            "details": """Searches both conversation titles and message content. Returns up to 20 results sorted by relevance.
Options:
  --limit N             Maximum results (default: 20)
  --title-only          Search only in titles
  --content-only        Search only in message content
  --starred             Show only starred conversations
  --pinned              Show only pinned conversations
  --archived            Show only archived conversations
  --include-archived    Include archived in results
  --source SOURCE       Filter by source platform
  --project PROJECT     Filter by project name
  --model MODEL         Filter by model
  --tags TAG1,TAG2      Filter by tags (comma-separated)
  --min-messages N      Minimum message count
  --max-messages N      Maximum message count
  --has-branches        Filter to branching conversations only""",
            "examples": [
                "search python",
                'search "error handling" --title-only',
                'search "API" --model gpt-4 --starred',
                "search debugging --tags python,troubleshooting",
            ],
        },
        "list": {
            "usage": "list [options]",
            "desc": "List recent conversations from the database",
            "details": """Shows the most recently updated conversations with filtering and organization options.
Options:
  --limit N             Maximum results (default: 20)
  --starred             Show only starred conversations
  --pinned              Show only pinned conversations
  --archived            Show only archived conversations
  --include-archived    Include archived in results (default: exclude)
  --source SOURCE       Filter by source platform (e.g., openai, anthropic)
  --project PROJECT     Filter by project name
  --model MODEL         Filter by model (e.g., gpt-4, claude-3)
  --tags TAG1,TAG2      Filter by tags (comma-separated)

Display:
  📌 = Pinned conversation
  ⭐ = Starred conversation
  📦 = Archived conversation""",
            "examples": [
                "list",
                "list --starred --limit 10",
                "list --model gpt-4",
                "list --tags python,machine-learning",
                "list --archived",
            ],
        },
        "net": {
            "usage": "net <subcommand> [options]",
            "desc": "Network and similarity commands for finding related conversations",
            "details": """Subcommands:
  embeddings [options]
    Generate embeddings for conversations in the database.
    Options:
      --provider PROVIDER   Embedding provider (default: tfidf)
      --force              Re-embed all conversations, ignoring cache
      --limit N            Limit number of conversations (default: all)
      --search QUERY       Filter by keyword search in title/content
      --starred            Only starred conversations
      --pinned             Only pinned conversations
      --tags TAG1,TAG2     Filter by tags (comma-separated)
      --source SOURCE      Filter by source (e.g., openai, anthropic)
      --project PROJECT    Filter by project name
      --model MODEL        Filter by model (e.g., gpt-4, claude-3)

  similar [conv_id] [--top-k N] [--threshold T]
    Find conversations similar to a given conversation.
    Options:
      conv_id              Conversation ID (uses current if not specified)
      --top-k N           Number of results (default: 10)
      --threshold T       Minimum similarity score (default: 0.0)
      --provider PROVIDER  Embedding provider (default: tfidf)

  links [--threshold T] [--max-links N] [--rebuild]
    Build a graph of conversation relationships based on similarity.
    Uses filters from most recent embedding session.
    Options:
      --threshold T       Minimum similarity for edge (default: 0.3)
      --max-links N       Max edges per node (default: 10)
      --rebuild           Force rebuild even if graph exists

  network [--rebuild]
    Display global network statistics for current graph.
    Metrics include: density, connectivity, diameter, clustering.
    Results are cached for fast repeated access.
    Options:
      --rebuild           Recompute metrics even if cached

  clusters [--algorithm louvain|label_propagation|greedy] [--min-size N]
    Detect conversation communities using community detection algorithms.

  neighbors <conv_id> [--depth N]
    Show neighbors of a conversation in the similarity graph.
    Uses current conversation if no ID specified.

  path <source> <target>
    Find shortest path between two conversations in the graph.

  central [--metric degree|betweenness|pagerank|eigenvector] [--top-k N]
    Find most central/connected conversations using centrality metrics.

  outliers [--top-k N]
    Find least connected conversations (potential outliers).

Note: Run 'net embeddings' once before using other commands.
Run 'net links' to build the graph before using clusters, neighbors, path, central, outliers.""",
            "examples": [
                "net embeddings",
                "net embeddings --force",
                "net embeddings --search python --limit 50",
                "net embeddings --starred --tags machine-learning",
                "net similar --top-k 5",
                "net similar abc123 --top-k 10 --threshold 0.3",
                "net links --threshold 0.3 --max-links 10",
                "net links --rebuild",
                "net network",
                "net clusters --algorithm louvain",
                "net neighbors abc123 --depth 2",
                "net path abc123 def456",
                "net central --metric pagerank --top-k 20",
                "net outliers --top-k 15",
            ],
        },
        "cd": {
            "usage": "cd [path]",
            "desc": "Change current directory in virtual filesystem",
            "details": """Navigate the conversation virtual filesystem.

Paths can be absolute (/tags/physics) or relative (../quantum).
Special: . (current directory), .. (parent directory)

Examples:
  /cd /tags/physics           # Absolute path
  /cd physics/simulator       # Relative path
  /cd ..                      # Parent directory
  /cd /starred                # View starred conversations""",
            "examples": [
                "cd /",
                "cd /tags/physics",
                "cd ../quantum",
                "cd /starred",
            ],
        },
        "pwd": {
            "usage": "pwd",
            "desc": "Print current working directory",
            "details": """Shows your current location in the virtual filesystem.""",
            "examples": ["pwd"],
        },
        "ls": {
            "usage": "ls [-l] [path]",
            "desc": "List directory contents",
            "details": """List conversations and subdirectories.

Options:
  -l    Long format with metadata (title, tags, date)

If no path specified, lists current directory.

Examples:
  /ls                # Current directory
  /ls -l             # Long format
  /ls /tags/physics  # Specific directory
  /ls -l /starred    # Starred conversations with details""",
            "examples": [
                "ls",
                "ls -l",
                "ls /tags/physics",
                "ls -l /starred",
            ],
        },
        "ln": {
            "usage": "ln <src> <dest>",
            "desc": "Link conversation to tag (add tag, like hardlink)",
            "details": """Add a tag to a conversation without removing existing tags.
Source must be a conversation, destination must be a /tags/* directory.
This is like creating a hardlink - the same conversation appears in multiple tag directories.""",
            "examples": [
                "ln /chats/abc123 /tags/physics/",
                "ln /starred/xyz789 /tags/important/",
                "ln abc123 /tags/research/ml/",
            ],
        },
        "cp": {
            "usage": "cp <src> <dest>",
            "desc": "Copy conversation (deep copy with new UUID)",
            "details": """Create a complete copy of a conversation with a new auto-generated UUID.
Source must be a conversation, destination can be /tags/* directory.
The copy will have all messages and tags, but a different ID.
This is a true copy - editing one won't affect the other.""",
            "examples": [
                "cp /chats/abc123 /tags/backup/",
                "cp /tags/test/xyz789 /tags/production/",
            ],
        },
        "mv": {
            "usage": "mv <src> <dest>",
            "desc": "Move conversation between tags",
            "details": """Move a conversation from one tag to another.
Source must be from /tags/*, removes old tag and adds new tag.
The conversation keeps its ID, just changes tags.""",
            "examples": [
                "mv /tags/draft/abc123 /tags/final/",
                "mv /tags/physics/old/xyz789 /tags/physics/new/",
            ],
        },
        "rm": {
            "usage": "rm <path>",
            "desc": "Remove tag from conversation or delete conversation",
            "details": """Two modes of operation:
1. /rm /tags/path/conv_id - Removes the tag from conversation
2. /rm /chats/conv_id - Permanently deletes conversation (with confirmation)

Deleting from /chats/ is destructive and requires confirmation.
Removing from /tags/* just removes the tag, doesn't delete the conversation.""",
            "examples": [
                "rm /tags/physics/abc123",
                "rm /chats/xyz789",
            ],
        },
        "mkdir": {
            "usage": "mkdir <path>",
            "desc": "Create tag hierarchy (conceptual)",
            "details": """Create a conceptual tag hierarchy in /tags/*.
Directories are created conceptually and will appear when conversations are tagged.
You don't need to create directories before tagging - this is mainly for documentation.""",
            "examples": [
                "mkdir /tags/research/ml/transformers/",
                "mkdir /tags/projects/new-feature/",
            ],
        },
    }

    def print_help(self, command: str = None):
        """Print help message"""
        if command:
            # Show detailed help for specific command
            cmd = command.lstrip("")  # Remove leading slash if present
            if cmd in self.COMMAND_HELP:
                help_info = self.COMMAND_HELP[cmd]
                self.console.print(f"\n[bold cyan]{cmd}[/bold cyan]")
                self.console.print(f"[dim]Usage:[/dim] {help_info['usage']}")
                self.console.print(f"\n{help_info['desc']}")

                if "details" in help_info:
                    self.console.print(f"\n[dim]Details:[/dim] {help_info['details']}")

                if "examples" in help_info:
                    self.console.print("\n[dim]Examples:[/dim]")
                    for ex in help_info["examples"]:
                        self.console.print(f"  {ex}")
                print()
            else:
                self.console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
                self.console.print("Type [bold]help[/bold] for list of all commands")
            return

        # Show general help
        print("\nAvailable commands:")
        print("\n  Basic:")
        print("    help [command]    - Show this help or detailed help for a command")
        print("    exit, quit        - Exit chat")
        print("    clear             - Clear conversation history")
        print("    new-chat [title]  - Save current & start new conversation")

        print("\n  Database:")
        print("    save              - Save conversation to database")
        print("    load <id>         - Load conversation from database")
        print("    delete [id]       - Delete conversation (current if no ID given)")
        print("    search <query>    - Search conversations")
        print("    list              - List recent conversations")
        print("    archive           - Archive current conversation")
        print("    unarchive         - Unarchive current conversation")
        print("    star              - Star current conversation")
        print("    unstar            - Unstar current conversation")
        print("    pin               - Pin current conversation")
        print("    unpin             - Unpin current conversation")

        print("\n  Conversation Management:")
        print("    title <text>      - Set conversation title")
        print("    user [name]       - Set/show current user name (for attribution)")
        print("    stats             - Show conversation statistics")
        print("    show <num>        - Display full message by number")
        print("    grep <pattern>    - Search within current conversation")
        print("    rollback [n]      - Remove last n exchanges (default: 1)")

        print("\n  Context Control:")
        print("    system <msg>      - Add system message")
        print("    context <file>    - Load file content into context")
        print(
            "    merge <id> [num]  - Merge conversation at message position (default: end)"
        )
        print(
            "    branch            - Save & create new conversation with same history"
        )
        print(
            "    fork <num>        - Fork conversation from message number in current path"
        )
        print(
            "    fork-id <id>      - Fork conversation from message by ID (full or partial)"
        )
        print("    duplicate [title] - Duplicate current conversation")
        print("    split <num>       - Split conversation at message number")
        print("    prune <msg-id>    - Delete message and all its descendants")
        print("    keep-path <num>   - Flatten tree, keeping only specified path")
        print("    tag <tag>         - Add tag to current conversation")
        print("    auto-tag          - Use LLM to suggest and add tags")

        print("\n  LLM Control:")
        print("    temp [0.0-2.0]    - Set/show temperature (default: 0.7)")
        print("    model [name]      - Switch/show model")
        print("    models            - List available models")
        print("    model_info [name] - Show detailed model information")
        print("    num_ctx [size]    - Set/show context window size")
        print("    stream            - Toggle streaming (raw stream vs markdown)")
        print("    regenerate        - Regenerate last assistant response")
        print("    retry [temp]      - Retry last message with optional temperature")
        print("    summary           - Ask LLM to summarize conversation")

        print("\n  Export:")
        print(
            "    export <fmt> [file] - Export conversation (markdown, json, jsonl, html)"
        )

        print("\n  Tree Navigation:")
        print("    tree              - Visualize conversation tree structure")
        print("    goto-longest      - Navigate to leaf of longest path")
        print("    goto-latest       - Navigate to most recent leaf node")
        print("    where             - Show current position in tree")
        print(
            "    history [length]  - Show message history (optional: max chars per message)"
        )
        print("    paths             - List all branches/paths through tree")
        print(
            "    alternatives      - Show alternative child branches at current position"
        )
        print("    Note: Message numbers shown in [brackets] for /fork reference.")

        print("\n  Shell:")
        print(
            "    !<command>         - Execute shell command (e.g., !ls, !cat file.txt)"
        )
        print("    cd <path>         - Change working directory for shell commands")

        print("\n  MCP (Model Context Protocol):")
        print("    mcp add <name> <cmd> [args...] - Add MCP server")
        print("    mcp remove <name>              - Remove MCP server")
        print("    mcp connect <name>             - Connect to MCP server")
        print("    mcp disconnect <name>          - Disconnect from MCP server")
        print("    mcp list                       - List configured servers")
        print("    mcp tools [server]             - List available tools")
        print("    mcp call <tool> [args...]      - Call an MCP tool")
        print("    mcp auto                       - Toggle automatic tool use by LLM")

        print("\n  Network / Similarity:")
        print(
            "    net embeddings [options]     - Generate embeddings (supports filters: --starred, --tags, etc.)"
        )
        print(
            "    net similar [id] [--top-k N] - Find similar conversations (uses current if no ID)"
        )
        print("    net links [--threshold N]    - Build conversation graph")
        print("    net network [--rebuild]      - Show network statistics")
        print("    net clusters [--algorithm]   - Detect conversation communities")
        print("    net neighbors <id>           - Show graph neighbors")
        print("    net path <src> <dst>         - Find path between conversations")
        print("    net central [--metric]       - Find most central conversations")
        print("    net outliers                 - Find least connected conversations")
        print("    Use 'help net' for detailed options and examples")

        print("\n  Virtual Filesystem:")
        print(
            "    cd [path]           - Change directory (/tags/physics, ../quantum, /starred)"
        )
        print("    pwd                 - Print working directory")
        print("    ls [-l] [path]      - List directory contents (-l for long format)")
        print("    ln <src> <dest>     - Link conversation to tag (add tag)")
        print("    cp <src> <dest>     - Copy conversation (deep copy with new UUID)")
        print("    mv <src> <dest>     - Move conversation between tags")
        print("    rm <path>           - Remove tag or delete conversation")
        print("    mkdir <path>        - Create tag hierarchy (conceptual)")
        print("    Use 'help <command>' for details on any VFS command")
        print()

    def handle_command(self, command: str) -> bool:
        """
        Handle commands.

        Args:
            command: Command string (without prefix)

        Returns:
            True if should continue, False if should exit
        """
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ["exit", "quit"]:
            return False

        elif cmd == "help":
            self.print_help(args)

        elif cmd == "clear":
            self.root = None
            self.current_message = None
            self.message_map = {}
            self.current_conversation_id = None
            self.conversation_title = None
            self.conversation_model = (
                self.provider.model
            )  # Set default model for new conversation
            self.print_success("Conversation cleared")

        elif cmd == "new-chat":
            # Save current conversation if it exists and has messages
            if self.root and self.db:
                # Auto-save current conversation
                try:
                    self.save_conversation()
                    print("✓ Current conversation saved")
                except Exception as e:
                    print(f"Warning: Could not save current conversation: {e}")

            # Clear current conversation
            self.root = None
            self.current_message = None
            self.message_map = {}
            self.current_conversation_id = None
            self.conversation_model = (
                self.provider.model
            )  # Set default model for new conversation

            # Set new title if provided
            if args:
                self.conversation_title = args
                print(f"✓ Started new conversation: '{args}'")
            else:
                self.conversation_title = None
                print("✓ Started new conversation")

        elif cmd == "system":
            if not args:
                print("Error: /system requires a message")
            else:
                self.add_message(LLMMessageRole.SYSTEM, args)
                print(f"✓ System message added: {args}")

        elif cmd == "save":
            self.save_conversation()

        elif cmd == "load":
            if not args:
                print("Error: /load requires a conversation ID")
            else:
                self.load_conversation(args)

        elif cmd == "delete":
            # If no args, delete currently loaded conversation
            conv_id = args if args else self.current_conversation_id
            if not conv_id:
                print(
                    "Error: No conversation to delete (not loaded and no ID provided)"
                )
            else:
                self.delete_conversation(conv_id)

        elif cmd == "search":
            if not args:
                print("Error: /search requires a query")
            else:
                self.search_conversations(args)

        elif cmd == "list":
            self.list_conversations(args)

        elif cmd == "archive":
            self.archive_conversation(archive=True)

        elif cmd == "unarchive":
            self.archive_conversation(archive=False)

        elif cmd == "star":
            self.star_conversation(star=True)

        elif cmd == "unstar":
            self.star_conversation(star=False)

        elif cmd == "pin":
            self.pin_conversation(pin=True)

        elif cmd == "unpin":
            self.pin_conversation(pin=False)

        elif cmd == "duplicate":
            self.duplicate_conversation(args if args else None)

        elif cmd == "tag":
            if not args:
                # Show current tags
                if not self.db or not self.current_conversation_id:
                    print("Error: No conversation loaded")
                    return
                try:
                    tree = self.db.load_conversation(self.current_conversation_id)
                    if tree and tree.metadata and tree.metadata.tags:
                        print(f"Tags: {', '.join(tree.metadata.tags)}")
                    else:
                        print("No tags")
                except Exception as e:
                    print(f"Error loading tags: {e}")
            else:
                self.add_tag(args)

        elif cmd == "project":
            if not args:
                # Show current project
                if self.conversation_project:
                    print(f"Project: {self.conversation_project}")
                else:
                    print("No project set")
            else:
                self.set_project(args)

        elif cmd == "auto-tag":
            self.auto_tag_conversation()

        elif cmd == "split":
            if not args:
                print("Error: /split requires a message number")
            else:
                try:
                    msg_num = int(args)
                    self.split_conversation(msg_num)
                except ValueError:
                    print(f"Error: Invalid message number: {args}")

        elif cmd == "prune":
            if not args:
                print("Error: /prune requires a message ID")
            else:
                self.prune_subtree(args)

        elif cmd == "keep-path":
            if not args:
                print("Error: /keep-path requires a path number")
            else:
                try:
                    path_num = int(args)
                    self.keep_path(path_num)
                except ValueError:
                    print(f"Error: Invalid path number: {args}")

        elif cmd == "title":
            if not args:
                print("Error: /title requires a new title")
            else:
                self.conversation_title = args
                print(f"✓ Conversation title set to: {args}")

        elif cmd == "user":
            if not args:
                if self.current_user:
                    print(f"Current user: {self.current_user}")
                else:
                    print("No user set (messages will have no user attribution)")
            else:
                self.current_user = args
                print(f"✓ User set to: {args}")

        elif cmd == "stats":
            self.show_stats()

        elif cmd == "show":
            if not args:
                print("Error: /show requires a message number")
            else:
                try:
                    msg_num = int(args)
                    self.show_message(msg_num)
                except ValueError:
                    print(f"Error: Invalid message number: {args}")

        elif cmd == "rollback":
            if not args:
                # Default to rolling back 1 exchange (2 messages)
                self.rollback(1)
            else:
                try:
                    n = int(args)
                    self.rollback(n)
                except ValueError:
                    print(f"Error: Invalid number: {args}")

        elif cmd == "temp":
            if not args:
                print(f"Current temperature: {self.temperature}")
            else:
                try:
                    temp = float(args)
                    if temp < 0.0 or temp > 2.0:
                        print("Error: Temperature must be between 0.0 and 2.0")
                    else:
                        self.temperature = temp
                        print(f"✓ Temperature set to {temp}")
                except ValueError:
                    print(f"Error: Invalid temperature: {args}")

        elif cmd == "model":
            if not args:
                # Show current model info
                print(f"Current model: {self.provider.model}")
                print(f"Provider: {self.provider.name}")

                # Show provider-specific info
                if hasattr(self.provider, "base_url"):
                    print(f"Base URL: {self.provider.base_url}")

                # Get detailed model info if available
                try:
                    model_info = self.provider.get_model_info(self.provider.model)
                    if model_info:
                        print("\nModel details:")
                        # Show key info based on provider
                        if "modelfile" in model_info:
                            # Ollama format
                            if "parameters" in model_info:
                                print(
                                    f"  Parameters: {model_info.get('parameters', 'N/A')}"
                                )
                            if "template" in model_info:
                                template = model_info.get("template", "")
                                if len(template) > 100:
                                    template = template[:100] + "..."
                                print(f"  Template: {template}")
                            if "details" in model_info:
                                details = model_info["details"]
                                if "family" in details:
                                    print(f"  Family: {details['family']}")
                                if "parameter_size" in details:
                                    print(f"  Size: {details['parameter_size']}")
                                if "quantization_level" in details:
                                    print(
                                        f"  Quantization: {details['quantization_level']}"
                                    )
                        else:
                            # Generic format
                            for key, value in model_info.items():
                                if key not in ["modelfile", "template", "license"]:
                                    print(f"  {key}: {value}")
                except Exception as e:
                    print(f"  (Could not retrieve model details: {e})")
            else:
                old_model = self.provider.model
                self.provider.model = args
                print(f"✓ Model changed from {old_model} to {args}")

        elif cmd == "models":
            self.list_models()

        elif cmd == "model_info":
            # Show detailed model info
            model_name = args if args else self.provider.model
            self.show_model_info(model_name)

        elif cmd == "num_ctx":
            if not args:
                # Show current setting
                if self.num_ctx:
                    print(f"Context window: {self.num_ctx:,} tokens")
                else:
                    print("Context window: not set (using model default)")
            else:
                try:
                    size = int(args)
                    if size < 128:
                        print("Error: Context window must be at least 128 tokens")
                        return True
                    self.num_ctx = size
                    print(f"✓ Context window set to {size:,} tokens")
                except ValueError:
                    print(f"Error: Invalid context size: {args}")

        elif cmd == "stream":
            self.streaming = not self.streaming
            status = "enabled" if self.streaming else "disabled"
            print(f"✓ Streaming {status}")

        elif cmd == "grep":
            if not args:
                print("Error: /grep requires a search pattern")
            else:
                self.grep_conversation(args)

        elif cmd == "export":
            if not args:
                print("Error: /export requires format (markdown, json, jsonl, html)")
            else:
                # Parse format and optional filename
                parts = args.split(maxsplit=1)
                fmt = parts[0].lower()
                filename = parts[1] if len(parts) > 1 else None
                self.export_conversation(fmt, filename)

        elif cmd == "regenerate":
            self.regenerate_last_response()

        elif cmd == "retry":
            # Parse optional temperature
            temp = None
            if args:
                try:
                    temp = float(args)
                    if temp < 0.0 or temp > 2.0:
                        print("Error: Temperature must be between 0.0 and 2.0")
                        return True
                except ValueError:
                    print(f"Error: Invalid temperature: {args}")
                    return True
            self.retry_last_message(temp)

        elif cmd == "summary":
            self.request_summary()

        elif cmd == "merge":
            if not args:
                print("Error: /merge requires a conversation ID")
            else:
                # Parse optional insertion point
                parts = args.split(maxsplit=1)
                conv_id = parts[0]
                insert_at = None
                if len(parts) > 1:
                    try:
                        insert_at = int(parts[1])
                    except ValueError:
                        print(f"Error: Invalid message number: {parts[1]}")
                        return True
                self.merge_conversation(conv_id, insert_at)

        elif cmd == "branch":
            self.branch_conversation()

        elif cmd == "fork":
            if not args:
                print("Error: /fork requires a message number")
            else:
                try:
                    msg_num = int(args)
                    self.fork_conversation(msg_num)
                except ValueError:
                    print(f"Error: Invalid message number: {args}")

        elif cmd == "fork-id":
            if not args:
                print("Error: /fork-id requires a message ID (full or partial)")
            else:
                self.fork_conversation_by_id(args)

        elif cmd == "context":
            if not args:
                print("Error: /context requires a file path")
            else:
                self.load_file_context(args)

        elif cmd == "mcp":
            if not args:
                print(
                    "Error: /mcp requires a subcommand (add, remove, connect, disconnect, list, tools, call)"
                )
            else:
                self.handle_mcp_command(args)

        elif cmd == "tree":
            self.show_tree()

        elif cmd == "goto-longest":
            self.goto_longest_path()

        elif cmd == "goto-latest":
            self.goto_latest_leaf()

        elif cmd == "where":
            self.show_current_position()

        elif cmd == "paths":
            self.show_all_paths()

        elif cmd == "alternatives":
            self.show_alternatives()

        elif cmd == "history":
            # Optional argument for max content length
            max_len = None
            if args:
                try:
                    max_len = int(args)
                except ValueError:
                    self.print_error(f"Invalid length: {args}")
                    return True
            self.show_history(max_len)

        elif cmd == "cd":
            self.handle_cd(args)

        elif cmd == "pwd":
            self.handle_pwd()

        elif cmd == "ls":
            self.handle_ls(args)

        elif cmd == "ln":
            self.handle_ln(args)

        elif cmd == "cp":
            self.handle_cp(args)

        elif cmd == "mv":
            self.handle_mv(args)

        elif cmd == "rm":
            self.handle_rm(args)

        elif cmd == "mkdir":
            self.handle_mkdir(args)

        elif cmd == "net":
            if not args:
                print("Error: /net requires a subcommand")
                print("Usage:")
                print("  /net embeddings [--provider tfidf]")
                print("  /net similar [conv_id] [--top-k N]")
                print("  /net links [--threshold N]")
                print("  /net network [--rebuild]")
                print("  /net clusters [--algorithm louvain]")
                print("  /net neighbors <id> [--depth N]")
                print("  /net path <source> <target>")
                print("  /net central [--metric degree|betweenness|pagerank]")
                print("  /net outliers [--top-k N]")
            else:
                self.handle_net_command(args)

        else:
            print(f"Unknown command: {cmd}")
            print("Type 'help' for available commands")

        return True

    def save_conversation(self):
        """Save current conversation to database"""
        if not self.db:
            print("Error: No database configured")
            return

        if not self.root:
            print("Error: No messages to save")
            return

        try:
            # Convert to DB format
            tree = self.tree_to_conversation_tree()

            # Save to database
            self.db.save_conversation(tree)
            self.current_conversation_id = tree.id

            print(f"✓ Conversation saved (ID: {tree.id[:8]}...)")
            print(f"  Title: {tree.title}")

        except Exception as e:
            print(f"Error saving conversation: {e}")

    def _auto_save_conversation(self):
        """
        Auto-save conversation after chat exchanges.

        Silently saves if we have a database and conversation ID.
        For new conversations, saves with an auto-generated title.
        """
        if not self.db or not self.root:
            return

        try:
            # Convert to DB format
            tree = self.tree_to_conversation_tree()

            # Save to database (silently)
            self.db.save_conversation(tree)
            self.current_conversation_id = tree.id

        except Exception:
            # Silently fail auto-save - user can manually save if needed
            pass

    def _generate_title(self) -> str:
        """Generate a title from the first user message"""
        current_path = self.get_current_path()
        for msg in current_path:
            if msg.role == LLMMessageRole.USER:
                # Take first 50 chars of first user message
                title = msg.content[:50].strip()
                if len(msg.content) > 50:
                    title += "..."
                return title
        return f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    def load_conversation(self, conv_id: str):
        """Load conversation from database"""
        if not self.db:
            print("Error: No database configured")
            return

        try:
            tree = None

            # If ID is partial (< 36 chars), use DB-level prefix resolution
            if len(conv_id) < 36:
                resolved_id = self.db.resolve_conversation(conv_id)
                if not resolved_id:
                    print(f"Error: No conversation found matching '{conv_id}' (or ID is ambiguous)")
                    return
                conv_id = resolved_id

            # Load the conversation (either full ID or resolved prefix)
            tree = self.db.load_conversation(conv_id)

            if not tree:
                print(f"Error: Conversation {conv_id} not found")
                return

            # Load conversation tree into TUI structure
            self.load_conversation_tree(tree)

            self.current_conversation_id = tree.id
            self.conversation_title = tree.title
            self.conversation_project = tree.metadata.project if tree.metadata else None

            current_path = self.get_current_path()
            print(f"✓ Loaded conversation: {tree.title}")
            print(f"  ID: {tree.id[:8]}...")
            print(f"  Messages in current path: {len(current_path)}")
            print(f"  Total messages in tree: {len(self.message_map)}")
            print(f"  Model: {tree.metadata.model or 'unknown'}")
            print()

            # Print conversation history (abbreviated)
            self.console.print("[dim]Conversation history (current path):[/dim]")
            self.show_conversation_history(max_content_length=100)

        except Exception as e:
            print(f"Error loading conversation: {e}")

    def delete_conversation(self, conv_id: str):
        """Delete conversation from database"""
        if not self.db:
            print("Error: No database configured")
            return

        try:
            # Try loading to confirm it exists and get title
            tree = self.db.load_conversation(conv_id)

            # If not found and ID is partial, use DB-level prefix resolution
            if not tree and len(conv_id) < 36:
                resolved_id = self.db.resolve_conversation(conv_id)
                if not resolved_id:
                    print(f"Error: No conversation found matching '{conv_id}' (or ID is ambiguous)")
                    return
                tree = self.db.load_conversation(resolved_id)

            if not tree:
                print(f"Error: Conversation {conv_id} not found")
                return

            # Confirm deletion
            print(f"\nAbout to delete conversation:")
            print(f"  ID: {tree.id[:8]}...")
            print(f"  Title: {tree.title}")
            print(f"  Messages: {len(tree.message_map)}")

            # If this is the currently loaded conversation, warn
            if self.current_conversation_id == tree.id:
                print(f"\n⚠️  Warning: This is the currently loaded conversation!")

            confirm = input("\nType 'yes' to confirm deletion: ").strip().lower()
            if confirm != "yes":
                print("Deletion cancelled")
                return

            # Delete from database
            self.db.delete_conversation(tree.id)
            print(f"✓ Deleted conversation: {tree.title}")

            # Clear current conversation if it was deleted
            if self.current_conversation_id == tree.id:
                self.root = None
                self.current_message = None
                self.message_map = {}
                self.current_conversation_id = None
                self.conversation_title = None
                print("  (Current conversation cleared)")

        except Exception as e:
            print(f"Error deleting conversation: {e}")

    def archive_conversation(self, archive: bool = True):
        """Archive or unarchive current conversation"""
        if not self.db or not self.current_conversation_id:
            print("Error: No conversation loaded or database not configured")
            return

        action = "archive" if archive else "unarchive"
        if self.db.archive_conversation(self.current_conversation_id, archive):
            print(f"✓ {action.capitalize()}d conversation: {self.conversation_title}")
        else:
            print(f"Error: Failed to {action} conversation")

    def star_conversation(self, star: bool = True):
        """Star or unstar current conversation"""
        if not self.db or not self.current_conversation_id:
            print("Error: No conversation loaded or database not configured")
            return

        action = "star" if star else "unstar"
        if self.db.star_conversation(self.current_conversation_id, star):
            print(f"✓ {action.capitalize()}red conversation: {self.conversation_title}")
        else:
            print(f"Error: Failed to {action} conversation")

    def pin_conversation(self, pin: bool = True):
        """Pin or unpin current conversation"""
        if not self.db or not self.current_conversation_id:
            print("Error: No conversation loaded or database not configured")
            return

        action = "pin" if pin else "unpin"
        if self.db.pin_conversation(self.current_conversation_id, pin):
            print(f"✓ {action.capitalize()}ned conversation: {self.conversation_title}")
        else:
            print(f"Error: Failed to {action} conversation")

    def duplicate_conversation(self, new_title: Optional[str] = None):
        """Duplicate current conversation"""
        if not self.db or not self.current_conversation_id:
            print("Error: No conversation loaded or database not configured")
            return

        new_id = self.db.duplicate_conversation(self.current_conversation_id, new_title)
        if new_id:
            new_tree = self.db.load_conversation(new_id)
            print(f"✓ Duplicated conversation")
            print(f"  Original: {self.conversation_title}")
            print(f"  New ID: {new_id[:8]}...")
            print(f"  New title: {new_tree.title}")
        else:
            print("Error: Failed to duplicate conversation")

    def add_tag(self, tag: str):
        """Add tag to current conversation"""
        if not self.db or not self.current_conversation_id:
            print("Error: No conversation loaded or database not configured")
            return

        try:
            self.db.add_tags(self.current_conversation_id, [tag])
            print(f"✓ Added tag: {tag}")
        except Exception as e:
            print(f"Error adding tag: {e}")

    def set_project(self, project: str):
        """Set project for current conversation"""
        if not self.db or not self.current_conversation_id:
            print("Error: No conversation loaded or database not configured")
            return

        try:
            self.db.update_conversation_metadata(
                self.current_conversation_id, project=project
            )
            self.conversation_project = project
            print(f"✓ Set project to: {project}")
        except Exception as e:
            print(f"Error setting project: {e}")

    def auto_tag_conversation(self):
        """Use LLM to suggest and add tags"""
        if not self.current_conversation_id:
            print("Error: No conversation loaded")
            return

        # Get conversation summary for tagging
        current_path = self.get_current_path()
        if len(current_path) < 2:
            print("Error: Need at least one exchange to auto-tag")
            return

        # Build context from conversation
        context = f"Title: {self.conversation_title}\n\n"
        for msg in current_path[:10]:  # First 10 messages
            role = msg.role.value.upper()
            content = msg.content[:200] if len(msg.content) > 200 else msg.content
            context += f"{role}: {content}\n\n"

        # Ask LLM to suggest tags
        tag_prompt = f"""Based on this conversation, suggest 3-5 relevant tags (single words or short phrases).
Return ONLY the tags as a comma-separated list, nothing else.

{context}

Tags:"""

        print("Asking LLM for tag suggestions...")
        try:
            from ctk.integrations.llm.base import Message, MessageRole

            response = self.provider.chat(
                [Message(role=MessageRole.USER, content=tag_prompt)], temperature=0.3
            )

            # Parse tags from response
            response_text = (
                response.content if hasattr(response, "content") else str(response)
            )
            tags = [t.strip() for t in response_text.strip().split(",")]
            tags = [t for t in tags if t]  # Remove empty

            if not tags:
                print("Error: No tags suggested")
                return

            print(f"\nSuggested tags: {', '.join(tags)}")
            confirm = input("Add these tags? (y/n): ").strip().lower()

            if confirm == "y":
                for tag in tags:
                    self.add_tag(tag)
            else:
                print("Cancelled")

        except Exception as e:
            print(f"Error getting tag suggestions: {e}")

    def split_conversation(self, msg_num: int):
        """Split conversation at message number into new conversation"""
        if not self.db:
            print("Error: Database not configured")
            return

        current_path = self.get_current_path()
        if msg_num < 0 or msg_num >= len(current_path):
            print(f"Error: Message number must be 0-{len(current_path)-1}")
            return

        # Save current conversation
        if self.current_conversation_id:
            self.save_conversation()

        # Create new conversation from split point onwards
        import uuid

        new_id = str(uuid.uuid4())
        new_title = f"Split from {self.conversation_title} at msg {msg_num}"

        # Create new tree with messages from split point
        from ctk.core.models import ConversationMetadata, ConversationTree

        new_tree = ConversationTree(
            id=new_id,
            title=new_title,
            metadata=ConversationMetadata(
                version="2.0.0", source="CTK Split", created_at=datetime.now()
            ),
        )

        # Copy messages from split point onwards
        for i in range(msg_num, len(current_path)):
            old_msg = current_path[i]
            # Create new message with new ID
            new_msg_id = str(uuid.uuid4())
            new_msg = Message(
                id=new_msg_id,
                role=old_msg.role,
                content=old_msg.content,
                timestamp=old_msg.timestamp,
                parent_id=None if i == msg_num else current_path[i - 1].id,
            )
            new_tree.add_message(new_msg)

        # Save new conversation
        self.db.save_conversation(new_tree)
        print(f"✓ Split conversation at message {msg_num}")
        print(f"  New conversation ID: {new_id[:8]}...")
        print(f"  New title: {new_title}")
        print(f"  Messages: {len(current_path) - msg_num}")

    def prune_subtree(self, msg_id_prefix: str):
        """Delete message and all its descendants"""
        # Find message by ID prefix
        matches = [
            (mid, msg)
            for mid, msg in self.message_map.items()
            if mid.startswith(msg_id_prefix)
        ]

        if len(matches) == 0:
            print(f"Error: No message found with ID starting with '{msg_id_prefix}'")
            return
        elif len(matches) > 1:
            print(f"Error: Multiple messages match '{msg_id_prefix}':")
            for mid, msg in matches[:5]:
                print(f"  - {mid[:8]}... ({msg.role.value})")
            return

        msg_id, target_msg = matches[0]

        # Count descendants
        def count_descendants(msg):
            count = 1
            for child in msg.children:
                count += count_descendants(child)
            return count

        total = count_descendants(target_msg)

        print(f"\nAbout to delete:")
        print(f"  Message: {msg_id[:8]}... ({target_msg.role.value})")
        print(f"  Total messages (including descendants): {total}")

        confirm = input("\nType 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Cancelled")
            return

        # Remove from parent's children
        if target_msg.parent:
            parent = self.message_map.get(target_msg.parent_id)
            if parent:
                parent.children = [c for c in parent.children if c.id != msg_id]

        # Recursively delete
        def delete_recursive(msg):
            for child in list(msg.children):
                delete_recursive(child)
            if msg.id in self.message_map:
                del self.message_map[msg.id]

        delete_recursive(target_msg)

        # Update current message if it was deleted
        if self.current_message and self.current_message.id not in self.message_map:
            # Move to parent or longest path
            self.current_message = (
                self.get_longest_path()[-1] if self.message_map else None
            )

        print(f"✓ Deleted {total} message(s)")

    def keep_path(self, path_num: int):
        """Flatten tree by keeping only one path"""
        paths = []
        for msg in self.message_map.values():
            if not msg.parent_id:
                # This is a root, get all paths from it
                def get_paths_from(node, current_path=None):
                    if current_path is None:
                        current_path = []
                    new_path = current_path + [node]
                    if not node.children:
                        return [new_path]
                    result = []
                    for child in node.children:
                        result.extend(get_paths_from(child, new_path))
                    return result

                paths.extend(get_paths_from(msg))

        if path_num < 0 or path_num >= len(paths):
            print(f"Error: Path number must be 0-{len(paths)-1}")
            print(f"Use /paths to see all paths")
            return

        keep = paths[path_num]
        keep_ids = {msg.id for msg in keep}

        # Count messages to delete
        delete_count = len(self.message_map) - len(keep_ids)

        print(f"\nKeeping path {path_num} ({len(keep)} messages)")
        print(f"Deleting {delete_count} messages")

        confirm = input("\nType 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Cancelled")
            return

        # Remove branches from kept messages
        for msg in keep:
            msg.children = [c for c in msg.children if c.id in keep_ids]

        # Delete messages not in path
        for msg_id in list(self.message_map.keys()):
            if msg_id not in keep_ids:
                del self.message_map[msg_id]

        # Update current message
        self.current_message = keep[-1]

        print(f"✓ Flattened to single path ({len(keep)} messages)")

    def search_conversations(self, args: str):
        """Search conversations in database with filtering options

        Usage: /search <query> [--limit N] [--title-only] [--content-only] [--starred] [--pinned] [--source SOURCE] [--model MODEL] [--tags TAG1,TAG2]
        """
        if not self.db:
            print("Error: No database configured")
            return

        # Parse arguments
        import shlex

        from ctk.core.db_helpers import search_conversations_helper

        try:
            arg_list = shlex.split(args) if args else []
        except ValueError as e:
            print(f"Error parsing arguments: {e}")
            return

        if not arg_list:
            print("Error: /search requires a query")
            return

        # First argument is the query
        query = arg_list[0]

        # Parse remaining arguments
        kwargs = {
            "limit": None,  # No limit by default - show all
            "offset": 0,
            "title_only": False,
            "content_only": False,
            "date_from": None,
            "date_to": None,
            "source": None,
            "project": None,
            "model": None,
            "tags": None,
            "min_messages": None,
            "max_messages": None,
            "has_branches": False,
            "archived": False,
            "starred": False,
            "pinned": False,
            "include_archived": False,
            "order_by": "updated_at",
            "ascending": False,
            "output_format": "table",
        }

        i = 1
        while i < len(arg_list):
            arg = arg_list[i]
            if arg == "--limit" and i + 1 < len(arg_list):
                kwargs["limit"] = int(arg_list[i + 1])
                i += 2
            elif arg == "--title-only":
                kwargs["title_only"] = True
                i += 1
            elif arg == "--content-only":
                kwargs["content_only"] = True
                i += 1
            elif arg == "--starred":
                kwargs["starred"] = True
                i += 1
            elif arg == "--pinned":
                kwargs["pinned"] = True
                i += 1
            elif arg == "--archived":
                kwargs["archived"] = True
                i += 1
            elif arg == "--include-archived":
                kwargs["include_archived"] = True
                i += 1
            elif arg == "--source" and i + 1 < len(arg_list):
                kwargs["source"] = arg_list[i + 1]
                i += 2
            elif arg == "--project" and i + 1 < len(arg_list):
                kwargs["project"] = arg_list[i + 1]
                i += 2
            elif arg == "--model" and i + 1 < len(arg_list):
                kwargs["model"] = arg_list[i + 1]
                i += 2
            elif arg == "--tags" and i + 1 < len(arg_list):
                kwargs["tags"] = arg_list[i + 1]
                i += 2
            elif arg == "--min-messages" and i + 1 < len(arg_list):
                kwargs["min_messages"] = int(arg_list[i + 1])
                i += 2
            elif arg == "--max-messages" and i + 1 < len(arg_list):
                kwargs["max_messages"] = int(arg_list[i + 1])
                i += 2
            elif arg == "--has-branches":
                kwargs["has_branches"] = True
                i += 1
            else:
                print(f"Unknown argument: {arg}")
                return

        try:
            search_conversations_helper(db=self.db, query=query, **kwargs)
            print(f"\nUse 'load <id>' to load a conversation")
        except Exception as e:
            print(f"Error searching conversations: {e}")

    def list_conversations(self, args: str = ""):
        """List recent conversations with filtering options

        Usage: /list [--limit N] [--starred] [--pinned] [--archived] [--source SOURCE] [--model MODEL] [--tags TAG1,TAG2]
        """
        if not self.db:
            print("Error: No database configured")
            return

        # Parse arguments
        import shlex

        from ctk.core.db_helpers import list_conversations_helper

        try:
            arg_list = shlex.split(args) if args else []
        except ValueError as e:
            print(f"Error parsing arguments: {e}")
            return

        # Simple argument parsing
        kwargs = {
            "limit": None,  # No limit by default - show all
            "json_output": False,
            "archived": False,
            "starred": False,
            "pinned": False,
            "include_archived": False,
            "source": None,
            "project": None,
            "model": None,
            "tags": None,
        }

        i = 0
        while i < len(arg_list):
            arg = arg_list[i]
            if arg == "--limit" and i + 1 < len(arg_list):
                kwargs["limit"] = int(arg_list[i + 1])
                i += 2
            elif arg == "--starred":
                kwargs["starred"] = True
                i += 1
            elif arg == "--pinned":
                kwargs["pinned"] = True
                i += 1
            elif arg == "--archived":
                kwargs["archived"] = True
                i += 1
            elif arg == "--include-archived":
                kwargs["include_archived"] = True
                i += 1
            elif arg == "--source" and i + 1 < len(arg_list):
                kwargs["source"] = arg_list[i + 1]
                i += 2
            elif arg == "--project" and i + 1 < len(arg_list):
                kwargs["project"] = arg_list[i + 1]
                i += 2
            elif arg == "--model" and i + 1 < len(arg_list):
                kwargs["model"] = arg_list[i + 1]
                i += 2
            elif arg == "--tags" and i + 1 < len(arg_list):
                kwargs["tags"] = arg_list[i + 1]
                i += 2
            else:
                print(f"Unknown argument: {arg}")
                return

        try:
            list_conversations_helper(db=self.db, **kwargs)
            print(f"\nUse 'load <id>' to continue a conversation")
        except Exception as e:
            print(f"Error listing conversations: {e}")

    def ask_query(self, query: str):
        """Use LLM to execute natural language database queries

        Args:
            query: Natural language query (e.g., "show starred conversations", "find discussions about AI")
        """
        if not self.db:
            print("Error: No database configured")
            return

        import json

        from ctk.core.config import get_config
        from ctk.core.tools import get_ask_tools

        # Get LLM provider config
        cfg = get_config()
        provider_name = self.provider.__class__.__name__.replace("Provider", "").lower()
        provider_config = cfg.get_provider_config(provider_name)

        # Build system prompt
        system_prompt = """You are a tool-calling assistant for CTK (Conversation Toolkit).

Your job is to:
1. Call the appropriate tool(s) based on the user's question
2. Return ONLY the exact tool output, verbatim, with no additional text

DO NOT add any introduction, explanation, or reformatting. Just output the tool results exactly as received.

CRITICAL RULES:
1. BOOLEAN FILTERS: Only include starred/pinned/archived parameters if the user EXPLICITLY mentions them.
2. QUERY PARAMETER:
   - If user mentions a topic, keyword, or "about X" or "related to X" → include query parameter
   - If user wants to list/show conversations by status only (starred/pinned/archived) → omit query parameter
   - If user wants all conversations → use empty {} (no query, no filters)

EXAMPLES:
User: "show me starred conversations"
Tool call: search_conversations({"starred": true})

User: "show me pinned and starred conversations"
Tool call: search_conversations({"starred": true, "pinned": true})

User: "list all conversations"
Tool call: search_conversations({})

User: "find conversations about python"
Tool call: search_conversations({"query": "python"})

User: "search for AI in starred conversations"
Tool call: search_conversations({"query": "AI", "starred": true})

Available operations:
- search_conversations: Search/list conversations (with optional text query and filters)
- get_conversation: Get details of a specific conversation
- get_statistics: Get database statistics"""

        # Get tools
        tools = get_ask_tools()
        formatted_tools = self.provider.format_tools_for_api(tools)

        # Build messages
        from ctk.integrations.llm.base import Message, MessageRole

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=query),
        ]

        try:
            # Call LLM
            response = self.provider.chat(
                messages, temperature=0.1, tools=formatted_tools
            )

            # Check if LLM wants to use tools
            if response.tool_calls:
                # Import execute_ask_tool from cli
                import os
                import sys

                sys.path.insert(
                    0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                )
                from cli import execute_ask_tool

                # Execute each tool call and display results
                for tool_call in response.tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args = tool_call["function"]["arguments"]
                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)

                    # Execute tool with Rich output
                    tool_result = execute_ask_tool(
                        self.db, tool_name, tool_args, debug=False, use_rich=True
                    )

                    # If there's a result string (for non-Rich output), print it
                    if tool_result:
                        print(tool_result)
            else:
                # No tool call - show LLM's text response if available
                if response.content:
                    print(response.content)
                else:
                    # Provide helpful guidance
                    print(
                        "I couldn't determine what to search for. Try asking something like:"
                    )
                    print("  - 'list all conversations'")
                    print("  - 'find conversations about python'")
                    print("  - 'show starred conversations'")
                    print("  - 'get statistics'")

        except Exception as e:
            print(f"Error executing query: {e}")
            import traceback

            traceback.print_exc()

    def show_stats(self):
        """Show conversation statistics"""
        if not self.root:
            print("No messages in current conversation")
            return

        current_path = self.get_current_path()
        all_messages = list(self.message_map.values())

        # Stats for current path
        user_count = sum(1 for m in current_path if m.role == LLMMessageRole.USER)
        assistant_count = sum(
            1 for m in current_path if m.role == LLMMessageRole.ASSISTANT
        )
        system_count = sum(1 for m in current_path if m.role == LLMMessageRole.SYSTEM)

        total_chars = sum(len(m.content) for m in current_path)
        avg_chars = total_chars // len(current_path) if current_path else 0

        # Tree stats
        total_messages = len(all_messages)
        total_branches = sum(1 for m in all_messages if len(m.children) > 1)

        print("\nConversation Statistics:")
        print("-" * 40)
        print(f"Current path: {len(current_path)} messages")
        print(f"  User: {user_count}")
        print(f"  Assistant: {assistant_count}")
        print(f"  System: {system_count}")
        print(f"\nFull tree: {total_messages} messages")
        print(f"  Branch points: {total_branches}")
        print(f"\nTotal characters (current path): {total_chars:,}")
        print(f"Average message length: {avg_chars} chars")
        if self.current_conversation_id:
            print(f"Conversation ID: {self.current_conversation_id[:8]}...")
        if self.conversation_title:
            print(f"Title: {self.conversation_title}")
        print("-" * 40)
        print()

    def list_models(self):
        """List available models from the provider"""
        try:
            models = self.provider.get_models()

            if not models:
                print("No models available")
                return

            print(f"\nAvailable models from {self.provider.name}:")
            print("=" * 60)

            for model in models:
                current = " (current)" if model.id == self.provider.model else ""
                print(f"\n  {model.name}{current}")
                print(f"    ID: {model.id}")
                if model.context_window:
                    print(f"    Context: {model.context_window:,} tokens")
                if model.metadata:
                    # Show relevant metadata
                    if "size" in model.metadata:
                        print(f"    Size: {model.metadata['size']}")
                    if "family" in model.metadata:
                        print(f"    Family: {model.metadata['family']}")
                    if "parameter_size" in model.metadata:
                        print(f"    Parameters: {model.metadata['parameter_size']}")

            print("=" * 60)
            print(f"\nUse 'model <id>' to switch models")

        except Exception as e:
            print(f"Error listing models: {e}")
            print("This provider may not support model listing")

    def show_model_info(self, model_name: str):
        """Show detailed information about a specific model"""
        try:
            # Get model info from provider
            info = self.provider.get_model_info(model_name)

            if not info:
                print(f"No information available for model: {model_name}")
                return

            print(f"\n{'=' * 60}")
            print(f"Model: {model_name}")
            print(f"{'=' * 60}\n")

            # Show runtime parameters first (num_ctx, etc.)
            if "parameters" in info:
                print("Runtime Parameters:")
                print(info["parameters"])
                print()

            # Pretty-print the model_info JSON (max capabilities)
            if "model_info" in info:
                print("Model Capabilities:")
                print(json.dumps(info["model_info"], indent=2, sort_keys=True))
            else:
                print("No detailed model information available")

            print(f"\n{'=' * 60}\n")

        except Exception as e:
            print(f"Error getting model info: {e}")
            print("This provider may not support detailed model information")

    def show_message(self, msg_num: int):
        """Show full content of a specific message in current path"""
        current_path = self.get_current_path()

        if msg_num < 1 or msg_num > len(current_path):
            print(f"Error: Message number must be between 1 and {len(current_path)}")
            return

        msg = current_path[msg_num - 1]
        role_name = {
            LLMMessageRole.USER: "You",
            LLMMessageRole.ASSISTANT: "Assistant",
            LLMMessageRole.SYSTEM: "System",
            LLMMessageRole.TOOL: "Tool",
        }.get(msg.role, str(msg.role))

        # Show metadata
        metadata_parts = []
        if msg.user:
            metadata_parts.append(f"User: {msg.user}")
        if msg.model:
            metadata_parts.append(f"Model: {msg.model}")
        if msg.children:
            metadata_parts.append(f"{len(msg.children)} branch(es)")

        metadata_str = " | ".join(metadata_parts) if metadata_parts else ""

        print(
            f"\nMessage {msg_num} ({role_name}){' - ' + metadata_str if metadata_str else ''}:"
        )
        print(f"ID: {msg.id[:8]}...")
        print("-" * 60)

        if self.render_markdown and msg.role == LLMMessageRole.ASSISTANT:
            self.console.print(Markdown(msg.content))
        else:
            print(msg.content)

        print("-" * 60)
        print()

    def rollback(self, n: int):
        """Move current position back n messages in the tree"""
        if n < 1:
            print("Error: Number must be positive")
            return

        if not self.current_message:
            print("Error: No messages to roll back")
            return

        # Move back n steps
        target = self.current_message
        for i in range(n):
            if not target.parent:
                print(f"Can only roll back {i} message(s) (reached root)")
                if i > 0:
                    self.current_message = target
                    current_path = self.get_current_path()
                    print(f"✓ Rolled back to message {len(current_path)}")
                return
            target = target.parent

        self.current_message = target
        current_path = self.get_current_path()
        print(f"✓ Rolled back {n} message(s)")
        print(f"  Current position: message {len(current_path)} of tree")
        print(f"  Next message will branch from here")

    def grep_conversation(self, pattern: str):
        """Search for pattern in current path"""
        import re

        current_path = self.get_current_path()
        if not current_path:
            print("No messages to search")
            return

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            print(f"Error: Invalid regex pattern: {e}")
            return

        matches = []
        for i, msg in enumerate(current_path):
            if regex.search(msg.content):
                matches.append((i + 1, msg))

        if not matches:
            print(f"No matches found for '{pattern}'")
            return

        print(f"\nFound {len(matches)} message(s) matching '{pattern}':")
        print("-" * 60)

        for msg_num, msg in matches:
            role_name = {
                LLMMessageRole.USER: "You",
                LLMMessageRole.ASSISTANT: "Assistant",
                LLMMessageRole.SYSTEM: "System",
                LLMMessageRole.TOOL: "Tool",
            }.get(msg.role, str(msg.role))

            # Show snippet with context
            lines = msg.content.split("\n")
            matching_lines = [line for line in lines if regex.search(line)]

            print(f"\nMessage {msg_num} ({role_name}):")
            for line in matching_lines[:3]:  # Show first 3 matching lines
                # Highlight the match
                highlighted = regex.sub(lambda m: f"**{m.group()}**", line[:100])
                print(f"  {highlighted}")
            if len(matching_lines) > 3:
                print(f"  ... and {len(matching_lines) - 3} more matches")

        print("-" * 60)
        print(f"\nUse 'show <num>' to view full message")

    def execute_shell_command(self, command: str):
        """Execute a shell command in the current working directory"""
        import shlex
        import subprocess

        if not command:
            print("Error: No command provided")
            return

        try:
            # Execute command in the current working directory
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Print stdout
            if result.stdout:
                print(result.stdout, end="")

            # Print stderr
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)

            # Print return code if non-zero
            if result.returncode != 0:
                print(f"[Exit code: {result.returncode}]")

        except subprocess.TimeoutExpired:
            print("Error: Command timed out after 30 seconds")
        except Exception as e:
            print(f"Error executing command: {e}")

    def change_directory(self, path: str):
        """Change the working directory for shell commands"""
        import os

        try:
            # Resolve path relative to current working directory
            if not os.path.isabs(path):
                new_path = os.path.join(self.cwd, path)
            else:
                new_path = path

            # Normalize and verify
            new_path = os.path.normpath(os.path.abspath(new_path))

            if not os.path.exists(new_path):
                print(f"Error: Directory does not exist: {new_path}")
                return

            if not os.path.isdir(new_path):
                print(f"Error: Not a directory: {new_path}")
                return

            self.cwd = new_path
            print(f"Changed directory to: {self.cwd}")

        except Exception as e:
            print(f"Error changing directory: {e}")

    def show_tree(self):
        """Visualize the conversation tree structure"""
        if not self.root:
            print("Error: No conversation tree to display")
            return

        def print_tree(
            msg: TreeMessage, prefix: str = "", is_last: bool = True, depth: int = 0
        ):
            """Recursively print tree structure"""
            # Determine connector (compact version)
            connector = "└─" if is_last else "├─"

            # Show message info with role emoji only
            role_emoji = {
                "system": "⚙",
                "user": "U",
                "assistant": "A",
                "tool": "T",
                "tool_result": "R",
            }
            emoji = role_emoji.get(msg.role.value, "?")

            # Very compact content preview (max 30 chars to save space)
            content_preview = msg.content[:30].replace("\n", " ").strip()
            if len(msg.content) > 30:
                content_preview += "..."

            # Show current position marker (compact)
            is_current = msg == self.current_message
            marker = " *" if is_current else ""

            # Compact metadata - only show if different from conversation default
            meta_parts = []
            if msg.model and msg.model != self.conversation_model:
                # Just show first part of model name
                short_model = msg.model.split(":")[0][:8]
                meta_parts.append(f"m:{short_model}")
            if msg.user:
                meta_parts.append(f"u:{msg.user[:8]}")
            meta_str = f" [{','.join(meta_parts)}]" if meta_parts else ""

            # Format: prefix + connector + emoji + id(short) + content + meta + marker
            print(
                f"{prefix}{connector}{emoji} {msg.id[:6]} {content_preview}{meta_str}{marker}"
            )

            # Print children
            if msg.children:
                # Update prefix for children (compact: 2 spaces instead of 4)
                extension = "  " if is_last else "│ "
                new_prefix = prefix + extension

                for i, child in enumerate(msg.children):
                    is_last_child = i == len(msg.children) - 1
                    print_tree(child, new_prefix, is_last_child, depth + 1)

        print("\nConversation Tree:")
        print("=" * 80)
        print_tree(self.root)
        print("=" * 80)
        print(f"\nTotal messages: {len(self.message_map)}")
        print(f"Current path length: {len(self.get_current_path())}")
        print(
            f"Current position: {self.current_message.id[:8] if self.current_message else 'root'}"
        )
        print(
            "\nLegend: U=user, A=assistant, ⚙=system, T=tool, R=result, *=current position"
        )

    def _build_vfs_message_path(self, conversation, target_message_id: str) -> str:
        """Build VFS message path segments for a target message in a conversation.

        Returns path like 'm1/m2/m3' for the message's position in the tree.
        """
        # Build path from root to target
        path_to_target = []
        current_id = target_message_id

        while current_id:
            msg = conversation.message_map.get(current_id)
            if not msg:
                break
            path_to_target.insert(0, msg)
            current_id = msg.parent_id

        if not path_to_target:
            return ""

        # Convert to VFS path segments (m1, m2, etc.)
        segments = []
        for i, msg in enumerate(path_to_target):
            if i == 0:
                # Root message - find its index among root messages
                try:
                    idx = conversation.root_message_ids.index(msg.id)
                except ValueError:
                    idx = 0
            else:
                # Non-root - find index among siblings
                parent_id = path_to_target[i - 1].id
                siblings = conversation.get_children(parent_id)
                try:
                    idx = next(j for j, s in enumerate(siblings) if s.id == msg.id)
                except StopIteration:
                    idx = 0
            segments.append(f"m{idx + 1}")

        return "/".join(segments)

    def goto_longest_path(self):
        """Navigate to the leaf node of the longest path"""
        from ctk.core.vfs import PathType, VFSPathParser

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [
                    PathType.CONVERSATION_ROOT,
                    PathType.MESSAGE_NODE,
                ]:
                    use_vfs = True
            except (AttributeError, ValueError, KeyError):
                pass

        # If internal tree is loaded AND we're not navigating via VFS, use internal state
        if self.root and not use_vfs:
            # Find all leaf nodes
            leaf_nodes = [msg for msg in self.message_map.values() if not msg.children]

            if not leaf_nodes:
                print("Error: No leaf nodes found")
                return

            # Find the leaf with the longest path to root
            def get_path_length(node: TreeMessage) -> int:
                length = 0
                current = node
                while current:
                    length += 1
                    current = current.parent
                return length

            longest_leaf = max(leaf_nodes, key=get_path_length)
            path_length = get_path_length(longest_leaf)

            self.current_message = longest_leaf
            print(f"✓ Moved to longest path leaf")
            print(f"  ID: {longest_leaf.id[:8]}...")
            print(f"  Path length: {path_length} messages")
            print(f"  Role: {longest_leaf.role.value}")
            print(f"  Content: {longest_leaf.content[:100]}")
            return

        # Otherwise, try to load from VFS path
        if not self.db:
            print("Error: No conversation tree loaded and no database available")
            return

        try:
            parsed = VFSPathParser.parse(self.vfs_cwd)

            if parsed.path_type not in [
                PathType.CONVERSATION_ROOT,
                PathType.MESSAGE_NODE,
            ]:
                print(f"Error: Not in a conversation directory (at {self.vfs_cwd})")
                return

            conv_id = parsed.conversation_id
            if not conv_id:
                print("Error: Could not determine conversation ID from path")
                return

            conversation = self.db.load_conversation(conv_id)
            if not conversation:
                print(f"Error: Conversation not found: {conv_id}")
                return

            # Find longest path
            paths = conversation.get_all_paths()
            if not paths:
                print("Error: No paths found in conversation")
                return

            longest_path = max(paths, key=len)
            target_msg = longest_path[-1]  # Leaf of longest path

            # Build VFS path to this message
            msg_path = self._build_vfs_message_path(conversation, target_msg.id)

            # Update VFS cwd - build base path from current location
            base_path = f"/chats/{conv_id}"
            if parsed.path_type == PathType.CONVERSATION_ROOT:
                # We're at conversation root, just append message path
                new_path = f"{self.vfs_cwd.rstrip('/')}/{msg_path}"
            else:
                # Navigate from conversation root
                new_path = f"{base_path}/{msg_path}"

            self.vfs_cwd = VFSPathParser.parse(new_path).normalized_path

            content_text = (
                target_msg.content.get_text()
                if hasattr(target_msg.content, "get_text")
                else str(
                    target_msg.content.text
                    if hasattr(target_msg.content, "text")
                    else target_msg.content
                )
            )

            print(f"✓ Moved to longest path leaf")
            print(f"  ID: {target_msg.id[:8]}...")
            print(f"  Path length: {len(longest_path)} messages")
            print(f"  Role: {target_msg.role.value if target_msg.role else 'unknown'}")
            print(f"  Content: {content_text[:100]}")
            print(f"  Path: {self.vfs_cwd}")

        except Exception as e:
            print(f"Error: {e}")

    def goto_latest_leaf(self):
        """Navigate to the most recently created leaf node"""
        from ctk.core.vfs import PathType, VFSPathParser

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [
                    PathType.CONVERSATION_ROOT,
                    PathType.MESSAGE_NODE,
                ]:
                    use_vfs = True
            except (AttributeError, ValueError, KeyError):
                pass

        # If internal tree is loaded AND we're not navigating via VFS, use internal state
        if self.root and not use_vfs:
            # Find all leaf nodes
            leaf_nodes = [msg for msg in self.message_map.values() if not msg.children]

            if not leaf_nodes:
                print("Error: No leaf nodes found")
                return

            # Find the leaf with the most recent timestamp
            latest_leaf = max(leaf_nodes, key=lambda msg: msg.timestamp)

            self.current_message = latest_leaf
            print(f"✓ Moved to most recent leaf")
            print(f"  ID: {latest_leaf.id[:8]}...")
            print(f"  Timestamp: {latest_leaf.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Role: {latest_leaf.role.value}")
            print(f"  Content: {latest_leaf.content[:100]}")
            return

        # Otherwise, try to load from VFS path
        if not self.db:
            print("Error: No conversation tree loaded and no database available")
            return

        try:
            parsed = VFSPathParser.parse(self.vfs_cwd)

            if parsed.path_type not in [
                PathType.CONVERSATION_ROOT,
                PathType.MESSAGE_NODE,
            ]:
                print(f"Error: Not in a conversation directory (at {self.vfs_cwd})")
                return

            conv_id = parsed.conversation_id
            if not conv_id:
                print("Error: Could not determine conversation ID from path")
                return

            conversation = self.db.load_conversation(conv_id)
            if not conversation:
                print(f"Error: Conversation not found: {conv_id}")
                return

            # Find all leaf nodes (messages with no children)
            leaf_msgs = []
            for msg in conversation.message_map.values():
                children = conversation.get_children(msg.id)
                if not children:
                    leaf_msgs.append(msg)

            if not leaf_msgs:
                print("Error: No leaf nodes found")
                return

            # Find the one with the most recent timestamp
            latest_msg = max(leaf_msgs, key=lambda m: m.timestamp or datetime.min)

            # Build VFS path to this message
            msg_path = self._build_vfs_message_path(conversation, latest_msg.id)

            # Update VFS cwd
            base_path = f"/chats/{conv_id}"
            if parsed.path_type == PathType.CONVERSATION_ROOT:
                new_path = f"{self.vfs_cwd.rstrip('/')}/{msg_path}"
            else:
                new_path = f"{base_path}/{msg_path}"

            self.vfs_cwd = VFSPathParser.parse(new_path).normalized_path

            content_text = (
                latest_msg.content.get_text()
                if hasattr(latest_msg.content, "get_text")
                else str(
                    latest_msg.content.text
                    if hasattr(latest_msg.content, "text")
                    else latest_msg.content
                )
            )
            timestamp_str = (
                latest_msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                if latest_msg.timestamp
                else "unknown"
            )

            print(f"✓ Moved to most recent leaf")
            print(f"  ID: {latest_msg.id[:8]}...")
            print(f"  Timestamp: {timestamp_str}")
            print(f"  Role: {latest_msg.role.value if latest_msg.role else 'unknown'}")
            print(f"  Content: {content_text[:100]}")
            print(f"  Path: {self.vfs_cwd}")

        except Exception as e:
            print(f"Error: {e}")

    def show_current_position(self):
        """Show information about current position in tree"""
        from ctk.core.vfs import PathType, VFSPathParser

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [
                    PathType.CONVERSATION_ROOT,
                    PathType.MESSAGE_NODE,
                ]:
                    use_vfs = True
            except (AttributeError, ValueError, KeyError):
                pass

        # If internal tree is loaded AND we're not navigating via VFS, use internal state
        if self.root and self.current_message and not use_vfs:
            current_path = self.get_current_path()
            position = len(current_path) - 1

            print(f"\nCurrent Position:")
            print("=" * 80)
            print(f"Message ID: {self.current_message.id[:8]}...")
            print(f"Position in path: #{position} / {len(current_path) - 1}")
            print(f"Role: {self.current_message.role.value}")
            if self.current_message.model:
                print(f"Model: {self.current_message.model}")
            if self.current_message.user:
                print(f"User: {self.current_message.user}")
            print(f"Timestamp: {self.current_message.timestamp}")
            print(f"\nContent:")
            print("-" * 80)
            print(self.current_message.content[:500])
            if len(self.current_message.content) > 500:
                print("...")
            print("-" * 80)

            # Show tree context
            if self.current_message.parent:
                print(
                    f"\nParent: {self.current_message.parent.id[:8]}... ({self.current_message.parent.role.value})"
                )
            else:
                print("\nParent: None (root message)")

            if self.current_message.children:
                print(f"Children: {len(self.current_message.children)}")
                for i, child in enumerate(self.current_message.children):
                    print(f"  [{i}] {child.id[:8]}... ({child.role.value})")
            else:
                print("Children: None (leaf node)")

            print("=" * 80)
            return

        # Otherwise, try to load from VFS path
        if not self.db:
            print("Error: No conversation tree loaded and no database available")
            return

        try:
            parsed = VFSPathParser.parse(self.vfs_cwd)

            if parsed.path_type not in [
                PathType.CONVERSATION_ROOT,
                PathType.MESSAGE_NODE,
            ]:
                print(f"Error: Not in a conversation directory (at {self.vfs_cwd})")
                return

            conv_id = parsed.conversation_id
            if not conv_id:
                print("Error: Could not determine conversation ID from path")
                return

            # Load conversation from database
            conversation = self.db.load_conversation(conv_id)
            if not conversation:
                print(f"Error: Conversation not found: {conv_id}")
                return

            print(f"\nCurrent Position (VFS):")
            print("=" * 80)
            print(f"Path: {self.vfs_cwd}")
            print(f"Conversation ID: {conv_id}")
            print(f"Title: {conversation.title or '(untitled)'}")
            print(f"Total messages: {len(conversation.message_map)}")
            print(f"Total paths: {len(conversation.get_all_paths())}")

            # If at a message node, show message info
            if parsed.path_type == PathType.MESSAGE_NODE and parsed.message_path:
                # Navigate to the message
                msg_path = parsed.message_path  # e.g., ['m1', 'm2']
                # Start from root messages
                current_messages = [
                    conversation.message_map.get(rid)
                    for rid in conversation.root_message_ids
                ]
                current_messages = [m for m in current_messages if m]

                target_message = None
                for i, segment in enumerate(msg_path):
                    # Extract message index from segment (m1 -> 1, m10 -> 10)
                    msg_idx = int(segment[1:]) - 1  # m1 is index 0
                    if 0 <= msg_idx < len(current_messages):
                        target_message = current_messages[msg_idx]
                        if i < len(msg_path) - 1:
                            # Get children for next iteration
                            children = conversation.get_children(target_message.id)
                            current_messages = children
                    else:
                        break

                if target_message:
                    print(f"\nMessage:")
                    print("-" * 80)
                    print(f"Message ID: {target_message.id[:8]}...")
                    print(
                        f"Role: {target_message.role.value if target_message.role else 'unknown'}"
                    )
                    # Message class stores model in metadata, not as direct attribute
                    model = getattr(target_message, "model", None) or (
                        target_message.metadata.get("model")
                        if hasattr(target_message, "metadata")
                        and target_message.metadata
                        else None
                    )
                    if model:
                        print(f"Model: {model}")
                    print(f"Timestamp: {target_message.timestamp}")
                    content_text = (
                        target_message.content.get_text()
                        if hasattr(target_message.content, "get_text")
                        else str(
                            target_message.content.text
                            if hasattr(target_message.content, "text")
                            else target_message.content
                        )
                    )
                    print(f"\nContent:")
                    print(content_text[:500])
                    if len(content_text) > 500:
                        print("...")
                    print("-" * 80)

                    # Show children
                    children = conversation.get_children(target_message.id)
                    if children:
                        print(f"\nChildren: {len(children)}")
                        for i, child in enumerate(children):
                            print(
                                f"  [m{i+1}] {child.id[:8]}... ({child.role.value if child.role else 'unknown'})"
                            )
                    else:
                        print("\nChildren: None (leaf node)")
            else:
                # At conversation root, show root messages
                print(f"\nRoot messages: {len(conversation.root_message_ids)}")
                for i, rid in enumerate(conversation.root_message_ids):
                    msg = conversation.message_map.get(rid)
                    if msg:
                        content_text = (
                            msg.content.get_text()
                            if hasattr(msg.content, "get_text")
                            else str(
                                msg.content.text
                                if hasattr(msg.content, "text")
                                else msg.content
                            )
                        )
                        preview = (
                            content_text[:50].replace("\n", " ").strip()
                            if content_text
                            else ""
                        )
                        if len(content_text) > 50:
                            preview += "..."
                        print(
                            f"  [m{i+1}] {msg.id[:8]}... ({msg.role.value if msg.role else 'unknown'}): {preview}"
                        )

            print("=" * 80)

        except Exception as e:
            print(f"Error: {e}")

    def show_all_paths(self):
        """Show all complete paths through the conversation tree"""
        if not self.root:
            print("Error: No conversation tree")
            return

        def get_all_leaf_paths(
            node: TreeMessage, current_path: List[TreeMessage]
        ) -> List[List[TreeMessage]]:
            """Recursively find all paths to leaf nodes"""
            current_path = current_path + [node]

            if not node.children:
                # Leaf node - return this path
                return [current_path]

            # Recurse into children
            all_paths = []
            for child in node.children:
                all_paths.extend(get_all_leaf_paths(child, current_path))

            return all_paths

        paths = get_all_leaf_paths(self.root, [])

        print(f"\nAll Paths ({len(paths)} total):")
        print("=" * 80)

        current_path = self.get_current_path()
        current_leaf = current_path[-1] if current_path else None

        for i, path in enumerate(paths):
            is_current = path[-1] == current_leaf
            marker = " 👈 CURRENT" if is_current else ""

            print(f"\nPath {i+1}: {len(path)} messages{marker}")
            print("-" * 80)

            for j, msg in enumerate(path):
                role_emoji = {
                    "system": "⚙️",
                    "user": "👤",
                    "assistant": "🤖",
                    "tool": "🔧",
                    "tool_result": "📊",
                }
                emoji = role_emoji.get(msg.role.value, "❓")
                content_preview = msg.content[:40].replace("\n", " ")
                if len(msg.content) > 40:
                    content_preview += "..."

                print(f"  [{j}] {emoji} {msg.id[:8]}... {content_preview}")

        print("=" * 80)

    def show_alternatives(self):
        """Show alternative branches at current position"""
        from ctk.core.vfs import PathType, VFSPathParser

        # Helper to count descendants in a conversation tree
        def count_descendants_in_conv(conversation, msg_id: str) -> int:
            children = conversation.get_children(msg_id)
            count = len(children)
            for child in children:
                count += count_descendants_in_conv(conversation, child.id)
            return count

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        # This handles the case where self.current_message is stale
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [
                    PathType.CONVERSATION_ROOT,
                    PathType.MESSAGE_NODE,
                ]:
                    use_vfs = True
            except (AttributeError, ValueError, KeyError):
                pass

        # If internal tree is loaded AND we're not navigating via VFS, use internal state
        if self.current_message and not use_vfs:
            if not self.current_message.children:
                print("No alternative branches - this is a leaf node")
                print("Next message you send will create the first child")
                return

            print(f"\nAlternative branches from current message:")
            print("=" * 80)
            print(f"Current message: {self.current_message.id[:8]}...")
            print(f"Role: {self.current_message.role.value}")
            print(f"Content: {self.current_message.content[:60]}")
            print()

            # Show all children as alternatives
            for i, child in enumerate(self.current_message.children):
                role_emoji = {
                    "system": "⚙️",
                    "user": "👤",
                    "assistant": "🤖",
                    "tool": "🔧",
                    "tool_result": "📊",
                }
                emoji = role_emoji.get(child.role.value, "❓")

                content_preview = child.content[:60].replace("\n", " ")
                if len(child.content) > 60:
                    content_preview += "..."

                meta = []
                if child.model:
                    meta.append(f"model:{child.model}")
                if child.user:
                    meta.append(f"user:{child.user}")
                meta_str = f" [{', '.join(meta)}]" if meta else ""

                # Count descendants
                def count_descendants(node: TreeMessage) -> int:
                    count = len(node.children)
                    for c in node.children:
                        count += count_descendants(c)
                    return count

                descendants = count_descendants(child)

                print(f"[{i}] {emoji} {child.id[:8]}...{meta_str}")
                print(f"    {content_preview}")
                print(f"    Descendants: {descendants}")
                print()

            print("=" * 80)
            print(f"Use 'fork-id {child.id[:8]}' to fork from alternative branch")
            print("Or send a new message to create another alternative")
            return

        # Otherwise, try to load from VFS path
        if not self.db:
            print("Error: Not at a message position and no database available")
            return

        try:
            parsed = VFSPathParser.parse(self.vfs_cwd)

            if parsed.path_type != PathType.MESSAGE_NODE or not parsed.message_path:
                print("Error: Not at a message position (navigate to a message first)")
                return

            conv_id = parsed.conversation_id
            if not conv_id:
                print("Error: Could not determine conversation ID from path")
                return

            conversation = self.db.load_conversation(conv_id)
            if not conversation:
                print(f"Error: Conversation not found: {conv_id}")
                return

            # Navigate to the current message
            msg_path = parsed.message_path
            current_messages = [
                conversation.message_map.get(rid)
                for rid in conversation.root_message_ids
            ]
            current_messages = [m for m in current_messages if m]

            target_message = None
            for i, segment in enumerate(msg_path):
                msg_idx = int(segment[1:]) - 1
                if 0 <= msg_idx < len(current_messages):
                    target_message = current_messages[msg_idx]
                    if i < len(msg_path) - 1:
                        current_messages = conversation.get_children(target_message.id)
                else:
                    break

            if not target_message:
                print("Error: Could not find message at current path")
                return

            # Get children of the current message
            children = conversation.get_children(target_message.id)

            if not children:
                print("No alternative branches - this is a leaf node")
                print("Use 'chat' command to start a conversation and add messages")
                return

            content_text = (
                target_message.content.get_text()
                if hasattr(target_message.content, "get_text")
                else str(
                    target_message.content.text
                    if hasattr(target_message.content, "text")
                    else target_message.content
                )
            )

            print(f"\nAlternative branches from current message:")
            print("=" * 80)
            print(f"Current message: {target_message.id[:8]}...")
            print(
                f"Role: {target_message.role.value if target_message.role else 'unknown'}"
            )
            print(f"Content: {content_text[:60]}")
            print()

            # Show all children as alternatives
            for i, child in enumerate(children):
                role = child.role.value if child.role else "unknown"
                role_emoji = {
                    "system": "⚙️",
                    "user": "👤",
                    "assistant": "🤖",
                    "tool": "🔧",
                    "tool_result": "📊",
                }
                emoji = role_emoji.get(role, "❓")

                child_content = (
                    child.content.get_text()
                    if hasattr(child.content, "get_text")
                    else str(
                        child.content.text
                        if hasattr(child.content, "text")
                        else child.content
                    )
                )
                content_preview = child_content[:60].replace("\n", " ")
                if len(child_content) > 60:
                    content_preview += "..."

                meta = []
                # Message class doesn't have model directly, check metadata
                model = (
                    getattr(child, "model", None) or child.metadata.get("model")
                    if hasattr(child, "metadata")
                    else None
                )
                if model:
                    meta.append(f"model:{model}")
                meta_str = f" [{', '.join(meta)}]" if meta else ""

                descendants = count_descendants_in_conv(conversation, child.id)

                print(f"[m{i+1}] {emoji} {child.id[:8]}...{meta_str}")
                print(f"    {content_preview}")
                print(f"    Descendants: {descendants}")
                print()

            print("=" * 80)
            print(f"Use 'cd m<N>' to navigate to an alternative branch")

        except Exception as e:
            print(f"Error: {e}")

    def show_conversation_history(self, max_content_length: Optional[int] = None):
        """
        Show conversation history of current path.

        Args:
            max_content_length: Max characters to show per message (None = show all)
        """
        current_path = self.get_current_path()

        self.console.print()

        for i, msg in enumerate(current_path):
            # Determine role name and color
            if msg.role == LLMMessageRole.USER:
                role_name = msg.user if msg.user else "You"
                role_display = (
                    f"[dim]\\[{i}][/dim] [bold green]{role_name}:[/bold green]"
                )
            elif msg.role == LLMMessageRole.ASSISTANT:
                role_name = msg.model if msg.model else "Assistant"
                role_display = (
                    f"[dim]\\[{i}][/dim] [bold magenta]{role_name}:[/bold magenta]"
                )
            elif msg.role == LLMMessageRole.SYSTEM:
                role_display = f"[dim]\\[{i}][/dim] [bold yellow]System:[/bold yellow]"
            else:
                role_display = f"[dim]\\[{i}][/dim] {msg.role.value}:"

            # Show header
            self.console.print(role_display)

            # Show content (truncated or full)
            content = msg.content
            if max_content_length is not None and len(content) > max_content_length:
                content = content[:max_content_length].replace("\n", " ") + "..."

            if (
                self.render_markdown
                and msg.role == LLMMessageRole.ASSISTANT
                and max_content_length is None
            ):
                # Only use markdown for full content
                from rich.markdown import Markdown

                self.console.print(Markdown(msg.content))
            else:
                self.console.print(content)

            self.console.print()  # Blank line between messages

    def show_history(self, max_content_length: Optional[int] = None):
        """Show message history of current path

        Args:
            max_content_length: Max chars per message (None = show all)
        """
        from ctk.core.vfs import PathType, VFSPathParser

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [
                    PathType.CONVERSATION_ROOT,
                    PathType.MESSAGE_NODE,
                ]:
                    use_vfs = True
            except (AttributeError, ValueError, KeyError):
                pass

        # If internal tree is loaded AND we're not navigating via VFS, use internal state
        if self.root and not use_vfs:
            self.show_conversation_history(max_content_length=max_content_length)
            return

        # Otherwise, try to load from VFS path
        if not self.db:
            self.print_error("No conversation tree loaded and no database available")
            return

        try:
            parsed = VFSPathParser.parse(self.vfs_cwd)

            if parsed.path_type not in [
                PathType.CONVERSATION_ROOT,
                PathType.MESSAGE_NODE,
            ]:
                self.print_error(f"Not in a conversation directory (at {self.vfs_cwd})")
                return

            conv_id = parsed.conversation_id
            if not conv_id:
                self.print_error("Could not determine conversation ID from path")
                return

            conversation = self.db.load_conversation(conv_id)
            if not conversation:
                self.print_error(f"Conversation not found: {conv_id}")
                return

            # Get the path to show
            if parsed.path_type == PathType.MESSAGE_NODE and parsed.message_path:
                # Navigate to specific message and show path to it
                msg_path = parsed.message_path
                current_messages = [
                    conversation.message_map.get(rid)
                    for rid in conversation.root_message_ids
                ]
                current_messages = [m for m in current_messages if m]

                path_messages = []
                for i, segment in enumerate(msg_path):
                    msg_idx = int(segment[1:]) - 1
                    if 0 <= msg_idx < len(current_messages):
                        target = current_messages[msg_idx]
                        path_messages.append(target)
                        if i < len(msg_path) - 1:
                            current_messages = conversation.get_children(target.id)
                    else:
                        break
            else:
                # At conversation root - show longest path
                paths = conversation.get_all_paths()
                path_messages = max(paths, key=len) if paths else []

            if not path_messages:
                self.print_error("No messages found")
                return

            # Display history
            self.console.print()
            for i, msg in enumerate(path_messages):
                role = msg.role.value if msg.role else "unknown"

                if role == "user":
                    role_display = f"[dim]\\[{i}][/dim] [bold green]You:[/bold green]"
                elif role == "assistant":
                    # Message class stores model in metadata, not as direct attribute
                    model_name = (
                        getattr(msg, "model", None)
                        or (
                            msg.metadata.get("model")
                            if hasattr(msg, "metadata") and msg.metadata
                            else None
                        )
                        or "Assistant"
                    )
                    role_display = (
                        f"[dim]\\[{i}][/dim] [bold magenta]{model_name}:[/bold magenta]"
                    )
                elif role == "system":
                    role_display = (
                        f"[dim]\\[{i}][/dim] [bold yellow]System:[/bold yellow]"
                    )
                else:
                    role_display = f"[dim]\\[{i}][/dim] {role}:"

                self.console.print(role_display)

                content_text = (
                    msg.content.get_text()
                    if hasattr(msg.content, "get_text")
                    else str(
                        msg.content.text
                        if hasattr(msg.content, "text")
                        else msg.content
                    )
                )

                if (
                    max_content_length is not None
                    and len(content_text) > max_content_length
                ):
                    content_text = (
                        content_text[:max_content_length].replace("\n", " ") + "..."
                    )

                if (
                    self.render_markdown
                    and role == "assistant"
                    and max_content_length is None
                ):
                    from rich.markdown import Markdown

                    self.console.print(Markdown(content_text))
                else:
                    self.console.print(content_text)

                self.console.print()

        except Exception as e:
            self.print_error(str(e))

    def export_conversation(self, fmt: str, filename: Optional[str] = None):
        """Export current conversation to a file"""
        if not self.root:
            print("Error: No messages to export")
            return

        # Convert tree to ConversationTree using helper
        tree = self.tree_to_conversation_tree()

        # Generate filename if not provided
        if not filename:
            safe_title = "".join(
                c for c in tree.title[:30] if c.isalnum() or c in (" ", "-", "_")
            ).strip()
            safe_title = safe_title.replace(" ", "_")
            filename = f"{safe_title}.{fmt}"

        # Export using appropriate exporter
        try:
            if fmt == "markdown":
                from ctk.integrations.exporters.markdown import \
                    MarkdownExporter

                exporter = MarkdownExporter()
                exporter.export_conversations([tree], output_file=filename)
            elif fmt == "json":
                from ctk.integrations.exporters.json import JSONExporter

                exporter = JSONExporter()
                exporter.export_conversations(
                    [tree], output_file=filename, format="ctk"
                )
            elif fmt == "jsonl":
                from ctk.integrations.exporters.jsonl import JSONLExporter

                exporter = JSONLExporter()
                exporter.export_conversations([tree], output_file=filename)
            elif fmt == "html":
                from ctk.integrations.exporters.html import HTMLExporter

                exporter = HTMLExporter()
                exporter.export_conversations([tree], output_path=filename)
            else:
                print(
                    f"Error: Unknown format '{fmt}'. Available: markdown, json, jsonl, html"
                )
                return

            print(f"✓ Exported conversation to {filename}")

        except Exception as e:
            print(f"Error exporting conversation: {e}")

    def regenerate_last_response(self):
        """Regenerate the last assistant response (creates a branch)"""
        if not self.current_message:
            print("Error: No messages to regenerate")
            return

        if self.current_message.role != LLMMessageRole.ASSISTANT:
            print("Error: Current message is not from assistant")
            return

        # Move back to parent (the user message)
        if not self.current_message.parent:
            print("Error: Cannot regenerate root message")
            return

        parent_msg = self.current_message.parent
        if parent_msg.role != LLMMessageRole.USER:
            print("Error: Parent is not a user message")
            return

        # Move current position to parent
        self.current_message = parent_msg

        print("Regenerating response (will create alternative branch)...")
        print()

        # Generate new response - this will create a sibling to the old assistant message
        self.chat(parent_msg.content)

        # Remove duplicate user message that chat() added
        if self.current_message and self.current_message.parent:
            # Find and remove the duplicate user message
            for child in self.current_message.parent.children[:]:
                if (
                    child.role == LLMMessageRole.USER
                    and child.content == parent_msg.content
                    and child != parent_msg
                ):
                    self.current_message.parent.children.remove(child)
                    del self.message_map[child.id]
                    break

    def retry_last_message(self, temp: Optional[float] = None):
        """Retry the last message with optional temperature override (creates branch)"""
        if not self.current_message:
            print("Error: No messages to retry")
            return

        # Should be at an assistant message
        if self.current_message.role != LLMMessageRole.ASSISTANT:
            print("Error: Current message is not from assistant")
            return

        # Get parent user message
        if (
            not self.current_message.parent
            or self.current_message.parent.role != LLMMessageRole.USER
        ):
            print("Error: Cannot find user message to retry")
            return

        user_msg = self.current_message.parent

        # Save original temperature
        orig_temp = self.temperature
        if temp is not None:
            self.temperature = temp
            print(
                f"Retrying with temperature {temp} (will create alternative branch)..."
            )
        else:
            print("Retrying last message (will create alternative branch)...")
        print()

        # Move to user message and regenerate
        self.current_message = user_msg
        self.chat(user_msg.content)

        # Remove duplicate user message
        if self.current_message and self.current_message.parent:
            for child in self.current_message.parent.children[:]:
                if (
                    child.role == LLMMessageRole.USER
                    and child.content == user_msg.content
                    and child != user_msg
                ):
                    self.current_message.parent.children.remove(child)
                    del self.message_map[child.id]
                    break

        # Restore original temperature
        if temp is not None:
            self.temperature = orig_temp

    def request_summary(self):
        """Ask the LLM to summarize the conversation so far"""
        if not self.root:
            print("Error: No conversation to summarize")
            return

        # Create a temporary system message asking for summary
        summary_prompt = "Please provide a concise summary of our conversation so far, highlighting the main topics and key points discussed."

        print("Requesting conversation summary...")
        print()

        # Send the summary request
        self.chat(summary_prompt)

    def merge_conversation(self, conv_id: str, insert_at: Optional[int] = None):
        """
        Merge another conversation into the current one

        Args:
            conv_id: ID of conversation to merge
            insert_at: Message number to insert after (None = append at end)
        """
        if not self.db:
            print("Error: No database configured")
            return

        try:
            # Try loading with the provided ID first (only if it looks like a full UUID)
            tree = None
            if len(conv_id) == 36:
                tree = self.db.load_conversation(conv_id)

            # If not found or ID is partial, use DB-level prefix resolution
            if not tree:
                resolved_id = self.db.resolve_conversation(conv_id)
                if not resolved_id:
                    print(f"Error: No conversation found matching '{conv_id}' (or ID is ambiguous)")
                    return
                tree = self.db.load_conversation(resolved_id)

            if not tree:
                print(f"Error: Conversation {conv_id} not found")
                return

            # Get messages from other conversation
            db_messages = tree.get_longest_path()
            if not db_messages and tree.message_map:
                db_messages = sorted(
                    tree.message_map.values(), key=lambda m: m.timestamp or datetime.min
                )

            # Determine insertion point
            if insert_at is not None:
                current_path = self.get_current_path()
                if insert_at < 0 or insert_at >= len(current_path):
                    print(f"Error: Message number must be 0-{len(current_path)-1}")
                    return

                # Save current position and move to insertion point
                saved_position = self.current_message
                self.current_message = current_path[insert_at]
                print(f"Inserting after message {insert_at}")
            else:
                saved_position = None
                print(f"Appending at end")

            # Add context marker
            self.add_message(
                LLMMessageRole.SYSTEM, f"[Context from conversation: {tree.title}]"
            )

            # Add messages from other conversation
            for db_msg in db_messages:
                self.add_message(
                    LLMMessageRole(db_msg.role.value), db_msg.content.text or ""
                )

            # Add closing context marker
            self.add_message(
                LLMMessageRole.SYSTEM, f"[End of context from: {tree.title}]"
            )

            current_path = self.get_current_path()
            print(f"✓ Merged {len(db_messages)} messages from: {tree.title}")
            print(f"  Current path now: {len(current_path)} messages")

        except Exception as e:
            print(f"Error merging conversation: {e}")

    def branch_conversation(self):
        """Save current conversation and start a new one with same history"""
        if not self.db:
            print("Error: No database configured")
            return

        if not self.root:
            print("Error: No messages to branch from")
            return

        # Save current conversation
        print("Saving current conversation...")
        self.save_conversation()

        # Create new conversation ID but keep tree structure
        old_id = self.current_conversation_id
        self.current_conversation_id = str(uuid.uuid4())
        old_title = self.conversation_title
        self.conversation_title = (
            f"Branch from: {old_title}" if old_title else f"Branch from {old_id[:8]}..."
        )

        current_path = self.get_current_path()
        print(f"✓ Created branch: {self.conversation_title}")
        print(f"  Old ID: {old_id[:8] if old_id else 'none'}...")
        print(f"  New ID: {self.current_conversation_id[:8]}...")
        print(f"  Current path preserved: {len(current_path)} messages")
        print(f"  Full tree preserved: {len(self.message_map)} messages")

    def fork_conversation(self, msg_num: int):
        """Fork conversation from a specific message number in current path (saves as new conversation)"""
        current_path = self.get_current_path()

        if msg_num < 0 or msg_num >= len(current_path):
            print(f"Error: Message number must be 0-{len(current_path)-1}")
            return

        # Save current conversation if it has an ID
        if self.current_conversation_id and self.db:
            print("Saving current conversation...")
            self.save_conversation()

        # Move current position to the specified message
        target_msg = current_path[msg_num]
        self.current_message = target_msg

        # Create new conversation ID
        old_id = self.current_conversation_id
        self.current_conversation_id = str(uuid.uuid4())
        old_title = self.conversation_title
        self.conversation_title = (
            f"Fork at msg {msg_num}: {old_title}"
            if old_title
            else f"Fork from {old_id[:8] if old_id else 'conversation'}..."
        )

        new_path = self.get_current_path()
        print(f"✓ Forked conversation at message {msg_num}")
        print(f"  New ID: {self.current_conversation_id[:8]}...")
        print(f"  Messages in new path: {len(new_path)}")
        print(f"  (Full tree preserved: {len(self.message_map)} messages)")

    def fork_conversation_by_id(self, target_id: str):
        """Fork conversation from a message by ID (full or partial)"""
        if not self.root:
            print("Error: No conversation tree")
            return

        # Find message by ID (full or partial)
        matches = [
            (msg_id, msg)
            for msg_id, msg in self.message_map.items()
            if msg_id.startswith(target_id)
        ]

        if len(matches) == 0:
            print(f"Error: No message found with ID starting with '{target_id}'")
            return
        elif len(matches) > 1:
            print(f"Error: Multiple messages match '{target_id}':")
            for msg_id, msg in matches[:5]:
                print(f"  - {msg_id[:8]}... ({msg.role.value})")
            print("Please provide more characters to uniquely identify the message")
            return

        # Exactly one match
        msg_id, target_msg = matches[0]

        # Save current conversation if it has an ID
        if self.current_conversation_id and self.db:
            print("Saving current conversation...")
            self.save_conversation()

        # Move current position to the specified message
        self.current_message = target_msg

        # Create new conversation ID
        old_id = self.current_conversation_id
        self.current_conversation_id = str(uuid.uuid4())
        old_title = self.conversation_title
        self.conversation_title = (
            f"Fork at {msg_id[:8]}: {old_title}"
            if old_title
            else f"Fork from {old_id[:8] if old_id else 'conversation'}..."
        )

        new_path = self.get_current_path()
        print(f"✓ Forked conversation at message {msg_id[:8]}...")
        print(f"  New ID: {self.current_conversation_id[:8]}...")
        print(f"  Messages in new path: {len(new_path)}")
        print(f"  (Full tree preserved: {len(self.message_map)} messages)")

    def load_file_context(self, filepath: str):
        """Load file content into conversation context"""
        import os

        if not os.path.exists(filepath):
            print(f"Error: File not found: {filepath}")
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Add file as system message
            self.add_message(
                LLMMessageRole.SYSTEM,
                f"[File: {filepath}]\n\n{content}\n\n[End of file: {filepath}]",
            )

            lines = len(content.split("\n"))
            chars = len(content)
            print(f"✓ Loaded file: {filepath}")
            print(f"  Lines: {lines}, Characters: {chars:,}")

        except Exception as e:
            print(f"Error loading file: {e}")

    def chat(self, user_message: str):
        """
        Send a message and get response.

        Adds user message and gets AI response.
        Supports automatic tool calling if enabled.
        When no conversation is loaded, uses CTK-aware system prompt with tools.

        Args:
            user_message: User's message
        """
        # Check if we're in "standalone" mode (no conversation loaded from VFS)
        # Note: We track this separately from current_conversation_id since auto-save
        # sets that, but we still want tools to work for new conversations
        standalone_mode = (
            not hasattr(self, "_loaded_from_vfs") or not self._loaded_from_vfs
        )

        # Inject CTK system prompt if standalone and no system prompt yet
        if standalone_mode and self.db:
            current_path = self.get_current_path()
            has_system_prompt = any(
                msg.role == LLMMessageRole.SYSTEM for msg in current_path
            )
            if not has_system_prompt:
                # Choose prompt based on whether tools are available
                if self.tools_disabled:
                    from ctk.core.prompts import get_ctk_system_prompt_no_tools

                    ctk_prompt = get_ctk_system_prompt_no_tools(self.db, self.vfs_cwd)
                else:
                    from ctk.core.prompts import get_ctk_system_prompt

                    ctk_prompt = get_ctk_system_prompt(self.db, self.vfs_cwd)
                # Insert system message at the root
                system_msg = TreeMessage(
                    role=LLMMessageRole.SYSTEM, content=ctk_prompt, parent=None
                )
                self.message_map[system_msg.id] = system_msg
                # Make current root a child of system message
                if self.root:
                    self.root.parent = system_msg
                    system_msg.children.append(self.root)
                self.root = system_msg
                # Set current_message so subsequent messages link to system prompt
                if self.current_message is None:
                    self.current_message = system_msg

        # Add user message
        self.add_message(LLMMessageRole.USER, user_message)

        try:
            # Tool calling loop - continue until no more tool calls
            max_iterations = 10  # Prevent infinite loops
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                # Prepare kwargs for LLM call
                kwargs = {}

                # Add num_ctx if set
                if self.num_ctx:
                    kwargs["num_ctx"] = self.num_ctx

                # Add CTK tools if in standalone mode, provider supports it, AND tools not disabled
                ctk_tools_enabled = (
                    standalone_mode
                    and self.provider.supports_tool_calling()
                    and not self.tools_disabled
                )
                if ctk_tools_enabled:
                    from ctk.core.tools import get_ask_tools

                    ctk_tools = get_ask_tools()
                    kwargs["tools"] = self.provider.format_tools_for_api(ctk_tools)

                # Add MCP tools if auto-tools enabled and provider supports it
                if self.mcp_auto_tools and self.provider.supports_tool_calling():
                    tool_dicts = self.mcp_client.get_tools_as_dicts()
                    if tool_dicts:
                        kwargs["tools"] = self.provider.format_tools_for_api(tool_dicts)

                        # Add system prompt for tool usage guidance if not already present
                        current_path = self.get_current_path()
                        has_system_prompt = any(
                            msg.role == LLMMessageRole.SYSTEM for msg in current_path
                        )
                        if not has_system_prompt:
                            tool_guidance = (
                                "You have access to tools for specific tasks. "
                                "Only use tools when the user explicitly requests a task that requires them. "
                                "For casual conversation, greetings, questions, or general discussion, respond directly without using tools. "
                                "Use tools for: code execution, data analysis, file operations, or other programmatic tasks."
                            )
                            # Insert system message at the root
                            system_msg = TreeMessage(
                                role=LLMMessageRole.SYSTEM,
                                content=tool_guidance,
                                parent=None,
                            )
                            self.message_map[system_msg.id] = system_msg
                            # Make current root a child of system message
                            if self.root:
                                self.root.parent = system_msg
                                system_msg.children.append(self.root)
                            self.root = system_msg

                response_text = ""

                if self.streaming and not kwargs.get("tools"):
                    # Token-by-token streaming (only when not using tools)
                    # Show model name on same line before streaming starts
                    self.console.print(
                        f"[bold magenta]{self.provider.model}:[/bold magenta] ", end=""
                    )

                    for chunk in self.provider.stream_chat(
                        self.get_messages_for_llm(),
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        **kwargs,
                    ):
                        print(chunk, end="", flush=True)
                        response_text += chunk
                    print()  # Final newline

                    # Add assistant response to tree
                    assistant_msg = self.add_message(
                        LLMMessageRole.ASSISTANT, response_text
                    )

                    break  # Done

                else:
                    # Non-streaming or tool-enabled: use chat() method
                    # Show spinner during generation
                    if kwargs.get("tools"):
                        status_msg = "Generating response (tools available)..."
                    else:
                        status_msg = "Generating response..."

                    # Print without newline so we can overwrite it
                    print(f"\r{status_msg} ⏳", end="", flush=True)

                    # Debug: show messages being sent (set CTK_DEBUG=1 to enable)
                    import os

                    if os.environ.get("CTK_DEBUG"):
                        msgs = self.get_messages_for_llm()
                        print(f"\n[DEBUG] Sending {len(msgs)} messages:")
                        for i, m in enumerate(msgs):
                            content_preview = (
                                m.content[:100] + "..."
                                if len(m.content) > 100
                                else m.content
                            )
                            print(f"  [{i}] {m.role}: {content_preview}")
                        print()

                    try:
                        response = self.provider.chat(
                            self.get_messages_for_llm(),
                            temperature=self.temperature,
                            max_tokens=self.max_tokens,
                            **kwargs,
                        )
                    except Exception as e:
                        # Auto-detect: if tools caused a 400 error, disable and retry
                        if (
                            "400" in str(e)
                            and kwargs.get("tools")
                            and not self.tools_disabled
                        ):
                            print(
                                f"\r{' ' * (len(status_msg) + 5)}\r", end="", flush=True
                            )
                            print(
                                f"⚠️  Model doesn't support tools. Disabling and retrying..."
                            )
                            self.tools_disabled = True
                            # Remove tools and retry
                            kwargs.pop("tools", None)
                            # Update system prompt to no-tools version
                            if (
                                standalone_mode
                                and self.db
                                and self.root
                                and self.root.role == LLMMessageRole.SYSTEM
                            ):
                                from ctk.core.prompts import \
                                    get_ctk_system_prompt_no_tools

                                self.root.content = get_ctk_system_prompt_no_tools(
                                    self.db, self.vfs_cwd
                                )
                            # Retry without tools
                            print(f"\rGenerating response... ⏳", end="", flush=True)
                            response = self.provider.chat(
                                self.get_messages_for_llm(),
                                temperature=self.temperature,
                                max_tokens=self.max_tokens,
                                **kwargs,
                            )
                        else:
                            raise

                    response_text = response.content

                    # Clear the status line by overwriting with spaces
                    print(f"\r{' ' * (len(status_msg) + 5)}\r", end="", flush=True)

                    # Add assistant response to tree first (so it has model metadata)
                    assistant_msg = self.add_message(
                        LLMMessageRole.ASSISTANT, response_text
                    )

                    # Display response with model prefix if different from conversation default
                    if response_text:
                        # Show model prefix if it differs from conversation default
                        model_prefix = ""
                        if (
                            assistant_msg.model
                            and assistant_msg.model != self.conversation_model
                        ):
                            model_prefix = f"{assistant_msg.model}: "

                        if self.render_markdown:
                            if model_prefix:
                                print(model_prefix)
                            self.console.print(Markdown(response_text))
                        else:
                            print(f"{model_prefix}{response_text}")

                    # Check for tool calls
                    tool_calls = self.provider.extract_tool_calls(response)

                    # Determine if we should process tool calls
                    should_process_tools = tool_calls and (
                        ctk_tools_enabled or self.mcp_auto_tools
                    )
                    if not should_process_tools:
                        break  # No tools called or tools disabled

                    # Execute tool calls
                    print(f"\n🔧 Executing {len(tool_calls)} tool call(s)...")

                    # Import pass-through check
                    from ctk.core.tools import is_pass_through_tool

                    # CTK tool names for routing
                    ctk_tool_names = {
                        "search_conversations",
                        "get_conversation",
                        "get_statistics",
                        "execute_shell_command",
                    }

                    # Track if any pass-through tool was executed
                    pass_through_executed = False

                    for tool_call in tool_calls:
                        tool_name = tool_call.get("function", {}).get(
                            "name"
                        ) or tool_call.get("name")
                        tool_args = tool_call.get("function", {}).get(
                            "arguments"
                        ) or tool_call.get("arguments", {})
                        tool_id = tool_call.get("id")

                        # Parse arguments if they're a JSON string
                        if isinstance(tool_args, str):
                            tool_args = json.loads(tool_args)

                        print(f"  → {tool_name}({json.dumps(tool_args)})")

                        # Check if this is a pass-through tool
                        is_pass_through = is_pass_through_tool(tool_name)

                        # Route to CTK tools or MCP tools
                        if tool_name in ctk_tool_names and ctk_tools_enabled:
                            # Execute CTK tool
                            try:
                                from ctk.cli import execute_ask_tool

                                # Create shell executor for execute_shell_command
                                def shell_executor(cmd):
                                    pipeline = self.shell_parser.parse(cmd)
                                    return self.command_dispatcher.execute(
                                        pipeline, print_output=False
                                    )

                                result = execute_ask_tool(
                                    self.db,
                                    tool_name,
                                    tool_args,
                                    debug=False,
                                    use_rich=False,
                                    shell_executor=shell_executor,
                                )

                                if is_pass_through:
                                    # Pass-through: show full output directly to user
                                    print(
                                        f"\n{result}" if result else "    (no output)"
                                    )
                                    pass_through_executed = True
                                    # Don't add to message tree - output is final
                                else:
                                    # Normal tool: show truncated result
                                    if result and len(result) > 200:
                                        print(f"    Result: {result[:200]}...")
                                    elif result:
                                        print(f"    Result: {result}")

                                    # Add tool result to tree for LLM processing
                                    tool_msg = self.provider.format_tool_result_message(
                                        tool_name, result or "(no output)", tool_id
                                    )
                                    self.add_message(tool_msg.role, tool_msg.content)

                            except Exception as e:
                                print(f"    Error: {e}")
                                if not is_pass_through:
                                    error_msg = (
                                        self.provider.format_tool_result_message(
                                            tool_name, f"Error: {str(e)}", tool_id
                                        )
                                    )
                                    self.add_message(error_msg.role, error_msg.content)

                        elif self.mcp_auto_tools:
                            # Call the tool via MCP
                            try:
                                result = self.mcp_client.call_tool(tool_name, tool_args)
                                result_display = result.for_display()

                                if is_pass_through:
                                    # Pass-through: show full output directly
                                    print(f"\n{result_display}")
                                    pass_through_executed = True
                                else:
                                    # Normal tool: show truncated result
                                    if len(result_display) > 200:
                                        print(f"    Result: {result_display[:200]}...")
                                    else:
                                        print(f"    Result: {result_display}")

                                    # Add tool result to tree
                                    tool_result_content = result.for_llm()
                                    tool_msg = self.provider.format_tool_result_message(
                                        tool_name, tool_result_content, tool_id
                                    )
                                    self.add_message(tool_msg.role, tool_msg.content)

                            except Exception as e:
                                print(f"    Error: {e}")
                                if not is_pass_through:
                                    # Add error as tool result
                                    error_msg = (
                                        self.provider.format_tool_result_message(
                                            tool_name,
                                            {"success": False, "error": str(e)},
                                            tool_id,
                                        )
                                    )
                                    self.add_message(error_msg.role, error_msg.content)

                    print()  # Blank line before next iteration

                    # If a pass-through tool was executed, stop the loop
                    # (output already shown to user, no need for LLM to summarize)
                    if pass_through_executed:
                        break

            if iteration >= max_iterations:
                print("⚠️  Maximum tool calling iterations reached")

            # Auto-save after successful chat exchange
            self._auto_save_conversation()

        except Exception as e:
            print(f"\033[31mError: {e}\033[0m")
            # Move back to parent since we didn't get a response
            if self.current_message and self.current_message.parent:
                # Remove the failed user message
                failed_msg = self.current_message
                self.current_message = failed_msg.parent
                self.current_message.children.remove(failed_msg)
                del self.message_map[failed_msg.id]

    def handle_mcp_command(self, args: str):
        """Handle MCP subcommands - delegates to tui_mcp module."""
        from .tui_mcp import handle_mcp_command as _handle_mcp

        result = _handle_mcp(
            self.mcp_client, args,
            mcp_auto_tools_ref=[self.mcp_auto_tools]
        )
        if result is not None:
            self.mcp_auto_tools = result

    def handle_net_command(self, args: str):
        """Handle network/similarity subcommands - delegates to tui_network module."""
        from .tui_network import handle_net_command as _handle_net

        _handle_net(
            db=self.db,
            args=args,
            current_conversation_id=self.current_conversation_id,
            navigator=self.vfs_navigator,
            vfs_cwd=self.vfs_cwd,
        )

    # ==================== VFS Command Handlers ====================

    def _ensure_vfs_navigator(self):
        """Lazy initialize VFS navigator."""
        if self.vfs_navigator is None:
            if not self.db:
                raise ValueError("Database required for VFS commands")
            from ctk.core.vfs_navigator import VFSNavigator

            self.vfs_navigator = VFSNavigator(self.db)

    def handle_cd(self, args: str):
        """Handle /cd command - delegates to tui_vfs module."""
        from .tui_vfs import handle_cd as _handle_cd

        self._ensure_vfs_navigator()
        new_cwd = _handle_cd(self.db, self.vfs_navigator, self.vfs_cwd, args)
        if new_cwd is not None:
            self.vfs_cwd = new_cwd

    def handle_pwd(self):
        """Handle /pwd command - delegates to tui_vfs module."""
        from .tui_vfs import handle_pwd as _handle_pwd

        _handle_pwd(self.vfs_cwd)

    def handle_ls(self, args: str):
        """Handle /ls command - delegates to tui_vfs module."""
        from .tui_vfs import handle_ls as _handle_ls

        self._ensure_vfs_navigator()
        _handle_ls(self.db, self.vfs_navigator, self.vfs_cwd, args, console=self.console)

    def handle_ln(self, args: str):
        """Handle /ln command - delegates to tui_vfs module."""
        from .tui_vfs import handle_ln as _handle_ln

        self._ensure_vfs_navigator()
        _handle_ln(self.db, self.vfs_navigator, self.vfs_cwd, args)

    def handle_cp(self, args: str):
        """Handle /cp command - delegates to tui_vfs module."""
        from .tui_vfs import handle_cp as _handle_cp

        self._ensure_vfs_navigator()
        _handle_cp(self.db, self.vfs_navigator, self.vfs_cwd, args)

    def handle_mv(self, args: str):
        """Handle /mv command - delegates to tui_vfs module."""
        from .tui_vfs import handle_mv as _handle_mv

        self._ensure_vfs_navigator()
        _handle_mv(self.db, self.vfs_navigator, self.vfs_cwd, args)

    def handle_rm(self, args: str):
        """Handle /rm command - delegates to tui_vfs module."""
        from .tui_vfs import handle_rm as _handle_rm

        self._ensure_vfs_navigator()
        _handle_rm(self.db, self.vfs_navigator, self.vfs_cwd, args)

    def handle_mkdir(self, args: str):
        """Handle /mkdir command - delegates to tui_vfs module."""
        from .tui_vfs import handle_mkdir as _handle_mkdir

        self._ensure_vfs_navigator()
        _handle_mkdir(self.db, self.vfs_navigator, self.vfs_cwd, args)


    def run(self):
        """Run the chat interface"""
        self.print_header()

        try:
            while True:
                # Get user input with mode-appropriate prompt
                try:
                    # Update environment variables
                    self._update_environment()

                    # Build prompt based on current mode
                    if self.mode == "shell":
                        # Shell mode: [/path] $
                        vfs_pwd = self.vfs_cwd if hasattr(self, "vfs_cwd") else "/"
                        prompt_text = f"[{vfs_pwd}] $"
                    else:
                        # Chat mode: existing chat prompt
                        user_name = self.current_user or "You"
                        vfs_pwd = (
                            self.vfs_cwd
                            if hasattr(self, "vfs_cwd") and self.vfs_cwd != "/"
                            else ""
                        )

                        if self.current_message:
                            current_path = self.get_current_path()
                            position = len(current_path) - 1
                            path_length = len(current_path)
                            prompt_text = f"{user_name} [{position}/{path_length-1}]"

                            # Add branch indicator if at a branching point
                            if (
                                self.current_message.children
                                and len(self.current_message.children) > 1
                            ):
                                prompt_text += (
                                    f" ({len(self.current_message.children)} branches)"
                                )
                        else:
                            prompt_text = user_name

                        # Add VFS pwd if not at root
                        if vfs_pwd:
                            prompt_text = f"[{vfs_pwd}] {prompt_text}"

                    user_input = self.session.prompt(
                        HTML(f"<prompt>{prompt_text}: </prompt>"), style=self.style
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not user_input:
                    continue

                # Handle OS shell commands (! prefix)
                if user_input.startswith("!"):
                    self.execute_shell_command(user_input[1:])
                    continue

                # Mode-specific input handling
                if self.mode == "shell":
                    # Shell mode: parse and route commands
                    if self.shell_parser.is_shell_command(user_input):
                        # Parse the command
                        pipeline = self.shell_parser.parse(user_input)

                        # Check for exit command
                        if pipeline.commands and pipeline.commands[
                            0
                        ].command.lower() in ["exit", "quit"]:
                            break

                        # Execute through dispatcher if registered
                        if pipeline.commands and self.command_dispatcher.has_command(
                            pipeline.commands[0].command.lower()
                        ):
                            result = self.command_dispatcher.execute(
                                pipeline, print_output=True
                            )
                            if not result.success and result.error:
                                print(f"Error: {result.error}")
                        else:
                            # Fall back to existing command handler for commands not yet in dispatcher
                            first_cmd = pipeline.commands[0].command.lower()
                            if first_cmd in self.known_commands:
                                if not self.handle_command(user_input):
                                    break
                            else:
                                print(f"Command not found: {first_cmd}")
                                print(
                                    "Type 'help' for commands, 'say <message>' to chat with LLM"
                                )
                    else:
                        # Input doesn't look like a command - show help
                        print(f"Unknown input. Use 'say <message>' to chat with LLM.")
                        print("Type 'help' for available commands.")

                else:
                    # Chat mode: check for /commands
                    if user_input.startswith("/"):
                        command = user_input[1:]  # Remove leading /
                        if command.lower() in ["exit", "quit"]:
                            # Return to shell mode
                            self.mode = "shell"
                            print("Returned to shell mode")
                            continue
                        # Handle other slash commands
                        if not self.handle_command(command):
                            break
                    else:
                        # Regular chat in chat mode
                        self.chat(user_input)

        except Exception as e:
            print(f"\nFatal error: {e}")
            sys.exit(1)
