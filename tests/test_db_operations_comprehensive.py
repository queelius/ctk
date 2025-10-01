#!/usr/bin/env python3
"""
Comprehensive test suite for CTK database operations
Tests all operations: merge, diff, intersect, filter, split, dedupe
Focuses on edge cases, error handling, and real-world scenarios
"""

import unittest
import tempfile
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import json
from unittest.mock import patch, MagicMock, PropertyMock

from ctk.core.database import ConversationDB
from ctk.core.db_operations import (
    DatabaseOperations,
    DuplicateStrategy,
    MergeStrategy,
    ConversationComparator
)
from ctk.core.models import (
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
    ConversationMetadata
)


class TestDatabaseOperationsComprehensive(unittest.TestCase):
    """Comprehensive tests for database operations"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.db_ops = DatabaseOperations(batch_size=10)

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_conversation(
        self,
        conv_id: str,
        title: str = "Test Conversation",
        source: str = "test",
        num_messages: int = 3,
        tags: list = None,
        model: str = None,
        project: str = None,
        branch_at: int = None  # Create branch at message index
    ) -> ConversationTree:
        """Helper to create test conversations with various configurations"""
        metadata = ConversationMetadata(
            source=source,
            tags=tags or [],
            model=model,
            project=project
        )

        conv = ConversationTree(
            id=conv_id,
            title=title,
            metadata=metadata
        )

        # Add linear messages
        parent_id = None
        for i in range(num_messages):
            msg = Message(
                id=f"{conv_id}_msg_{i}",
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=MessageContent(text=f"Message {i} in {conv_id}"),
                parent_id=parent_id
            )
            conv.add_message(msg)

            # Create branch if requested
            if branch_at == i:
                branch_msg = Message(
                    id=f"{conv_id}_msg_{i}_branch",
                    role=msg.role,
                    content=MessageContent(text=f"Branch at message {i}"),
                    parent_id=parent_id
                )
                conv.add_message(branch_msg)

            parent_id = msg.id

        return conv

    def _create_database(self, db_path: str, conversations: list):
        """Helper to create and populate test database"""
        db = ConversationDB(db_path)
        for conv in conversations:
            db.save_conversation(conv)
        db.close()

    def _count_conversations(self, db_path: str) -> int:
        """Count conversations in database"""
        db = ConversationDB(db_path)
        count = db.get_conversation_count()
        db.close()
        return count

    # =============================================================================
    # MERGE TESTS
    # =============================================================================

    def test_merge_empty_databases(self):
        """Test merging empty databases"""
        db1 = Path(self.test_dir) / "empty1.db"
        db2 = Path(self.test_dir) / "empty2.db"
        output = Path(self.test_dir) / "merged.db"

        # Create empty databases
        self._create_database(str(db1), [])
        self._create_database(str(db2), [])

        stats = self.db_ops.merge(
            [str(db1), str(db2)],
            str(output)
        )

        self.assertEqual(stats['total_input'], 0)
        self.assertEqual(stats['total_output'], 0)
        self.assertEqual(self._count_conversations(str(output)), 0)

    def test_merge_single_database(self):
        """Test merging a single database (should copy)"""
        db1 = Path(self.test_dir) / "single.db"
        output = Path(self.test_dir) / "merged.db"

        convs = [
            self._create_conversation("conv1", "First"),
            self._create_conversation("conv2", "Second")
        ]
        self._create_database(str(db1), convs)

        stats = self.db_ops.merge([str(db1)], str(output))

        self.assertEqual(stats['total_input'], 2)
        self.assertEqual(stats['total_output'], 2)
        self.assertEqual(self._count_conversations(str(output)), 2)

    def test_merge_with_exact_duplicates(self):
        """Test merging with exact duplicate IDs"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"
        output = Path(self.test_dir) / "merged.db"

        # Same conversation ID in both databases
        conv1 = self._create_conversation("shared", "Version 1", num_messages=2)
        conv2 = self._create_conversation("shared", "Version 2", num_messages=4)

        self._create_database(str(db1), [conv1])
        self._create_database(str(db2), [conv2])

        # Test with NEWEST strategy (should keep conv2)
        stats = self.db_ops.merge(
            [str(db1), str(db2)],
            str(output),
            strategy=MergeStrategy.NEWEST
        )

        self.assertEqual(stats['total_input'], 2)
        self.assertEqual(stats['total_output'], 1)
        self.assertEqual(stats['duplicates_found'], 1)

        # Verify the correct version was kept
        db = ConversationDB(str(output))
        conv = db.load_conversation("shared")
        db.close()

        self.assertEqual(conv.title, "Version 2")
        self.assertEqual(len(conv.message_map), 4)

    def test_merge_with_longest_strategy(self):
        """Test merge with LONGEST strategy"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"
        output = Path(self.test_dir) / "merged.db"

        # Longer conversation in db1
        conv1 = self._create_conversation("shared", "Longer", num_messages=10)
        conv2 = self._create_conversation("shared", "Shorter", num_messages=3)

        self._create_database(str(db1), [conv1])
        self._create_database(str(db2), [conv2])

        stats = self.db_ops.merge(
            [str(db1), str(db2)],
            str(output),
            strategy=MergeStrategy.LONGEST
        )

        # Verify the longer version was kept
        db = ConversationDB(str(output))
        conv = db.load_conversation("shared")
        db.close()

        self.assertEqual(conv.title, "Longer")
        self.assertEqual(len(conv.message_map), 10)

    def test_merge_multiple_databases(self):
        """Test merging 3+ databases"""
        dbs = []
        all_convs = []

        for i in range(4):
            db_path = Path(self.test_dir) / f"db{i}.db"
            convs = [
                self._create_conversation(f"db{i}_conv1", f"DB{i} Conv1"),
                self._create_conversation(f"db{i}_conv2", f"DB{i} Conv2"),
                self._create_conversation("shared", f"Shared from DB{i}", num_messages=i+1)
            ]
            self._create_database(str(db_path), convs)
            dbs.append(str(db_path))
            all_convs.extend(convs[:2])  # Don't count shared multiple times

        output = Path(self.test_dir) / "merged.db"
        stats = self.db_ops.merge(dbs, str(output))

        # Should have all unique convs plus one shared
        self.assertEqual(stats['total_output'], 9)  # 8 unique + 1 shared

    def test_merge_with_progress_callback(self):
        """Test merge with progress callback"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"
        output = Path(self.test_dir) / "merged.db"

        self._create_database(str(db1), [self._create_conversation("conv1")])
        self._create_database(str(db2), [self._create_conversation("conv2")])

        progress_updates = []

        def progress_callback(current, total, message):
            progress_updates.append((current, total, message))

        stats = self.db_ops.merge(
            [str(db1), str(db2)],
            str(output),
            progress_callback=progress_callback
        )

        # Verify progress was reported
        self.assertTrue(len(progress_updates) > 0)

    # =============================================================================
    # DIFF TESTS
    # =============================================================================

    def test_diff_identical_databases(self):
        """Test diff on identical databases"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"

        convs = [
            self._create_conversation("conv1", "First"),
            self._create_conversation("conv2", "Second")
        ]
        self._create_database(str(db1), convs)
        self._create_database(str(db2), convs)

        diff_result = self.db_ops.diff(str(db1), str(db2))

        self.assertEqual(len(diff_result['only_in_first']), 0)
        self.assertEqual(len(diff_result['only_in_second']), 0)
        self.assertEqual(len(diff_result['in_both']), 2)
        self.assertEqual(len(diff_result['different']), 0)

    def test_diff_completely_different(self):
        """Test diff on completely different databases"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"

        convs1 = [
            self._create_conversation("conv1", "First"),
            self._create_conversation("conv2", "Second")
        ]
        convs2 = [
            self._create_conversation("conv3", "Third"),
            self._create_conversation("conv4", "Fourth")
        ]

        self._create_database(str(db1), convs1)
        self._create_database(str(db2), convs2)

        diff_result = self.db_ops.diff(str(db1), str(db2))

        self.assertEqual(len(diff_result['only_in_first']), 2)
        self.assertEqual(len(diff_result['only_in_second']), 2)
        self.assertEqual(len(diff_result['in_both']), 0)

    def test_diff_with_modifications(self):
        """Test diff detecting modified conversations"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"

        # Same ID, different content
        conv1 = self._create_conversation("shared", "Version 1", num_messages=2)
        conv2 = self._create_conversation("shared", "Version 2", num_messages=3)

        self._create_database(str(db1), [conv1])
        self._create_database(str(db2), [conv2])

        diff_result = self.db_ops.diff(str(db1), str(db2))

        self.assertEqual(len(diff_result['in_both']), 1)
        self.assertEqual(len(diff_result['different']), 1)
        self.assertIn("shared", diff_result['different'])

    def test_diff_output_to_file(self):
        """Test diff with output file"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"
        output = Path(self.test_dir) / "diff.json"

        self._create_database(str(db1), [self._create_conversation("conv1")])
        self._create_database(str(db2), [self._create_conversation("conv2")])

        diff_result = self.db_ops.diff(str(db1), str(db2), output_file=str(output))

        # Verify output file was created
        self.assertTrue(output.exists())

        with open(output, 'r') as f:
            saved_diff = json.load(f)

        self.assertEqual(saved_diff['only_in_first'], diff_result['only_in_first'])

    # =============================================================================
    # INTERSECT TESTS
    # =============================================================================

    def test_intersect_no_overlap(self):
        """Test intersect with no overlapping conversations"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"
        output = Path(self.test_dir) / "intersect.db"

        self._create_database(str(db1), [self._create_conversation("conv1")])
        self._create_database(str(db2), [self._create_conversation("conv2")])

        stats = self.db_ops.intersect([str(db1), str(db2)], str(output))

        self.assertEqual(stats['total_output'], 0)
        self.assertEqual(self._count_conversations(str(output)), 0)

    def test_intersect_partial_overlap(self):
        """Test intersect with partial overlap"""
        db1 = Path(self.test_dir) / "db1.db"
        db2 = Path(self.test_dir) / "db2.db"
        output = Path(self.test_dir) / "intersect.db"

        convs1 = [
            self._create_conversation("conv1", "Only in 1"),
            self._create_conversation("shared", "Shared"),
            self._create_conversation("conv2", "Only in 1 too")
        ]
        convs2 = [
            self._create_conversation("shared", "Shared"),
            self._create_conversation("conv3", "Only in 2")
        ]

        self._create_database(str(db1), convs1)
        self._create_database(str(db2), convs2)

        stats = self.db_ops.intersect([str(db1), str(db2)], str(output))

        self.assertEqual(stats['total_output'], 1)

        # Verify it's the shared conversation
        db = ConversationDB(str(output))
        conv = db.load_conversation("shared")
        db.close()
        self.assertIsNotNone(conv)

    def test_intersect_three_databases(self):
        """Test intersect with three databases"""
        dbs = []

        for i in range(3):
            db_path = Path(self.test_dir) / f"db{i}.db"
            convs = [
                self._create_conversation("common", "Common to all"),
                self._create_conversation(f"partial{i}", f"Partial {i}"),
                self._create_conversation(f"unique{i}", f"Unique to {i}")
            ]

            # Add partial overlap between consecutive databases
            if i > 0:
                convs.append(self._create_conversation(f"partial{i-1}", f"Shared with {i-1}"))

            self._create_database(str(db_path), convs)
            dbs.append(str(db_path))

        output = Path(self.test_dir) / "intersect.db"
        stats = self.db_ops.intersect(dbs, str(output))

        # Only "common" should be in all three
        self.assertEqual(stats['total_output'], 1)

    # =============================================================================
    # FILTER TESTS
    # =============================================================================

    def test_filter_by_source(self):
        """Test filtering by source"""
        db_path = Path(self.test_dir) / "test.db"
        filtered = Path(self.test_dir) / "filtered.db"

        convs = [
            self._create_conversation("conv1", source="chatgpt"),
            self._create_conversation("conv2", source="claude"),
            self._create_conversation("conv3", source="chatgpt"),
            self._create_conversation("conv4", source="copilot")
        ]
        self._create_database(str(db_path), convs)

        stats = self.db_ops.filter(
            str(db_path),
            str(filtered),
            source="chatgpt"
        )

        self.assertEqual(stats['total_output'], 2)

    def test_filter_by_tags(self):
        """Test filtering by tags"""
        db_path = Path(self.test_dir) / "test.db"
        filtered = Path(self.test_dir) / "filtered.db"

        convs = [
            self._create_conversation("conv1", tags=["python", "coding"]),
            self._create_conversation("conv2", tags=["javascript"]),
            self._create_conversation("conv3", tags=["python", "data"]),
            self._create_conversation("conv4", tags=["rust"])
        ]
        self._create_database(str(db_path), convs)

        stats = self.db_ops.filter(
            str(db_path),
            str(filtered),
            tags=["python"]
        )

        self.assertEqual(stats['total_output'], 2)

    def test_filter_by_message_count(self):
        """Test filtering by message count"""
        db_path = Path(self.test_dir) / "test.db"
        filtered = Path(self.test_dir) / "filtered.db"

        convs = [
            self._create_conversation("conv1", num_messages=2),
            self._create_conversation("conv2", num_messages=5),
            self._create_conversation("conv3", num_messages=10),
            self._create_conversation("conv4", num_messages=3)
        ]
        self._create_database(str(db_path), convs)

        # Filter for conversations with 4-10 messages
        stats = self.db_ops.filter(
            str(db_path),
            str(filtered),
            min_messages=4,
            max_messages=10
        )

        self.assertEqual(stats['total_output'], 2)  # conv2 and conv3

    def test_filter_combined_criteria(self):
        """Test filtering with multiple criteria"""
        db_path = Path(self.test_dir) / "test.db"
        filtered = Path(self.test_dir) / "filtered.db"

        convs = [
            self._create_conversation("conv1", source="chatgpt", tags=["python"], num_messages=5),
            self._create_conversation("conv2", source="chatgpt", tags=["javascript"], num_messages=3),
            self._create_conversation("conv3", source="claude", tags=["python"], num_messages=6),
            self._create_conversation("conv4", source="chatgpt", tags=["python"], num_messages=2)
        ]
        self._create_database(str(db_path), convs)

        # Filter for chatgpt conversations with python tag and 4+ messages
        stats = self.db_ops.filter(
            str(db_path),
            str(filtered),
            source="chatgpt",
            tags=["python"],
            min_messages=4
        )

        self.assertEqual(stats['total_output'], 1)  # Only conv1

    def test_filter_with_custom_query(self):
        """Test filtering with custom SQL query"""
        db_path = Path(self.test_dir) / "test.db"
        filtered = Path(self.test_dir) / "filtered.db"

        convs = [
            self._create_conversation("conv1", title="Important Discussion"),
            self._create_conversation("conv2", title="Casual Chat"),
            self._create_conversation("conv3", title="Important Meeting"),
            self._create_conversation("conv4", title="Random Talk")
        ]
        self._create_database(str(db_path), convs)

        # Custom query to filter by title containing "Important"
        stats = self.db_ops.filter(
            str(db_path),
            str(filtered),
            query="title LIKE '%Important%'"
        )

        self.assertEqual(stats['total_output'], 2)

    # =============================================================================
    # SPLIT TESTS
    # =============================================================================

    def test_split_by_count(self):
        """Test splitting database by count"""
        db_path = Path(self.test_dir) / "test.db"

        convs = [self._create_conversation(f"conv{i}") for i in range(10)]
        self._create_database(str(db_path), convs)

        output_dbs = self.db_ops.split(
            str(db_path),
            self.test_dir,
            split_by="count",
            value=3
        )

        # Should create 4 databases (3, 3, 3, 1)
        self.assertEqual(len(output_dbs), 4)

        # Check counts
        counts = [self._count_conversations(db) for db in output_dbs]
        self.assertEqual(counts, [3, 3, 3, 1])

    def test_split_by_size(self):
        """Test splitting database by size"""
        db_path = Path(self.test_dir) / "test.db"

        # Create conversations of different sizes
        convs = []
        for i in range(5):
            # Vary message count to create different sizes
            convs.append(self._create_conversation(f"conv{i}", num_messages=(i+1)*2))

        self._create_database(str(db_path), convs)

        # Get database size
        db_size = Path(db_path).stat().st_size

        # Split into chunks of approximately half the size
        output_dbs = self.db_ops.split(
            str(db_path),
            self.test_dir,
            split_by="size",
            value=db_size // 2
        )

        # Should create at least 2 databases
        self.assertGreaterEqual(len(output_dbs), 2)

    def test_split_by_source(self):
        """Test splitting database by source"""
        db_path = Path(self.test_dir) / "test.db"

        convs = [
            self._create_conversation("conv1", source="chatgpt"),
            self._create_conversation("conv2", source="claude"),
            self._create_conversation("conv3", source="chatgpt"),
            self._create_conversation("conv4", source="copilot"),
            self._create_conversation("conv5", source="claude")
        ]
        self._create_database(str(db_path), convs)

        output_dbs = self.db_ops.split(
            str(db_path),
            self.test_dir,
            split_by="source"
        )

        # Should create 3 databases (one per source)
        self.assertEqual(len(output_dbs), 3)

        # Verify each database contains only one source
        for db_path in output_dbs:
            db = ConversationDB(db_path)
            convs = db.list_conversations()

            if convs:
                first_conv = db.load_conversation(convs[0]['id'])
                source = first_conv.metadata.source

                # All conversations should have same source
                for conv_info in convs:
                    conv = db.load_conversation(conv_info['id'])
                    self.assertEqual(conv.metadata.source, source)

            db.close()

    def test_split_by_project(self):
        """Test splitting database by project"""
        db_path = Path(self.test_dir) / "test.db"

        convs = [
            self._create_conversation("conv1", project="project_a"),
            self._create_conversation("conv2", project="project_b"),
            self._create_conversation("conv3", project="project_a"),
            self._create_conversation("conv4", project=None),  # No project
            self._create_conversation("conv5", project="project_c")
        ]
        self._create_database(str(db_path), convs)

        output_dbs = self.db_ops.split(
            str(db_path),
            self.test_dir,
            split_by="project"
        )

        # Should create 4 databases (3 projects + 1 for no project)
        self.assertEqual(len(output_dbs), 4)

    # =============================================================================
    # DEDUPE TESTS
    # =============================================================================

    def test_dedupe_exact_duplicates(self):
        """Test deduplication of exact ID duplicates"""
        db_path = Path(self.test_dir) / "duplicates.db"
        deduped = Path(self.test_dir) / "deduped.db"

        # Create database with duplicate IDs
        db = ConversationDB(str(db_path))

        # Add same conversation multiple times (simulating import error)
        conv1 = self._create_conversation("dup", "First Version", num_messages=2)
        conv2 = self._create_conversation("dup", "Second Version", num_messages=3)
        conv3 = self._create_conversation("dup", "Third Version", num_messages=4)
        unique = self._create_conversation("unique", "Unique Conv")

        # Save in sequence
        db.save_conversation(conv1)
        db.save_conversation(conv2)
        db.save_conversation(conv3)
        db.save_conversation(unique)
        db.close()

        stats = self.db_ops.dedupe(
            str(db_path),
            str(deduped),
            strategy=DuplicateStrategy.EXACT,
            keep="longest"
        )

        self.assertEqual(stats['duplicates_found'], 2)  # 2 duplicates of "dup"
        self.assertEqual(stats['conversations_kept'], 2)  # "dup" and "unique"

        # Verify longest version was kept
        db = ConversationDB(str(deduped))
        conv = db.load_conversation("dup")
        db.close()

        self.assertEqual(len(conv.message_map), 4)  # Third version

    def test_dedupe_by_hash(self):
        """Test deduplication by content hash"""
        db_path = Path(self.test_dir) / "duplicates.db"
        deduped = Path(self.test_dir) / "deduped.db"

        # Create conversations with same content but different IDs
        convs = [
            self._create_conversation("conv1", "Same Title", num_messages=3),
            self._create_conversation("conv2", "Same Title", num_messages=3),  # Same content
            self._create_conversation("conv3", "Different", num_messages=2)
        ]

        # Make conv1 and conv2 have identical content
        convs[1].message_map = convs[0].message_map.copy()
        for msg_id in convs[1].message_map:
            convs[1].message_map[msg_id].id = msg_id.replace("conv1", "conv2")

        self._create_database(str(db_path), convs)

        stats = self.db_ops.dedupe(
            str(db_path),
            str(deduped),
            strategy=DuplicateStrategy.HASH
        )

        # Should find hash duplicates
        self.assertGreater(stats['duplicates_found'], 0)

    def test_dedupe_dry_run(self):
        """Test dedupe in dry run mode"""
        db_path = Path(self.test_dir) / "duplicates.db"

        convs = [
            self._create_conversation("dup", "Version 1"),
            self._create_conversation("dup", "Version 2"),
            self._create_conversation("unique", "Unique")
        ]

        db = ConversationDB(str(db_path))
        for conv in convs:
            db.save_conversation(conv)
        db.close()

        # Run in dry run mode
        stats = self.db_ops.dedupe(
            str(db_path),
            dry_run=True
        )

        # Should report duplicates but not remove them
        self.assertEqual(stats['duplicates_found'], 1)
        self.assertEqual(stats['conversations_removed'], 0)

        # Original database should be unchanged
        self.assertEqual(self._count_conversations(str(db_path)), 2)  # Still has both versions of "dup"

    def test_dedupe_in_place(self):
        """Test in-place deduplication"""
        db_path = Path(self.test_dir) / "duplicates.db"

        convs = [
            self._create_conversation("dup", "Version 1"),
            self._create_conversation("dup", "Version 2"),
            self._create_conversation("unique", "Unique")
        ]

        db = ConversationDB(str(db_path))
        for conv in convs:
            db.save_conversation(conv)
        db.close()

        initial_count = self._count_conversations(str(db_path))

        # Dedupe in place (no output_db specified)
        stats = self.db_ops.dedupe(
            str(db_path),
            output_db=None,  # In-place
            strategy=DuplicateStrategy.EXACT
        )

        # Database should have fewer conversations
        final_count = self._count_conversations(str(db_path))
        self.assertLess(final_count, initial_count)
        self.assertEqual(final_count, 2)  # dup (one version) + unique

    # =============================================================================
    # COMPARATOR TESTS
    # =============================================================================

    def test_comparator_identical_conversations(self):
        """Test comparator with identical conversations"""
        conv1 = self._create_conversation("test", "Title", num_messages=3)
        conv2 = self._create_conversation("test", "Title", num_messages=3)

        comparator = ConversationComparator()

        # Identical conversations should have same hash
        hash1 = comparator.compute_hash(conv1)
        hash2 = comparator.compute_hash(conv2)
        self.assertEqual(hash1, hash2)

        # And high similarity
        similarity = comparator.compute_similarity(conv1, conv2)
        self.assertGreater(similarity, 0.99)

    def test_comparator_different_conversations(self):
        """Test comparator with different conversations"""
        conv1 = self._create_conversation("test", "Title 1", num_messages=3)
        conv2 = self._create_conversation("test", "Title 2", num_messages=4)

        comparator = ConversationComparator()

        # Different conversations should have different hashes
        hash1 = comparator.compute_hash(conv1)
        hash2 = comparator.compute_hash(conv2)
        self.assertNotEqual(hash1, hash2)

        # And lower similarity
        similarity = comparator.compute_similarity(conv1, conv2)
        self.assertLess(similarity, 0.9)

    def test_comparator_similarity_threshold(self):
        """Test comparator similarity calculation"""
        conv1 = self._create_conversation("test", "Similar Title", num_messages=5)
        conv2 = self._create_conversation("test", "Similar Title!", num_messages=5)

        comparator = ConversationComparator()

        similarity = comparator.compute_similarity(conv1, conv2)

        # Should be similar but not identical
        self.assertGreater(similarity, 0.8)
        self.assertLess(similarity, 1.0)

    def test_comparator_with_branches(self):
        """Test comparator with branching conversations"""
        conv1 = self._create_conversation("test", "Branched", num_messages=5, branch_at=2)
        conv2 = self._create_conversation("test", "Branched", num_messages=5, branch_at=3)

        comparator = ConversationComparator()

        # Different branch points should make them different
        hash1 = comparator.compute_hash(conv1)
        hash2 = comparator.compute_hash(conv2)
        self.assertNotEqual(hash1, hash2)

    # =============================================================================
    # ERROR HANDLING TESTS
    # =============================================================================

    def test_merge_nonexistent_database(self):
        """Test merge with nonexistent input database"""
        output = Path(self.test_dir) / "output.db"
        nonexistent = Path(self.test_dir) / "nonexistent.db"

        with self.assertRaises(Exception):
            self.db_ops.merge([str(nonexistent)], str(output))

    def test_filter_invalid_query(self):
        """Test filter with invalid SQL query"""
        db_path = Path(self.test_dir) / "test.db"
        filtered = Path(self.test_dir) / "filtered.db"

        self._create_database(str(db_path), [self._create_conversation("test")])

        # Invalid SQL should raise exception
        with self.assertRaises(Exception):
            self.db_ops.filter(
                str(db_path),
                str(filtered),
                query="INVALID SQL SYNTAX HERE"
            )

    def test_split_empty_database(self):
        """Test splitting an empty database"""
        db_path = Path(self.test_dir) / "empty.db"

        self._create_database(str(db_path), [])

        output_dbs = self.db_ops.split(
            str(db_path),
            self.test_dir,
            split_by="count",
            value=5
        )

        # Should create no output databases for empty input
        self.assertEqual(len(output_dbs), 0)

    def test_operations_with_corrupted_database(self):
        """Test operations with corrupted database file"""
        db_path = Path(self.test_dir) / "corrupted.db"

        # Create a corrupted database file
        with open(db_path, 'wb') as f:
            f.write(b"This is not a valid SQLite database")

        output = Path(self.test_dir) / "output.db"

        # Operations should handle corrupted database gracefully
        with self.assertRaises(sqlite3.DatabaseError):
            self.db_ops.merge([str(db_path)], str(output))

    # =============================================================================
    # PERFORMANCE TESTS
    # =============================================================================

    def test_large_batch_processing(self):
        """Test operations with large batches"""
        db_path = Path(self.test_dir) / "large.db"

        # Create many conversations
        convs = [self._create_conversation(f"conv{i}") for i in range(100)]
        self._create_database(str(db_path), convs)

        # Test with different batch sizes
        for batch_size in [10, 50, 100]:
            ops = DatabaseOperations(batch_size=batch_size)

            output = Path(self.test_dir) / f"output_{batch_size}.db"
            stats = ops.merge([str(db_path)], str(output))

            self.assertEqual(stats['total_output'], 100)

    def test_streaming_large_database(self):
        """Test streaming operations on large database"""
        db_path = Path(self.test_dir) / "large.db"

        # Create database with many conversations
        db = ConversationDB(str(db_path))
        for i in range(50):
            conv = self._create_conversation(f"conv{i}", num_messages=10)
            db.save_conversation(conv)
        db.close()

        # Test streaming with filter
        filtered = Path(self.test_dir) / "filtered.db"
        stats = self.db_ops.filter(
            str(db_path),
            str(filtered),
            min_messages=5
        )

        self.assertEqual(stats['total_input'], 50)
        self.assertEqual(stats['total_output'], 50)  # All have 10 messages


if __name__ == '__main__':
    unittest.main()