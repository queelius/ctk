"""
Organization command handlers

Implements: star, pin, archive, unstar, unpin, unarchive, title
"""

from typing import Callable, Dict, List

from ctk.core.command_dispatcher import CommandResult
from ctk.core.database import ConversationDB
from ctk.core.vfs import PathType, VFSPathParser
from ctk.core.vfs_navigator import VFSNavigator


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
                if conv_id_or_prefix.startswith("/"):
                    parsed = VFSPathParser.parse(conv_id_or_prefix)
                    if parsed.conversation_id:
                        return (parsed.conversation_id, None)
                    else:
                        return (None, f"Not a conversation path: {conv_id_or_prefix}")
                else:
                    # Try prefix resolution
                    if self.tui:
                        chats_path = VFSPathParser.parse("/chats")
                        try:
                            conv_id = self.navigator.resolve_prefix(
                                conv_id_or_prefix, chats_path
                            )
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

    def cmd_star(self, args: List[str], stdin: str = "") -> CommandResult:
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
            return CommandResult(
                success=True, output=f"Starred conversation: {conv_id[:8]}\n"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"star: {str(e)}")

    def cmd_unstar(self, args: List[str], stdin: str = "") -> CommandResult:
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
            return CommandResult(
                success=True, output=f"Unstarred conversation: {conv_id[:8]}\n"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"unstar: {str(e)}")

    def cmd_pin(self, args: List[str], stdin: str = "") -> CommandResult:
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
            return CommandResult(
                success=True, output=f"Pinned conversation: {conv_id[:8]}\n"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"pin: {str(e)}")

    def cmd_unpin(self, args: List[str], stdin: str = "") -> CommandResult:
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
            return CommandResult(
                success=True, output=f"Unpinned conversation: {conv_id[:8]}\n"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"unpin: {str(e)}")

    def cmd_archive(self, args: List[str], stdin: str = "") -> CommandResult:
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
            return CommandResult(
                success=True, output=f"Archived conversation: {conv_id[:8]}\n"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"archive: {str(e)}")

    def cmd_unarchive(self, args: List[str], stdin: str = "") -> CommandResult:
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
            return CommandResult(
                success=True, output=f"Unarchived conversation: {conv_id[:8]}\n"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"unarchive: {str(e)}")

    def cmd_title(self, args: List[str], stdin: str = "") -> CommandResult:
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
            return CommandResult(
                success=False, output="", error="title: no title provided"
            )

        # Check if first arg is a conversation ID or part of title
        first_arg = args[0]

        # Try to parse as conversation ID/path
        conv_id = None
        title_parts = args

        if first_arg.startswith("/") or len(first_arg) >= 8:
            # Might be a conversation ID
            test_id, error = self._get_conversation_id([first_arg])
            if not error:
                conv_id = test_id
                title_parts = args[1:]
                if not title_parts:
                    return CommandResult(
                        success=False, output="", error="title: no title provided"
                    )

        # If no explicit ID, use current path
        if conv_id is None:
            conv_id, error = self._get_conversation_id([])
            if error:
                return CommandResult(success=False, output="", error=f"title: {error}")

        # Join remaining args as title
        new_title = " ".join(title_parts)

        try:
            success = self.db.update_conversation_metadata(conv_id, title=new_title)
            if success:
                return CommandResult(
                    success=True, output=f"Set title to: {new_title}\n"
                )
            else:
                return CommandResult(
                    success=False, output="", error=f"title: Conversation not found"
                )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"title: {str(e)}")

    def cmd_delete(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Delete a conversation

        Usage:
            delete                  - Delete current conversation
            delete <conv_id>        - Delete specific conversation
            delete -f               - Delete without confirmation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        # Check for force flag
        force = "-f" in args or "--force" in args
        args = [a for a in args if a not in ["-f", "--force"]]

        conv_id, error = self._get_conversation_id(args)
        if error:
            return CommandResult(success=False, output="", error=f"delete: {error}")

        try:
            # Get conversation info for confirmation
            conv = self.db.load_conversation(conv_id)
            if not conv:
                return CommandResult(
                    success=False, output="", error=f"delete: Conversation not found"
                )

            if not force:
                title = conv.title or "Untitled"
                return CommandResult(
                    success=False,
                    output="",
                    error=f"delete: Use -f to confirm deletion of '{title}' ({conv_id[:8]}...)",
                )

            self.db.delete_conversation(conv_id)
            return CommandResult(
                success=True, output=f"Deleted conversation: {conv_id[:8]}\n"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"delete: {str(e)}")

    def cmd_duplicate(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Duplicate a conversation

        Usage:
            duplicate              - Duplicate current conversation
            duplicate <conv_id>    - Duplicate specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        conv_id, error = self._get_conversation_id(args)
        if error:
            return CommandResult(success=False, output="", error=f"duplicate: {error}")

        try:
            new_id = self.db.duplicate_conversation(conv_id)
            if new_id:
                new_conv = self.db.load_conversation(new_id)
                title = new_conv.title if new_conv else "Unknown"
                return CommandResult(
                    success=True,
                    output=f"Duplicated conversation\n  New ID: {new_id[:8]}...\n  Title: {title}\n",
                )
            else:
                return CommandResult(
                    success=False, output="", error="duplicate: Failed to duplicate"
                )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"duplicate: {str(e)}")

    def cmd_tag(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Add tags to a conversation

        Usage:
            tag <tag1,tag2,...>           - Add tags to current conversation
            tag <conv_id> <tag1,tag2,...> - Add tags to specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        if not args:
            return CommandResult(
                success=False, output="", error="tag: no tags provided"
            )

        # Check if first arg is a conversation ID
        first_arg = args[0]
        conv_id = None
        tag_arg = args[0]

        if len(args) > 1 and (first_arg.startswith("/") or len(first_arg) >= 8):
            test_id, error = self._get_conversation_id([first_arg])
            if not error:
                conv_id = test_id
                tag_arg = args[1]

        if conv_id is None:
            conv_id, error = self._get_conversation_id([])
            if error:
                return CommandResult(success=False, output="", error=f"tag: {error}")

        # Parse tags (comma-separated)
        tags = [t.strip() for t in tag_arg.split(",") if t.strip()]
        if not tags:
            return CommandResult(
                success=False, output="", error="tag: no valid tags provided"
            )

        try:
            self.db.add_tags(conv_id, tags)
            return CommandResult(
                success=True,
                output=f"Added tags to {conv_id[:8]}...: {', '.join(tags)}\n",
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"tag: {str(e)}")

    def cmd_untag(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Remove a tag from a conversation

        Usage:
            untag <tag>            - Remove tag from current conversation
            untag <conv_id> <tag>  - Remove tag from specific conversation

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with success status
        """
        if not args:
            return CommandResult(
                success=False, output="", error="untag: no tag provided"
            )

        # Check if first arg is a conversation ID
        first_arg = args[0]
        conv_id = None
        tag = args[0]

        if len(args) > 1 and (first_arg.startswith("/") or len(first_arg) >= 8):
            test_id, error = self._get_conversation_id([first_arg])
            if not error:
                conv_id = test_id
                tag = args[1]

        if conv_id is None:
            conv_id, error = self._get_conversation_id([])
            if error:
                return CommandResult(success=False, output="", error=f"untag: {error}")

        try:
            self.db.remove_tag(conv_id, tag)
            return CommandResult(
                success=True, output=f"Removed tag '{tag}' from {conv_id[:8]}...\n"
            )
        except Exception as e:
            return CommandResult(success=False, output="", error=f"untag: {str(e)}")

    def cmd_export(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Export a conversation

        Usage:
            export                     - Export current conversation as JSON
            export <conv_id>           - Export specific conversation
            export -f json|jsonl|md    - Export in specific format

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with exported content
        """
        import json

        # Parse format flag
        fmt = "json"
        filtered_args = []
        i = 0
        while i < len(args):
            if args[i] in ["-f", "--format"] and i + 1 < len(args):
                fmt = args[i + 1]
                i += 2
            else:
                filtered_args.append(args[i])
                i += 1

        conv_id, error = self._get_conversation_id(filtered_args)
        if error:
            return CommandResult(success=False, output="", error=f"export: {error}")

        try:
            conv = self.db.load_conversation(conv_id)
            if not conv:
                return CommandResult(
                    success=False, output="", error="export: Conversation not found"
                )

            if fmt == "json":
                data = conv.to_dict()
                output = json.dumps(data, indent=2, default=str)

            elif fmt == "jsonl":
                lines = []
                for msg in conv.get_longest_path():
                    role = (
                        msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                    )
                    content = msg.content.text if msg.content else ""
                    lines.append(json.dumps({"role": role, "content": content}))
                output = "\n".join(lines)

            elif fmt in ["md", "markdown"]:
                lines = [f"# {conv.title or 'Untitled'}\n"]
                lines.append(f"**ID:** {conv.id}\n")
                if conv.metadata.model:
                    lines.append(f"**Model:** {conv.metadata.model}\n")
                lines.append("\n---\n")

                for msg in conv.get_longest_path():
                    role = (
                        msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                    )
                    content = msg.content.text if msg.content else ""
                    lines.append(f"\n## {role.upper()}\n\n{content}\n")

                output = "\n".join(lines)

            else:
                return CommandResult(
                    success=False, output="", error=f"export: Unknown format '{fmt}'"
                )

            return CommandResult(success=True, output=output)

        except Exception as e:
            return CommandResult(success=False, output="", error=f"export: {str(e)}")


def create_organization_commands(
    db: ConversationDB, navigator: VFSNavigator, tui_instance=None
) -> Dict[str, Callable]:
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
        "star": org.cmd_star,
        "unstar": org.cmd_unstar,
        "pin": org.cmd_pin,
        "unpin": org.cmd_unpin,
        "archive": org.cmd_archive,
        "unarchive": org.cmd_unarchive,
        "title": org.cmd_title,
        "delete": org.cmd_delete,
        "duplicate": org.cmd_duplicate,
        "tag": org.cmd_tag,
        "untag": org.cmd_untag,
        "export": org.cmd_export,
    }
