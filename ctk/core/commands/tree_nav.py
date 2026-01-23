"""
Tree navigation commands for shell mode.

Commands for navigating branching conversation trees:
- fork: Fork conversation at a message
- fork-id: Fork by message ID
- branch: Create a branch at current position
- merge: Merge another conversation
- goto-longest: Navigate to longest path
- goto-latest: Navigate to latest leaf
- where: Show current position
- alternatives: Show alternative branches
- rollback: Undo messages
- split: Split conversation at a message
- prune: Remove a subtree
- keep-path: Keep only one path
"""

from typing import Any, Callable, Dict, Optional

from ctk.core.command_dispatcher import CommandResult


def create_tree_nav_commands(
    db=None,
    tui_instance=None,
) -> Dict[str, Callable]:
    """
    Create tree navigation command handlers.

    Args:
        db: Database instance (optional)
        tui_instance: TUI instance for access to conversation tree

    Returns:
        Dictionary mapping command names to handler functions
    """

    def cmd_fork(args: str) -> CommandResult:
        """Fork conversation at a message number.

        Usage: fork <message_number>

        Creates a branch in the conversation tree at the specified message.
        Allows exploring alternative conversation paths.

        Examples:
            fork 3          Fork at message 3
            fork 0          Fork at the beginning
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(success=False, output="", error="fork requires a message number")

        try:
            msg_num = int(args.strip())
            tui_instance.fork_conversation(msg_num)
            return CommandResult(success=True, output="")
        except ValueError:
            return CommandResult(success=False, output="", error=f"Invalid message number: {args}")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Fork error: {e}")

    def cmd_fork_id(args: str) -> CommandResult:
        """Fork conversation at a message by ID.

        Usage: fork-id <message_id>

        Creates a branch at the message with the specified ID (full or partial).
        Use 'where' to see current message IDs.

        Examples:
            fork-id abc123    Fork at message with ID starting with abc123
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="fork-id requires a message ID (full or partial)"
            )

        try:
            tui_instance.fork_conversation_by_id(args.strip())
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Fork error: {e}")

    def cmd_branch(args: str) -> CommandResult:
        """Create a branch at current position.

        Usage: branch

        Creates a new branch at the current message position.
        The next message you send will be on the new branch.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        try:
            tui_instance.branch_conversation()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Branch error: {e}")

    def cmd_merge(args: str) -> CommandResult:
        """Merge another conversation into current.

        Usage: merge <conversation_id> [insert_at]

        Merges messages from another conversation into the current one.
        Optionally specify where to insert (message number).

        Examples:
            merge abc123        Merge conversation abc123 at end
            merge abc123 5      Insert at message 5
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(success=False, output="", error="merge requires a conversation ID")

        parts = args.split(maxsplit=1)
        conv_id = parts[0]
        insert_at = None
        if len(parts) > 1:
            try:
                insert_at = int(parts[1])
            except ValueError:
                return CommandResult(
                    success=False,
                    output="",
                    error=f"Invalid message number: {parts[1]}"
                )

        try:
            tui_instance.merge_conversation(conv_id, insert_at)
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Merge error: {e}")

    def cmd_goto_longest(args: str) -> CommandResult:
        """Navigate to the longest path in the tree.

        Usage: goto-longest

        Moves the current position to the leaf of the longest path
        in the conversation tree.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        try:
            tui_instance.goto_longest_path()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Navigation error: {e}")

    def cmd_goto_latest(args: str) -> CommandResult:
        """Navigate to the most recently added message.

        Usage: goto-latest

        Moves to the leaf with the most recent timestamp
        in the conversation tree.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        try:
            tui_instance.goto_latest_leaf()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Navigation error: {e}")

    def cmd_where(args: str) -> CommandResult:
        """Show current position in conversation tree.

        Usage: where

        Displays your current position in the conversation tree,
        including message ID, depth, and branch information.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        try:
            tui_instance.show_current_position()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error showing position: {e}")

    def cmd_alternatives(args: str) -> CommandResult:
        """Show alternative branches at current position.

        Usage: alternatives

        Lists sibling messages (alternative responses) at the
        current position in the tree.
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        try:
            tui_instance.show_alternatives()
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error showing alternatives: {e}")

    def cmd_rollback(args: str) -> CommandResult:
        """Undo recent messages.

        Usage: rollback [n]

        Removes the last n exchanges (user + assistant pairs).
        Default is 1 exchange (2 messages).

        Examples:
            rollback        Remove last exchange
            rollback 3      Remove last 3 exchanges
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")

        n = 1
        if args:
            try:
                n = int(args.strip())
            except ValueError:
                return CommandResult(success=False, output="", error=f"Invalid number: {args}")

        try:
            tui_instance.rollback(n)
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Rollback error: {e}")

    def cmd_split(args: str) -> CommandResult:
        """Split conversation at a message.

        Usage: split <message_number>

        Creates a new conversation starting from the specified message.
        The original conversation keeps messages up to that point.

        Examples:
            split 5         Split at message 5
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(success=False, output="", error="split requires a message number")

        try:
            msg_num = int(args.strip())
            tui_instance.split_conversation(msg_num)
            return CommandResult(success=True, output="")
        except ValueError:
            return CommandResult(success=False, output="", error=f"Invalid message number: {args}")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Split error: {e}")

    def cmd_prune(args: str) -> CommandResult:
        """Remove a subtree from the conversation.

        Usage: prune <message_id>

        Removes the message with the specified ID and all its descendants.
        Use with caution - this cannot be undone.

        Examples:
            prune abc123    Remove message abc123 and its children
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(success=False, output="", error="prune requires a message ID")

        try:
            tui_instance.prune_subtree(args.strip())
            return CommandResult(success=True, output="")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Prune error: {e}")

    def cmd_keep_path(args: str) -> CommandResult:
        """Keep only one path, removing other branches.

        Usage: keep-path <path_number>

        Simplifies the conversation tree by keeping only the specified
        path and removing all other branches.

        Examples:
            keep-path 0     Keep path 0, remove all others
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(success=False, output="", error="keep-path requires a path number")

        try:
            path_num = int(args.strip())
            tui_instance.keep_path(path_num)
            return CommandResult(success=True, output="")
        except ValueError:
            return CommandResult(success=False, output="", error=f"Invalid path number: {args}")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Keep-path error: {e}")

    def cmd_show_message(args: str) -> CommandResult:
        """Show a specific message by number.

        Usage: show-message <message_number>

        Displays the content of a specific message in the current path.

        Examples:
            show-message 3    Show message 3
        """
        if not tui_instance:
            return CommandResult(success=False, output="", error="TUI not available")
        if not args:
            return CommandResult(
                success=False,
                output="",
                error="show-message requires a message number"
            )

        try:
            msg_num = int(args.strip())
            tui_instance.show_message(msg_num)
            return CommandResult(success=True, output="")
        except ValueError:
            return CommandResult(success=False, output="", error=f"Invalid message number: {args}")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Error showing message: {e}")

    return {
        "fork": cmd_fork,
        "fork-id": cmd_fork_id,
        "branch": cmd_branch,
        "merge": cmd_merge,
        "goto-longest": cmd_goto_longest,
        "goto-latest": cmd_goto_latest,
        "where": cmd_where,
        "alternatives": cmd_alternatives,
        "rollback": cmd_rollback,
        "split": cmd_split,
        "prune": cmd_prune,
        "keep-path": cmd_keep_path,
        "show-message": cmd_show_message,
    }
