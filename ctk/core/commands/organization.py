"""
Organization command handlers

Implements: star, pin, archive, unstar, unpin, unarchive, title
"""

from typing import List, Dict, Callable
from ctk.core.command_dispatcher import CommandResult
from ctk.core.vfs_navigator import VFSNavigator
from ctk.core.vfs import VFSPathParser, PathType
from ctk.core.database import ConversationDB


class OrganizationCommands:
    """Handler for conversation organization commands"""

    def __init__(self, db: ConversationDB, navigator: VFSNavigator, tui_instance=None):
        """
        Initialize organization command handlers

        Args:
            db: Database instance
            navigator: VFS navigator
            tui_instance: Optional TUI instance for current path state
        """
        self.db = db
        self.navigator = navigator
        self.tui = tui_instance

    def _get_conversation_id(self, args: List[str]) -> tuple[str, str]:
        """
        Get conversation ID from args or current path

        Returns:
            Tuple of (conv_id, error_message)
        """
        if args:
            # Explicit conversation ID provided
            conv_id_or_prefix = args[0]

            # Try as path first
            try:
                if conv_id_or_prefix.startswith('/'):
                    parsed = VFSPathParser.parse(conv_id_or_prefix)
                    if parsed.conversation_id:
                        return (parsed.conversation_id, None)
                    else:
                        return (None, f"Not a conversation path: {conv_id_or_prefix}")
                else:
                    # Try prefix resolution
                    if self.tui:
                        chats_path = VFSPathParser.parse('/chats')
                        try:
                            conv_id = self.navigator.resolve_prefix(conv_id_or_prefix, chats_path)
                            if conv_id:
                                return (conv_id, None)
                        except ValueError:
                            pass
                    # Use as direct ID
                    return (conv_id_or_prefix, None)
            except Exception as e:
                return (None, f"Invalid path: {e}")
        else:
            # Use current path
            if not self.tui:
                return (None, "No conversation in current context")

            current_path = self.tui.vfs_cwd
            parsed = VFSPathParser.parse(current_path)

            if parsed.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                return (parsed.conversation_id, None)
            else:
                return (None, "Not in a conversation directory")

    def cmd_star(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Star a conversation

        Usage:
            star                - Star current conversation
            star <conv_id>      - Star specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        conv_id, error = self._get_conversation_id(args)
        if error:
            return CommandResult(success=False, output="", error=f"star: {error}")

        # Star the conversation
        try:
            self.db.star_conversation(conv_id)
            return CommandResult(success=True, output=f"Starred conversation: {conv_id[:8]}\n")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"star: {str(e)}")

    def cmd_unstar(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Unstar a conversation

        Usage:
            unstar              - Unstar current conversation
            unstar <conv_id>    - Unstar specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        conv_id, error = self._get_conversation_id(args)
        if error:
            return CommandResult(success=False, output="", error=f"unstar: {error}")

        try:
            self.db.star_conversation(conv_id, star=False)
            return CommandResult(success=True, output=f"Unstarred conversation: {conv_id[:8]}\n")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"unstar: {str(e)}")

    def cmd_pin(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Pin a conversation

        Usage:
            pin                 - Pin current conversation
            pin <conv_id>       - Pin specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        conv_id, error = self._get_conversation_id(args)
        if error:
            return CommandResult(success=False, output="", error=f"pin: {error}")

        try:
            self.db.pin_conversation(conv_id)
            return CommandResult(success=True, output=f"Pinned conversation: {conv_id[:8]}\n")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"pin: {str(e)}")

    def cmd_unpin(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Unpin a conversation

        Usage:
            unpin               - Unpin current conversation
            unpin <conv_id>     - Unpin specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        conv_id, error = self._get_conversation_id(args)
        if error:
            return CommandResult(success=False, output="", error=f"unpin: {error}")

        try:
            self.db.pin_conversation(conv_id, pin=False)
            return CommandResult(success=True, output=f"Unpinned conversation: {conv_id[:8]}\n")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"unpin: {str(e)}")

    def cmd_archive(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Archive a conversation

        Usage:
            archive             - Archive current conversation
            archive <conv_id>   - Archive specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        conv_id, error = self._get_conversation_id(args)
        if error:
            return CommandResult(success=False, output="", error=f"archive: {error}")

        try:
            self.db.archive_conversation(conv_id)
            return CommandResult(success=True, output=f"Archived conversation: {conv_id[:8]}\n")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"archive: {str(e)}")

    def cmd_unarchive(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Unarchive a conversation

        Usage:
            unarchive           - Unarchive current conversation
            unarchive <conv_id> - Unarchive specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        conv_id, error = self._get_conversation_id(args)
        if error:
            return CommandResult(success=False, output="", error=f"unarchive: {error}")

        try:
            self.db.archive_conversation(conv_id, archive=False)
            return CommandResult(success=True, output=f"Unarchived conversation: {conv_id[:8]}\n")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"unarchive: {str(e)}")

    def cmd_title(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Set conversation title

        Usage:
            title <new_title>           - Set title for current conversation
            title <conv_id> <new_title> - Set title for specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        if not args:
            return CommandResult(success=False, output="", error="title: no title provided")

        # Check if first arg is a conversation ID or part of title
        first_arg = args[0]

        # Try to parse as conversation ID/path
        conv_id = None
        title_parts = args

        if first_arg.startswith('/') or len(first_arg) >= 8:
            # Might be a conversation ID
            test_id, error = self._get_conversation_id([first_arg])
            if not error:
                conv_id = test_id
                title_parts = args[1:]
                if not title_parts:
                    return CommandResult(success=False, output="", error="title: no title provided")

        # If no explicit ID, use current path
        if conv_id is None:
            conv_id, error = self._get_conversation_id([])
            if error:
                return CommandResult(success=False, output="", error=f"title: {error}")

        # Join remaining args as title
        new_title = ' '.join(title_parts)

        try:
            success = self.db.update_conversation_metadata(conv_id, title=new_title)
            if success:
                return CommandResult(success=True, output=f"Set title to: {new_title}\n")
            else:
                return CommandResult(success=False, output="", error=f"title: Conversation not found")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"title: {str(e)}")


def create_organization_commands(db: ConversationDB, navigator: VFSNavigator, tui_instance=None) -> Dict[str, Callable]:
    """
    Create organization command handlers

    Args:
        db: Database instance
        navigator: VFS navigator
        tui_instance: Optional TUI instance for current path state

    Returns:
        Dictionary mapping command names to handlers
    """
    org = OrganizationCommands(db, navigator, tui_instance)

    return {
        'star': org.cmd_star,
        'unstar': org.cmd_unstar,
        'pin': org.cmd_pin,
        'unpin': org.cmd_unpin,
        'archive': org.cmd_archive,
        'unarchive': org.cmd_unarchive,
        'title': org.cmd_title,
    }
