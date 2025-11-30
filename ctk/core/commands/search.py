"""
Search command handlers

Implements: find
"""

import re
from typing import List, Dict, Callable, Optional
from ctk.core.command_dispatcher import CommandResult
from ctk.core.vfs_navigator import VFSNavigator
from ctk.core.vfs import PathType, VFSPathParser
from ctk.core.database import ConversationDB


class SearchCommands:
    """Handler for search commands"""

    def __init__(self, db: ConversationDB, navigator: VFSNavigator, tui_instance=None):
        """
        Initialize search command handlers

        Args:
            db: Database instance
            navigator: VFS navigator for path resolution
            tui_instance: Optional TUI instance for current path state
        """
        self.db = db
        self.navigator = navigator
        self.tui = tui_instance

    def cmd_find(self, args: List[str], stdin: str = '') -> CommandResult:
        """
        Find conversations or messages in VFS

        Usage:
            find                        - Find all conversations
            find <path>                 - Find in specific path
            find -name <pattern>        - Find by title/name pattern
            find -content <pattern>     - Find by message content
            find -role <role>           - Find by message role (user/assistant/system)
            find -type d                - Find directories (conversations)
            find -type f                - Find files (messages)
            find /starred -name "test"  - Find in starred conversations with "test" in title
            find -content "error" -i    - Case-insensitive content search
            find -l                     - Long format with metadata table

        Options:
            -name <pattern>     - Match conversation title or message path
            -content <pattern>  - Match message content text
            -role <role>        - Match message role (user, assistant, system)
            -type d|f           - Match type (d=directory/conversation, f=file/message)
            -i                  - Case-insensitive matching
            -limit <n>          - Limit results to n items
            -l                  - Long format: show table with title, model, date

        Args:
            args: Command arguments
            stdin: Standard input (ignored)

        Returns:
            CommandResult with search results
        """
        # Parse arguments
        search_path = None
        name_pattern = None
        content_pattern = None
        role_filter = None
        type_filter = None  # 'd' or 'f'
        case_insensitive = False
        limit = None
        long_format = False

        i = 0
        while i < len(args):
            arg = args[i]

            if arg.startswith('-'):
                if arg == '-name' and i + 1 < len(args):
                    name_pattern = args[i + 1]
                    i += 2
                elif arg == '-content' and i + 1 < len(args):
                    content_pattern = args[i + 1]
                    i += 2
                elif arg == '-role' and i + 1 < len(args):
                    role_filter = args[i + 1].lower()
                    i += 2
                elif arg == '-type' and i + 1 < len(args):
                    type_filter = args[i + 1]
                    i += 2
                elif arg == '-i':
                    case_insensitive = True
                    i += 1
                elif arg == '-l':
                    long_format = True
                    i += 1
                elif arg == '-limit' and i + 1 < len(args):
                    try:
                        limit = int(args[i + 1])
                    except ValueError:
                        return CommandResult(success=False, output="", error=f"find: invalid limit: {args[i + 1]}")
                    i += 2
                else:
                    return CommandResult(success=False, output="", error=f"find: unknown option: {arg}")
            else:
                # This is the search path
                search_path = arg
                i += 1

        # Default to current path if not specified
        if search_path is None:
            search_path = self.tui.vfs_cwd if self.tui else '/'

        # Compile regex patterns
        regex_flags = re.IGNORECASE if case_insensitive else 0
        name_regex = None
        content_regex = None

        try:
            if name_pattern:
                # Convert shell-style wildcards to regex
                regex_pattern = name_pattern.replace('*', '.*').replace('?', '.')
                name_regex = re.compile(regex_pattern, regex_flags)
            if content_pattern:
                content_regex = re.compile(content_pattern, regex_flags)
        except re.error as e:
            return CommandResult(success=False, output="", error=f"find: invalid pattern: {e}")

        # Perform search
        try:
            results = []

            # Parse search path
            parsed_path = VFSPathParser.parse(search_path)

            # Determine what to search based on path type
            if parsed_path.path_type == PathType.ROOT:
                # Search all conversations
                results = self._search_conversations(
                    name_regex, content_regex, role_filter, type_filter, limit
                )
            elif parsed_path.path_type in [PathType.CHATS, PathType.STARRED, PathType.PINNED,
                                           PathType.ARCHIVED, PathType.TAGS, PathType.SOURCE,
                                           PathType.MODEL, PathType.RECENT]:
                # Search conversations in this directory
                entries = self.navigator.list_directory(parsed_path)
                conv_ids = [entry.name for entry in entries if entry.is_directory]

                results = self._search_conversations(
                    name_regex, content_regex, role_filter, type_filter, limit, conv_ids
                )
            elif parsed_path.path_type in [PathType.CONVERSATION_ROOT, PathType.MESSAGE_NODE]:
                # Search within a specific conversation
                conv_id = parsed_path.conversation_id
                results = self._search_in_conversation(
                    conv_id, name_regex, content_regex, role_filter, type_filter, limit
                )
            else:
                return CommandResult(success=False, output="", error=f"find: cannot search in {search_path}")

            # Format output
            if not results:
                return CommandResult(success=True, output="")

            # For long format, display rich table with metadata
            if long_format and type_filter != 'f':
                # Extract conversation IDs from paths
                conv_ids = set()
                for result_path in results:
                    # Extract conversation ID from path like /chats/abc123/ or /chats/abc123/m1/m2
                    parts = result_path.strip('/').split('/')
                    if len(parts) >= 2 and parts[0] == 'chats':
                        conv_ids.add(parts[1])

                # Load conversation summaries from database
                from ctk.core.helpers import format_conversations_table
                all_summaries = self.db.list_conversations()

                # Filter to only the matching conversations
                conversations = [s for s in all_summaries if s.id in conv_ids]

                # Display rich table
                from rich.console import Console
                console = Console()

                # Capture table output to string
                import io
                buffer = io.StringIO()
                temp_console = Console(file=buffer, force_terminal=True)

                format_conversations_table(conversations, show_message_count=False, console=temp_console)
                table_output = buffer.getvalue()

                return CommandResult(success=True, output=table_output)

            # Default format: just paths (good for piping)
            output_lines = []
            for result in results:
                output_lines.append(result)

            output = '\n'.join(output_lines) + '\n'
            return CommandResult(success=True, output=output)

        except Exception as e:
            return CommandResult(success=False, output="", error=f"find: {str(e)}")

    def _search_conversations(
        self,
        name_regex: Optional[re.Pattern],
        content_regex: Optional[re.Pattern],
        role_filter: Optional[str],
        type_filter: Optional[str],
        limit: Optional[int],
        conv_ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        Search conversations

        Args:
            name_regex: Pattern to match conversation title
            content_regex: Pattern to match message content
            role_filter: Filter by message role
            type_filter: 'd' for directories, 'f' for files
            limit: Maximum results
            conv_ids: Optional list of specific conversation IDs to search

        Returns:
            List of result strings (paths)
        """
        results = []

        # Get conversations to search
        if conv_ids:
            conversations = [self.db.load_conversation(cid) for cid in conv_ids]
            conversations = [c for c in conversations if c]  # Filter None
        else:
            # Get all conversations
            all_convs = self.db.list_conversations()
            conversations = [self.db.load_conversation(c.id) for c in all_convs]

        # Search each conversation
        for conv in conversations:
            if limit is not None and len(results) >= limit:
                break

            # Check type filter for conversation (directory)
            if type_filter == 'f':
                continue  # Skip directories if looking for files

            # Check name pattern against title
            if name_regex:
                if not name_regex.search(conv.title or ''):
                    # If searching by name and doesn't match, skip unless also searching content
                    if not content_regex and not role_filter:
                        continue

            # If searching by content or role, need to search messages
            if content_regex or role_filter:
                # Search messages in this conversation
                message_results = self._search_messages_in_conversation(
                    conv, content_regex, role_filter
                )

                # Add message paths to results
                for msg_path in message_results:
                    if limit is not None and len(results) >= limit:
                        break
                    results.append(f"/chats/{conv.id}/{msg_path}")
            else:
                # Just list the conversation
                if not type_filter or type_filter == 'd':
                    results.append(f"/chats/{conv.id}/")

        return results

    def _search_in_conversation(
        self,
        conv_id: str,
        name_regex: Optional[re.Pattern],
        content_regex: Optional[re.Pattern],
        role_filter: Optional[str],
        type_filter: Optional[str],
        limit: Optional[int]
    ) -> List[str]:
        """
        Search within a specific conversation

        Args:
            conv_id: Conversation ID
            name_regex: Pattern to match (not used for messages)
            content_regex: Pattern to match message content
            role_filter: Filter by message role
            type_filter: 'd' for directories, 'f' for files
            limit: Maximum results

        Returns:
            List of result strings (paths)
        """
        results = []

        # Load conversation
        conv = self.db.load_conversation(conv_id)
        if not conv:
            return results

        # Search messages
        message_results = self._search_messages_in_conversation(
            conv, content_regex, role_filter, type_filter
        )

        # Add conversation prefix to paths
        for msg_path in message_results:
            if limit is not None and len(results) >= limit:
                break
            results.append(f"/chats/{conv_id}/{msg_path}")

        return results

    def _search_messages_in_conversation(
        self,
        conv,
        content_regex: Optional[re.Pattern],
        role_filter: Optional[str],
        type_filter: Optional[str] = None
    ) -> List[str]:
        """
        Search messages within a conversation

        Args:
            conv: ConversationTree object
            content_regex: Pattern to match message content
            role_filter: Filter by message role
            type_filter: 'd' for directories, 'f' for files

        Returns:
            List of message paths (e.g., "m1/m2/m3")
        """
        from ctk.core.tree import ConversationTreeNavigator

        results = []
        nav = ConversationTreeNavigator(conv)

        # Helper to build path string
        def get_message_path(msg) -> str:
            """Get path from root to message as m1/m2/m3 format"""
            path_msgs = msg.get_path_to_root()
            # Skip system messages at root if they're empty
            if path_msgs and path_msgs[0].role.value == 'system' and not path_msgs[0].content.strip():
                path_msgs = path_msgs[1:]

            # Convert to m1/m2/m3 format
            # Need to track sibling indices
            path_parts = []
            for i, msg_in_path in enumerate(path_msgs):
                if i == 0:
                    # Root level - find index in root_message_ids
                    try:
                        idx = conv.root_message_ids.index(msg_in_path.id) + 1
                        path_parts.append(f"m{idx}")
                    except ValueError:
                        pass
                else:
                    # Child level - find index in parent's children
                    parent = path_msgs[i - 1]
                    children = conv.get_children(parent.id)
                    child_ids = [c.id for c in children]
                    try:
                        idx = child_ids.index(msg_in_path.id) + 1
                        path_parts.append(f"m{idx}")
                    except ValueError:
                        pass

            return '/'.join(path_parts) if path_parts else ''

        # Search all messages
        for msg in nav.message_map.values():
            # Check type filter
            if type_filter == 'd':
                continue  # Messages are files, not directories

            # Check role filter
            if role_filter:
                if msg.role.value.lower() != role_filter:
                    continue

            # Check content pattern
            if content_regex:
                content = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)
                if not content_regex.search(content):
                    continue

            # Message matches - add its path
            msg_path = get_message_path(msg)
            if msg_path:
                results.append(msg_path)

        return results


def create_search_commands(db: ConversationDB, navigator: VFSNavigator, tui_instance=None) -> Dict[str, Callable]:
    """
    Create search command handlers

    Args:
        db: Database instance
        navigator: VFS navigator
        tui_instance: Optional TUI instance for current path state

    Returns:
        Dictionary mapping command names to handlers
    """
    search = SearchCommands(db, navigator, tui_instance)

    return {
        'find': search.cmd_find,
    }
