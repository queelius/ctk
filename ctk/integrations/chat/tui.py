"""
Terminal UI for CTK chat.
"""

import sys
import uuid
import json
from typing import List, Optional
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown

from ctk.integrations.llm.base import Message as LLMMessage, MessageRole as LLMMessageRole, LLMProvider
from ctk.integrations.llm.mcp_client import MCPClient, MCPServer
from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree,
    Message as DBMessage,
    MessageRole as DBMessageRole,
    MessageContent,
    ConversationMetadata
)
from ctk.core.tree import TreeMessage, ConversationTreeNavigator
from ctk.core.shell_parser import ShellParser
from ctk.core.command_dispatcher import CommandDispatcher, CommandResult
from ctk.core.commands.unix import create_unix_commands


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

    def __init__(self, provider: LLMProvider, db: Optional[ConversationDB] = None,
                 render_markdown: bool = True, disable_tools: bool = False):
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
        self.conversation_model: str = provider.model  # Default model for this conversation
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
            'help', 'exit', 'quit', 'clear', 'new-chat',
            'save', 'load', 'delete', 'search', 'list', 'browse',
            'archive', 'star', 'pin', 'title', 'tag', 'export',
            'show', 'tree', 'paths', 'fork', 'fork-id', 'context',
            'mcp', 'cd', 'pwd', 'ls', 'ln', 'cp', 'mv', 'rm', 'mkdir',
            'net', 'goto-longest', 'goto-latest', 'where', 'alternatives',
            'history', 'models', 'model', 'temp', 'regenerate', 'edit',
            'say', 'find', 'unstar', 'unpin', 'unarchive', 'chat',
        }

        # Prompt toolkit setup
        self.session = PromptSession(
            history=InMemoryHistory(),
            auto_suggest=AutoSuggestFromHistory(),
        )

        # Style for prompt
        self.style = Style.from_dict({
            'prompt': '#00aa00 bold',
            'user': '#00aaaa',
            'assistant': '#aa00aa',
            'system': '#888888',
            'error': '#aa0000 bold',
        })

        # Shell mode support
        self.mode = 'shell'  # 'shell' or 'chat'
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
            unix_commands = create_unix_commands(self.db, self.vfs_navigator, tui_instance=self)
            self.command_dispatcher.register_commands(unix_commands)

            # Register navigation commands
            from ctk.core.commands.navigation import create_navigation_commands
            nav_commands = create_navigation_commands(self.vfs_navigator, tui_instance=self)
            self.command_dispatcher.register_commands(nav_commands)

            # Register visualization commands
            from ctk.core.commands.visualization import create_visualization_commands
            viz_commands = create_visualization_commands(self.db, self.vfs_navigator, tui_instance=self)
            self.command_dispatcher.register_commands(viz_commands)

            # Register organization commands
            from ctk.core.commands.organization import create_organization_commands
            org_commands = create_organization_commands(self.db, self.vfs_navigator, tui_instance=self)
            self.command_dispatcher.register_commands(org_commands)

            # Register search commands
            from ctk.core.commands.search import create_search_commands
            search_commands = create_search_commands(self.db, self.vfs_navigator, tui_instance=self)
            self.command_dispatcher.register_commands(search_commands)

        # Register chat commands (always available, even without db)
        from ctk.core.commands.chat import create_chat_commands
        chat_commands = create_chat_commands(tui_instance=self)
        self.command_dispatcher.register_commands(chat_commands)

        # Update environment variables
        self._update_environment()

    def _update_environment(self):
        """Update shell environment variables"""
        env = {
            'CWD': self.vfs_cwd,
            'PWD': self.vfs_cwd,
            'MODEL': self.provider.model if self.provider else '',
            'PROVIDER': self.provider.name if self.provider else '',
        }

        # Add conversation-specific variables if in a conversation
        if self.current_conversation_id:
            env['CONV_ID'] = self.current_conversation_id

        if self.current_message:
            path = self.get_current_path()
            env['MSG_COUNT'] = str(len(path))

        self.shell_parser.set_environment(env)

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
                tags=[self.provider.name, 'chat'],
            )
        )

        # Convert all TreeMessages to DBMessages recursively
        def convert_node(tree_msg: TreeMessage, parent_id: Optional[str] = None):
            db_msg = DBMessage(
                id=tree_msg.id,
                role=DBMessageRole(tree_msg.role.value),
                content=MessageContent(text=tree_msg.content),
                timestamp=tree_msg.timestamp,
                parent_id=parent_id,
                metadata={'model': tree_msg.model, 'user': tree_msg.user} if (tree_msg.model or tree_msg.user) else None
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

    def add_message(self, role: LLMMessageRole, content: str, parent: Optional[TreeMessage] = None) -> TreeMessage:
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

        msg = TreeMessage(role=role, content=content, parent=parent, model=model, user=user)
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
        'help': {
            'usage': 'help [command]',
            'desc': 'Show general help or detailed help for a specific command',
            'examples': ['help', 'help fork', 'help export']
        },
        'save': {
            'usage': 'save',
            'desc': 'Save the current conversation to the database',
            'details': 'Persists the entire conversation tree including all branches and metadata. Requires database to be configured.'
        },
        'load': {
            'usage': 'load <id>',
            'desc': 'Load a conversation from the database',
            'details': 'Accepts full or partial conversation ID. Use /list or /search to find conversation IDs.',
            'examples': ['load abc123', 'load abc']
        },
        'delete': {
            'usage': 'delete [id]',
            'desc': 'Delete a conversation from the database',
            'details': 'If no ID provided, deletes the currently loaded conversation. Requires confirmation.',
            'examples': ['delete', 'delete abc123']
        },
        'archive': {
            'usage': 'archive',
            'desc': 'Archive the current conversation',
            'details': 'Archived conversations are hidden from default list/search results. Use --include-archived flag in CLI to see them.'
        },
        'unarchive': {
            'usage': 'unarchive',
            'desc': 'Unarchive the current conversation'
        },
        'star': {
            'usage': 'star',
            'desc': 'Star the current conversation for quick access',
            'details': 'Starred conversations can be filtered with ctk list --starred'
        },
        'unstar': {
            'usage': 'unstar',
            'desc': 'Remove star from current conversation'
        },
        'pin': {
            'usage': 'pin',
            'desc': 'Pin the current conversation',
            'details': 'Pinned conversations appear first in lists'
        },
        'unpin': {
            'usage': 'unpin',
            'desc': 'Unpin the current conversation'
        },
        'fork': {
            'usage': 'fork <num>',
            'desc': 'Fork conversation from a message number in current path',
            'details': 'Creates a new conversation starting from the specified message. Use /history to see message numbers.',
            'examples': ['fork 5', 'fork 0']
        },
        'fork-id': {
            'usage': 'fork-id <id>',
            'desc': 'Fork conversation from a message by ID',
            'details': 'Accepts full or partial message ID. Use /tree to see message IDs.',
            'examples': ['fork-id abc123']
        },
        'duplicate': {
            'usage': 'duplicate [title]',
            'desc': 'Duplicate the current conversation',
            'details': 'Creates a complete copy with new ID. Optional custom title, otherwise prefixed with "Copy of".',
            'examples': ['duplicate', 'duplicate "My experiment"']
        },
        'split': {
            'usage': 'split <num>',
            'desc': 'Split conversation at message number into new conversation',
            'details': 'Creates a new conversation containing messages from the split point onwards.',
            'examples': ['split 10']
        },
        'prune': {
            'usage': 'prune <msg-id>',
            'desc': 'Delete a message and all its descendants',
            'details': 'Permanently removes the specified message and all child messages. Requires confirmation. Use /tree to find message IDs.',
            'examples': ['prune abc123']
        },
        'keep-path': {
            'usage': 'keep-path <num>',
            'desc': 'Flatten tree by keeping only one path',
            'details': 'Removes all branches except the specified path. Use /paths to see path numbers. Requires confirmation.',
            'examples': ['keep-path 0']
        },
        'tag': {
            'usage': 'tag [tag]',
            'desc': 'Show current tags or add a tag to the conversation',
            'details': 'Without arguments, displays current conversation tags. With an argument, adds the tag to the conversation. Tags help organize and filter conversations.',
            'examples': ['tag', 'tag python', 'tag machine-learning']
        },
        'project': {
            'usage': 'project [name]',
            'desc': 'Show current project or set project for the conversation',
            'details': 'Without arguments, displays current project. With an argument, sets the project name. Projects help organize related conversations.',
            'examples': ['project', 'project research', 'project ctk-dev']
        },
        'auto-tag': {
            'usage': 'auto-tag',
            'desc': 'Use LLM to suggest and add tags automatically',
            'details': 'Analyzes the conversation and suggests 3-5 relevant tags. You can approve or reject the suggestions.'
        },
        'export': {
            'usage': 'export <format> [file]',
            'desc': 'Export conversation to file',
            'details': 'Formats: markdown, json, jsonl, html. If no file specified, generates default name.',
            'examples': ['export markdown', 'export json output.json', 'export html report.html']
        },
        'tree': {
            'usage': 'tree',
            'desc': 'Visualize conversation tree structure',
            'details': 'Shows branching structure with message IDs, roles, and content previews. Current position marked with *.'
        },
        'paths': {
            'usage': 'paths',
            'desc': 'List all branches/paths through the conversation tree',
            'details': 'Shows each possible path from root to leaf. Useful before /keep-path.'
        },
        'merge': {
            'usage': 'merge <id> [num]',
            'desc': 'Merge another conversation into this one',
            'details': 'Inserts messages from another conversation. Optional message number specifies insertion point (default: end).',
            'examples': ['merge abc123', 'merge abc123 5']
        },
        'history': {
            'usage': 'history [length]',
            'desc': 'Show message history of current path',
            'details': 'Optional length parameter truncates message content to N characters.',
            'examples': ['history', 'history 100']
        },
        'temp': {
            'usage': 'temp [value]',
            'desc': 'Set or show temperature (0.0-2.0)',
            'details': 'Controls randomness of responses. Lower = more focused, higher = more creative. Default: 0.7',
            'examples': ['temp', 'temp 0.9']
        },
        'model': {
            'usage': 'model [name]',
            'desc': 'Switch model or show current model',
            'examples': ['model', 'model llama3.2', 'model gpt-4']
        },
        'search': {
            'usage': 'search <query> [options]',
            'desc': 'Search conversations in the database',
            'details': '''Searches both conversation titles and message content. Returns up to 20 results sorted by relevance.
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
  --has-branches        Filter to branching conversations only''',
            'examples': [
                'search python',
                'search "error handling" --title-only',
                'search "API" --model gpt-4 --starred',
                'search debugging --tags python,troubleshooting'
            ]
        },
        'list': {
            'usage': 'list [options]',
            'desc': 'List recent conversations from the database',
            'details': '''Shows the most recently updated conversations with filtering and organization options.
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
  📦 = Archived conversation''',
            'examples': [
                'list',
                'list --starred --limit 10',
                'list --model gpt-4',
                'list --tags python,machine-learning',
                'list --archived'
            ]
        },
        'net': {
            'usage': 'net <subcommand> [options]',
            'desc': 'Network and similarity commands for finding related conversations',
            'details': '''Subcommands:
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
Run 'net links' to build the graph before using clusters, neighbors, path, central, outliers.''',
            'examples': [
                'net embeddings',
                'net embeddings --force',
                'net embeddings --search python --limit 50',
                'net embeddings --starred --tags machine-learning',
                'net similar --top-k 5',
                'net similar abc123 --top-k 10 --threshold 0.3',
                'net links --threshold 0.3 --max-links 10',
                'net links --rebuild',
                'net network',
                'net clusters --algorithm louvain',
                'net neighbors abc123 --depth 2',
                'net path abc123 def456',
                'net central --metric pagerank --top-k 20',
                'net outliers --top-k 15',
            ]
        },
        'cd': {
            'usage': 'cd [path]',
            'desc': 'Change current directory in virtual filesystem',
            'details': '''Navigate the conversation virtual filesystem.

Paths can be absolute (/tags/physics) or relative (../quantum).
Special: . (current directory), .. (parent directory)

Examples:
  /cd /tags/physics           # Absolute path
  /cd physics/simulator       # Relative path
  /cd ..                      # Parent directory
  /cd /starred                # View starred conversations''',
            'examples': [
                'cd /',
                'cd /tags/physics',
                'cd ../quantum',
                'cd /starred',
            ]
        },
        'pwd': {
            'usage': 'pwd',
            'desc': 'Print current working directory',
            'details': '''Shows your current location in the virtual filesystem.''',
            'examples': ['pwd']
        },
        'ls': {
            'usage': 'ls [-l] [path]',
            'desc': 'List directory contents',
            'details': '''List conversations and subdirectories.

Options:
  -l    Long format with metadata (title, tags, date)

If no path specified, lists current directory.

Examples:
  /ls                # Current directory
  /ls -l             # Long format
  /ls /tags/physics  # Specific directory
  /ls -l /starred    # Starred conversations with details''',
            'examples': [
                'ls',
                'ls -l',
                'ls /tags/physics',
                'ls -l /starred',
            ]
        },
        'ln': {
            'usage': 'ln <src> <dest>',
            'desc': 'Link conversation to tag (add tag, like hardlink)',
            'details': '''Add a tag to a conversation without removing existing tags.
Source must be a conversation, destination must be a /tags/* directory.
This is like creating a hardlink - the same conversation appears in multiple tag directories.''',
            'examples': [
                'ln /chats/abc123 /tags/physics/',
                'ln /starred/xyz789 /tags/important/',
                'ln abc123 /tags/research/ml/',
            ]
        },
        'cp': {
            'usage': 'cp <src> <dest>',
            'desc': 'Copy conversation (deep copy with new UUID)',
            'details': '''Create a complete copy of a conversation with a new auto-generated UUID.
Source must be a conversation, destination can be /tags/* directory.
The copy will have all messages and tags, but a different ID.
This is a true copy - editing one won't affect the other.''',
            'examples': [
                'cp /chats/abc123 /tags/backup/',
                'cp /tags/test/xyz789 /tags/production/',
            ]
        },
        'mv': {
            'usage': 'mv <src> <dest>',
            'desc': 'Move conversation between tags',
            'details': '''Move a conversation from one tag to another.
Source must be from /tags/*, removes old tag and adds new tag.
The conversation keeps its ID, just changes tags.''',
            'examples': [
                'mv /tags/draft/abc123 /tags/final/',
                'mv /tags/physics/old/xyz789 /tags/physics/new/',
            ]
        },
        'rm': {
            'usage': 'rm <path>',
            'desc': 'Remove tag from conversation or delete conversation',
            'details': '''Two modes of operation:
1. /rm /tags/path/conv_id - Removes the tag from conversation
2. /rm /chats/conv_id - Permanently deletes conversation (with confirmation)

Deleting from /chats/ is destructive and requires confirmation.
Removing from /tags/* just removes the tag, doesn't delete the conversation.''',
            'examples': [
                'rm /tags/physics/abc123',
                'rm /chats/xyz789',
            ]
        },
        'mkdir': {
            'usage': 'mkdir <path>',
            'desc': 'Create tag hierarchy (conceptual)',
            'details': '''Create a conceptual tag hierarchy in /tags/*.
Directories are created conceptually and will appear when conversations are tagged.
You don't need to create directories before tagging - this is mainly for documentation.''',
            'examples': [
                'mkdir /tags/research/ml/transformers/',
                'mkdir /tags/projects/new-feature/',
            ]
        },
    }

    def print_help(self, command: str = None):
        """Print help message"""
        if command:
            # Show detailed help for specific command
            cmd = command.lstrip('')  # Remove leading slash if present
            if cmd in self.COMMAND_HELP:
                help_info = self.COMMAND_HELP[cmd]
                self.console.print(f"\n[bold cyan]{cmd}[/bold cyan]")
                self.console.print(f"[dim]Usage:[/dim] {help_info['usage']}")
                self.console.print(f"\n{help_info['desc']}")

                if 'details' in help_info:
                    self.console.print(f"\n[dim]Details:[/dim] {help_info['details']}")

                if 'examples' in help_info:
                    self.console.print("\n[dim]Examples:[/dim]")
                    for ex in help_info['examples']:
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
        print("    merge <id> [num]  - Merge conversation at message position (default: end)")
        print("    branch            - Save & create new conversation with same history")
        print("    fork <num>        - Fork conversation from message number in current path")
        print("    fork-id <id>      - Fork conversation from message by ID (full or partial)")
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
        print("    export <fmt> [file] - Export conversation (markdown, json, jsonl, html)")

        print("\n  Tree Navigation:")
        print("    tree              - Visualize conversation tree structure")
        print("    goto-longest      - Navigate to leaf of longest path")
        print("    goto-latest       - Navigate to most recent leaf node")
        print("    where             - Show current position in tree")
        print("    history [length]  - Show message history (optional: max chars per message)")
        print("    paths             - List all branches/paths through tree")
        print("    alternatives      - Show alternative child branches at current position")
        print("    Note: Message numbers shown in [brackets] for /fork reference.")

        print("\n  Shell:")
        print("    !<command>         - Execute shell command (e.g., !ls, !cat file.txt)")
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
        print("    net embeddings [options]     - Generate embeddings (supports filters: --starred, --tags, etc.)")
        print("    net similar [id] [--top-k N] - Find similar conversations (uses current if no ID)")
        print("    net links [--threshold N]    - Build conversation graph")
        print("    net network [--rebuild]      - Show network statistics")
        print("    net clusters [--algorithm]   - Detect conversation communities")
        print("    net neighbors <id>           - Show graph neighbors")
        print("    net path <src> <dst>         - Find path between conversations")
        print("    net central [--metric]       - Find most central conversations")
        print("    net outliers                 - Find least connected conversations")
        print("    Use 'help net' for detailed options and examples")

        print("\n  Virtual Filesystem:")
        print("    cd [path]           - Change directory (/tags/physics, ../quantum, /starred)")
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

        if cmd in ['exit', 'quit']:
            return False

        elif cmd == 'help':
            self.print_help(args)

        elif cmd == 'clear':
            self.root = None
            self.current_message = None
            self.message_map = {}
            self.current_conversation_id = None
            self.conversation_title = None
            self.conversation_model = self.provider.model  # Set default model for new conversation
            self.print_success("Conversation cleared")

        elif cmd == 'new-chat':
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
            self.conversation_model = self.provider.model  # Set default model for new conversation

            # Set new title if provided
            if args:
                self.conversation_title = args
                print(f"✓ Started new conversation: '{args}'")
            else:
                self.conversation_title = None
                print("✓ Started new conversation")

        elif cmd == 'system':
            if not args:
                print("Error: /system requires a message")
            else:
                self.add_message(LLMMessageRole.SYSTEM, args)
                print(f"✓ System message added: {args}")

        elif cmd == 'save':
            self.save_conversation()

        elif cmd == 'load':
            if not args:
                print("Error: /load requires a conversation ID")
            else:
                self.load_conversation(args)

        elif cmd == 'delete':
            # If no args, delete currently loaded conversation
            conv_id = args if args else self.current_conversation_id
            if not conv_id:
                print("Error: No conversation to delete (not loaded and no ID provided)")
            else:
                self.delete_conversation(conv_id)

        elif cmd == 'search':
            if not args:
                print("Error: /search requires a query")
            else:
                self.search_conversations(args)

        elif cmd == 'list':
            self.list_conversations(args)

        elif cmd == 'archive':
            self.archive_conversation(archive=True)

        elif cmd == 'unarchive':
            self.archive_conversation(archive=False)

        elif cmd == 'star':
            self.star_conversation(star=True)

        elif cmd == 'unstar':
            self.star_conversation(star=False)

        elif cmd == 'pin':
            self.pin_conversation(pin=True)

        elif cmd == 'unpin':
            self.pin_conversation(pin=False)

        elif cmd == 'duplicate':
            self.duplicate_conversation(args if args else None)

        elif cmd == 'tag':
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

        elif cmd == 'project':
            if not args:
                # Show current project
                if self.conversation_project:
                    print(f"Project: {self.conversation_project}")
                else:
                    print("No project set")
            else:
                self.set_project(args)

        elif cmd == 'auto-tag':
            self.auto_tag_conversation()

        elif cmd == 'split':
            if not args:
                print("Error: /split requires a message number")
            else:
                try:
                    msg_num = int(args)
                    self.split_conversation(msg_num)
                except ValueError:
                    print(f"Error: Invalid message number: {args}")

        elif cmd == 'prune':
            if not args:
                print("Error: /prune requires a message ID")
            else:
                self.prune_subtree(args)

        elif cmd == 'keep-path':
            if not args:
                print("Error: /keep-path requires a path number")
            else:
                try:
                    path_num = int(args)
                    self.keep_path(path_num)
                except ValueError:
                    print(f"Error: Invalid path number: {args}")

        elif cmd == 'title':
            if not args:
                print("Error: /title requires a new title")
            else:
                self.conversation_title = args
                print(f"✓ Conversation title set to: {args}")

        elif cmd == 'user':
            if not args:
                if self.current_user:
                    print(f"Current user: {self.current_user}")
                else:
                    print("No user set (messages will have no user attribution)")
            else:
                self.current_user = args
                print(f"✓ User set to: {args}")

        elif cmd == 'stats':
            self.show_stats()

        elif cmd == 'show':
            if not args:
                print("Error: /show requires a message number")
            else:
                try:
                    msg_num = int(args)
                    self.show_message(msg_num)
                except ValueError:
                    print(f"Error: Invalid message number: {args}")

        elif cmd == 'rollback':
            if not args:
                # Default to rolling back 1 exchange (2 messages)
                self.rollback(1)
            else:
                try:
                    n = int(args)
                    self.rollback(n)
                except ValueError:
                    print(f"Error: Invalid number: {args}")

        elif cmd == 'temp':
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

        elif cmd == 'model':
            if not args:
                # Show current model info
                print(f"Current model: {self.provider.model}")
                print(f"Provider: {self.provider.name}")

                # Show provider-specific info
                if hasattr(self.provider, 'base_url'):
                    print(f"Base URL: {self.provider.base_url}")

                # Get detailed model info if available
                try:
                    model_info = self.provider.get_model_info(self.provider.model)
                    if model_info:
                        print("\nModel details:")
                        # Show key info based on provider
                        if 'modelfile' in model_info:
                            # Ollama format
                            if 'parameters' in model_info:
                                print(f"  Parameters: {model_info.get('parameters', 'N/A')}")
                            if 'template' in model_info:
                                template = model_info.get('template', '')
                                if len(template) > 100:
                                    template = template[:100] + '...'
                                print(f"  Template: {template}")
                            if 'details' in model_info:
                                details = model_info['details']
                                if 'family' in details:
                                    print(f"  Family: {details['family']}")
                                if 'parameter_size' in details:
                                    print(f"  Size: {details['parameter_size']}")
                                if 'quantization_level' in details:
                                    print(f"  Quantization: {details['quantization_level']}")
                        else:
                            # Generic format
                            for key, value in model_info.items():
                                if key not in ['modelfile', 'template', 'license']:
                                    print(f"  {key}: {value}")
                except Exception as e:
                    print(f"  (Could not retrieve model details: {e})")
            else:
                old_model = self.provider.model
                self.provider.model = args
                print(f"✓ Model changed from {old_model} to {args}")

        elif cmd == 'models':
            self.list_models()

        elif cmd == 'model_info':
            # Show detailed model info
            model_name = args if args else self.provider.model
            self.show_model_info(model_name)

        elif cmd == 'num_ctx':
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

        elif cmd == 'stream':
            self.streaming = not self.streaming
            status = "enabled" if self.streaming else "disabled"
            print(f"✓ Streaming {status}")

        elif cmd == 'grep':
            if not args:
                print("Error: /grep requires a search pattern")
            else:
                self.grep_conversation(args)

        elif cmd == 'export':
            if not args:
                print("Error: /export requires format (markdown, json, jsonl, html)")
            else:
                # Parse format and optional filename
                parts = args.split(maxsplit=1)
                fmt = parts[0].lower()
                filename = parts[1] if len(parts) > 1 else None
                self.export_conversation(fmt, filename)

        elif cmd == 'regenerate':
            self.regenerate_last_response()

        elif cmd == 'retry':
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

        elif cmd == 'summary':
            self.request_summary()

        elif cmd == 'merge':
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

        elif cmd == 'branch':
            self.branch_conversation()

        elif cmd == 'fork':
            if not args:
                print("Error: /fork requires a message number")
            else:
                try:
                    msg_num = int(args)
                    self.fork_conversation(msg_num)
                except ValueError:
                    print(f"Error: Invalid message number: {args}")

        elif cmd == 'fork-id':
            if not args:
                print("Error: /fork-id requires a message ID (full or partial)")
            else:
                self.fork_conversation_by_id(args)

        elif cmd == 'context':
            if not args:
                print("Error: /context requires a file path")
            else:
                self.load_file_context(args)

        elif cmd == 'mcp':
            if not args:
                print("Error: /mcp requires a subcommand (add, remove, connect, disconnect, list, tools, call)")
            else:
                self.handle_mcp_command(args)

        elif cmd == 'tree':
            self.show_tree()

        elif cmd == 'goto-longest':
            self.goto_longest_path()

        elif cmd == 'goto-latest':
            self.goto_latest_leaf()

        elif cmd == 'where':
            self.show_current_position()

        elif cmd == 'paths':
            self.show_all_paths()

        elif cmd == 'alternatives':
            self.show_alternatives()

        elif cmd == 'history':
            # Optional argument for max content length
            max_len = None
            if args:
                try:
                    max_len = int(args)
                except ValueError:
                    self.print_error(f"Invalid length: {args}")
                    return True
            self.show_history(max_len)

        elif cmd == 'cd':
            self.handle_cd(args)

        elif cmd == 'pwd':
            self.handle_pwd()

        elif cmd == 'ls':
            self.handle_ls(args)

        elif cmd == 'ln':
            self.handle_ln(args)

        elif cmd == 'cp':
            self.handle_cp(args)

        elif cmd == 'mv':
            self.handle_mv(args)

        elif cmd == 'rm':
            self.handle_rm(args)

        elif cmd == 'mkdir':
            self.handle_mkdir(args)

        elif cmd == 'net':
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

            # If ID is partial (< 36 chars), do prefix matching
            if len(conv_id) < 36:
                # Search for conversations with IDs starting with this prefix
                all_convs = self.db.list_conversations(limit=None, include_archived=True)
                matches = [c for c in all_convs if c.id.startswith(conv_id)]

                if len(matches) == 0:
                    print(f"Error: No conversation found matching '{conv_id}'")
                    return
                elif len(matches) > 1:
                    print(f"Error: Multiple conversations match '{conv_id}':")
                    for match in matches[:5]:
                        print(f"  - {match.id[:8]}... {match.title}")
                    print("Please provide more characters to uniquely identify the conversation")
                    return
                else:
                    # Exactly one match - load it
                    conv_id = matches[0].id

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

            # If not found and ID is partial, search for matches
            if not tree and len(conv_id) < 36:
                all_convs = self.db.list_conversations(limit=1000)
                matches = [c for c in all_convs if c.id.startswith(conv_id)]

                if len(matches) == 0:
                    print(f"Error: No conversation found matching '{conv_id}'")
                    return
                elif len(matches) > 1:
                    print(f"Error: Multiple conversations match '{conv_id}':")
                    for match in matches[:5]:
                        print(f"  - {match.id[:8]}... {match.title}")
                    print("Please provide more characters to uniquely identify the conversation")
                    return
                else:
                    # Exactly one match
                    tree = self.db.load_conversation(matches[0].id)

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
            if confirm != 'yes':
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
                self.current_conversation_id,
                project=project
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
                [Message(role=MessageRole.USER, content=tag_prompt)],
                temperature=0.3
            )

            # Parse tags from response
            response_text = response.content if hasattr(response, 'content') else str(response)
            tags = [t.strip() for t in response_text.strip().split(',')]
            tags = [t for t in tags if t]  # Remove empty

            if not tags:
                print("Error: No tags suggested")
                return

            print(f"\nSuggested tags: {', '.join(tags)}")
            confirm = input("Add these tags? (y/n): ").strip().lower()

            if confirm == 'y':
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
        from ctk.core.models import ConversationTree, ConversationMetadata
        new_tree = ConversationTree(
            id=new_id,
            title=new_title,
            metadata=ConversationMetadata(
                version="2.0.0",
                source="CTK Split",
                created_at=datetime.now()
            )
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
                parent_id=None if i == msg_num else current_path[i-1].id
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
        matches = [(mid, msg) for mid, msg in self.message_map.items() if mid.startswith(msg_id_prefix)]

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
        if confirm != 'yes':
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
            self.current_message = self.get_longest_path()[-1] if self.message_map else None

        print(f"✓ Deleted {total} message(s)")

    def keep_path(self, path_num: int):
        """Flatten tree by keeping only one path"""
        paths = []
        for msg in self.message_map.values():
            if not msg.parent_id:
                # This is a root, get all paths from it
                def get_paths_from(node, current_path=[]):
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
        if confirm != 'yes':
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

        from ctk.core.helpers import search_conversations_helper

        # Parse arguments
        import shlex
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
            'limit': None,  # No limit by default - show all
            'offset': 0,
            'title_only': False,
            'content_only': False,
            'date_from': None,
            'date_to': None,
            'source': None,
            'project': None,
            'model': None,
            'tags': None,
            'min_messages': None,
            'max_messages': None,
            'has_branches': False,
            'archived': False,
            'starred': False,
            'pinned': False,
            'include_archived': False,
            'order_by': 'updated_at',
            'ascending': False,
            'output_format': 'table'
        }

        i = 1
        while i < len(arg_list):
            arg = arg_list[i]
            if arg == '--limit' and i + 1 < len(arg_list):
                kwargs['limit'] = int(arg_list[i + 1])
                i += 2
            elif arg == '--title-only':
                kwargs['title_only'] = True
                i += 1
            elif arg == '--content-only':
                kwargs['content_only'] = True
                i += 1
            elif arg == '--starred':
                kwargs['starred'] = True
                i += 1
            elif arg == '--pinned':
                kwargs['pinned'] = True
                i += 1
            elif arg == '--archived':
                kwargs['archived'] = True
                i += 1
            elif arg == '--include-archived':
                kwargs['include_archived'] = True
                i += 1
            elif arg == '--source' and i + 1 < len(arg_list):
                kwargs['source'] = arg_list[i + 1]
                i += 2
            elif arg == '--project' and i + 1 < len(arg_list):
                kwargs['project'] = arg_list[i + 1]
                i += 2
            elif arg == '--model' and i + 1 < len(arg_list):
                kwargs['model'] = arg_list[i + 1]
                i += 2
            elif arg == '--tags' and i + 1 < len(arg_list):
                kwargs['tags'] = arg_list[i + 1]
                i += 2
            elif arg == '--min-messages' and i + 1 < len(arg_list):
                kwargs['min_messages'] = int(arg_list[i + 1])
                i += 2
            elif arg == '--max-messages' and i + 1 < len(arg_list):
                kwargs['max_messages'] = int(arg_list[i + 1])
                i += 2
            elif arg == '--has-branches':
                kwargs['has_branches'] = True
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

        from ctk.core.helpers import list_conversations_helper

        # Parse arguments
        import shlex
        try:
            arg_list = shlex.split(args) if args else []
        except ValueError as e:
            print(f"Error parsing arguments: {e}")
            return

        # Simple argument parsing
        kwargs = {
            'limit': None,  # No limit by default - show all
            'json_output': False,
            'archived': False,
            'starred': False,
            'pinned': False,
            'include_archived': False,
            'source': None,
            'project': None,
            'model': None,
            'tags': None
        }

        i = 0
        while i < len(arg_list):
            arg = arg_list[i]
            if arg == '--limit' and i + 1 < len(arg_list):
                kwargs['limit'] = int(arg_list[i + 1])
                i += 2
            elif arg == '--starred':
                kwargs['starred'] = True
                i += 1
            elif arg == '--pinned':
                kwargs['pinned'] = True
                i += 1
            elif arg == '--archived':
                kwargs['archived'] = True
                i += 1
            elif arg == '--include-archived':
                kwargs['include_archived'] = True
                i += 1
            elif arg == '--source' and i + 1 < len(arg_list):
                kwargs['source'] = arg_list[i + 1]
                i += 2
            elif arg == '--project' and i + 1 < len(arg_list):
                kwargs['project'] = arg_list[i + 1]
                i += 2
            elif arg == '--model' and i + 1 < len(arg_list):
                kwargs['model'] = arg_list[i + 1]
                i += 2
            elif arg == '--tags' and i + 1 < len(arg_list):
                kwargs['tags'] = arg_list[i + 1]
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

        from ctk.core.helpers import get_ask_tools
        from ctk.core.config import get_config
        import json

        # Get LLM provider config
        cfg = get_config()
        provider_name = self.provider.__class__.__name__.replace('Provider', '').lower()
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
            Message(role=MessageRole.USER, content=query)
        ]

        try:
            # Call LLM
            response = self.provider.chat(messages, temperature=0.1, tools=formatted_tools)

            # Check if LLM wants to use tools
            if response.tool_calls:
                # Import execute_ask_tool from cli
                import sys
                import os
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                from cli import execute_ask_tool

                # Execute each tool call and display results
                for tool_call in response.tool_calls:
                    tool_name = tool_call['function']['name']
                    tool_args = tool_call['function']['arguments']
                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)

                    # Execute tool with Rich output
                    tool_result = execute_ask_tool(self.db, tool_name, tool_args, debug=False, use_rich=True)

                    # If there's a result string (for non-Rich output), print it
                    if tool_result:
                        print(tool_result)
            else:
                # No tool call - show LLM's text response if available
                if response.content:
                    print(response.content)
                else:
                    # Provide helpful guidance
                    print("I couldn't determine what to search for. Try asking something like:")
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
        assistant_count = sum(1 for m in current_path if m.role == LLMMessageRole.ASSISTANT)
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
                    if 'size' in model.metadata:
                        print(f"    Size: {model.metadata['size']}")
                    if 'family' in model.metadata:
                        print(f"    Family: {model.metadata['family']}")
                    if 'parameter_size' in model.metadata:
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
            if 'parameters' in info:
                print("Runtime Parameters:")
                print(info['parameters'])
                print()

            # Pretty-print the model_info JSON (max capabilities)
            if 'model_info' in info:
                print("Model Capabilities:")
                print(json.dumps(info['model_info'], indent=2, sort_keys=True))
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
            LLMMessageRole.TOOL: "Tool"
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

        print(f"\nMessage {msg_num} ({role_name}){' - ' + metadata_str if metadata_str else ''}:")
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
                LLMMessageRole.TOOL: "Tool"
            }.get(msg.role, str(msg.role))

            # Show snippet with context
            lines = msg.content.split('\n')
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
        import subprocess
        import shlex

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
                timeout=30
            )

            # Print stdout
            if result.stdout:
                print(result.stdout, end='')

            # Print stderr
            if result.stderr:
                print(result.stderr, end='', file=sys.stderr)

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

        def print_tree(msg: TreeMessage, prefix: str = "", is_last: bool = True, depth: int = 0):
            """Recursively print tree structure"""
            # Determine connector (compact version)
            connector = "└─" if is_last else "├─"

            # Show message info with role emoji only
            role_emoji = {"system": "⚙", "user": "U", "assistant": "A", "tool": "T", "tool_result": "R"}
            emoji = role_emoji.get(msg.role.value, "?")

            # Very compact content preview (max 30 chars to save space)
            content_preview = msg.content[:30].replace('\n', ' ').strip()
            if len(msg.content) > 30:
                content_preview += "..."

            # Show current position marker (compact)
            is_current = (msg == self.current_message)
            marker = " *" if is_current else ""

            # Compact metadata - only show if different from conversation default
            meta_parts = []
            if msg.model and msg.model != self.conversation_model:
                # Just show first part of model name
                short_model = msg.model.split(':')[0][:8]
                meta_parts.append(f"m:{short_model}")
            if msg.user:
                meta_parts.append(f"u:{msg.user[:8]}")
            meta_str = f" [{','.join(meta_parts)}]" if meta_parts else ""

            # Format: prefix + connector + emoji + id(short) + content + meta + marker
            print(f"{prefix}{connector}{emoji} {msg.id[:6]} {content_preview}{meta_str}{marker}")

            # Print children
            if msg.children:
                # Update prefix for children (compact: 2 spaces instead of 4)
                extension = "  " if is_last else "│ "
                new_prefix = prefix + extension

                for i, child in enumerate(msg.children):
                    is_last_child = (i == len(msg.children) - 1)
                    print_tree(child, new_prefix, is_last_child, depth + 1)

        print("\nConversation Tree:")
        print("=" * 80)
        print_tree(self.root)
        print("=" * 80)
        print(f"\nTotal messages: {len(self.message_map)}")
        print(f"Current path length: {len(self.get_current_path())}")
        print(f"Current position: {self.current_message.id[:8] if self.current_message else 'root'}")
        print("\nLegend: U=user, A=assistant, ⚙=system, T=tool, R=result, *=current position")


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
                parent_id = path_to_target[i-1].id
                siblings = conversation.get_children(parent_id)
                try:
                    idx = next(j for j, s in enumerate(siblings) if s.id == msg.id)
                except StopIteration:
                    idx = 0
            segments.append(f"m{idx + 1}")

        return "/".join(segments)

    def goto_longest_path(self):
        """Navigate to the leaf node of the longest path"""
        from ctk.core.vfs import VFSPathParser, PathType

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                    use_vfs = True
            except:
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

            if parsed.path_type not in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
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

            content_text = target_msg.content.get_text() if hasattr(target_msg.content, 'get_text') else str(target_msg.content.text if hasattr(target_msg.content, 'text') else target_msg.content)

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
        from ctk.core.vfs import VFSPathParser, PathType

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                    use_vfs = True
            except:
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

            if parsed.path_type not in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
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

            content_text = latest_msg.content.get_text() if hasattr(latest_msg.content, 'get_text') else str(latest_msg.content.text if hasattr(latest_msg.content, 'text') else latest_msg.content)
            timestamp_str = latest_msg.timestamp.strftime('%Y-%m-%d %H:%M:%S') if latest_msg.timestamp else 'unknown'

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
        from ctk.core.vfs import VFSPathParser, PathType

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                    use_vfs = True
            except:
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
                print(f"\nParent: {self.current_message.parent.id[:8]}... ({self.current_message.parent.role.value})")
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

            if parsed.path_type not in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
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
                current_messages = [conversation.message_map.get(rid) for rid in conversation.root_message_ids]
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
                    print(f"Role: {target_message.role.value if target_message.role else 'unknown'}")
                    # Message class stores model in metadata, not as direct attribute
                    model = getattr(target_message, 'model', None) or (target_message.metadata.get('model') if hasattr(target_message, 'metadata') and target_message.metadata else None)
                    if model:
                        print(f"Model: {model}")
                    print(f"Timestamp: {target_message.timestamp}")
                    content_text = target_message.content.get_text() if hasattr(target_message.content, 'get_text') else str(target_message.content.text if hasattr(target_message.content, 'text') else target_message.content)
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
                            print(f"  [m{i+1}] {child.id[:8]}... ({child.role.value if child.role else 'unknown'})")
                    else:
                        print("\nChildren: None (leaf node)")
            else:
                # At conversation root, show root messages
                print(f"\nRoot messages: {len(conversation.root_message_ids)}")
                for i, rid in enumerate(conversation.root_message_ids):
                    msg = conversation.message_map.get(rid)
                    if msg:
                        content_text = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content.text if hasattr(msg.content, 'text') else msg.content)
                        preview = content_text[:50].replace('\n', ' ').strip() if content_text else ""
                        if len(content_text) > 50:
                            preview += "..."
                        print(f"  [m{i+1}] {msg.id[:8]}... ({msg.role.value if msg.role else 'unknown'}): {preview}")

            print("=" * 80)

        except Exception as e:
            print(f"Error: {e}")

    def show_all_paths(self):
        """Show all complete paths through the conversation tree"""
        if not self.root:
            print("Error: No conversation tree")
            return

        def get_all_leaf_paths(node: TreeMessage, current_path: List[TreeMessage]) -> List[List[TreeMessage]]:
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
            is_current = (path[-1] == current_leaf)
            marker = " 👈 CURRENT" if is_current else ""

            print(f"\nPath {i+1}: {len(path)} messages{marker}")
            print("-" * 80)

            for j, msg in enumerate(path):
                role_emoji = {"system": "⚙️", "user": "👤", "assistant": "🤖", "tool": "🔧", "tool_result": "📊"}
                emoji = role_emoji.get(msg.role.value, "❓")
                content_preview = msg.content[:40].replace('\n', ' ')
                if len(msg.content) > 40:
                    content_preview += "..."

                print(f"  [{j}] {emoji} {msg.id[:8]}... {content_preview}")

        print("=" * 80)

    def show_alternatives(self):
        """Show alternative branches at current position"""
        from ctk.core.vfs import VFSPathParser, PathType

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
                if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                    use_vfs = True
            except:
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
                role_emoji = {"system": "⚙️", "user": "👤", "assistant": "🤖", "tool": "🔧", "tool_result": "📊"}
                emoji = role_emoji.get(child.role.value, "❓")

                content_preview = child.content[:60].replace('\n', ' ')
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
            current_messages = [conversation.message_map.get(rid) for rid in conversation.root_message_ids]
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

            content_text = target_message.content.get_text() if hasattr(target_message.content, 'get_text') else str(target_message.content.text if hasattr(target_message.content, 'text') else target_message.content)

            print(f"\nAlternative branches from current message:")
            print("=" * 80)
            print(f"Current message: {target_message.id[:8]}...")
            print(f"Role: {target_message.role.value if target_message.role else 'unknown'}")
            print(f"Content: {content_text[:60]}")
            print()

            # Show all children as alternatives
            for i, child in enumerate(children):
                role = child.role.value if child.role else "unknown"
                role_emoji = {"system": "⚙️", "user": "👤", "assistant": "🤖", "tool": "🔧", "tool_result": "📊"}
                emoji = role_emoji.get(role, "❓")

                child_content = child.content.get_text() if hasattr(child.content, 'get_text') else str(child.content.text if hasattr(child.content, 'text') else child.content)
                content_preview = child_content[:60].replace('\n', ' ')
                if len(child_content) > 60:
                    content_preview += "..."

                meta = []
                # Message class doesn't have model directly, check metadata
                model = getattr(child, 'model', None) or child.metadata.get('model') if hasattr(child, 'metadata') else None
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
                role_display = f"[dim]\\[{i}][/dim] [bold green]{role_name}:[/bold green]"
            elif msg.role == LLMMessageRole.ASSISTANT:
                role_name = msg.model if msg.model else "Assistant"
                role_display = f"[dim]\\[{i}][/dim] [bold magenta]{role_name}:[/bold magenta]"
            elif msg.role == LLMMessageRole.SYSTEM:
                role_display = f"[dim]\\[{i}][/dim] [bold yellow]System:[/bold yellow]"
            else:
                role_display = f"[dim]\\[{i}][/dim] {msg.role.value}:"

            # Show header
            self.console.print(role_display)

            # Show content (truncated or full)
            content = msg.content
            if max_content_length is not None and len(content) > max_content_length:
                content = content[:max_content_length].replace('\n', ' ') + "..."

            if self.render_markdown and msg.role == LLMMessageRole.ASSISTANT and max_content_length is None:
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
        from ctk.core.vfs import VFSPathParser, PathType

        # Check if we're at a VFS conversation path - if so, prioritize VFS loading
        use_vfs = False
        if self.db:
            try:
                parsed = VFSPathParser.parse(self.vfs_cwd)
                if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                    use_vfs = True
            except:
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

            if parsed.path_type not in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
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
                current_messages = [conversation.message_map.get(rid) for rid in conversation.root_message_ids]
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
                    model_name = getattr(msg, 'model', None) or (msg.metadata.get('model') if hasattr(msg, 'metadata') and msg.metadata else None) or "Assistant"
                    role_display = f"[dim]\\[{i}][/dim] [bold magenta]{model_name}:[/bold magenta]"
                elif role == "system":
                    role_display = f"[dim]\\[{i}][/dim] [bold yellow]System:[/bold yellow]"
                else:
                    role_display = f"[dim]\\[{i}][/dim] {role}:"

                self.console.print(role_display)

                content_text = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content.text if hasattr(msg.content, 'text') else msg.content)

                if max_content_length is not None and len(content_text) > max_content_length:
                    content_text = content_text[:max_content_length].replace('\n', ' ') + "..."

                if self.render_markdown and role == "assistant" and max_content_length is None:
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
            safe_title = "".join(c for c in tree.title[:30] if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_title = safe_title.replace(' ', '_')
            filename = f"{safe_title}.{fmt}"

        # Export using appropriate exporter
        try:
            if fmt == 'markdown':
                from ctk.integrations.exporters.markdown import MarkdownExporter
                exporter = MarkdownExporter()
                exporter.export_conversations([tree], output_file=filename)
            elif fmt == 'json':
                from ctk.integrations.exporters.json import JSONExporter
                exporter = JSONExporter()
                exporter.export_conversations([tree], output_file=filename, format='ctk')
            elif fmt == 'jsonl':
                from ctk.integrations.exporters.jsonl import JSONLExporter
                exporter = JSONLExporter()
                exporter.export_conversations([tree], output_file=filename)
            elif fmt == 'html':
                from ctk.integrations.exporters.html import HTMLExporter
                exporter = HTMLExporter()
                exporter.export_conversations([tree], output_path=filename)
            else:
                print(f"Error: Unknown format '{fmt}'. Available: markdown, json, jsonl, html")
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
                if child.role == LLMMessageRole.USER and child.content == parent_msg.content and child != parent_msg:
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
        if not self.current_message.parent or self.current_message.parent.role != LLMMessageRole.USER:
            print("Error: Cannot find user message to retry")
            return

        user_msg = self.current_message.parent

        # Save original temperature
        orig_temp = self.temperature
        if temp is not None:
            self.temperature = temp
            print(f"Retrying with temperature {temp} (will create alternative branch)...")
        else:
            print("Retrying last message (will create alternative branch)...")
        print()

        # Move to user message and regenerate
        self.current_message = user_msg
        self.chat(user_msg.content)

        # Remove duplicate user message
        if self.current_message and self.current_message.parent:
            for child in self.current_message.parent.children[:]:
                if child.role == LLMMessageRole.USER and child.content == user_msg.content and child != user_msg:
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

            # If not found or ID is partial, search for matches
            if not tree:
                all_convs = self.db.list_conversations(limit=1000)
                matches = [c for c in all_convs if c.id.startswith(conv_id)]

                if len(matches) == 0:
                    print(f"Error: No conversation found matching '{conv_id}'")
                    return
                elif len(matches) > 1:
                    print(f"Error: Multiple conversations match '{conv_id}':")
                    for match in matches[:5]:
                        print(f"  - {match.id[:8]}... {match.title}")
                    print("Please provide more characters to uniquely identify the conversation")
                    return
                else:
                    # Exactly one match - load it
                    tree = self.db.load_conversation(matches[0].id)

            if not tree:
                print(f"Error: Conversation {conv_id} not found")
                return

            # Get messages from other conversation
            db_messages = tree.get_longest_path()
            if not db_messages and tree.message_map:
                db_messages = sorted(tree.message_map.values(), key=lambda m: m.timestamp or datetime.min)

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
            self.add_message(LLMMessageRole.SYSTEM, f"[Context from conversation: {tree.title}]")

            # Add messages from other conversation
            for db_msg in db_messages:
                self.add_message(
                    LLMMessageRole(db_msg.role.value),
                    db_msg.content.text or ""
                )

            # Add closing context marker
            self.add_message(LLMMessageRole.SYSTEM, f"[End of context from: {tree.title}]")

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
        self.conversation_title = f"Branch from: {old_title}" if old_title else f"Branch from {old_id[:8]}..."

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
        self.conversation_title = f"Fork at msg {msg_num}: {old_title}" if old_title else f"Fork from {old_id[:8] if old_id else 'conversation'}..."

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
        matches = [(msg_id, msg) for msg_id, msg in self.message_map.items() if msg_id.startswith(target_id)]

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
        self.conversation_title = f"Fork at {msg_id[:8]}: {old_title}" if old_title else f"Fork from {old_id[:8] if old_id else 'conversation'}..."

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
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Add file as system message
            self.add_message(
                LLMMessageRole.SYSTEM,
                f"[File: {filepath}]\n\n{content}\n\n[End of file: {filepath}]"
            )

            lines = len(content.split('\n'))
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
        # Check if we're in "standalone" mode (no conversation loaded)
        standalone_mode = self.current_conversation_id is None

        # Inject CTK system prompt if standalone and no system prompt yet
        if standalone_mode and self.db:
            current_path = self.get_current_path()
            has_system_prompt = any(msg.role == LLMMessageRole.SYSTEM for msg in current_path)
            if not has_system_prompt:
                # Choose prompt based on whether tools are available
                if self.tools_disabled:
                    from ctk.core.helpers import get_ctk_system_prompt_no_tools
                    ctk_prompt = get_ctk_system_prompt_no_tools(self.db, self.vfs_cwd)
                else:
                    from ctk.core.helpers import get_ctk_system_prompt
                    ctk_prompt = get_ctk_system_prompt(self.db, self.vfs_cwd)
                # Insert system message at the root
                system_msg = TreeMessage(role=LLMMessageRole.SYSTEM, content=ctk_prompt, parent=None)
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
                    kwargs['num_ctx'] = self.num_ctx

                # Add CTK tools if in standalone mode, provider supports it, AND tools not disabled
                ctk_tools_enabled = standalone_mode and self.provider.supports_tool_calling() and not self.tools_disabled
                if ctk_tools_enabled:
                    from ctk.core.helpers import get_ask_tools
                    ctk_tools = get_ask_tools()
                    kwargs['tools'] = self.provider.format_tools_for_api(ctk_tools)

                # Add MCP tools if auto-tools enabled and provider supports it
                if self.mcp_auto_tools and self.provider.supports_tool_calling():
                    tool_dicts = self.mcp_client.get_tools_as_dicts()
                    if tool_dicts:
                        kwargs['tools'] = self.provider.format_tools_for_api(tool_dicts)

                        # Add system prompt for tool usage guidance if not already present
                        current_path = self.get_current_path()
                        has_system_prompt = any(msg.role == LLMMessageRole.SYSTEM for msg in current_path)
                        if not has_system_prompt:
                            tool_guidance = (
                                "You have access to tools for specific tasks. "
                                "Only use tools when the user explicitly requests a task that requires them. "
                                "For casual conversation, greetings, questions, or general discussion, respond directly without using tools. "
                                "Use tools for: code execution, data analysis, file operations, or other programmatic tasks."
                            )
                            # Insert system message at the root
                            system_msg = TreeMessage(role=LLMMessageRole.SYSTEM, content=tool_guidance, parent=None)
                            self.message_map[system_msg.id] = system_msg
                            # Make current root a child of system message
                            if self.root:
                                self.root.parent = system_msg
                                system_msg.children.append(self.root)
                            self.root = system_msg

                response_text = ""

                if self.streaming and not kwargs.get('tools'):
                    # Token-by-token streaming (only when not using tools)
                    # Show model name on same line before streaming starts
                    self.console.print(f"[bold magenta]{self.provider.model}:[/bold magenta] ", end="")

                    for chunk in self.provider.stream_chat(
                        self.get_messages_for_llm(),
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        **kwargs
                    ):
                        print(chunk, end="", flush=True)
                        response_text += chunk
                    print()  # Final newline

                    # Add assistant response to tree
                    assistant_msg = self.add_message(LLMMessageRole.ASSISTANT, response_text)

                    break  # Done

                else:
                    # Non-streaming or tool-enabled: use chat() method
                    # Show spinner during generation
                    if kwargs.get('tools'):
                        status_msg = "Generating response (tools available)..."
                    else:
                        status_msg = "Generating response..."

                    # Print without newline so we can overwrite it
                    print(f"\r{status_msg} ⏳", end="", flush=True)

                    # Debug: show messages being sent (set CTK_DEBUG=1 to enable)
                    import os
                    if os.environ.get('CTK_DEBUG'):
                        msgs = self.get_messages_for_llm()
                        print(f"\n[DEBUG] Sending {len(msgs)} messages:")
                        for i, m in enumerate(msgs):
                            content_preview = m.content[:100] + "..." if len(m.content) > 100 else m.content
                            print(f"  [{i}] {m.role}: {content_preview}")
                        print()

                    try:
                        response = self.provider.chat(
                            self.get_messages_for_llm(),
                            temperature=self.temperature,
                            max_tokens=self.max_tokens,
                            **kwargs
                        )
                    except Exception as e:
                        # Auto-detect: if tools caused a 400 error, disable and retry
                        if '400' in str(e) and kwargs.get('tools') and not self.tools_disabled:
                            print(f"\r{' ' * (len(status_msg) + 5)}\r", end="", flush=True)
                            print(f"⚠️  Model doesn't support tools. Disabling and retrying...")
                            self.tools_disabled = True
                            # Remove tools and retry
                            kwargs.pop('tools', None)
                            # Update system prompt to no-tools version
                            if standalone_mode and self.db and self.root and self.root.role == LLMMessageRole.SYSTEM:
                                from ctk.core.helpers import get_ctk_system_prompt_no_tools
                                self.root.content = get_ctk_system_prompt_no_tools(self.db, self.vfs_cwd)
                            # Retry without tools
                            print(f"\rGenerating response... ⏳", end="", flush=True)
                            response = self.provider.chat(
                                self.get_messages_for_llm(),
                                temperature=self.temperature,
                                max_tokens=self.max_tokens,
                                **kwargs
                            )
                        else:
                            raise

                    response_text = response.content

                    # Clear the status line by overwriting with spaces
                    print(f"\r{' ' * (len(status_msg) + 5)}\r", end="", flush=True)

                    # Add assistant response to tree first (so it has model metadata)
                    assistant_msg = self.add_message(LLMMessageRole.ASSISTANT, response_text)

                    # Display response with model prefix if different from conversation default
                    if response_text:
                        # Show model prefix if it differs from conversation default
                        model_prefix = ""
                        if assistant_msg.model and assistant_msg.model != self.conversation_model:
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
                    should_process_tools = tool_calls and (ctk_tools_enabled or self.mcp_auto_tools)
                    if not should_process_tools:
                        break  # No tools called or tools disabled

                    # Execute tool calls
                    print(f"\n🔧 Executing {len(tool_calls)} tool call(s)...")

                    # CTK tool names for routing
                    ctk_tool_names = {'search_conversations', 'get_conversation', 'get_statistics', 'execute_shell_command'}

                    for tool_call in tool_calls:
                        tool_name = tool_call.get('function', {}).get('name') or tool_call.get('name')
                        tool_args = tool_call.get('function', {}).get('arguments') or tool_call.get('arguments', {})
                        tool_id = tool_call.get('id')

                        # Parse arguments if they're a JSON string
                        if isinstance(tool_args, str):
                            tool_args = json.loads(tool_args)

                        print(f"  → {tool_name}({json.dumps(tool_args)})")

                        # Route to CTK tools or MCP tools
                        if tool_name in ctk_tool_names and ctk_tools_enabled:
                            # Execute CTK tool
                            try:
                                from ctk.cli import execute_ask_tool

                                # Create shell executor for execute_shell_command
                                def shell_executor(cmd):
                                    pipeline = self.shell_parser.parse(cmd)
                                    return self.command_dispatcher.execute(pipeline, print_output=False)

                                result = execute_ask_tool(
                                    self.db,
                                    tool_name,
                                    tool_args,
                                    debug=False,
                                    use_rich=False,
                                    shell_executor=shell_executor
                                )

                                # Show result
                                if result and len(result) > 200:
                                    print(f"    Result: {result[:200]}...")
                                elif result:
                                    print(f"    Result: {result}")

                                # Add tool result to tree
                                tool_msg = self.provider.format_tool_result_message(
                                    tool_name,
                                    result or "(no output)",
                                    tool_id
                                )
                                self.add_message(tool_msg.role, tool_msg.content)

                            except Exception as e:
                                print(f"    Error: {e}")
                                error_msg = self.provider.format_tool_result_message(
                                    tool_name,
                                    f"Error: {str(e)}",
                                    tool_id
                                )
                                self.add_message(error_msg.role, error_msg.content)

                        elif self.mcp_auto_tools:
                            # Call the tool via MCP
                            try:
                                result = self.mcp_client.call_tool(tool_name, tool_args)

                                # Show result
                                result_display = result.for_display()
                                if len(result_display) > 200:
                                    print(f"    Result: {result_display[:200]}...")
                                else:
                                    print(f"    Result: {result_display}")

                                # Add tool result to tree
                                tool_result_content = result.for_llm()
                                tool_msg = self.provider.format_tool_result_message(
                                    tool_name,
                                    tool_result_content,
                                    tool_id
                                )
                                self.add_message(tool_msg.role, tool_msg.content)

                            except Exception as e:
                                print(f"    Error: {e}")
                                # Add error as tool result
                                error_msg = self.provider.format_tool_result_message(
                                    tool_name,
                                    {"success": False, "error": str(e)},
                                    tool_id
                                )
                                self.add_message(error_msg.role, error_msg.content)

                    print()  # Blank line before next iteration

            if iteration >= max_iterations:
                print("⚠️  Maximum tool calling iterations reached")

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
        """Handle MCP subcommands"""
        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower()
        subargs = parts[1] if len(parts) > 1 else ""

        if subcmd == 'add':
            # /mcp add <name> <command> [args...]
            if not subargs:
                print("Error: /mcp add requires name and command")
                print("Usage: /mcp add <name> <command> [args...]")
                print("Example: /mcp add filesystem python -m mcp_server_filesystem /path")
                return

            parts = subargs.split(maxsplit=2)
            if len(parts) < 2:
                print("Error: /mcp add requires name and command")
                return

            name = parts[0]
            command = parts[1]
            cmd_args = parts[2].split() if len(parts) > 2 else []

            server = MCPServer(
                name=name,
                command=command,
                args=cmd_args
            )
            self.mcp_client.add_server(server)
            print(f"✓ Added MCP server '{name}'")

        elif subcmd == 'remove':
            if not subargs:
                print("Error: /mcp remove requires server name")
                return

            self.mcp_client.remove_server(subargs)
            print(f"✓ Removed MCP server '{subargs}'")

        elif subcmd == 'connect':
            if not subargs:
                print("Error: /mcp connect requires server name")
                return

            try:
                success = self.mcp_client.connect_server(subargs)
                if success:
                    print(f"✓ Connected to MCP server '{subargs}'")
                    # Show available tools
                    tools = self.mcp_client.get_server_tools(subargs)
                    if tools:
                        print(f"  Available tools ({len(tools)}):")
                        for tool in tools[:5]:  # Show first 5
                            desc = f" - {tool.description}" if tool.description else ""
                            print(f"    - {tool.name}{desc}")
                        if len(tools) > 5:
                            print(f"    ... and {len(tools) - 5} more")
            except Exception as e:
                print(f"Error connecting to server: {e}")

        elif subcmd == 'disconnect':
            if not subargs:
                print("Error: /mcp disconnect requires server name")
                return

            try:
                self.mcp_client.disconnect_server(subargs)
                print(f"✓ Disconnected from MCP server '{subargs}'")
            except Exception as e:
                print(f"Error disconnecting from server: {e}")

        elif subcmd == 'list':
            servers = self.mcp_client.list_servers()
            if not servers:
                print("No MCP servers configured")
                return

            print("\nConfigured MCP servers:")
            for server in servers:
                status = "connected" if self.mcp_client.is_connected(server.name) else "disconnected"
                print(f"  - {server.name} ({status})")
                print(f"    Command: {server.command} {' '.join(server.args)}")
                if server.description:
                    print(f"    Description: {server.description}")

        elif subcmd == 'tools':
            # Show tools from specific server or all
            if subargs:
                tools = self.mcp_client.get_server_tools(subargs)
                if not tools:
                    if self.mcp_client.is_connected(subargs):
                        print(f"No tools available from server '{subargs}'")
                    else:
                        print(f"Server '{subargs}' is not connected")
                    return

                print(f"\nTools from '{subargs}':")
            else:
                tools = self.mcp_client.get_all_tools()
                if not tools:
                    print("No tools available (no servers connected)")
                    return

                print("\nAll available tools:")

            for tool in tools:
                desc = f" - {tool.description}" if tool.description else ""
                print(f"  - {tool.name}{desc}")
                if tool.input_schema:
                    # Show required parameters
                    props = tool.input_schema.get('properties', {})
                    required = tool.input_schema.get('required', [])
                    if props:
                        print(f"    Parameters:")
                        for param, schema in props.items():
                            req = " (required)" if param in required else ""
                            param_desc = schema.get('description', '')
                            print(f"      - {param}: {schema.get('type', 'any')}{req}")
                            if param_desc:
                                print(f"        {param_desc}")

        elif subcmd == 'call':
            # /mcp call <tool_name> [json_args]
            if not subargs:
                print("Error: /mcp call requires tool name")
                print("Usage: /mcp call <tool_name> [json_args]")
                print('Example: /mcp call read_file {"path": "/etc/hosts"}')
                return

            parts = subargs.split(maxsplit=1)
            tool_name = parts[0]

            # Parse arguments as JSON if provided
            arguments = {}
            if len(parts) > 1:
                try:
                    arguments = json.loads(parts[1])
                except json.JSONDecodeError as e:
                    print(f"Error: Invalid JSON arguments: {e}")
                    return

            try:
                print(f"Calling tool '{tool_name}'...")
                result = self.mcp_client.call_tool(tool_name, arguments)
                print(f"\nTool result:")
                # Use the for_display() method for human-readable output
                print(result.for_display())
            except Exception as e:
                print(f"Error calling tool: {e}")

        elif subcmd == 'auto':
            # Toggle automatic tool use
            self.mcp_auto_tools = not self.mcp_auto_tools
            status = "enabled" if self.mcp_auto_tools else "disabled"
            print(f"✓ Automatic tool use {status}")
            if self.mcp_auto_tools:
                connected = self.mcp_client.get_connected_servers()
                if connected:
                    tools = self.mcp_client.get_all_tools()
                    print(f"  {len(tools)} tool(s) available from {len(connected)} server(s)")
                else:
                    print("  Warning: No MCP servers connected")
                    print("  Use 'mcp connect <server>' to connect to a server")

        else:
            print(f"Unknown MCP subcommand: {subcmd}")
            print("Available: add, remove, connect, disconnect, list, tools, call, auto")

    def handle_net_command(self, args: str):
        """Handle network/similarity subcommands"""
        from ctk.core.similarity import (
            ConversationEmbedder,
            ConversationEmbeddingConfig,
            SimilarityComputer,
            SimilarityMetric,
            ChunkingStrategy,
            AggregationStrategy,
        )
        from ctk.integrations.embeddings.tfidf import TFIDFEmbedding
        from rich.table import Table
        from rich.console import Console

        if not self.db:
            print("Error: No database configured")
            return

        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower()
        subargs = parts[1] if len(parts) > 1 else ""

        console = Console()

        if subcmd == 'embeddings':
            # Parse options
            provider = "tfidf"
            force = False
            limit = None  # None = all conversations
            starred = None
            pinned = None
            tags = None
            source = None
            project = None
            model = None
            search = None

            if subargs:
                arg_parts = subargs.split()
                i = 0
                while i < len(arg_parts):
                    arg = arg_parts[i]

                    if arg == '--provider':
                        if i + 1 >= len(arg_parts):
                            print("Error: --provider requires a value")
                            return
                        provider = arg_parts[i + 1]
                        i += 2
                    elif arg == '--limit':
                        if i + 1 >= len(arg_parts):
                            print("Error: --limit requires a value")
                            return
                        try:
                            limit = int(arg_parts[i + 1])
                        except ValueError:
                            print(f"Error: --limit must be an integer, got '{arg_parts[i + 1]}'")
                            return
                        i += 2
                    elif arg == '--force':
                        force = True
                        i += 1
                    elif arg == '--starred':
                        starred = True
                        i += 1
                    elif arg == '--pinned':
                        pinned = True
                        i += 1
                    elif arg == '--tags':
                        if i + 1 >= len(arg_parts):
                            print("Error: --tags requires a value")
                            return
                        tags = [t.strip() for t in arg_parts[i + 1].split(',')]
                        i += 2
                    elif arg == '--source':
                        if i + 1 >= len(arg_parts):
                            print("Error: --source requires a value")
                            return
                        source = arg_parts[i + 1]
                        i += 2
                    elif arg == '--project':
                        if i + 1 >= len(arg_parts):
                            print("Error: --project requires a value")
                            return
                        project = arg_parts[i + 1]
                        i += 2
                    elif arg == '--model':
                        if i + 1 >= len(arg_parts):
                            print("Error: --model requires a value")
                            return
                        model = arg_parts[i + 1]
                        i += 2
                    elif arg == '--search':
                        if i + 1 >= len(arg_parts):
                            print("Error: --search requires a value")
                            return
                        search = arg_parts[i + 1]
                        i += 2
                    else:
                        print(f"Error: Unknown option '{arg}'")
                        print("Valid options: --provider, --limit, --force, --starred, --pinned, --tags, --source, --project, --model, --search")
                        return

            # Build filter description
            filter_desc = []
            if starred:
                filter_desc.append("starred")
            if pinned:
                filter_desc.append("pinned")
            if tags:
                filter_desc.append(f"tags={','.join(tags)}")
            if source:
                filter_desc.append(f"source={source}")
            if project:
                filter_desc.append(f"project={project}")
            if model:
                filter_desc.append(f"model={model}")
            if search:
                filter_desc.append(f"search='{search}'")

            filter_str = f" ({', '.join(filter_desc)})" if filter_desc else ""
            print(f"Generating embeddings using {provider}{filter_str}...")

            # Configure embedder
            config = ConversationEmbeddingConfig(
                provider=provider,
                chunking=ChunkingStrategy.MESSAGE,
                aggregation=AggregationStrategy.WEIGHTED_MEAN,
                role_weights={"user": 2.0, "assistant": 1.0, "system": 0.5},
                include_title=True,
                include_tags=True,
                provider_config={"max_features": 5000, "ngram_range": [1, 2]}
            )

            embedder = ConversationEmbedder(config)

            # Get conversations with filters
            if search:
                # Use search_conversations for keyword filtering
                conversations = self.db.search_conversations(
                    query_text=search,
                    limit=limit,
                    starred=starred,
                    pinned=pinned,
                    tags=tags,
                    source=source,
                    project=project,
                    model=model
                )
            else:
                # Use list_conversations for non-search filters
                conversations = self.db.list_conversations(
                    limit=limit,
                    starred=starred,
                    pinned=pinned,
                    tags=tags,
                    source=source,
                    project=project,
                    model=model
                )

            if not conversations:
                print("No conversations found matching filters")
                return

            print(f"Found {len(conversations)} conversations")

            # Fit TF-IDF if using that provider
            if provider == "tfidf":
                print("Fitting TF-IDF on corpus...")
                corpus_texts = []
                for conv_summary in conversations:
                    conv = self.db.load_conversation(conv_summary.id)
                    if conv:
                        text_parts = []
                        if conv.title:
                            text_parts.append(conv.title)
                        if conv.metadata.tags:
                            text_parts.append(" ".join(conv.metadata.tags))
                        for msg in conv.message_map.values():
                            if hasattr(msg.content, 'text') and msg.content.text:
                                text_parts.append(msg.content.text)
                        corpus_texts.append(" ".join(text_parts))

                embedder.provider.fit(corpus_texts)
                print(f"✓ Fitted with {embedder.provider.get_dimensions()} features")

            # Embed conversations
            print("Embedding conversations...")
            count = 0
            for conv_summary in conversations:
                conv = self.db.load_conversation(conv_summary.id)
                if conv:
                    # Check if already embedded
                    if not force:
                        existing = self.db.get_embedding(
                            conv.id, model=provider, provider=provider,
                            chunking_strategy="message",
                            aggregation_strategy="weighted_mean"
                        )
                        if existing is not None:
                            continue

                    embedding = embedder.embed_conversation(conv)
                    self.db.save_embedding(
                        conversation_id=conv.id,
                        embedding=embedding,
                        provider=provider,
                        model=provider,
                        chunking_strategy="message",
                        aggregation_strategy="weighted_mean",
                        aggregation_weights=config.role_weights
                    )
                    count += 1

            print(f"✓ Embedded {count} conversations")

            # Save embedding session metadata
            filters_dict = {}
            if starred is not None:
                filters_dict['starred'] = starred
            if pinned is not None:
                filters_dict['pinned'] = pinned
            if tags is not None:
                filters_dict['tags'] = tags
            if source is not None:
                filters_dict['source'] = source
            if project is not None:
                filters_dict['project'] = project
            if model is not None:
                filters_dict['model'] = model
            if search is not None:
                filters_dict['search'] = search
            if limit is not None:
                filters_dict['limit'] = limit

            session_id = self.db.save_embedding_session(
                provider=provider,
                model=provider,  # For TF-IDF, model == provider
                chunking_strategy="message",
                aggregation_strategy="weighted_mean",
                num_conversations=len(conversations),
                role_weights=config.role_weights,
                filters=filters_dict if filters_dict else None,
                mark_current=True
            )
            print(f"✓ Saved embedding session (ID: {session_id})")

        elif subcmd == 'similar':
            # Parse arguments
            import shlex
            try:
                arg_parts = shlex.split(subargs) if subargs else []
            except ValueError:
                arg_parts = subargs.split() if subargs else []

            conv_id = None
            top_k = 10
            threshold = 0.0
            provider = "tfidf"

            # Parse arguments
            i = 0
            while i < len(arg_parts):
                arg = arg_parts[i]
                if arg == '--top-k':
                    if i + 1 < len(arg_parts):
                        try:
                            top_k = int(arg_parts[i + 1])
                            i += 2
                            continue
                        except ValueError:
                            print(f"Error: Invalid top-k value: {arg_parts[i + 1]}")
                            return
                elif arg == '--threshold':
                    if i + 1 < len(arg_parts):
                        try:
                            threshold = float(arg_parts[i + 1])
                            i += 2
                            continue
                        except ValueError:
                            print(f"Error: Invalid threshold value: {arg_parts[i + 1]}")
                            return
                elif arg == '--provider':
                    if i + 1 < len(arg_parts):
                        provider = arg_parts[i + 1]
                        i += 2
                        continue
                elif not arg.startswith('--'):
                    conv_id = arg
                    i += 1
                else:
                    i += 1

            # Use current conversation if none specified
            if not conv_id:
                conv_id = self.current_conversation_id
                # Also try to get from VFS path if in a conversation directory
                if not conv_id and hasattr(self, 'vfs_cwd'):
                    from ctk.core.vfs import VFSPathParser, PathType
                    try:
                        parsed = VFSPathParser.parse(self.vfs_cwd)
                        if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                            conv_id = parsed.conversation_id
                    except Exception:
                        pass
                if not conv_id:
                    print("Error: No conversation specified and not in a conversation directory")
                    print("Usage: /net similar [conv_id] [--top-k N] [--threshold N]")
                    return

            # Resolve prefix if needed
            if conv_id and len(conv_id) < 36:
                from ctk.core.vfs import VFSPathParser
                try:
                    chats_path = VFSPathParser.parse('/chats')
                    resolved = self.navigator.resolve_prefix(conv_id, chats_path)
                    if resolved:
                        conv_id = resolved
                except Exception:
                    pass  # Use original conv_id if resolution fails

            # Load conversation
            query_conv = self.db.load_conversation(conv_id)
            if not query_conv:
                print(f"Error: Conversation not found: {conv_id}")
                return

            print(f"Finding conversations similar to: '{query_conv.title}'")

            # Setup similarity computer
            config = ConversationEmbeddingConfig(
                provider=provider,
                chunking=ChunkingStrategy.MESSAGE,
                aggregation=AggregationStrategy.WEIGHTED_MEAN,
                role_weights={"user": 2.0, "assistant": 1.0, "system": 0.5},
                provider_config={"max_features": 5000, "ngram_range": [1, 2]}
            )

            embedder = ConversationEmbedder(config)

            # Load and fit TF-IDF if needed
            if provider == "tfidf" and not embedder.provider.is_fitted:
                conversations = self.db.list_conversations()
                corpus_texts = []
                for conv_summary in conversations:
                    conv = self.db.load_conversation(conv_summary.id)
                    if conv:
                        text_parts = []
                        if conv.title:
                            text_parts.append(conv.title)
                        if conv.metadata.tags:
                            text_parts.append(" ".join(conv.metadata.tags))
                        for msg in conv.message_map.values():
                            if hasattr(msg.content, 'text') and msg.content.text:
                                text_parts.append(msg.content.text)
                        corpus_texts.append(" ".join(text_parts))

                embedder.provider.fit(corpus_texts)

            similarity = SimilarityComputer(embedder, metric=SimilarityMetric.COSINE, db=self.db)

            # Find similar
            results = similarity.find_similar(
                query_conv,
                top_k=top_k,
                threshold=threshold,
                use_cache=True
            )

            if not results:
                print(f"No similar conversations found (threshold={threshold})")
                return

            # Display results in table
            table = Table(title=f"Similar Conversations (top {len(results)})")
            table.add_column("Rank", style="cyan", width=6)
            table.add_column("Similarity", style="green", width=12)
            table.add_column("Title", style="white")
            table.add_column("Tags", style="yellow")
            table.add_column("ID", style="dim", width=15)

            for i, result in enumerate(results, 1):
                similar_conv = self.db.load_conversation(result.conversation2_id)
                if similar_conv:
                    tags_str = ", ".join(similar_conv.metadata.tags) if similar_conv.metadata.tags else ""
                    table.add_row(
                        str(i),
                        f"{result.similarity:.3f}",
                        similar_conv.title or "(untitled)",
                        tags_str,
                        result.conversation2_id[:12] + "..."
                    )

            console.print(table)

        elif subcmd == 'links':
            # Parse options
            threshold = 0.3  # Default similarity threshold
            max_links = 10  # Default max links per node
            rebuild = False  # Force rebuild

            if subargs:
                arg_parts = subargs.split()
                i = 0
                while i < len(arg_parts):
                    arg = arg_parts[i]

                    if arg == '--threshold':
                        if i + 1 >= len(arg_parts):
                            print("Error: --threshold requires a value")
                            return
                        try:
                            threshold = float(arg_parts[i + 1])
                        except ValueError:
                            print(f"Error: --threshold must be a number, got '{arg_parts[i + 1]}'")
                            return
                        i += 2
                    elif arg == '--max-links':
                        if i + 1 >= len(arg_parts):
                            print("Error: --max-links requires a value")
                            return
                        try:
                            max_links = int(arg_parts[i + 1])
                        except ValueError:
                            print(f"Error: --max-links must be an integer, got '{arg_parts[i + 1]}'")
                            return
                        i += 2
                    elif arg == '--rebuild':
                        rebuild = True
                        i += 1
                    else:
                        print(f"Error: Unknown option '{arg}'")
                        print("Valid options: --threshold, --max-links, --rebuild")
                        return

            # Check if graph already exists
            existing_graph = self.db.get_current_graph()
            if existing_graph and not rebuild:
                print("Graph already exists:")
                print(f"  Created: {existing_graph['created_at']}")
                print(f"  Nodes: {existing_graph['num_nodes']}")
                print(f"  Edges: {existing_graph['num_edges']}")
                print(f"  Threshold: {existing_graph['threshold']}")
                print(f"  File: {existing_graph['graph_file_path']}")
                print("\nUse --rebuild to force rebuild")
                return

            # Get current embedding session
            session = self.db.get_current_embedding_session()
            if not session:
                print("Error: No embedding session found. Run /net embeddings first.")
                return

            print(f"Building graph from embedding session {session['id']}...")

            # Get conversations using same filters as embedding session
            filters = session.get('filters') or {}
            print(f"Using filters: {filters if filters else 'none'}")

            if filters.get('search'):
                conversations = self.db.search_conversations(
                    query_text=filters.get('search'),
                    limit=filters.get('limit'),
                    starred=filters.get('starred'),
                    pinned=filters.get('pinned'),
                    tags=filters.get('tags'),
                    source=filters.get('source'),
                    project=filters.get('project'),
                    model=filters.get('model')
                )
            else:
                conversations = self.db.list_conversations(
                    limit=filters.get('limit'),
                    starred=filters.get('starred'),
                    pinned=filters.get('pinned'),
                    tags=filters.get('tags'),
                    source=filters.get('source'),
                    project=filters.get('project'),
                    model=filters.get('model')
                )

            if not conversations:
                print("Error: No conversations found with current filters")
                return

            print(f"Found {len(conversations)} conversations")

            # Build graph
            print(f"Computing pairwise similarities (threshold={threshold})...")
            from ctk.core.similarity import SimilarityComputer, ConversationGraphBuilder

            config = ConversationEmbeddingConfig(
                provider=session['provider'],
                chunking=ChunkingStrategy.MESSAGE,
                aggregation=AggregationStrategy.WEIGHTED_MEAN,
                role_weights=session.get('role_weights') or {"user": 2.0, "assistant": 1.0},
                include_title=True,
                include_tags=True
            )

            embedder = ConversationEmbedder(config)
            sim_computer = SimilarityComputer(embedder, db=self.db)
            graph_builder = ConversationGraphBuilder(sim_computer)

            conversation_ids = [c.id for c in conversations]
            graph = graph_builder.build_graph(
                conversations=conversation_ids,
                threshold=threshold,
                max_links_per_node=max_links,
                use_cache=True,
                show_progress=True
            )

            print(f"✓ Graph: {len(graph.nodes)} nodes, {len(graph.links)} edges")

            # Save graph to file
            import json
            from datetime import datetime
            from pathlib import Path

            # Create graphs directory in database directory
            if self.db.db_dir:
                graphs_dir = self.db.db_dir / "graphs"
            else:
                # For non-file databases, use current directory
                graphs_dir = Path("graphs")

            graphs_dir.mkdir(exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            graph_filename = f"graph_{timestamp}.json"
            graph_path = graphs_dir / graph_filename

            # Save graph
            with open(graph_path, 'w') as f:
                json.dump(graph.to_dict(), f, indent=2)

            print(f"✓ Saved to: {graph_path}")

            # Save graph metadata to database
            self.db.save_current_graph(
                graph_file_path=str(graph_path),
                threshold=threshold,
                max_links_per_node=max_links,
                embedding_session_id=session['id'],
                num_nodes=len(graph.nodes),
                num_edges=len(graph.links)
            )

            print("✓ Graph metadata saved to database")
            print(f"\nUse /net network to view global statistics")

        elif subcmd == 'network':
            # Parse options
            rebuild = False

            if subargs:
                if '--rebuild' in subargs:
                    rebuild = True

            # Get current graph
            graph_metadata = self.db.get_current_graph()
            if not graph_metadata:
                print("Error: No graph found. Run 'net links' first to build a graph.")
                return

            # Check if metrics already computed
            if graph_metadata.get('density') is not None and not rebuild:
                # Metrics already cached, just display
                from ctk.core.network_analysis import format_network_stats
                stats_str = format_network_stats(graph_metadata)
                print(stats_str)
                return

            # Need to compute metrics
            print("Computing network statistics...")

            from ctk.core.network_analysis import (
                load_graph_from_file,
                compute_global_metrics,
                save_network_metrics_to_db,
                format_network_stats
            )

            # Load graph from file
            graph_path = graph_metadata['graph_file_path']
            try:
                G = load_graph_from_file(graph_path)
            except FileNotFoundError:
                print(f"Error: Graph file not found: {graph_path}")
                print("Run 'net links --rebuild' to regenerate the graph")
                return
            except Exception as e:
                print(f"Error loading graph: {e}")
                return

            # Compute metrics
            metrics = compute_global_metrics(G)

            # Save to database
            save_network_metrics_to_db(self.db, metrics)

            # Reload metadata (now with cached metrics)
            graph_metadata = self.db.get_current_graph()

            # Display
            stats_str = format_network_stats(graph_metadata, G)
            print(stats_str)

        elif subcmd == 'clusters':
            from ctk.core.network_analysis import load_graph_from_file
            # Parse options
            algorithm = 'louvain'
            min_size = 2

            if subargs:
                arg_parts = subargs.split()
                i = 0
                while i < len(arg_parts):
                    arg = arg_parts[i]
                    if arg == '--algorithm' and i + 1 < len(arg_parts):
                        algorithm = arg_parts[i + 1]
                        i += 2
                    elif arg == '--min-size' and i + 1 < len(arg_parts):
                        try:
                            min_size = int(arg_parts[i + 1])
                        except ValueError:
                            print(f"Error: --min-size must be an integer")
                            return
                        i += 2
                    else:
                        i += 1

            # Load graph
            graph_metadata = self.db.get_current_graph()
            if not graph_metadata:
                print("Error: No graph found. Run 'net links' first.")
                return

            G = load_graph_from_file(graph_metadata['graph_file_path'])
            print(f"Detecting communities using {algorithm}...")

            # Community detection
            import networkx as nx
            if algorithm == 'louvain':
                try:
                    communities = nx.community.louvain_communities(G, seed=42)
                except AttributeError:
                    from networkx.algorithms.community import greedy_modularity_communities
                    communities = list(greedy_modularity_communities(G))
            elif algorithm == 'label_propagation':
                from networkx.algorithms.community import label_propagation_communities
                communities = list(label_propagation_communities(G))
            else:
                from networkx.algorithms.community import greedy_modularity_communities
                communities = list(greedy_modularity_communities(G))

            # Filter and sort
            communities = [c for c in communities if len(c) >= min_size]
            communities = sorted(communities, key=len, reverse=True)

            if not communities:
                print("No communities found with minimum size")
                return

            print(f"\nFound {len(communities)} communities\n")

            for i, community in enumerate(communities, 1):
                print(f"Community {i} ({len(community)} conversations)")
                for conv_id in list(community)[:5]:
                    conv = self.db.load_conversation(conv_id)
                    title = conv.title if conv else "(untitled)"
                    print(f"  {conv_id[:8]}... {title[:50]}")
                if len(community) > 5:
                    print(f"  ... and {len(community) - 5} more")
                print()

        elif subcmd == 'neighbors':
            from ctk.core.network_analysis import load_graph_from_file
            # Parse options
            conv_id = None
            depth = 1

            if subargs:
                arg_parts = subargs.split()
                i = 0
                while i < len(arg_parts):
                    arg = arg_parts[i]
                    if arg == '--depth' and i + 1 < len(arg_parts):
                        try:
                            depth = int(arg_parts[i + 1])
                        except ValueError:
                            print("Error: --depth must be an integer")
                            return
                        i += 2
                    elif not arg.startswith('--'):
                        conv_id = arg
                        i += 1
                    else:
                        i += 1

            # Use current conversation if not specified
            if not conv_id:
                conv_id = self.current_conversation_id
                if not conv_id and hasattr(self, 'vfs_cwd'):
                    from ctk.core.vfs import VFSPathParser, PathType
                    try:
                        parsed = VFSPathParser.parse(self.vfs_cwd)
                        if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                            conv_id = parsed.conversation_id
                    except Exception:
                        pass
                if not conv_id:
                    print("Error: No conversation specified")
                    return

            # Resolve prefix
            if len(conv_id) < 36:
                from ctk.core.vfs import VFSPathParser
                try:
                    chats_path = VFSPathParser.parse('/chats')
                    resolved = self.navigator.resolve_prefix(conv_id, chats_path)
                    if resolved:
                        conv_id = resolved
                    else:
                        # Try direct DB lookup
                        all_convs = self.db.list_conversations(limit=10000)
                        matches = [c for c in all_convs if c.id.startswith(conv_id)]
                        if len(matches) == 1:
                            conv_id = matches[0].id
                        elif len(matches) > 1:
                            print(f"Ambiguous prefix '{conv_id}', matches:")
                            for m in matches[:5]:
                                print(f"  {m.id[:12]}... {m.title or '(untitled)'}")
                            return
                        else:
                            print(f"No conversation found with prefix: {conv_id}")
                            return
                except Exception as e:
                    # Fallback to direct DB lookup
                    all_convs = self.db.list_conversations(limit=10000)
                    matches = [c for c in all_convs if c.id.startswith(conv_id)]
                    if len(matches) == 1:
                        conv_id = matches[0].id
                    elif len(matches) > 1:
                        print(f"Ambiguous prefix '{conv_id}', matches:")
                        for m in matches[:5]:
                            print(f"  {m.id[:12]}... {m.title or '(untitled)'}")
                        return
                    else:
                        print(f"No conversation found with prefix: {conv_id}")
                        return

            # Load graph
            graph_metadata = self.db.get_current_graph()
            if not graph_metadata:
                print("Error: No graph found. Run 'net links' first.")
                return

            G = load_graph_from_file(graph_metadata['graph_file_path'])

            if conv_id not in G:
                print(f"Conversation {conv_id[:8]}... not in graph")
                return

            # Get neighbors
            import networkx as nx
            if depth == 1:
                neighbors = set(G.neighbors(conv_id))
            else:
                neighbors = set()
                current_level = {conv_id}
                for _ in range(depth):
                    next_level = set()
                    for node in current_level:
                        next_level.update(G.neighbors(node))
                    neighbors.update(next_level)
                    current_level = next_level - {conv_id}
                neighbors.discard(conv_id)

            source_conv = self.db.load_conversation(conv_id)
            source_title = source_conv.title if source_conv else "(untitled)"

            print(f"\nNeighbors of: {source_title} ({conv_id[:8]}...)")
            print(f"Depth: {depth}, Found: {len(neighbors)}\n")

            if not neighbors:
                print("No neighbors found")
                return

            # Display with weights
            neighbor_data = []
            for nid in neighbors:
                conv = self.db.load_conversation(nid)
                title = conv.title if conv else "(untitled)"
                weight = G[conv_id][nid].get('weight', 0) if G.has_edge(conv_id, nid) else 0
                neighbor_data.append((nid, title, weight))

            neighbor_data.sort(key=lambda x: x[2], reverse=True)

            for nid, title, weight in neighbor_data[:20]:
                weight_str = f"{weight:.3f}" if weight > 0 else "-"
                print(f"  {nid[:8]}... [{weight_str}] {title[:45]}")

            if len(neighbors) > 20:
                print(f"\n... and {len(neighbors) - 20} more")

        elif subcmd == 'path':
            from ctk.core.network_analysis import load_graph_from_file
            # Parse source and target
            if not subargs or len(subargs.split()) < 2:
                print("Error: path requires source and target IDs")
                print("Usage: net path <source> <target>")
                return

            parts = subargs.split()
            source_arg = parts[0]
            target_arg = parts[1]

            # Resolve prefixes
            from ctk.core.vfs import VFSPathParser
            chats_path = VFSPathParser.parse('/chats')

            source_id = source_arg
            if len(source_arg) < 36:
                try:
                    resolved = self.navigator.resolve_prefix(source_arg, chats_path)
                    if resolved:
                        source_id = resolved
                except Exception:
                    pass

            target_id = target_arg
            if len(target_arg) < 36:
                try:
                    resolved = self.navigator.resolve_prefix(target_arg, chats_path)
                    if resolved:
                        target_id = resolved
                except Exception:
                    pass

            # Load graph
            graph_metadata = self.db.get_current_graph()
            if not graph_metadata:
                print("Error: No graph found. Run 'net links' first.")
                return

            G = load_graph_from_file(graph_metadata['graph_file_path'])

            if source_id not in G:
                print(f"Source {source_id[:8]}... not in graph")
                return
            if target_id not in G:
                print(f"Target {target_id[:8]}... not in graph")
                return

            # Find path
            import networkx as nx
            try:
                path = nx.shortest_path(G, source_id, target_id)
            except nx.NetworkXNoPath:
                print("No path exists between these conversations")
                return

            print(f"\nPath found with {len(path)} steps:\n")

            for i, cid in enumerate(path):
                conv = self.db.load_conversation(cid)
                title = conv.title if conv else "(untitled)"
                marker = "●" if i == 0 or i == len(path) - 1 else "○"
                prefix = "→ " if i > 0 else "  "
                print(f"{prefix}{marker} {cid[:8]}... {title[:50]}")

                if i < len(path) - 1:
                    next_id = path[i + 1]
                    if G.has_edge(cid, next_id):
                        weight = G[cid][next_id].get('weight', 0)
                        print(f"     similarity: {weight:.3f}")

        elif subcmd == 'central':
            from ctk.core.network_analysis import load_graph_from_file
            # Parse options
            metric = 'degree'
            top_k = 10

            if subargs:
                arg_parts = subargs.split()
                i = 0
                while i < len(arg_parts):
                    arg = arg_parts[i]
                    if arg == '--metric' and i + 1 < len(arg_parts):
                        metric = arg_parts[i + 1]
                        i += 2
                    elif arg == '--top-k' and i + 1 < len(arg_parts):
                        try:
                            top_k = int(arg_parts[i + 1])
                        except ValueError:
                            print("Error: --top-k must be an integer")
                            return
                        i += 2
                    else:
                        i += 1

            # Load graph
            graph_metadata = self.db.get_current_graph()
            if not graph_metadata:
                print("Error: No graph found. Run 'net links' first.")
                return

            G = load_graph_from_file(graph_metadata['graph_file_path'])

            print(f"Computing {metric} centrality...")

            import networkx as nx
            if metric == 'degree':
                centrality = nx.degree_centrality(G)
            elif metric == 'betweenness':
                centrality = nx.betweenness_centrality(G)
            elif metric == 'pagerank':
                centrality = nx.pagerank(G)
            elif metric == 'eigenvector':
                try:
                    centrality = nx.eigenvector_centrality(G, max_iter=1000)
                except nx.PowerIterationFailedConvergence:
                    print("Eigenvector centrality failed, using degree")
                    centrality = nx.degree_centrality(G)
            else:
                print(f"Unknown metric: {metric}")
                return

            sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)

            print(f"\nTop {top_k} by {metric} centrality:\n")

            for i, (cid, score) in enumerate(sorted_nodes[:top_k], 1):
                conv = self.db.load_conversation(cid)
                title = conv.title if conv else "(untitled)"
                print(f"  {i:2}. [{score:.4f}] {cid[:8]}... {title[:45]}")

        elif subcmd == 'outliers':
            from ctk.core.network_analysis import load_graph_from_file
            # Parse options
            top_k = 10

            if subargs:
                arg_parts = subargs.split()
                i = 0
                while i < len(arg_parts):
                    arg = arg_parts[i]
                    if arg == '--top-k' and i + 1 < len(arg_parts):
                        try:
                            top_k = int(arg_parts[i + 1])
                        except ValueError:
                            print("Error: --top-k must be an integer")
                            return
                        i += 2
                    else:
                        i += 1

            # Load graph
            graph_metadata = self.db.get_current_graph()
            if not graph_metadata:
                print("Error: No graph found. Run 'net links' first.")
                return

            G = load_graph_from_file(graph_metadata['graph_file_path'])

            import networkx as nx
            centrality = nx.degree_centrality(G)
            sorted_nodes = sorted(centrality.items(), key=lambda x: x[1])

            print(f"\nTop {top_k} outliers (least connected):\n")

            for i, (cid, score) in enumerate(sorted_nodes[:top_k], 1):
                conv = self.db.load_conversation(cid)
                title = conv.title if conv else "(untitled)"
                degree = G.degree(cid)
                print(f"  {i:2}. [degree={degree}] {cid[:8]}... {title[:45]}")

            isolated = list(nx.isolates(G))
            if isolated:
                print(f"\nFound {len(isolated)} completely isolated nodes")

        else:
            print(f"Unknown net subcommand: {subcmd}")
            print("Available: embeddings, similar, links, network, clusters, neighbors, path, central, outliers")

    # ==================== VFS Command Handlers ====================

    def _ensure_vfs_navigator(self):
        """Lazy initialize VFS navigator"""
        if self.vfs_navigator is None:
            if not self.db:
                raise ValueError("Database required for VFS commands")
            from ctk.core.vfs_navigator import VFSNavigator

            self.vfs_navigator = VFSNavigator(self.db)

    def handle_cd(self, args: str):
        """Handle /cd command"""
        if not self.db:
            print("Error: Database required for VFS commands")
            return

        self._ensure_vfs_navigator()

        from ctk.core.vfs import VFSPathParser

        # Default to "/" if no args
        path = args.strip() if args else "/"

        # Try normal path parsing FIRST
        try:
            # Parse path
            vfs_path = VFSPathParser.parse(path, self.vfs_cwd)

            # Check if it's a directory
            if not vfs_path.is_directory:
                print(f"Error: Not a directory: {vfs_path.normalized_path}")
                return

            # Special case: Try prefix resolution for ID-like paths
            # Handles both:
            #   - Single segment: "cd fb70" from /chats/
            #   - Multi-segment: "cd chats/fb70" from /

            # Extract the last segment and check if it looks like a conversation ID
            path_segments = path.rstrip('/').split('/')
            last_segment = path_segments[-1] if path_segments else ''

            # Check if we're navigating to a conversation directory
            target_in_conv_dir = (vfs_path.normalized_path.startswith('/chats/') or
                                  vfs_path.normalized_path.startswith('/starred/') or
                                  vfs_path.normalized_path.startswith('/pinned/') or
                                  vfs_path.normalized_path.startswith('/archived/') or
                                  vfs_path.normalized_path.startswith('/tags/') or
                                  vfs_path.normalized_path.startswith('/recent/') or
                                  vfs_path.normalized_path.startswith('/source/') or
                                  vfs_path.normalized_path.startswith('/model/'))

            # Check if last segment looks like an ID (3+ chars, alphanumeric with dashes)
            looks_like_id = (len(last_segment) >= 3 and
                            last_segment.replace('-', '').replace('_', '').isalnum())

            if target_in_conv_dir and looks_like_id:
                # Get the parent directory for prefix resolution
                parent_path = '/'.join(vfs_path.normalized_path.rstrip('/').split('/')[:-1]) or '/'

                try:
                    # Try prefix resolution in the parent directory
                    parent_vfs = VFSPathParser.parse(parent_path)
                    resolved_id = self.vfs_navigator.resolve_prefix(last_segment, parent_vfs)

                    if resolved_id:
                        # Prefix resolution succeeded - navigate to resolved conversation
                        self.vfs_cwd = VFSPathParser.parse(f"{parent_path}/{resolved_id}").normalized_path
                        print(f"Resolved '{last_segment}' to: {resolved_id}")
                        return
                except ValueError as prefix_error:
                    # Prefix resolution failed
                    # Check if parent is an ID-only directory
                    in_id_only_dir = parent_path in ['/chats', '/starred', '/pinned', '/archived']

                    if in_id_only_dir:
                        # In ID-only directories, show the prefix error and stop
                        print(f"Error: {prefix_error}")
                        return
                    # Else fall through to normal parsing (for tags, recent, etc.)

            # Change directory using normal parsing result
            self.vfs_cwd = vfs_path.normalized_path
            # print(f"Changed to: {self.vfs_cwd}")  # Optional confirmation

        except ValueError as parse_error:
            # Normal parsing failed - try prefix resolution for conversation IDs
            # Only try if path looks like an ID (no slashes, alphanumeric with dashes, at least 3 chars)
            if '/' not in path and len(path) >= 3 and path.replace('-', '').replace('_', '').isalnum():
                try:
                    # Try to resolve as prefix in current directory
                    current_path = VFSPathParser.parse(self.vfs_cwd)
                    resolved_id = self.vfs_navigator.resolve_prefix(path, current_path)

                    if resolved_id:
                        # Successfully resolved - navigate to conversation
                        self.vfs_cwd = VFSPathParser.parse(resolved_id, self.vfs_cwd).normalized_path
                        print(f"Resolved '{path}' to: {resolved_id}")
                        return
                except ValueError as prefix_error:
                    # Prefix resolution also failed
                    # Check if we're in a directory where only conversation IDs are valid
                    # (like /chats/, /starred/, /pinned/, etc.)
                    # Note: Root / is NOT in this list because it has named directories
                    in_id_only_dir = self.vfs_cwd in ['/chats', '/starred', '/pinned', '/archived'] or \
                                     self.vfs_cwd.startswith('/source/') or \
                                     self.vfs_cwd.startswith('/model/') or \
                                     self.vfs_cwd.startswith('/tags/') or \
                                     self.vfs_cwd.startswith('/recent/')

                    if in_id_only_dir:
                        # In a directory where only IDs are expected - show prefix error
                        print(f"Error: {prefix_error}")
                        return

            # Show original parsing error
            print(f"Error: {parse_error}")
        except Exception as e:
            print(f"Error changing directory: {e}")

    def handle_pwd(self):
        """Handle /pwd command"""
        print(self.vfs_cwd)

    def handle_ls(self, args: str):
        """Handle /ls command"""
        if not self.db:
            print("Error: Database required for VFS commands")
            return

        self._ensure_vfs_navigator()

        from ctk.core.vfs import VFSPathParser
        from rich.table import Table

        # Parse options
        show_long = False
        path = None

        if args:
            parts = args.strip().split()
            for part in parts:
                if part == '-l':
                    show_long = True
                elif not path:
                    path = part

        # Default to current directory
        if not path:
            path = self.vfs_cwd

        try:
            # Parse path
            vfs_path = VFSPathParser.parse(path, self.vfs_cwd)

            # Get directory listing
            entries = self.vfs_navigator.list_directory(vfs_path)

            if not entries:
                print("(empty)")
                return

            # Display entries
            if show_long:
                # Determine if we're listing message nodes
                is_message_listing = any(e.message_id is not None for e in entries)

                # Long format with table
                table = Table(show_header=True, header_style="bold")
                table.add_column("Name")
                table.add_column("Type")

                if is_message_listing:
                    # Message node columns
                    table.add_column("Role")
                    table.add_column("Content Preview")
                    table.add_column("Created")
                else:
                    # Conversation columns
                    table.add_column("Title")
                    table.add_column("Tags")
                    table.add_column("Modified")

                for entry in sorted(entries, key=lambda e: (not e.is_directory, e.name)):
                    entry_type = "dir" if entry.is_directory else "file"

                    name = entry.name
                    if entry.is_directory and not name.endswith('/'):
                        name += "/"

                    if is_message_listing:
                        # Message node display
                        role = entry.role or "unknown"
                        preview = entry.content_preview or ""
                        created = entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else ""

                        # Add indicator if has children (branches)
                        if entry.has_children:
                            name += " *"

                        table.add_row(name, entry_type, role, preview, created)
                    else:
                        # Conversation display
                        title = entry.title or ""
                        if title and len(title) > 40:
                            title = title[:37] + "..."
                        tags = ", ".join(entry.tags[:3]) if entry.tags else ""
                        if entry.tags and len(entry.tags) > 3:
                            tags += f" (+{len(entry.tags)-3})"

                        modified = ""
                        if entry.updated_at:
                            modified = entry.updated_at.strftime("%Y-%m-%d")

                        # Add flags
                        flags = []
                        if entry.starred:
                            flags.append("⭐")
                        if entry.pinned:
                            flags.append("📌")
                        if entry.archived:
                            flags.append("📦")

                        if flags:
                            name = f"{name} {' '.join(flags)}"

                        table.add_row(name, entry_type, title, tags, modified)

                self.console.print(table)
            else:
                # Simple format (like ls)
                # Group by type: directories first, then files
                dirs = [e for e in entries if e.is_directory]
                files = [e for e in entries if not e.is_directory]

                # Print directories
                if dirs:
                    dir_names = [f"{d.name}/" for d in sorted(dirs, key=lambda e: e.name)]
                    print("  ".join(dir_names))

                # Print files
                if files:
                    file_entries = []
                    for f in sorted(files, key=lambda e: e.name):
                        name = f.name
                        # Add flags
                        if f.starred:
                            name += " ⭐"
                        if f.pinned:
                            name += " 📌"
                        if f.archived:
                            name += " 📦"
                        file_entries.append(name)
                    print("  ".join(file_entries))

        except ValueError as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Error listing directory: {e}")
            import traceback
            traceback.print_exc()

    def handle_ln(self, args: str):
        """Handle /ln command - link (add tag)"""
        if not self.db:
            print("Error: Database required for VFS commands")
            return

        self._ensure_vfs_navigator()
        from ctk.core.vfs import VFSPathParser

        # Parse args: /ln <src> <dest>
        parts = args.strip().split(None, 1)
        if len(parts) != 2:
            print("Usage: /ln <src> <dest>")
            print("Example: /ln /chats/abc123 /tags/physics/")
            return

        src_path_str, dest_path_str = parts

        try:
            # Parse source path
            src_path = VFSPathParser.parse(src_path_str, self.vfs_cwd)
            if src_path.is_directory:
                print(f"Error: Source must be a conversation, not a directory: {src_path.normalized_path}")
                return
            if not src_path.conversation_id:
                print(f"Error: Source is not a conversation: {src_path.normalized_path}")
                return

            # Parse destination path
            dest_path = VFSPathParser.parse(dest_path_str, self.vfs_cwd)
            if not dest_path.is_directory:
                print(f"Error: Destination must be a directory: {dest_path.normalized_path}")
                return

            # Only /tags/* is mutable
            if dest_path.path_type.value not in ['tags', 'tag_dir']:
                print(f"Error: Can only link to /tags/* directories (destination is read-only)")
                return

            # Get tag name from destination path
            if dest_path.path_type.value == 'tags':
                print("Error: Must specify a tag name, not just /tags/")
                return

            tag_name = dest_path.tag_path

            # Add tag to conversation
            success = self.db.add_tags(src_path.conversation_id, [tag_name])
            if success:
                print(f"Linked {src_path.conversation_id} -> {tag_name}")
            else:
                print(f"Error: Failed to link conversation")

        except ValueError as e:
            print(f"Error: {e}")

    def handle_cp(self, args: str):
        """Handle /cp command - copy (deep copy with new UUID)"""
        if not self.db:
            print("Error: Database required for VFS commands")
            return

        self._ensure_vfs_navigator()
        from ctk.core.vfs import VFSPathParser

        # Parse args: /cp <src> <dest>
        parts = args.strip().split(None, 1)
        if len(parts) != 2:
            print("Usage: /cp <src> <dest>")
            print("Example: /cp /chats/abc123 /tags/physics/")
            return

        src_path_str, dest_path_str = parts

        try:
            # Parse source path
            src_path = VFSPathParser.parse(src_path_str, self.vfs_cwd)
            if src_path.is_directory:
                print(f"Error: Source must be a conversation, not a directory: {src_path.normalized_path}")
                return
            if not src_path.conversation_id:
                print(f"Error: Source is not a conversation: {src_path.normalized_path}")
                return

            # Parse destination path
            dest_path = VFSPathParser.parse(dest_path_str, self.vfs_cwd)
            if not dest_path.is_directory:
                print(f"Error: Destination must be a directory: {dest_path.normalized_path}")
                return

            # Only /tags/* is mutable
            if dest_path.path_type.value not in ['tags', 'tag_dir']:
                print(f"Error: Can only copy to /tags/* directories (destination is read-only)")
                return

            # Duplicate conversation
            new_id = self.db.duplicate_conversation(src_path.conversation_id)
            if not new_id:
                print(f"Error: Failed to duplicate conversation")
                return

            print(f"Copied conversation -> {new_id}")

            # If destination is a specific tag directory, add the tag
            if dest_path.path_type.value == 'tag_dir':
                tag_name = dest_path.tag_path
                self.db.add_tags(new_id, [tag_name])
                print(f"Tagged with: {tag_name}")

        except ValueError as e:
            print(f"Error: {e}")

    def handle_mv(self, args: str):
        """Handle /mv command - move between tags"""
        if not self.db:
            print("Error: Database required for VFS commands")
            return

        self._ensure_vfs_navigator()
        from ctk.core.vfs import VFSPathParser

        # Parse args: /mv <src> <dest>
        parts = args.strip().split(None, 1)
        if len(parts) != 2:
            print("Usage: /mv <src> <dest>")
            print("Example: /mv /tags/old/abc123 /tags/new/")
            return

        src_path_str, dest_path_str = parts

        try:
            # Parse source path
            src_path = VFSPathParser.parse(src_path_str, self.vfs_cwd)
            if src_path.is_directory:
                print(f"Error: Source must be a conversation, not a directory: {src_path.normalized_path}")
                return
            if not src_path.conversation_id:
                print(f"Error: Source is not a conversation: {src_path.normalized_path}")
                return

            # Source must be from /tags/* to move
            if src_path.path_type.value != 'tag_dir':
                print(f"Error: Can only move from /tags/* (source must be a tagged conversation)")
                return

            # Parse destination path
            dest_path = VFSPathParser.parse(dest_path_str, self.vfs_cwd)
            if not dest_path.is_directory:
                print(f"Error: Destination must be a directory: {dest_path.normalized_path}")
                return

            # Only /tags/* is mutable
            if dest_path.path_type.value not in ['tags', 'tag_dir']:
                print(f"Error: Can only move to /tags/* directories")
                return

            # Get tag names
            old_tag = src_path.tag_path
            if dest_path.path_type.value == 'tags':
                print("Error: Must specify a tag name, not just /tags/")
                return
            new_tag = dest_path.tag_path

            # Remove old tag, add new tag
            removed = self.db.remove_tag(src_path.conversation_id, old_tag)
            if removed:
                added = self.db.add_tags(src_path.conversation_id, [new_tag])
                if added:
                    print(f"Moved {src_path.conversation_id}: {old_tag} -> {new_tag}")
                else:
                    # Rollback - add old tag back
                    self.db.add_tags(src_path.conversation_id, [old_tag])
                    print(f"Error: Failed to add new tag")
            else:
                print(f"Error: Failed to remove old tag")

        except ValueError as e:
            print(f"Error: {e}")

    def handle_rm(self, args: str):
        """Handle /rm command - remove tag or delete conversation"""
        if not self.db:
            print("Error: Database required for VFS commands")
            return

        self._ensure_vfs_navigator()
        from ctk.core.vfs import VFSPathParser

        # Parse args: /rm <path>
        path_str = args.strip()
        if not path_str:
            print("Usage: /rm <path>")
            print("Examples:")
            print("  /rm /tags/physics/abc123  - Remove tag from conversation")
            print("  /rm /chats/abc123         - Delete conversation (with confirmation)")
            return

        try:
            # Parse path
            vfs_path = VFSPathParser.parse(path_str, self.vfs_cwd)

            if vfs_path.is_directory:
                print(f"Error: Cannot remove directory: {vfs_path.normalized_path}")
                print("(Directories are automatically cleaned up when empty)")
                return

            if not vfs_path.conversation_id:
                print(f"Error: Path is not a conversation: {vfs_path.normalized_path}")
                return

            # Two cases:
            # 1. /chats/abc123 - Actually delete conversation (with confirmation)
            # 2. /tags/path/abc123 - Remove tag from conversation

            if vfs_path.path_type.value == 'chats':
                # Confirm deletion
                conv = self.db.get_conversation(vfs_path.conversation_id)
                if not conv:
                    print(f"Error: Conversation not found: {vfs_path.conversation_id}")
                    return

                title = conv.title or vfs_path.conversation_id
                print(f"WARNING: This will permanently delete conversation: {title}")
                confirm = input("Type 'yes' to confirm: ").strip().lower()
                if confirm != 'yes':
                    print("Deletion cancelled")
                    return

                success = self.db.delete_conversation(vfs_path.conversation_id)
                if success:
                    print(f"Deleted conversation: {vfs_path.conversation_id}")
                else:
                    print(f"Error: Failed to delete conversation")

            elif vfs_path.path_type.value == 'tag_dir':
                # Remove tag from conversation
                tag_name = vfs_path.tag_path
                success = self.db.remove_tag(vfs_path.conversation_id, tag_name)
                if success:
                    print(f"Removed tag '{tag_name}' from {vfs_path.conversation_id}")
                else:
                    print(f"Error: Failed to remove tag")

            else:
                print(f"Error: Cannot remove from read-only directory: {vfs_path.normalized_path}")

        except ValueError as e:
            print(f"Error: {e}")

    def handle_mkdir(self, args: str):
        """Handle /mkdir command - create tag hierarchy (conceptual)"""
        if not self.db:
            print("Error: Database required for VFS commands")
            return

        self._ensure_vfs_navigator()
        from ctk.core.vfs import VFSPathParser

        # Parse args: /mkdir <path>
        path_str = args.strip()
        if not path_str:
            print("Usage: /mkdir <path>")
            print("Example: /mkdir /tags/research/ml/transformers/")
            return

        try:
            # Parse path
            vfs_path = VFSPathParser.parse(path_str, self.vfs_cwd)

            # Must be in /tags/*
            if vfs_path.path_type.value not in ['tags', 'tag_dir']:
                print(f"Error: Can only create directories in /tags/*")
                return

            if vfs_path.path_type.value == 'tags':
                print("Note: /tags/ already exists")
                return

            # For /tags/*, the directory is conceptual
            # It will appear when conversations are tagged
            tag_path = vfs_path.tag_path
            print(f"Created tag hierarchy: {tag_path}")
            print("Note: This is conceptual - the directory will appear when conversations are tagged")

        except ValueError as e:
            print(f"Error: {e}")

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
                    if self.mode == 'shell':
                        # Shell mode: [/path] $
                        vfs_pwd = self.vfs_cwd if hasattr(self, 'vfs_cwd') else "/"
                        prompt_text = f"[{vfs_pwd}] $"
                    else:
                        # Chat mode: existing chat prompt
                        user_name = self.current_user or "You"
                        vfs_pwd = self.vfs_cwd if hasattr(self, 'vfs_cwd') and self.vfs_cwd != "/" else ""

                        if self.current_message:
                            current_path = self.get_current_path()
                            position = len(current_path) - 1
                            path_length = len(current_path)
                            prompt_text = f"{user_name} [{position}/{path_length-1}]"

                            # Add branch indicator if at a branching point
                            if self.current_message.children and len(self.current_message.children) > 1:
                                prompt_text += f" ({len(self.current_message.children)} branches)"
                        else:
                            prompt_text = user_name

                        # Add VFS pwd if not at root
                        if vfs_pwd:
                            prompt_text = f"[{vfs_pwd}] {prompt_text}"

                    user_input = self.session.prompt(
                        HTML(f'<prompt>{prompt_text}: </prompt>'),
                        style=self.style
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not user_input:
                    continue

                # Handle OS shell commands (! prefix)
                if user_input.startswith('!'):
                    self.execute_shell_command(user_input[1:])
                    continue

                # Mode-specific input handling
                if self.mode == 'shell':
                    # Shell mode: parse and route commands
                    if self.shell_parser.is_shell_command(user_input):
                        # Parse the command
                        pipeline = self.shell_parser.parse(user_input)

                        # Check for exit command
                        if pipeline.commands and pipeline.commands[0].command.lower() in ['exit', 'quit']:
                            break

                        # Execute through dispatcher if registered
                        if pipeline.commands and self.command_dispatcher.has_command(pipeline.commands[0].command.lower()):
                            result = self.command_dispatcher.execute(pipeline, print_output=True)
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
                                print("Type 'help' for commands, 'say <message>' to chat with LLM")
                    else:
                        # Input doesn't look like a command - show help
                        print(f"Unknown input. Use 'say <message>' to chat with LLM.")
                        print("Type 'help' for available commands.")

                else:
                    # Chat mode: check for /commands
                    if user_input.startswith('/'):
                        command = user_input[1:]  # Remove leading /
                        if command.lower() in ['exit', 'quit']:
                            # Return to shell mode
                            self.mode = 'shell'
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
