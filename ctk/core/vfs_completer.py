"""
VFS Tab Completion for prompt_toolkit.

Provides intelligent tab completion for VFS paths, conversation IDs,
and message nodes.
"""

from typing import Iterable, Optional, List
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from .vfs import VFSPathParser
from .vfs_navigator import VFSNavigator, VFSEntry


class VFSCompleter(Completer):
    """Tab completion for VFS paths (uses navigator's cache)"""

    # Maximum number of completions to show
    MAX_COMPLETIONS = 100

    def __init__(self, navigator: VFSNavigator, get_cwd_func):
        """
        Initialize VFS completer.

        Args:
            navigator: VFSNavigator instance
            get_cwd_func: Function that returns current working directory
        """
        self.navigator = navigator
        self.get_cwd = get_cwd_func

    def clear_cache(self):
        """Clear the completion cache (delegates to navigator)"""
        self.navigator.clear_cache()

    def _get_cached_entries(self, vfs_path) -> Optional[List[VFSEntry]]:
        """
        Get directory entries (uses navigator's cache).

        Args:
            vfs_path: Parsed VFS path

        Returns:
            List of VFSEntry if successful, None otherwise
        """
        try:
            # Navigator has its own caching, so just delegate
            return self.navigator.list_directory(vfs_path)
        except:
            return None

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """
        Generate completions for current input.

        Args:
            document: Current document (contains text before cursor)
            complete_event: Completion event

        Yields:
            Completion objects
        """
        # Get text before cursor
        text_before_cursor = document.text_before_cursor

        # Extract the last word (path component) for completion
        words = text_before_cursor.split()
        if not words:
            return

        # The word we're completing
        current_word = words[-1] if text_before_cursor[-1] != ' ' else ''

        # Determine context - are we completing a command or a path?
        # If first word is a VFS command (cd, ls, etc.), complete paths
        vfs_commands = {'cd', 'ls', 'ln', 'cp', 'mv', 'rm', 'mkdir', 'pwd'}

        if len(words) == 1 and text_before_cursor[-1] != ' ':
            # Completing first word - could be command or chat input
            # Only complete if it looks like a command
            if any(cmd.startswith(current_word.lower()) for cmd in vfs_commands):
                for cmd in sorted(vfs_commands):
                    if cmd.startswith(current_word.lower()):
                        yield Completion(
                            cmd,
                            start_position=-len(current_word),
                            display=cmd,
                            display_meta='command'
                        )
            return

        # Check if we're in a VFS command context
        first_word = words[0].lower()
        if first_word not in vfs_commands:
            return  # Not completing a VFS path

        # Complete VFS path
        try:
            yield from self._complete_path(current_word)
        except:
            pass  # Silently fail on completion errors

    def _complete_path(self, partial_path: str) -> Iterable[Completion]:
        """
        Complete a VFS path.

        Args:
            partial_path: Partial path to complete

        Yields:
            Completion objects
        """
        try:
            cwd = self.get_cwd()

            # Determine the directory to list and the prefix to match
            if '/' in partial_path:
                # Path contains slashes - complete from parent directory
                parts = partial_path.rsplit('/', 1)
                if len(parts) == 2:
                    parent_path, prefix = parts
                    if not parent_path:
                        parent_path = '/'
                else:
                    parent_path = '/'
                    prefix = ''
            else:
                # No slashes - complete from current directory
                parent_path = cwd
                prefix = partial_path

            # Parse parent directory
            try:
                parent_vfs_path = VFSPathParser.parse(parent_path, cwd)
            except:
                return

            # List directory contents (uses navigator's cache)
            entries = self._get_cached_entries(parent_vfs_path)
            if not entries:
                return

            # Generate completions (with limit for performance)
            completion_count = 0
            total_matches = 0

            # First pass: count total matches
            for entry in entries:
                if entry.name.startswith(prefix):
                    total_matches += 1

            # Second pass: generate completions up to limit
            for entry in entries:
                name = entry.name

                # Filter by prefix
                if not name.startswith(prefix):
                    continue

                # Check if we've hit the limit
                if completion_count >= self.MAX_COMPLETIONS:
                    break

                # Determine display info
                if entry.is_directory:
                    display_name = name + '/'
                    meta = 'directory'
                elif entry.conversation_id:
                    display_name = name
                    meta = entry.title[:40] if entry.title else 'conversation'
                else:
                    display_name = name
                    meta = 'file'

                # Add role for message nodes
                if entry.message_id:
                    meta = f"{entry.role}: {entry.content_preview[:30]}" if entry.content_preview else entry.role

                # Calculate replacement
                if '/' in partial_path:
                    # Replace just the last component
                    replacement = name
                else:
                    replacement = name

                yield Completion(
                    replacement,
                    start_position=-len(prefix),
                    display=display_name,
                    display_meta=meta
                )
                completion_count += 1

            # If more matches exist beyond limit, show indicator
            if total_matches > self.MAX_COMPLETIONS:
                remaining = total_matches - self.MAX_COMPLETIONS
                yield Completion(
                    "",
                    start_position=0,
                    display="...",
                    display_meta=f"({remaining} more matches - type more chars to narrow down)"
                )

        except Exception:
            pass  # Silently fail on errors
