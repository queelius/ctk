"""
Shell completer for VFS paths and commands.

Provides tab completion for:
- Shell commands (cd, ls, cat, etc.)
- VFS paths (slugs, UUIDs, virtual directories)
"""

from typing import Iterable, Optional, List, Tuple, Dict
from time import time
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


class ShellCompleter(Completer):
    """
    Tab completer for shell commands and VFS paths.

    Supports:
    - Command completion at start of line
    - Path completion after commands like cd, ls, cat
    - Slug and UUID prefix matching for conversations

    Uses caching to avoid repeated database queries during typing.
    """

    # Commands that take path arguments
    PATH_COMMANDS = {
        'cd', 'ls', 'cat', 'head', 'tail', 'tree', 'paths',
        'star', 'unstar', 'pin', 'unpin', 'archive', 'unarchive',
        'title', 'delete', 'duplicate', 'tag', 'untag', 'export',
        'show', 'chat',
    }

    # All known commands
    ALL_COMMANDS = {
        # Navigation
        'cd', 'ls', 'pwd',
        # Unix-like
        'cat', 'head', 'tail', 'echo', 'grep',
        # Search
        'find',
        # Visualization
        'tree', 'paths',
        # Organization
        'star', 'unstar', 'pin', 'unpin', 'archive', 'unarchive',
        'title', 'delete', 'duplicate', 'tag', 'untag', 'export',
        # Chat
        'chat', 'complete',
        # Settings
        'set', 'get',
        # Built-in
        'help', 'exit', 'quit', 'clear',
    }

    # Cache TTL in seconds
    CACHE_TTL = 10.0

    def __init__(self, tui_instance=None):
        """
        Initialize completer.

        Args:
            tui_instance: TUI instance for accessing VFS navigator and database
        """
        self.tui = tui_instance
        # Cache: parent_path -> (timestamp, entries)
        self._cache: Dict[str, Tuple[float, List]] = {}

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Generate completions for the current input."""
        text = document.text_before_cursor

        # Split into words
        words = text.split()

        if not words:
            # Empty input - complete commands
            yield from self._complete_commands('')
            return

        # Check if we're completing the first word (command)
        if len(words) == 1 and not text.endswith(' '):
            # Completing command name
            yield from self._complete_commands(words[0])
            return

        # We have a command - check if it takes path arguments
        command = words[0]
        if command in self.PATH_COMMANDS:
            # Get the partial path being typed
            if text.endswith(' '):
                partial = ''
            else:
                partial = words[-1]

            yield from self._complete_paths(partial)

    def _complete_commands(self, prefix: str) -> Iterable[Completion]:
        """Complete command names."""
        prefix_lower = prefix.lower()
        for cmd in sorted(self.ALL_COMMANDS):
            if cmd.startswith(prefix_lower):
                yield Completion(
                    cmd,
                    start_position=-len(prefix),
                    display_meta='command'
                )

    def _get_cached_entries(self, parent_path: str) -> List:
        """Get directory entries with caching."""
        now = time()

        # Check local cache first
        if parent_path in self._cache:
            cached_time, cached_entries = self._cache[parent_path]
            if now - cached_time < self.CACHE_TTL:
                return cached_entries

        # Cache miss - fetch from navigator (which has its own cache)
        from ctk.core.vfs import VFSPathParser
        parsed = VFSPathParser.parse(parent_path)
        entries = self.tui.vfs_navigator.list_directory(parsed)

        # Store in local cache
        self._cache[parent_path] = (now, entries)
        return entries

    def clear_cache(self):
        """Clear the completer's cache."""
        self._cache.clear()

    def _complete_paths(self, partial: str) -> Iterable[Completion]:
        """Complete VFS paths including slugs."""
        if not self.tui or not self.tui.vfs_navigator:
            return

        try:
            # Determine parent path and prefix to match
            if partial.startswith('/'):
                # Absolute path
                if '/' in partial[1:]:
                    # Has directory component
                    last_slash = partial.rfind('/')
                    parent_path = partial[:last_slash] or '/'
                    prefix = partial[last_slash + 1:]
                else:
                    # Just starting from root
                    parent_path = '/'
                    prefix = partial[1:]
            else:
                # Relative path
                parent_path = self.tui.vfs_cwd
                prefix = partial

            # Fast path: Use index for /chats completions
            if parent_path == '/chats' or parent_path == '/chats/':
                yield from self._complete_from_index(prefix, partial.startswith('/'))
                return

            # Standard path: Get entries with caching
            entries = self._get_cached_entries(parent_path)

            # Generate completions
            for entry in entries:
                # Build possible match strings
                matches = []

                # Primary: slug (if available)
                if entry.slug:
                    matches.append((entry.slug, 'slug'))

                # Secondary: UUID prefix
                if entry.conversation_id:
                    # Get UUID prefix length from settings
                    uuid_len = getattr(self.tui, 'uuid_prefix_len', 8)
                    uuid_prefix = entry.conversation_id[:uuid_len]
                    matches.append((uuid_prefix, 'uuid'))
                    # Also match full UUID
                    matches.append((entry.conversation_id, 'full-uuid'))

                # Fallback: entry name
                if entry.name and not entry.conversation_id:
                    matches.append((entry.name, 'name'))

                # Check each match
                prefix_lower = prefix.lower()
                for match_text, match_type in matches:
                    if match_text.lower().startswith(prefix_lower):
                        # Build display text
                        if entry.is_directory:
                            display = match_text + '/'
                        else:
                            display = match_text

                        # Build completion text
                        if partial.startswith('/'):
                            # Absolute path - include parent
                            if parent_path == '/':
                                completion = '/' + match_text
                            else:
                                completion = parent_path + '/' + match_text
                            if entry.is_directory:
                                completion += '/'
                        else:
                            # Relative path
                            completion = match_text
                            if entry.is_directory:
                                completion += '/'

                        # Create completion
                        yield Completion(
                            completion,
                            start_position=-len(partial),
                            display=display,
                            display_meta=match_type
                        )
                        break  # Only yield one completion per entry

        except Exception:
            # Silently fail on completion errors
            pass

    def _complete_from_index(self, prefix: str, is_absolute: bool) -> Iterable[Completion]:
        """
        Complete conversation identifiers using ConversationIndex.

        O(1) for exact matches, O(k) for prefix matches where k = number of matches.
        Much faster than loading all conversations via list_directory().

        Args:
            prefix: Prefix to match (slug or ID)
            is_absolute: Whether this is an absolute path (starts with /)
        """
        try:
            # Get completions from the index
            index = self.tui.vfs_navigator.index
            completions = index.get_completions(prefix, limit=20)

            # Get UUID prefix length setting
            uuid_len = getattr(self.tui, 'uuid_prefix_len', 8)

            for display_text, conv_id, slug in completions:
                # Build completion text
                if is_absolute:
                    completion = '/chats/' + (slug or conv_id[:uuid_len]) + '/'
                else:
                    completion = (slug or conv_id[:uuid_len]) + '/'

                # Determine display and meta
                if slug:
                    display = slug + '/'
                    meta = 'slug'
                else:
                    display = conv_id[:uuid_len] + '/'
                    meta = 'uuid'

                yield Completion(
                    completion,
                    start_position=-len(prefix) if not is_absolute else -(len('/chats/') + len(prefix)),
                    display=display,
                    display_meta=meta
                )
        except Exception:
            # Silently fail on completion errors
            pass


def create_shell_completer(tui_instance=None) -> ShellCompleter:
    """Create a shell completer instance."""
    return ShellCompleter(tui_instance=tui_instance)
