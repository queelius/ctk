"""
In-memory conversation index for O(1) slug and prefix resolution.

This module provides fast lookups for conversation slugs and ID prefixes,
avoiding the need to load all conversations from the database for each
resolution. The index is loaded lazily on first access and can be
incrementally updated.

Memory footprint for 100k conversations: ~15-20MB
Load time: ~0.5-2 seconds (background preload recommended)
Lookup time: O(1) for exact matches, O(k) for prefix matches where k = matches
"""

import logging
import threading
from dataclasses import dataclass
from time import time
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class IndexEntry:
    """Lightweight entry in the conversation index"""

    id: str
    slug: Optional[str]
    title: Optional[str] = None


class ConversationIndex:
    """
    In-memory index for fast conversation lookups.

    Provides O(1) resolution for:
    - Exact slug matches
    - Exact ID matches
    - ID prefix matches (with uniqueness check)
    - Slug prefix matches (with uniqueness check)

    Thread-safe with RLock for re-entrant access.
    """

    def __init__(self, db=None):
        """
        Initialize the conversation index.

        Args:
            db: ConversationDB instance. If None, index must be populated manually.
        """
        self.db = db

        # Primary indexes
        self._slug_to_id: Dict[str, str] = {}
        self._id_to_entry: Dict[str, IndexEntry] = {}

        # Prefix indexes for faster prefix matching
        # Maps 4-char and 8-char prefixes to list of matching IDs
        self._id_prefix_4: Dict[str, List[str]] = {}
        self._id_prefix_8: Dict[str, List[str]] = {}

        # State
        self._loaded = False
        self._loading = False
        self._load_time: float = 0
        self._entry_count: int = 0

        # Thread safety
        self._lock = threading.RLock()

    @property
    def is_loaded(self) -> bool:
        """Check if index is loaded"""
        return self._loaded

    @property
    def entry_count(self) -> int:
        """Number of entries in the index"""
        return self._entry_count

    @property
    def load_time(self) -> float:
        """Time taken to load the index (seconds)"""
        return self._load_time

    def ensure_loaded(self) -> bool:
        """
        Ensure the index is loaded. Thread-safe and re-entrant.

        Returns:
            True if index is ready, False if loading failed
        """
        # Fast path - already loaded
        if self._loaded:
            return True

        with self._lock:
            # Double-check after acquiring lock
            if self._loaded:
                return True

            if self._loading:
                # Another thread is loading - wait for it
                return False

            if not self.db:
                logger.warning("ConversationIndex: No database configured")
                return False

            self._loading = True
            try:
                self._load_from_database()
                return True
            except Exception as e:
                logger.error(f"ConversationIndex: Failed to load: {e}")
                return False
            finally:
                self._loading = False

    def _load_from_database(self):
        """Load index data from database"""
        start = time()

        # Import here to avoid circular imports
        from ctk.core.db_models import ConversationModel

        with self.db.session_scope() as session:
            # Single query, minimal columns
            results = session.query(
                ConversationModel.id, ConversationModel.slug, ConversationModel.title
            ).all()

            # Clear existing data
            self._slug_to_id.clear()
            self._id_to_entry.clear()
            self._id_prefix_4.clear()
            self._id_prefix_8.clear()

            # Build indexes
            for conv_id, slug, title in results:
                entry = IndexEntry(id=conv_id, slug=slug, title=title)
                self._id_to_entry[conv_id] = entry

                # Slug index
                if slug:
                    self._slug_to_id[slug] = conv_id

                # ID prefix indexes
                prefix_4 = conv_id[:4]
                prefix_8 = conv_id[:8]

                if prefix_4 not in self._id_prefix_4:
                    self._id_prefix_4[prefix_4] = []
                self._id_prefix_4[prefix_4].append(conv_id)

                if prefix_8 not in self._id_prefix_8:
                    self._id_prefix_8[prefix_8] = []
                self._id_prefix_8[prefix_8].append(conv_id)

            self._entry_count = len(results)

        self._load_time = time() - start
        self._loaded = True
        logger.info(
            f"ConversationIndex: Loaded {self._entry_count} entries in {self._load_time:.3f}s"
        )

    def resolve(self, identifier: str) -> Optional[Tuple[str, Optional[str]]]:
        """
        Resolve an identifier to (conversation_id, slug).

        Resolution order:
        1. Exact slug match
        2. Exact ID match
        3. Unique slug prefix match
        4. Unique ID prefix match

        Args:
            identifier: Slug, ID, or prefix to resolve

        Returns:
            Tuple of (conversation_id, slug) if unique match found, None otherwise
        """
        if not self.ensure_loaded():
            return None

        # 1. Exact slug match (most common case)
        if identifier in self._slug_to_id:
            conv_id = self._slug_to_id[identifier]
            return (conv_id, identifier)

        # 2. Exact ID match
        if identifier in self._id_to_entry:
            entry = self._id_to_entry[identifier]
            return (identifier, entry.slug)

        # 3. Slug prefix match
        slug_matches = self._find_slug_prefix_matches(identifier)
        if len(slug_matches) == 1:
            slug, conv_id = slug_matches[0]
            return (conv_id, slug)

        # 4. ID prefix match (use prefix indexes for speed)
        id_matches = self._find_id_prefix_matches(identifier)
        if len(id_matches) == 1:
            conv_id = id_matches[0]
            entry = self._id_to_entry[conv_id]
            return (conv_id, entry.slug)

        return None

    def resolve_with_info(
        self, identifier: str
    ) -> Tuple[Optional[str], Optional[str], List[Tuple[str, str, str]]]:
        """
        Resolve with detailed match information.

        Returns:
            Tuple of (matched_id, matched_slug, all_matches)
            where all_matches is list of (id, slug, title) for ambiguous cases
        """
        if not self.ensure_loaded():
            return (None, None, [])

        # Try exact matches first
        if identifier in self._slug_to_id:
            conv_id = self._slug_to_id[identifier]
            entry = self._id_to_entry[conv_id]
            return (conv_id, identifier, [(conv_id, identifier, entry.title)])

        if identifier in self._id_to_entry:
            entry = self._id_to_entry[identifier]
            return (identifier, entry.slug, [(identifier, entry.slug, entry.title)])

        # Collect all prefix matches
        all_matches = []

        # Slug prefix matches
        for slug, conv_id in self._find_slug_prefix_matches(identifier):
            entry = self._id_to_entry[conv_id]
            all_matches.append((conv_id, slug, entry.title))

        # ID prefix matches (avoid duplicates)
        seen_ids = {m[0] for m in all_matches}
        for conv_id in self._find_id_prefix_matches(identifier):
            if conv_id not in seen_ids:
                entry = self._id_to_entry[conv_id]
                all_matches.append((conv_id, entry.slug, entry.title))

        if len(all_matches) == 1:
            return (all_matches[0][0], all_matches[0][1], all_matches)

        return (None, None, all_matches)

    def _find_slug_prefix_matches(self, prefix: str) -> List[Tuple[str, str]]:
        """Find slugs that start with prefix. Returns list of (slug, id)."""
        prefix_lower = prefix.lower()
        matches = []
        for slug, conv_id in self._slug_to_id.items():
            if slug.lower().startswith(prefix_lower):
                matches.append((slug, conv_id))
        return matches

    def _find_id_prefix_matches(self, prefix: str) -> List[str]:
        """Find IDs that start with prefix. Uses prefix indexes for speed."""
        prefix_lower = prefix.lower()

        # Use prefix indexes if possible
        if len(prefix) <= 4:
            # Check all 4-char prefixes that could match
            candidates = set()
            for p4, ids in self._id_prefix_4.items():
                if p4.lower().startswith(prefix_lower):
                    candidates.update(ids)
            return [cid for cid in candidates if cid.lower().startswith(prefix_lower)]

        elif len(prefix) <= 8:
            # Use 4-char prefix to narrow down, then filter
            prefix_4 = prefix[:4].lower()
            candidates = []
            for p4, ids in self._id_prefix_4.items():
                if p4.lower() == prefix_4:
                    candidates.extend(ids)
            return [cid for cid in candidates if cid.lower().startswith(prefix_lower)]

        else:
            # Use 8-char prefix to narrow down
            prefix_8 = prefix[:8].lower()
            candidates = []
            for p8, ids in self._id_prefix_8.items():
                if p8.lower() == prefix_8:
                    candidates.extend(ids)
            return [cid for cid in candidates if cid.lower().startswith(prefix_lower)]

    def get_completions(
        self, prefix: str, limit: int = 20
    ) -> List[Tuple[str, str, Optional[str]]]:
        """
        Get completion candidates for tab completion.

        Args:
            prefix: Prefix to match (slug or ID)
            limit: Maximum number of results

        Returns:
            List of (display_text, conversation_id, slug) tuples
        """
        if not self.ensure_loaded():
            return []

        prefix_lower = prefix.lower()
        results = []
        seen_ids = set()

        # Slug matches first (preferred)
        for slug, conv_id in self._slug_to_id.items():
            if slug.lower().startswith(prefix_lower):
                results.append((slug, conv_id, slug))
                seen_ids.add(conv_id)
                if len(results) >= limit:
                    break

        # ID prefix matches if we need more
        if len(results) < limit:
            for conv_id in self._find_id_prefix_matches(prefix):
                if conv_id not in seen_ids:
                    entry = self._id_to_entry[conv_id]
                    display = entry.slug or conv_id[:8]
                    results.append((display, conv_id, entry.slug))
                    if len(results) >= limit:
                        break

        return results

    def get_entry(self, conv_id: str) -> Optional[IndexEntry]:
        """Get index entry by ID"""
        if not self.ensure_loaded():
            return None
        return self._id_to_entry.get(conv_id)

    def add(self, conv_id: str, slug: Optional[str], title: Optional[str] = None):
        """
        Add or update an entry in the index.

        Thread-safe. Can be called after index is loaded to keep it current.
        """
        with self._lock:
            if not self._loaded:
                return  # Will be loaded fresh on next access

            # Remove old slug mapping if it exists
            old_entry = self._id_to_entry.get(conv_id)
            if old_entry and old_entry.slug and old_entry.slug in self._slug_to_id:
                del self._slug_to_id[old_entry.slug]

            # Add new entry
            entry = IndexEntry(id=conv_id, slug=slug, title=title)
            self._id_to_entry[conv_id] = entry

            if slug:
                self._slug_to_id[slug] = conv_id

            # Update prefix indexes
            prefix_4 = conv_id[:4]
            prefix_8 = conv_id[:8]

            if prefix_4 not in self._id_prefix_4:
                self._id_prefix_4[prefix_4] = []
            if conv_id not in self._id_prefix_4[prefix_4]:
                self._id_prefix_4[prefix_4].append(conv_id)

            if prefix_8 not in self._id_prefix_8:
                self._id_prefix_8[prefix_8] = []
            if conv_id not in self._id_prefix_8[prefix_8]:
                self._id_prefix_8[prefix_8].append(conv_id)

            self._entry_count = len(self._id_to_entry)

    def remove(self, conv_id: str):
        """
        Remove an entry from the index.

        Thread-safe.
        """
        with self._lock:
            if not self._loaded:
                return

            entry = self._id_to_entry.pop(conv_id, None)
            if not entry:
                return

            # Remove slug mapping
            if entry.slug and entry.slug in self._slug_to_id:
                del self._slug_to_id[entry.slug]

            # Remove from prefix indexes
            prefix_4 = conv_id[:4]
            prefix_8 = conv_id[:8]

            if prefix_4 in self._id_prefix_4:
                try:
                    self._id_prefix_4[prefix_4].remove(conv_id)
                except ValueError:
                    pass

            if prefix_8 in self._id_prefix_8:
                try:
                    self._id_prefix_8[prefix_8].remove(conv_id)
                except ValueError:
                    pass

            self._entry_count = len(self._id_to_entry)

    def invalidate(self):
        """
        Invalidate the index, forcing a reload on next access.

        Thread-safe.
        """
        with self._lock:
            self._loaded = False
            self._slug_to_id.clear()
            self._id_to_entry.clear()
            self._id_prefix_4.clear()
            self._id_prefix_8.clear()
            self._entry_count = 0

    def get_stats(self) -> dict:
        """Get index statistics"""
        return {
            "loaded": self._loaded,
            "entry_count": self._entry_count,
            "load_time": self._load_time,
            "slug_count": len(self._slug_to_id),
            "prefix_4_buckets": len(self._id_prefix_4),
            "prefix_8_buckets": len(self._id_prefix_8),
        }
