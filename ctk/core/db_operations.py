"""
Database operations for CTK - merge, diff, intersect, filter, etc.
Following Unix philosophy: do one thing well, composable, pipeable
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple, Iterator, Union
from datetime import datetime
from enum import Enum
from collections import defaultdict
import sqlite3
from contextlib import contextmanager

from sqlalchemy import create_engine, select, and_, or_, func, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.engine import Engine

from .database import ConversationDB
from .db_models import ConversationModel, MessageModel, TagModel, PathModel
from .models import ConversationTree

logger = logging.getLogger(__name__)


class DuplicateStrategy(Enum):
    """Strategies for handling duplicates"""
    EXACT = "exact"           # Exact ID match
    HASH = "hash"             # Content hash match
    SIMILARITY = "similarity"  # Fuzzy content matching
    SMART = "smart"           # Combination of strategies


class MergeStrategy(Enum):
    """Strategies for resolving conflicts during merge"""
    NEWEST = "newest"         # Keep newest version
    OLDEST = "oldest"         # Keep oldest version
    LONGEST = "longest"       # Keep version with most messages
    MANUAL = "manual"         # Interactive resolution
    SKIP = "skip"            # Skip conflicts


class DatabaseOperations:
    """
    Core database operations for CTK.
    Designed for efficiency with large databases using streaming and batching.
    """

    def __init__(self, batch_size: int = 1000):
        """
        Initialize database operations handler

        Args:
            batch_size: Number of conversations to process at once
        """
        self.batch_size = batch_size
        self.comparator = ConversationComparator()

    def merge(
        self,
        input_dbs: List[str],
        output_db: str,
        strategy: MergeStrategy = MergeStrategy.NEWEST,
        dedupe: DuplicateStrategy = DuplicateStrategy.EXACT,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Merge multiple databases into one.

        Args:
            input_dbs: List of database paths to merge
            output_db: Output database path
            strategy: How to resolve conflicts
            dedupe: Deduplication strategy
            progress_callback: Optional callback for progress updates

        Returns:
            Statistics about the merge operation
        """
        stats = {
            'total_input': 0,
            'total_output': 0,
            'duplicates_found': 0,
            'conflicts_resolved': 0,
            'databases_merged': len(input_dbs)
        }

        # Create output database
        output = ConversationDB(output_db)
        seen_ids = set()
        seen_hashes = set() if dedupe in [DuplicateStrategy.HASH, DuplicateStrategy.SMART] else None

        for db_path in input_dbs:
            logger.info(f"Merging database: {db_path}")

            with ConversationDB(db_path) as input_db:
                # Stream conversations in batches
                for batch in self._stream_conversations(input_db):
                    for conv in batch:
                        stats['total_input'] += 1

                        # Check for duplicates
                        is_duplicate, duplicate_type = self._check_duplicate(
                            conv, seen_ids, seen_hashes, dedupe
                        )

                        if is_duplicate:
                            stats['duplicates_found'] += 1

                            if strategy == MergeStrategy.SKIP:
                                continue

                            # Resolve conflict
                            conv = self._resolve_conflict(
                                conv, output, duplicate_type, strategy
                            )
                            if conv is None:
                                continue

                            stats['conflicts_resolved'] += 1

                        # Save conversation
                        output.save_conversation(conv)
                        seen_ids.add(conv.id)

                        if seen_hashes is not None:
                            conv_hash = self.comparator.compute_hash(conv)
                            seen_hashes.add(conv_hash)

                        stats['total_output'] += 1

                        if progress_callback:
                            progress_callback(stats)

        output.close()
        return stats

    def diff(
        self,
        left_db: str,
        right_db: str,
        output_db: Optional[str] = None,
        symmetric: bool = False,
        comparison: DuplicateStrategy = DuplicateStrategy.EXACT
    ) -> Dict[str, Any]:
        """
        Find conversations that exist in one database but not another.

        Args:
            left_db: First database path
            right_db: Second database path
            output_db: Optional output database for unique conversations
            symmetric: If True, return differences from both sides
            comparison: How to compare conversations

        Returns:
            Statistics about differences
        """
        stats = {
            'left_total': 0,
            'right_total': 0,
            'left_unique': 0,
            'right_unique': 0,
            'common': 0
        }

        # Build index of right database
        right_index = self._build_index(right_db, comparison)
        stats['right_total'] = len(right_index)

        left_unique = []

        with ConversationDB(left_db) as left:
            for batch in self._stream_conversations(left):
                for conv in batch:
                    stats['left_total'] += 1

                    # Check if conversation exists in right
                    key = self._get_comparison_key(conv, comparison)
                    if key in right_index:
                        stats['common'] += 1
                    else:
                        stats['left_unique'] += 1
                        left_unique.append(conv)

        # Save unique conversations if output specified
        if output_db and left_unique:
            output = ConversationDB(output_db)
            for conv in left_unique:
                output.save_conversation(conv)
            output.close()

        # If symmetric, also find right-unique
        if symmetric:
            stats['right_unique'] = stats['right_total'] - stats['common']

        return stats

    def intersect(
        self,
        input_dbs: List[str],
        output_db: str,
        min_count: Optional[int] = None,
        comparison: DuplicateStrategy = DuplicateStrategy.EXACT
    ) -> Dict[str, Any]:
        """
        Find conversations common to multiple databases.

        Args:
            input_dbs: List of database paths
            output_db: Output database path
            min_count: Minimum number of databases conversation must appear in
            comparison: How to compare conversations

        Returns:
            Statistics about intersection
        """
        if min_count is None:
            min_count = len(input_dbs)  # Must be in all databases

        stats = {
            'total_unique': 0,
            'common_to_all': 0,
            'common_to_min': 0,
            'databases_checked': len(input_dbs)
        }

        # Build occurrence map
        occurrence_map = defaultdict(set)  # key -> set of database indices

        for idx, db_path in enumerate(input_dbs):
            with ConversationDB(db_path) as db:
                for batch in self._stream_conversations(db):
                    for conv in batch:
                        key = self._get_comparison_key(conv, comparison)
                        occurrence_map[key].add(idx)

        stats['total_unique'] = len(occurrence_map)

        # Find common conversations
        output = ConversationDB(output_db)

        # Need to re-scan to get actual conversation objects
        saved_keys = set()

        for db_path in input_dbs:
            with ConversationDB(db_path) as db:
                for batch in self._stream_conversations(db):
                    for conv in batch:
                        key = self._get_comparison_key(conv, comparison)

                        if key in saved_keys:
                            continue

                        occurrences = len(occurrence_map[key])

                        if occurrences >= min_count:
                            output.save_conversation(conv)
                            saved_keys.add(key)

                            if occurrences == len(input_dbs):
                                stats['common_to_all'] += 1
                            stats['common_to_min'] += 1

        output.close()
        return stats

    def filter(
        self,
        input_db: str,
        output_db: str,
        source: Optional[str] = None,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        min_messages: Optional[int] = None,
        max_messages: Optional[int] = None,
        query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Filter conversations based on criteria.

        Args:
            input_db: Input database path
            output_db: Output database path
            source: Filter by source (chatgpt, claude, etc.)
            after: Only conversations after this date
            before: Only conversations before this date
            tags: Required tags
            min_messages: Minimum message count
            max_messages: Maximum message count
            query: SQL WHERE clause for advanced filtering

        Returns:
            Statistics about filtering
        """
        stats = {
            'total_input': 0,
            'total_output': 0,
            'filtered_out': 0
        }

        output = ConversationDB(output_db)

        with ConversationDB(input_db) as input:
            # Build filter query
            with input.session_scope() as session:
                q = session.query(ConversationModel)

                if source:
                    q = q.filter(ConversationModel.source == source)

                if after:
                    q = q.filter(ConversationModel.updated_at >= after)

                if before:
                    q = q.filter(ConversationModel.updated_at <= before)

                if tags:
                    for tag in tags:
                        q = q.join(ConversationModel.tags).filter(TagModel.name == tag)

                if query:
                    # Allow raw SQL for power users
                    q = q.filter(text(query))

                # Collect conversation IDs that pass filters
                conv_ids_to_save = []

                for conv_model in q.yield_per(self.batch_size):
                    stats['total_input'] += 1

                    # Additional filtering that's easier to do in Python
                    # Count messages via relationship
                    msg_count = len(conv_model.messages) if conv_model.messages else 0
                    if min_messages and msg_count < min_messages:
                        stats['filtered_out'] += 1
                        continue

                    if max_messages and msg_count > max_messages:
                        stats['filtered_out'] += 1
                        continue

                    conv_ids_to_save.append(conv_model.id)

            # Load and save conversations outside the session scope
            for conv_id in conv_ids_to_save:
                conv = input.load_conversation(conv_id)
                if conv:
                    output.save_conversation(conv)
                    stats['total_output'] += 1

        output.close()
        return stats

    def dedupe(
        self,
        input_db: str,
        output_db: Optional[str] = None,
        strategy: DuplicateStrategy = DuplicateStrategy.EXACT,
        similarity_threshold: float = 0.95,
        keep: str = "newest",
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Remove duplicate conversations from a database.

        Args:
            input_db: Input database path
            output_db: Output database path (if None, modifies input)
            strategy: Deduplication strategy
            similarity_threshold: Threshold for similarity matching (0-1)
            keep: Which duplicate to keep (newest, oldest, longest)
            dry_run: If True, only report what would be removed

        Returns:
            Statistics about deduplication
        """
        stats = {
            'total_conversations': 0,
            'duplicates_found': 0,
            'groups_found': 0,
            'conversations_kept': 0,
            'conversations_removed': 0
        }

        # Find duplicate groups
        duplicate_groups = self._find_duplicate_groups(
            input_db, strategy, similarity_threshold
        )

        stats['groups_found'] = len(duplicate_groups)

        if dry_run:
            # Just report statistics
            for group in duplicate_groups:
                stats['duplicates_found'] += len(group) - 1

            with ConversationDB(input_db) as db:
                stats['total_conversations'] = db.get_statistics()['total_conversations']

            stats['conversations_kept'] = stats['total_conversations'] - stats['duplicates_found']
            return stats

        # Perform deduplication
        if output_db:
            # Create new database with deduplicated data
            self._dedupe_to_new_db(input_db, output_db, duplicate_groups, keep, stats)
        else:
            # Modify input database in place
            self._dedupe_in_place(input_db, duplicate_groups, keep, stats)

        return stats

    def split(
        self,
        input_db: str,
        output_dir: str,
        by: str = "source",
        chunks: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Split a database into multiple databases based on criteria.

        Args:
            input_db: Input database path
            output_dir: Directory for output databases
            by: Split criteria (source, month, tag, or custom field)
            chunks: Number of equal-sized chunks (ignores 'by' parameter)

        Returns:
            Statistics about the split
        """
        stats = {
            'total_conversations': 0,
            'databases_created': 0,
            'split_by': by if not chunks else f'{chunks} chunks'
        }

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        if chunks:
            # Split into equal chunks
            return self._split_into_chunks(input_db, output_path, chunks, stats)

        # Split by field
        split_map = defaultdict(list)

        with ConversationDB(input_db) as input:
            for batch in self._stream_conversations(input):
                for conv in batch:
                    stats['total_conversations'] += 1

                    # Determine split key
                    split_key = self._get_split_key(conv, by)
                    split_map[split_key].append(conv)

        # Create output databases
        for key, conversations in split_map.items():
            safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(key))
            output_file = output_path / f"{safe_key}.db"

            with ConversationDB(str(output_file)) as output:
                for conv in conversations:
                    output.save_conversation(conv)

            stats['databases_created'] += 1
            logger.info(f"Created {output_file} with {len(conversations)} conversations")

        return stats

    # Helper methods

    def _stream_conversations(
        self,
        db: ConversationDB,
        batch_size: Optional[int] = None
    ) -> Iterator[List[ConversationTree]]:
        """Stream conversations in batches for memory efficiency"""
        if batch_size is None:
            batch_size = self.batch_size

        offset = 0
        while True:
            batch = []

            # Get conversation IDs in this batch
            with db.session_scope() as session:
                conv_models = session.query(ConversationModel.id)\
                    .offset(offset)\
                    .limit(batch_size)\
                    .all()

                if not conv_models:
                    break

                conv_ids = [model.id for model in conv_models]

            # Load full conversations using their IDs
            for conv_id in conv_ids:
                conv = db.load_conversation(conv_id)
                if conv:
                    batch.append(conv)

            yield batch
            offset += batch_size

    def _build_index(
        self,
        db_path: str,
        comparison: DuplicateStrategy
    ) -> Set[str]:
        """Build an index of conversation keys for comparison"""
        index = set()

        with ConversationDB(db_path) as db:
            for batch in self._stream_conversations(db):
                for conv in batch:
                    key = self._get_comparison_key(conv, comparison)
                    index.add(key)

        return index

    def _get_comparison_key(
        self,
        conv: ConversationTree,
        strategy: DuplicateStrategy
    ) -> str:
        """Get comparison key based on strategy"""
        if strategy == DuplicateStrategy.EXACT:
            return conv.id
        elif strategy == DuplicateStrategy.HASH:
            return self.comparator.compute_hash(conv)
        elif strategy == DuplicateStrategy.SIMILARITY:
            # For similarity, we need to compare against all
            # This is handled differently in find_duplicates
            return self.comparator.compute_hash(conv)
        else:  # SMART
            # Use combination of ID and hash
            return f"{conv.id}:{self.comparator.compute_hash(conv)}"

    def _check_duplicate(
        self,
        conv: ConversationTree,
        seen_ids: Set[str],
        seen_hashes: Optional[Set[str]],
        strategy: DuplicateStrategy
    ) -> Tuple[bool, Optional[str]]:
        """Check if conversation is a duplicate"""
        if strategy == DuplicateStrategy.EXACT:
            if conv.id in seen_ids:
                return True, "id"

        elif strategy == DuplicateStrategy.HASH and seen_hashes:
            conv_hash = self.comparator.compute_hash(conv)
            if conv_hash in seen_hashes:
                return True, "hash"

        elif strategy == DuplicateStrategy.SMART:
            if conv.id in seen_ids:
                return True, "id"
            if seen_hashes:
                conv_hash = self.comparator.compute_hash(conv)
                if conv_hash in seen_hashes:
                    return True, "hash"

        return False, None

    def _resolve_conflict(
        self,
        new_conv: ConversationTree,
        output_db: ConversationDB,
        conflict_type: str,
        strategy: MergeStrategy
    ) -> Optional[ConversationTree]:
        """Resolve a merge conflict"""
        if strategy == MergeStrategy.SKIP:
            return None

        # Load existing conversation
        existing = output_db.load_conversation(new_conv.id)
        if not existing:
            return new_conv

        if strategy == MergeStrategy.NEWEST:
            if new_conv.metadata.updated_at > existing.metadata.updated_at:
                return new_conv
            return None

        elif strategy == MergeStrategy.OLDEST:
            if new_conv.metadata.updated_at < existing.metadata.updated_at:
                return new_conv
            return None

        elif strategy == MergeStrategy.LONGEST:
            if len(new_conv.message_map) > len(existing.message_map):
                return new_conv
            return None

        # MANUAL strategy would require interactive resolution
        # For now, default to keeping existing
        return None

    def _get_split_key(self, conv: ConversationTree, by: str) -> str:
        """Get the key to use for splitting"""
        if by == "source":
            return conv.metadata.source or "unknown"
        elif by == "month":
            if conv.metadata.created_at:
                return conv.metadata.created_at.strftime("%Y-%m")
            return "unknown"
        elif by == "model":
            return conv.metadata.model or "unknown"
        elif by == "project":
            return conv.metadata.project or "unknown"
        elif by.startswith("tags["):
            # Extract tag index
            import re
            match = re.match(r"tags\[(\d+)\]", by)
            if match and conv.metadata.tags:
                idx = int(match.group(1))
                if idx < len(conv.metadata.tags):
                    return conv.metadata.tags[idx]
            return "untagged"
        else:
            # Try to get attribute dynamically
            return str(getattr(conv.metadata, by, "unknown"))

    def _find_duplicate_groups(
        self,
        db_path: str,
        strategy: DuplicateStrategy,
        threshold: float
    ) -> List[List[str]]:
        """Find groups of duplicate conversations"""
        groups = []
        processed = set()

        if strategy == DuplicateStrategy.SIMILARITY:
            # Use comparator for similarity-based grouping
            groups = self.comparator.find_similar_groups(db_path, threshold)
        else:
            # Use hash/id based grouping
            hash_map = defaultdict(list)

            with ConversationDB(db_path) as db:
                for batch in self._stream_conversations(db):
                    for conv in batch:
                        if conv.id not in processed:
                            key = self._get_comparison_key(conv, strategy)
                            hash_map[key].append(conv.id)
                            processed.add(conv.id)

            # Extract groups with duplicates
            groups = [ids for ids in hash_map.values() if len(ids) > 1]

        return groups

    def _dedupe_to_new_db(
        self,
        input_db: str,
        output_db: str,
        duplicate_groups: List[List[str]],
        keep: str,
        stats: Dict[str, Any]
    ):
        """Create new database with deduplicated data"""
        # Build set of IDs to skip
        skip_ids = set()
        keep_ids = set()

        with ConversationDB(input_db) as input:
            for group in duplicate_groups:
                # Determine which to keep
                keeper = self._select_keeper(input, group, keep)
                keep_ids.add(keeper)
                for conv_id in group:
                    if conv_id != keeper:
                        skip_ids.add(conv_id)

        # Copy non-duplicate conversations
        output = ConversationDB(output_db)

        with ConversationDB(input_db) as input:
            for batch in self._stream_conversations(input):
                for conv in batch:
                    stats['total_conversations'] += 1

                    if conv.id not in skip_ids:
                        output.save_conversation(conv)
                        stats['conversations_kept'] += 1
                    else:
                        stats['conversations_removed'] += 1

        output.close()

    def _dedupe_in_place(
        self,
        db_path: str,
        duplicate_groups: List[List[str]],
        keep: str,
        stats: Dict[str, Any]
    ):
        """Remove duplicates from database in place"""
        with ConversationDB(db_path) as db:
            for group in duplicate_groups:
                # Determine which to keep
                keeper = self._select_keeper(db, group, keep)

                # Delete others
                with db.session_scope() as session:
                    for conv_id in group:
                        if conv_id != keeper:
                            session.query(ConversationModel)\
                                .filter_by(id=conv_id)\
                                .delete()
                            stats['conversations_removed'] += 1

    def _select_keeper(
        self,
        db: ConversationDB,
        group: List[str],
        keep: str
    ) -> str:
        """Select which conversation to keep from a duplicate group"""
        candidates = []

        for conv_id in group:
            conv = db.load_conversation(conv_id)
            if conv:
                candidates.append(conv)

        if not candidates:
            return group[0]

        if keep == "newest":
            return max(candidates, key=lambda c: c.metadata.updated_at or datetime.min).id
        elif keep == "oldest":
            return min(candidates, key=lambda c: c.metadata.updated_at or datetime.max).id
        elif keep == "longest":
            return max(candidates, key=lambda c: len(c.message_map)).id
        else:
            return candidates[0].id

    def _split_into_chunks(
        self,
        input_db: str,
        output_dir: Path,
        chunks: int,
        stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Split database into equal-sized chunks"""
        # First count total conversations
        with ConversationDB(input_db) as db:
            total = db.get_statistics()['total_conversations']

        chunk_size = (total + chunks - 1) // chunks  # Ceiling division

        chunk_dbs = []
        for i in range(chunks):
            output_file = output_dir / f"chunk_{i+1:03d}.db"
            chunk_dbs.append(ConversationDB(str(output_file)))

        current_chunk = 0
        count_in_chunk = 0

        with ConversationDB(input_db) as input:
            for batch in self._stream_conversations(input):
                for conv in batch:
                    stats['total_conversations'] += 1

                    chunk_dbs[current_chunk].save_conversation(conv)
                    count_in_chunk += 1

                    if count_in_chunk >= chunk_size and current_chunk < chunks - 1:
                        current_chunk += 1
                        count_in_chunk = 0

        # Close all chunk databases
        for db in chunk_dbs:
            db.close()

        stats['databases_created'] = chunks
        return stats


class ConversationComparator:
    """
    Handles conversation comparison and similarity detection.
    """

    def compute_hash(self, conv: ConversationTree) -> str:
        """
        Compute a content hash for a conversation.
        Considers message content but not metadata.
        """
        hasher = hashlib.sha256()

        # Sort messages by ID for consistency
        sorted_messages = sorted(
            conv.message_map.values(),
            key=lambda m: m.id
        )

        for msg in sorted_messages:
            # Hash role and content
            hasher.update(msg.role.value.encode())
            hasher.update(str(msg.content.to_dict()).encode())

        return hasher.hexdigest()

    def compute_similarity(
        self,
        conv1: ConversationTree,
        conv2: ConversationTree
    ) -> float:
        """
        Compute similarity between two conversations (0-1).
        Uses Jaccard similarity on message content.
        """
        # Extract text from both conversations
        text1 = self._extract_text(conv1)
        text2 = self._extract_text(conv2)

        # Tokenize into words
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        if union == 0:
            return 0.0

        return intersection / union

    def find_similar_groups(
        self,
        db_path: str,
        threshold: float = 0.95
    ) -> List[List[str]]:
        """
        Find groups of similar conversations using clustering.
        """
        groups = []
        processed = set()

        db_ops = DatabaseOperations()
        conversations = []

        # Load all conversations (this could be optimized for very large DBs)
        with ConversationDB(db_path) as db:
            for batch in db_ops._stream_conversations(db):
                conversations.extend(batch)

        # Simple clustering algorithm
        for i, conv1 in enumerate(conversations):
            if conv1.id in processed:
                continue

            group = [conv1.id]
            processed.add(conv1.id)

            for j, conv2 in enumerate(conversations[i+1:], i+1):
                if conv2.id not in processed:
                    similarity = self.compute_similarity(conv1, conv2)
                    if similarity >= threshold:
                        group.append(conv2.id)
                        processed.add(conv2.id)

            if len(group) > 1:
                groups.append(group)

        return groups

    def _extract_text(self, conv: ConversationTree) -> str:
        """Extract all text content from a conversation"""
        texts = []

        for msg in conv.message_map.values():
            if hasattr(msg.content, 'text') and msg.content.text:
                texts.append(msg.content.text)
            elif hasattr(msg.content, 'parts') and msg.content.parts:
                for part in msg.content.parts:
                    if isinstance(part, str):
                        texts.append(part)
                    elif hasattr(part, 'text'):
                        texts.append(part.text)

        return " ".join(texts)