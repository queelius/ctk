"""
Database operation commands for shell mode.

Commands:
- save: Save current conversation to database
- load: Load a conversation from database
- search: Search conversations by query
- list: List conversations with filters
"""

from typing import Any, Callable, Dict, Optional

from ctk.core.command_dispatcher import CommandResult


def create_database_commands(
    db=None,
    tui_instance=None,
) -> Dict[str, Callable]:
    """
    Create database operation command handlers.

    Args:
        db: Database instance
        tui_instance: TUI instance for access to conversation state

    Returns:
        Dictionary mapping command names to handler functions
    """

    def cmd_save(args: str) -> CommandResult:
        """Save current conversation to database.

        Usage: save

        Saves the current conversation to the database. Creates a new
        conversation if this is the first save, or updates the existing
        conversation if already saved.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not db:
            return CommandResult(success=False, output="", error="No database configured")
        if not tui_instance.root:
            return CommandResult(success=False, output="", error="No messages to save")

        try:
            # Convert to DB format
            tree = tui_instance.tree_to_conversation_tree()

            # Save to database
            db.save_conversation(tree)
            tui_instance.current_conversation_id = tree.id

            output = f"Conversation saved (ID: {tree.id[:8]}...)\n"
            output += f"  Title: {tree.title}"
            return CommandResult(success=True, output=output)

        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error saving conversation: {e}")

    def cmd_load(args: str) -> CommandResult:
        """Load a conversation from database.

        Usage: load <conversation_id>

        Loads a conversation by its ID (full or partial prefix).
        The current conversation will be replaced.

        Examples:
            load 7c8a9b2e          Load conversation by ID prefix
            load 7c8a9b2e-1234... Load by full ID
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not db:
            return CommandResult(success=False, output="", error="No database configured")
        if not args:
            return CommandResult(success=False, output="", error="load requires a conversation ID")

        conv_id = args.strip()
        try:
            tui_instance.load_conversation(conv_id)
            return CommandResult(
                success=True,
                output=f"Loaded conversation: {tui_instance.conversation_title or conv_id[:8]}"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error loading conversation: {e}")

    def cmd_search(args: str) -> CommandResult:
        """Search conversations by query text.

        Usage: search <query>

        Searches conversation titles and message content for the query.
        Results are displayed in a table format.

        Examples:
            search python          Find conversations mentioning 'python'
            search bug fix         Search for 'bug fix'
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not db:
            return CommandResult(success=False, output="", error="No database configured")
        if not args:
            return CommandResult(success=False, output="", error="search requires a query")

        query = args.strip()
        try:
            # Use TUI's search method which handles formatting
            tui_instance.search_conversations(query)
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Search error: {e}")

    def cmd_list(args: str) -> CommandResult:
        """List conversations with optional filters.

        Usage: list [options]

        Lists conversations from the database. Supports filtering
        by starred, pinned, archived status.

        Options:
            --starred, -s    Show only starred conversations
            --pinned, -p     Show only pinned conversations
            --archived, -a   Show only archived conversations
            --limit N        Limit results to N conversations

        Examples:
            list              List recent conversations
            list --starred    List starred conversations
            list -a           List archived conversations
            list --limit 5    List last 5 conversations
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not db:
            return CommandResult(success=False, output="", error="No database configured")

        try:
            # Parse arguments (TUI's list_conversations handles this)
            tui_instance.list_conversations(args)
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"List error: {e}")

    return {
        "save": cmd_save,
        "load": cmd_load,
        "search": cmd_search,
        "list": cmd_list,
    }
