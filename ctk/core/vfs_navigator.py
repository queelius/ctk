"""
Virtual filesystem navigator for conversation browsing.

Provides directory listing and navigation for the VFS.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from time import time

from .vfs import VFSPath, VFSPathParser, PathType
from .database import ConversationDB
from .views import ViewStore


@dataclass
class VFSEntry:
    """Entry in a VFS directory listing"""
    name: str
    is_directory: bool
    conversation_id: Optional[str] = None
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: Optional[List[str]] = None
    starred: bool = False
    pinned: bool = False
    archived: bool = False
    source: Optional[str] = None
    model: Optional[str] = None
    # For message nodes
    message_id: Optional[str] = None
    role: Optional[str] = None
    content_preview: Optional[str] = None
    has_children: bool = False


class VFSNavigator:
    """Navigator for virtual filesystem with caching for performance"""

    # Cache TTL in seconds
    CACHE_TTL = 2.0

    def __init__(self, db: ConversationDB, views_dir: Optional[str] = None):
        """
        Initialize VFS navigator.

        Args:
            db: ConversationDB instance
            views_dir: Optional path to views directory (defaults to views/ in db directory)
        """
        self.db = db
        self._views_dir = views_dir
        self._view_store: Optional[ViewStore] = None

        # Cache: path_key -> (timestamp, entries)
        self._cache: Dict[str, Tuple[float, List[VFSEntry]]] = {}

    @property
    def view_store(self) -> Optional[ViewStore]:
        """Lazy-load ViewStore from views directory"""
        if self._view_store is None and self._views_dir:
            self._view_store = ViewStore(self._views_dir)
        elif self._view_store is None and hasattr(self.db, 'db_path') and self.db.db_path:
            # Try to derive views dir from database path
            from pathlib import Path
            db_dir = Path(self.db.db_path).parent
            views_path = db_dir / "views"
            if views_path.exists():
                self._view_store = ViewStore(str(views_path))
        return self._view_store

    def clear_cache(self):
        """Clear the directory listing cache"""
        self._cache.clear()

    def _get_cache_key(self, vfs_path: VFSPath) -> str:
        """Generate cache key for VFS path"""
        # Include path type and message path to ensure unique keys
        key = vfs_path.normalized_path
        if vfs_path.message_path:
            key += f"::msg::{'/'.join(vfs_path.message_path)}"
        return key

    def resolve_prefix(self, prefix: str, vfs_path: VFSPath) -> Optional[str]:
        """
        Resolve a partial conversation ID prefix to full ID.

        Args:
            prefix: Partial conversation ID (e.g., "466a")
            vfs_path: Current VFS path context

        Returns:
            Full conversation ID if unique match found, None otherwise

        Raises:
            ValueError: If multiple matches or no matches
        """
        # Get list of conversations in current context
        try:
            entries = self.list_directory(vfs_path)
        except:
            return None

        # Find all conversation entries that match prefix
        matches = []
        for entry in entries:
            if entry.conversation_id and entry.conversation_id.startswith(prefix):
                matches.append(entry.conversation_id)

        if len(matches) == 0:
            raise ValueError(f"No conversation found matching prefix: {prefix}")
        elif len(matches) == 1:
            return matches[0]
        else:
            # Multiple matches - show options
            match_list = "\n  ".join(matches[:5])
            if len(matches) > 5:
                match_list += f"\n  ... and {len(matches) - 5} more"
            raise ValueError(
                f"Prefix '{prefix}' matches {len(matches)} conversations:\n  {match_list}\n"
                f"Please provide more characters to uniquely identify the conversation."
            )

    def list_directory(self, vfs_path: VFSPath) -> List[VFSEntry]:
        """
        List contents of a directory with caching.

        Args:
            vfs_path: Parsed VFS path

        Returns:
            List of VFSEntry objects

        Raises:
            ValueError: If path is not a directory
        """
        if not vfs_path.is_directory:
            raise ValueError(f"Not a directory: {vfs_path.normalized_path}")

        # Check cache first
        cache_key = self._get_cache_key(vfs_path)
        now = time()

        if cache_key in self._cache:
            cached_time, cached_entries = self._cache[cache_key]
            if now - cached_time < self.CACHE_TTL:
                return cached_entries

        # Cache miss or expired - fetch fresh data
        # Route to appropriate handler based on path type
        if vfs_path.path_type == PathType.ROOT:
            entries = self._list_root()
        elif vfs_path.path_type == PathType.CHATS:
            entries = self._list_chats()
        elif vfs_path.path_type == PathType.CONVERSATION_ROOT:
            entries = self._list_conversation_root(vfs_path.conversation_id)
        elif vfs_path.path_type == PathType.MESSAGE_NODE:
            entries = self._list_message_node(vfs_path.conversation_id, vfs_path.message_path)
        elif vfs_path.path_type == PathType.TAGS:
            entries = self._list_tags_root()
        elif vfs_path.path_type == PathType.TAG_DIR:
            entries = self._list_tag_directory(vfs_path.tag_path)
        elif vfs_path.path_type == PathType.STARRED:
            entries = self._list_starred()
        elif vfs_path.path_type == PathType.PINNED:
            entries = self._list_pinned()
        elif vfs_path.path_type == PathType.ARCHIVED:
            entries = self._list_archived()
        elif vfs_path.path_type == PathType.RECENT:
            entries = self._list_recent(vfs_path.segments)
        elif vfs_path.path_type == PathType.SOURCE:
            entries = self._list_source(vfs_path.segments)
        elif vfs_path.path_type == PathType.MODEL:
            entries = self._list_model(vfs_path.segments)
        elif vfs_path.path_type == PathType.VIEWS:
            entries = self._list_views()
        elif vfs_path.path_type == PathType.VIEW_DIR:
            entries = self._list_view_contents(vfs_path.view_name)
        else:
            raise ValueError(f"Cannot list directory type: {vfs_path.path_type}")

        # Cache the result
        self._cache[cache_key] = (now, entries)

        return entries

    def _list_root(self) -> List[VFSEntry]:
        """List root directory (/)"""
        entries = [
            VFSEntry(name="chats", is_directory=True),
            VFSEntry(name="tags", is_directory=True),
            VFSEntry(name="starred", is_directory=True),
            VFSEntry(name="pinned", is_directory=True),
            VFSEntry(name="archived", is_directory=True),
            VFSEntry(name="recent", is_directory=True),
            VFSEntry(name="source", is_directory=True),
            VFSEntry(name="model", is_directory=True),
        ]
        # Only show views directory if view store is available
        if self.view_store is not None:
            entries.append(VFSEntry(name="views", is_directory=True))
        return entries

    def _list_chats(self) -> List[VFSEntry]:
        """List /chats/ directory"""
        conversations = self.db.list_conversations()

        entries = []
        for conv in conversations:
            # Conversations now appear as directories (can be entered)
            entries.append(VFSEntry(
                name=conv.id,
                is_directory=True,  # Changed: conversations are now directories
                conversation_id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                tags=conv.tags,
                starred=conv.starred_at is not None,
                pinned=conv.pinned_at is not None,
                archived=conv.archived_at is not None,
                source=conv.source,
                model=conv.model
            ))

        return entries

    def _list_conversation_root(self, conversation_id: str) -> List[VFSEntry]:
        """
        List /chats/<id>/ directory (conversation as directory).

        Shows all root message nodes in the conversation tree.
        """
        # Load conversation from database
        conversation = self.db.load_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        entries = []

        # List all root messages
        for i, root_id in enumerate(conversation.root_message_ids, start=1):
            message = conversation.message_map.get(root_id)
            if not message:
                continue

            # Get children to determine if it's a directory
            children = conversation.get_children(root_id)
            has_children = len(children) > 0

            # Get content preview (first 50 chars)
            content_text = message.content.get_text() if message.content else ""
            preview = content_text[:50] + "..." if len(content_text) > 50 else content_text

            entries.append(VFSEntry(
                name=f"m{i}",  # m1, m2, m3, etc.
                is_directory=True,  # Message nodes are always directories (can navigate into)
                conversation_id=conversation_id,
                message_id=message.id,
                role=message.role.value if message.role else "user",
                content_preview=preview,
                created_at=message.timestamp,
                has_children=has_children
            ))

        return entries

    def _list_message_node(self, conversation_id: str, message_path: List[str]) -> List[VFSEntry]:
        """
        List /chats/<id>/m1/m2/... directory (message node).

        Shows all children of the specified message node.

        Args:
            conversation_id: Conversation ID
            message_path: List of message node names (e.g., ['m1', 'm2'])
        """
        # Load conversation from database
        conversation = self.db.load_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        # Navigate to the target message node
        # message_path is like ['m1', 'm2', 'm5']
        # We need to map this to actual message IDs

        current_message_id = None

        for node_name in message_path:
            # Extract index from node name (m1 -> 1, m2 -> 2)
            if not node_name.lower().startswith('m'):
                raise ValueError(f"Invalid message node: {node_name}")

            try:
                node_index = int(node_name[1:])  # Remove 'm' prefix
            except ValueError:
                raise ValueError(f"Invalid message node: {node_name}")

            # Get available children at this level
            if current_message_id is None:
                # At root level - use root_message_ids
                available_ids = conversation.root_message_ids
            else:
                # Get children of current message
                children = conversation.get_children(current_message_id)
                available_ids = [child.id for child in children]

            # Map index to message ID (1-indexed)
            if node_index < 1 or node_index > len(available_ids):
                raise ValueError(f"Message node {node_name} out of range (1-{len(available_ids)})")

            current_message_id = available_ids[node_index - 1]

        # Get the current message to expose its metadata as files
        current_message = conversation.message_map.get(current_message_id)

        entries = []

        # Add metadata files for the current message
        if current_message:
            # text file - contains the message content
            entries.append(VFSEntry(
                name="text",
                is_directory=False,
                conversation_id=conversation_id,
                message_id=current_message_id
            ))

            # role file - contains the role (user/assistant/system)
            entries.append(VFSEntry(
                name="role",
                is_directory=False,
                conversation_id=conversation_id,
                message_id=current_message_id
            ))

            # timestamp file - contains the creation timestamp
            entries.append(VFSEntry(
                name="timestamp",
                is_directory=False,
                conversation_id=conversation_id,
                message_id=current_message_id
            ))

            # id file - contains the message ID
            entries.append(VFSEntry(
                name="id",
                is_directory=False,
                conversation_id=conversation_id,
                message_id=current_message_id
            ))

        # Now list child messages
        children = conversation.get_children(current_message_id)

        for i, child in enumerate(children, start=1):
            # Check if this child has its own children
            grandchildren = conversation.get_children(child.id)
            has_children = len(grandchildren) > 0

            # Get content preview
            content_text = child.content.get_text() if child.content else ""
            preview = content_text[:50] + "..." if len(content_text) > 50 else content_text

            entries.append(VFSEntry(
                name=f"m{i}",
                is_directory=True,
                conversation_id=conversation_id,
                message_id=child.id,
                role=child.role.value if child.role else "user",
                content_preview=preview,
                created_at=child.timestamp,
                has_children=has_children
            ))

        return entries

    def _list_tags_root(self) -> List[VFSEntry]:
        """List /tags/ directory (top-level tags)"""
        tag_names = self.db.list_tag_children(parent_tag=None)

        return [
            VFSEntry(name=tag, is_directory=True)
            for tag in tag_names
        ]

    def _list_tag_directory(self, tag_path: str) -> List[VFSEntry]:
        """
        List /tags/path/ directory.

        Shows both subdirectories (child tags) and conversations (tagged items).
        """
        entries = []

        # Add child tag directories
        children = self.db.list_tag_children(parent_tag=tag_path)
        for child in children:
            entries.append(VFSEntry(name=child, is_directory=True))

        # Add conversations with this exact tag
        conversations = self.db.list_conversations_by_tag(tag_path)
        for conv in conversations:
            entries.append(VFSEntry(
                name=conv.id,
                is_directory=True,  # Conversations are directories
                conversation_id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                tags=conv.tags,
                starred=conv.starred_at is not None,
                pinned=conv.pinned_at is not None,
                archived=conv.archived_at is not None,
                source=conv.source,
                model=conv.model
            ))

        return entries

    def _list_starred(self) -> List[VFSEntry]:
        """List /starred/ directory"""
        conversations = self.db.list_conversations(starred=True)

        entries = []
        for conv in conversations:
            entries.append(VFSEntry(
                name=conv.id,
                is_directory=True,  # Conversations are directories
                conversation_id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                tags=conv.tags,
                starred=True,
                pinned=conv.pinned_at is not None,
                archived=conv.archived_at is not None,
                source=conv.source,
                model=conv.model
            ))

        return entries

    def _list_pinned(self) -> List[VFSEntry]:
        """List /pinned/ directory"""
        conversations = self.db.list_conversations(pinned=True)

        entries = []
        for conv in conversations:
            entries.append(VFSEntry(
                name=conv.id,
                is_directory=True,  # Conversations are directories
                conversation_id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                tags=conv.tags,
                starred=conv.starred_at is not None,
                pinned=True,
                archived=conv.archived_at is not None,
                source=conv.source,
                model=conv.model
            ))

        return entries

    def _list_archived(self) -> List[VFSEntry]:
        """List /archived/ directory"""
        conversations = self.db.list_conversations(archived=True)

        entries = []
        for conv in conversations:
            entries.append(VFSEntry(
                name=conv.id,
                is_directory=True,  # Conversations are directories
                conversation_id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                tags=conv.tags,
                starred=conv.starred_at is not None,
                pinned=conv.pinned_at is not None,
                archived=True,
                source=conv.source,
                model=conv.model
            ))

        return entries

    def _list_recent(self, segments: List[str]) -> List[VFSEntry]:
        """
        List /recent/* directory.

        /recent/ shows: today, this-week, this-month, older
        /recent/today/ shows conversations from today
        etc.
        """
        if len(segments) == 1:
            # /recent/ - show time periods
            return [
                VFSEntry(name="today", is_directory=True),
                VFSEntry(name="this-week", is_directory=True),
                VFSEntry(name="this-month", is_directory=True),
                VFSEntry(name="older", is_directory=True),
            ]
        else:
            # /recent/<period>/ - show conversations
            period = segments[1]

            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())
            month_start = today_start.replace(day=1)

            # Get all conversations and filter by date
            all_convs = self.db.list_conversations()

            filtered = []
            for conv in all_convs:
                # Use created_at for "recent" filtering (not updated_at)
                # This shows truly recent conversations, not batch-updated ones
                conv_date = conv.created_at or conv.updated_at
                if not conv_date:
                    continue

                if period == "today":
                    if conv_date >= today_start:
                        filtered.append(conv)
                elif period == "this-week":
                    if week_start <= conv_date < today_start:
                        filtered.append(conv)
                elif period == "this-month":
                    if month_start <= conv_date < week_start:
                        filtered.append(conv)
                elif period == "older":
                    if conv_date < month_start:
                        filtered.append(conv)

            entries = []
            for conv in filtered:
                entries.append(VFSEntry(
                    name=conv.id,
                    is_directory=True,  # Conversations are directories
                    conversation_id=conv.id,
                    title=conv.title,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    tags=conv.tags,
                    starred=conv.starred_at is not None,
                    pinned=conv.pinned_at is not None,
                    archived=conv.archived_at is not None,
                    source=conv.source,
                    model=conv.model
                ))

            return entries

    def _list_source(self, segments: List[str]) -> List[VFSEntry]:
        """
        List /source/* directory.

        /source/ shows: openai, anthropic, gemini, etc.
        /source/openai/ shows conversations from OpenAI
        """
        if len(segments) == 1:
            # /source/ - list all sources
            all_convs = self.db.list_conversations()
            sources = set()
            for conv in all_convs:
                if conv.source:
                    sources.add(conv.source)

            return [
                VFSEntry(name=source, is_directory=True)
                for source in sorted(sources)
            ]
        else:
            # /source/<name>/ - list conversations from source
            source_name = segments[1]
            conversations = self.db.list_conversations(source=source_name)

            entries = []
            for conv in conversations:
                entries.append(VFSEntry(
                    name=conv.id,
                    is_directory=True,  # Conversations are directories
                    conversation_id=conv.id,
                    title=conv.title,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    tags=conv.tags,
                    starred=conv.starred_at is not None,
                    pinned=conv.pinned_at is not None,
                    archived=conv.archived_at is not None,
                    source=conv.source,
                    model=conv.model
                ))

            return entries

    def _list_model(self, segments: List[str]) -> List[VFSEntry]:
        """
        List /model/* directory.

        /model/ shows: gpt-4, claude-3, etc.
        /model/gpt-4/ shows conversations using GPT-4
        """
        if len(segments) == 1:
            # /model/ - list all models
            all_convs = self.db.list_conversations()
            models = set()
            for conv in all_convs:
                if conv.model:
                    models.add(conv.model)

            return [
                VFSEntry(name=model, is_directory=True)
                for model in sorted(models)
            ]
        else:
            # /model/<name>/ - list conversations using model
            model_name = segments[1]
            conversations = self.db.list_conversations(model=model_name)

            entries = []
            for conv in conversations:
                entries.append(VFSEntry(
                    name=conv.id,
                    is_directory=True,  # Conversations are directories
                    conversation_id=conv.id,
                    title=conv.title,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    tags=conv.tags,
                    starred=conv.starred_at is not None,
                    pinned=conv.pinned_at is not None,
                    archived=conv.archived_at is not None,
                    source=conv.source,
                    model=conv.model
                ))

            return entries

    def _list_views(self) -> List[VFSEntry]:
        """
        List /views/ directory.

        Shows all available named views.
        """
        if self.view_store is None:
            return []

        entries = []
        for view_name in self.view_store.list_views():
            # Load view to get metadata
            view = self.view_store.load(view_name)
            entries.append(VFSEntry(
                name=view_name,
                is_directory=True,
                title=view.title if view else None,
                created_at=view.created_at if view else None,
                updated_at=view.updated_at if view else None
            ))

        return entries

    def _list_view_contents(self, view_name: str) -> List[VFSEntry]:
        """
        List /views/<name>/ directory.

        Shows all conversations in the named view (evaluated).
        """
        if self.view_store is None:
            raise ValueError("View store not available")

        # Evaluate the view to get conversations
        evaluated = self.view_store.evaluate(view_name, self.db)
        if evaluated is None:
            raise ValueError(f"View not found: {view_name}")

        entries = []
        for item in evaluated.items:
            # Load conversation to get full metadata
            conv = self.db.load_conversation(item.conversation_id)
            if conv is None:
                # Conversation no longer exists - skip silently
                continue

            entries.append(VFSEntry(
                name=item.conversation_id,
                is_directory=True,  # Conversations are directories
                conversation_id=item.conversation_id,
                title=item.title_override or conv.title,  # Use override if available
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                tags=conv.tags,
                starred=conv.starred_at is not None,
                pinned=conv.pinned_at is not None,
                archived=conv.archived_at is not None,
                source=conv.source,
                model=conv.model
            ))

        return entries
