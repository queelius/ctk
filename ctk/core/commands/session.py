"""
Session management commands for shell mode.

Commands:
- clear: Clear current conversation
- new-chat: Start a new conversation
- system: Add a system message
- context: Load file as context
- user: Get/set current user name
- stats: Show conversation statistics
"""

from typing import Any, Callable, Dict, Optional

from ctk.core.command_dispatcher import CommandResult


def create_session_commands(
    db=None,
    tui_instance=None,
) -> Dict[str, Callable]:
    """
    Create session management command handlers.

    Args:
        db: Database instance (optional)
        tui_instance: TUI instance for access to conversation state

    Returns:
        Dictionary mapping command names to handler functions
    """

    def cmd_clear(args: str) -> CommandResult:
        """Clear current conversation.

        Usage: clear

        Clears all messages from the current conversation without saving.
        Use 'new-chat' if you want to save first.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        tui_instance.root = None
        tui_instance.current_message = None
        tui_instance.message_map = {}
        tui_instance.current_conversation_id = None
        tui_instance.conversation_title = None
        tui_instance.conversation_model = (
            tui_instance.provider.model if tui_instance.provider else None
        )
        return CommandResult(success=True, output="Conversation cleared")

    def cmd_new_chat(args: str) -> CommandResult:
        """Start a new conversation.

        Usage: new-chat [title]

        Saves the current conversation (if any) and starts fresh.
        Optionally provide a title for the new conversation.

        Examples:
            new-chat                Start new untitled conversation
            new-chat Python Help    Start with title 'Python Help'
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        output_lines = []

        # Save current conversation if it exists and has messages
        if tui_instance.root and db:
            try:
                tree = tui_instance.tree_to_conversation_tree()
                db.save_conversation(tree)
                output_lines.append("Current conversation saved")
            except Exception as e:
                output_lines.append(f"Warning: Could not save current conversation: {e}")

        # Clear current conversation
        tui_instance.root = None
        tui_instance.current_message = None
        tui_instance.message_map = {}
        tui_instance.current_conversation_id = None
        tui_instance.conversation_model = (
            tui_instance.provider.model if tui_instance.provider else None
        )

        # Set new title if provided
        if args:
            tui_instance.conversation_title = args.strip()
            output_lines.append(f"Started new conversation: '{args.strip()}'")
        else:
            tui_instance.conversation_title = None
            output_lines.append("Started new conversation")

        return CommandResult(success=True, output="\n".join(output_lines))

    def cmd_system(args: str) -> CommandResult:
        """Add a system message to the conversation.

        Usage: system <message>

        Adds a system-role message that provides instructions or context
        to the LLM. System messages typically appear at the start of
        conversations and guide the model's behavior.

        Examples:
            system You are a helpful coding assistant
            system Always respond in JSON format
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(success=False, output="", error="system requires a message")

        from ctk.integrations.llm.base import MessageRole as LLMMessageRole

        tui_instance.add_message(LLMMessageRole.SYSTEM, args.strip())
        return CommandResult(
            success=True,
            output=f"System message added: {args.strip()[:50]}..."
        )

    def cmd_context(args: str) -> CommandResult:
        """Load a file's content as context.

        Usage: context <file_path>

        Reads the specified file and adds its content as context
        for the LLM to reference in subsequent messages.

        Examples:
            context main.py              Load Python file
            context ~/docs/notes.md      Load markdown file
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(success=False, output="", error="context requires a file path")

        try:
            tui_instance.load_file_context(args.strip())
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error loading context: {e}")

    def cmd_user(args: str) -> CommandResult:
        """Get or set current user name.

        Usage: user [name]

        Without argument, shows current user name.
        With argument, sets the user name for message attribution.

        Examples:
            user              Show current user
            user Alice        Set user to 'Alice'
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        if not args:
            if tui_instance.current_user:
                return CommandResult(
                    success=True,
                    output=f"Current user: {tui_instance.current_user}"
                )
            else:
                return CommandResult(
                    success=True,
                    output="No user set (messages will have no user attribution)"
                )
        else:
            tui_instance.current_user = args.strip()
            return CommandResult(
                success=True,
                output=f"User set to: {args.strip()}"
            )

    def cmd_stats(args: str) -> CommandResult:
        """Show conversation/database statistics.

        Usage: stats

        Displays statistics about the current conversation and database,
        including message counts, sources, and models.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        try:
            tui_instance.show_stats()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error showing stats: {e}")

    def cmd_project(args: str) -> CommandResult:
        """Get or set project name for current conversation.

        Usage: project [name]

        Without argument, shows current project name.
        With argument, sets the project for organization.

        Examples:
            project               Show current project
            project my-app        Set project to 'my-app'
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        if not args:
            if tui_instance.conversation_project:
                return CommandResult(
                    success=True,
                    output=f"Project: {tui_instance.conversation_project}"
                )
            else:
                return CommandResult(success=True, output="No project set")
        else:
            tui_instance.conversation_project = args.strip()
            return CommandResult(
                success=True,
                output=f"Project set to: {args.strip()}"
            )

    def cmd_history(args: str) -> CommandResult:
        """Show conversation history.

        Usage: history [max_length]

        Displays the current conversation history with message numbers.
        Optionally limit content length for readability.

        Examples:
            history          Show full history
            history 100      Truncate messages to 100 chars
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        max_len = None
        if args:
            try:
                max_len = int(args.strip())
            except ValueError:
                return CommandResult(success=False, output="", error=f"Invalid length: {args}")

        try:
            tui_instance.show_history(max_len)
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error showing history: {e}")

    def cmd_summary(args: str) -> CommandResult:
        """Request a summary of the conversation.

        Usage: summary

        Asks the LLM to generate a summary of the current conversation.
        Useful for long conversations to get an overview.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        try:
            tui_instance.request_summary()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error generating summary: {e}")

    return {
        "clear": cmd_clear,
        "new-chat": cmd_new_chat,
        "system": cmd_system,
        "context": cmd_context,
        "user": cmd_user,
        "stats": cmd_stats,
        "project": cmd_project,
        "history": cmd_history,
        "summary": cmd_summary,
    }
