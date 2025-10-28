"""
Command handlers for CTK operations.

This module contains pure command handlers that execute business logic
without any UI concerns. Both CLI and TUI can use these handlers with
their own formatters for output.

Design:
- Handlers accept dependencies (db, formatter) via parameters
- Return structured data or success/error codes
- No direct I/O or printing (delegated to formatters)
- Reusable across all interfaces (CLI, TUI, REST API, etc.)
"""

from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from ctk.core.database import ConversationDB
from ctk.core.models import ConversationTree


class CommandError(Exception):
    """Raised when a command fails"""
    pass


class ConversationResolver:
    """Resolves conversation IDs, including partial matches"""

    @staticmethod
    def resolve_id(db: ConversationDB, conv_id: str) -> Optional[ConversationTree]:
        """
        Resolve conversation ID (full or partial) to a ConversationTree.

        Args:
            db: Database instance
            conv_id: Full or partial conversation ID

        Returns:
            ConversationTree if exactly one match found, None otherwise

        Raises:
            CommandError: If multiple matches found or no matches found
        """
        # Try exact match first
        tree = db.load_conversation(conv_id)
        if tree:
            return tree

        # Try partial match if ID looks incomplete
        if len(conv_id) < 36:
            all_convs = db.list_conversations(limit=1000)
            matches = [c for c in all_convs if c.id.startswith(conv_id)]

            if len(matches) == 0:
                raise CommandError(f"No conversation found matching '{conv_id}'")
            elif len(matches) > 1:
                match_list = '\n'.join([
                    f"  - {m.id[:8]}... {m.title}"
                    for m in matches[:5]
                ])
                raise CommandError(
                    f"Multiple conversations match '{conv_id}':\n{match_list}\n"
                    f"Please provide more characters to uniquely identify the conversation"
                )
            else:
                # Exactly one match
                return db.load_conversation(matches[0].id)

        # No matches
        raise CommandError(f"Conversation {conv_id} not found")


class ListCommand:
    """List conversations with filtering"""

    @staticmethod
    def execute(
        db: ConversationDB,
        limit: int = 100,
        source: Optional[str] = None,
        model: Optional[str] = None,
        tags: Optional[List[str]] = None,
        archived: Optional[bool] = None,
        starred: Optional[bool] = None,
        pinned: Optional[bool] = None,
        include_archived: bool = False
    ) -> List[Any]:
        """
        List conversations from database.

        Args:
            db: Database instance
            limit: Maximum number of results
            source: Filter by source platform
            model: Filter by model
            tags: Filter by tags list
            archived: Show only archived (True) or non-archived (False)
            starred: Show only starred conversations
            pinned: Show only pinned conversations
            include_archived: Include archived in results

        Returns:
            List of conversation summaries
        """
        filter_args = {
            'limit': limit,
            'source': source,
            'model': model,
            'include_archived': include_archived,
        }

        if tags:
            filter_args['tags'] = tags

        if archived is not None:
            filter_args['archived'] = archived
        if starred is not None:
            filter_args['starred'] = starred
        if pinned is not None:
            filter_args['pinned'] = pinned

        return db.list_conversations(**filter_args)


class SearchCommand:
    """Search conversations"""

    @staticmethod
    def execute(
        db: ConversationDB,
        query_text: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        title_only: bool = False,
        content_only: bool = False,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        source: Optional[str] = None,
        model: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_messages: Optional[int] = None,
        max_messages: Optional[int] = None,
        has_branches: bool = False,
        archived: Optional[bool] = None,
        starred: Optional[bool] = None,
        pinned: Optional[bool] = None,
        include_archived: bool = False,
        order_by: str = 'updated_at',
        ascending: bool = False
    ) -> List[Any]:
        """
        Search conversations with advanced filtering.

        Args:
            db: Database instance
            query_text: Search query
            (other args as per database.search_conversations)

        Returns:
            List of matching conversations
        """
        search_args = {
            'query_text': query_text,
            'limit': limit,
            'offset': offset,
            'title_only': title_only,
            'content_only': content_only,
            'date_from': date_from,
            'date_to': date_to,
            'source': source,
            'model': model,
            'tags': tags,
            'min_messages': min_messages,
            'max_messages': max_messages,
            'has_branches': has_branches,
            'include_archived': include_archived,
            'order_by': order_by,
            'ascending': ascending,
        }

        if archived is not None:
            search_args['archived'] = archived
        if starred is not None:
            search_args['starred'] = starred
        if pinned is not None:
            search_args['pinned'] = pinned

        return db.search_conversations(**search_args)


class DeleteCommand:
    """Delete a conversation"""

    @staticmethod
    def execute(
        db: ConversationDB,
        conv_id: str,
        confirm_fn: Optional[Callable[[ConversationTree], bool]] = None,
        skip_confirmation: bool = False
    ) -> ConversationTree:
        """
        Delete a conversation from database.

        Args:
            db: Database instance
            conv_id: Conversation ID (full or partial)
            confirm_fn: Optional confirmation function that receives ConversationTree
                       and returns True to proceed, False to cancel
            skip_confirmation: If True, skip confirmation

        Returns:
            The deleted ConversationTree

        Raises:
            CommandError: If conversation not found or deletion fails
        """
        # Resolve ID
        tree = ConversationResolver.resolve_id(db, conv_id)

        # Confirm deletion unless skipped
        if not skip_confirmation:
            if confirm_fn:
                if not confirm_fn(tree):
                    raise CommandError("Deletion cancelled")

        # Delete
        success = db.delete_conversation(tree.id)
        if not success:
            raise CommandError("Failed to delete conversation")

        return tree


class ArchiveCommand:
    """Archive/unarchive a conversation"""

    @staticmethod
    def execute(
        db: ConversationDB,
        conv_id: str,
        archive: bool = True
    ) -> ConversationTree:
        """
        Archive or unarchive a conversation.

        Args:
            db: Database instance
            conv_id: Conversation ID (full or partial)
            archive: True to archive, False to unarchive

        Returns:
            The modified ConversationTree

        Raises:
            CommandError: If conversation not found or operation fails
        """
        tree = ConversationResolver.resolve_id(db, conv_id)

        success = db.archive_conversation(tree.id, archive=archive)
        if not success:
            action = "archive" if archive else "unarchive"
            raise CommandError(f"Failed to {action} conversation")

        return tree


class StarCommand:
    """Star/unstar a conversation"""

    @staticmethod
    def execute(
        db: ConversationDB,
        conv_id: str,
        star: bool = True
    ) -> ConversationTree:
        """
        Star or unstar a conversation.

        Args:
            db: Database instance
            conv_id: Conversation ID (full or partial)
            star: True to star, False to unstar

        Returns:
            The modified ConversationTree

        Raises:
            CommandError: If conversation not found or operation fails
        """
        tree = ConversationResolver.resolve_id(db, conv_id)

        success = db.star_conversation(tree.id, star=star)
        if not success:
            action = "star" if star else "unstar"
            raise CommandError(f"Failed to {action} conversation")

        return tree


class PinCommand:
    """Pin/unpin a conversation"""

    @staticmethod
    def execute(
        db: ConversationDB,
        conv_id: str,
        pin: bool = True
    ) -> ConversationTree:
        """
        Pin or unpin a conversation.

        Args:
            db: Database instance
            conv_id: Conversation ID (full or partial)
            pin: True to pin, False to unpin

        Returns:
            The modified ConversationTree

        Raises:
            CommandError: If conversation not found or operation fails
        """
        tree = ConversationResolver.resolve_id(db, conv_id)

        success = db.pin_conversation(tree.id, pin=pin)
        if not success:
            action = "pin" if pin else "unpin"
            raise CommandError(f"Failed to {action} conversation")

        return tree


class ShowCommand:
    """Show a specific conversation"""

    @staticmethod
    def execute(
        db: ConversationDB,
        conv_id: str
    ) -> ConversationTree:
        """
        Load and return a conversation.

        Args:
            db: Database instance
            conv_id: Conversation ID (full or partial)

        Returns:
            ConversationTree

        Raises:
            CommandError: If conversation not found
        """
        return ConversationResolver.resolve_id(db, conv_id)


class TitleCommand:
    """Rename a conversation"""

    @staticmethod
    def execute(
        db: ConversationDB,
        conv_id: str,
        new_title: str
    ) -> tuple[ConversationTree, str]:
        """
        Rename a conversation.

        Args:
            db: Database instance
            conv_id: Conversation ID (full or partial)
            new_title: New title

        Returns:
            Tuple of (ConversationTree, old_title)

        Raises:
            CommandError: If conversation not found or update fails
        """
        tree = ConversationResolver.resolve_id(db, conv_id)
        old_title = tree.title

        tree.title = new_title
        db.save_conversation(tree)

        return tree, old_title


class DuplicateCommand:
    """Duplicate a conversation"""

    @staticmethod
    def execute(
        db: ConversationDB,
        conv_id: str,
        new_title: Optional[str] = None
    ) -> tuple[str, ConversationTree]:
        """
        Duplicate a conversation.

        Args:
            db: Database instance
            conv_id: Conversation ID (full or partial)
            new_title: Optional title for duplicate

        Returns:
            Tuple of (new_id, new_tree)

        Raises:
            CommandError: If conversation not found or duplication fails
        """
        tree = ConversationResolver.resolve_id(db, conv_id)

        new_id = db.duplicate_conversation(tree.id, new_title=new_title)
        if not new_id:
            raise CommandError("Failed to duplicate conversation")

        new_tree = db.load_conversation(new_id)
        return new_id, new_tree
