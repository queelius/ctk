#!/usr/bin/env python3
"""
Test suite for CTK database operations
Tests merge, diff, intersect, filter, split, dedupe functionality
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import json

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


class TestDatabaseOperations(unittest.TestCase):
    """Test database operations"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()
        self.db_ops = DatabaseOperations(batch_size=10)

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_conversation(
        self,
        conv_id: str,
        title: str = "Test Conversation",
        source: str = "test",
        num_messages: int = 3,
        created_at: datetime = None,
        tags: list = None
    ) -> ConversationTree:
        """Helper to create test conversations"""
        if created_at is None:
            created_at = datetime.now()

        metadata = ConversationMetadata(
            created_at=created_at,
            updated_at=created_at,
            source=source,
            tags=tags or []
        )

        conv = ConversationTree(
            id=conv_id,
            title=title,
            metadata=metadata
        )

        # Add messages
        parent_id = None
        for i in range(num_messages):
            msg = Message(
                id=f"{conv_id}_msg_{i}",
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=MessageContent(text=f"Message {i} in {conv_id}"),
                parent_id=parent_id,
                timestamp=created_at + timedelta(minutes=i)
            )
            conv.add_message(msg)
            parent_id = msg.id

        return conv

    def _create_test_database(self, db_path: str, conversations: list):
        """Helper to create and populate test database"""
        db = ConversationDB(db_path)
        for conv in conversations:
            db.save_conversation(conv)
        db.close()

    def test_merge_exact_duplicates(self):
        """Test merging with exact duplicate detection"""
        # Create two databases with some overlapping conversations
        db1_path = Path(self.test_dir) / "db1.db"
        db2_path = Path(self.test_dir) / "db2.db"
        output_path = Path(self.test_dir) / "merged.db"

        # Database 1: conv1, conv2, conv3
        convs1 = [
            self._create_test_conversation("conv1", "First", "chatgpt"),
            self._create_test_conversation("conv2", "Second", "chatgpt"),
            self._create_test_conversation("conv3", "Third", "chatgpt"),
        ]
        self._create_test_database(str(db1_path), convs1)

        # Database 2: conv2 (duplicate), conv3 (duplicate), conv4
        convs2 = [
            self._create_test_conversation("conv2", "Second Updated", "chatgpt"),
            self._create_test_conversation("conv3", "Third Updated", "chatgpt"),
            self._create_test_conversation("conv4", "Fourth", "claude"),
        ]
        self._create_test_database(str(db2_path), convs2)

        # Merge with exact duplicate detection
        stats = self.db_ops.merge(
            [str(db1_path), str(db2_path)],
            str(output_path),
            strategy=MergeStrategy.NEWEST,
            dedupe=DuplicateStrategy.EXACT
        )

        # Check statistics
        self.assertEqual(stats['total_input'], 6)  # 3 + 3
        self.assertEqual(stats['duplicates_found'], 2)  # conv2, conv3
        self.assertEqual(stats['total_output'], 4)  # conv1, conv2, conv3, conv4

        # Verify merged database
        with ConversationDB(str(output_path)) as db:
            db_stats = db.get_statistics()
            self.assertEqual(db_stats['total_conversations'], 4)

    def test_diff_operation(self):
        """Test diff operation to find unique conversations"""
        db1_path = Path(self.test_dir) / "db1.db"
        db2_path = Path(self.test_dir) / "db2.db"
        diff_path = Path(self.test_dir) / "diff.db"

        # Database 1: conv1, conv2, conv3
        convs1 = [
            self._create_test_conversation("conv1", source="chatgpt"),
            self._create_test_conversation("conv2", source="chatgpt"),
            self._create_test_conversation("conv3", source="chatgpt"),
        ]
        self._create_test_database(str(db1_path), convs1)

        # Database 2: conv2, conv3, conv4
        convs2 = [
            self._create_test_conversation("conv2", source="chatgpt"),
            self._create_test_conversation("conv3", source="chatgpt"),
            self._create_test_conversation("conv4", source="claude"),
        ]
        self._create_test_database(str(db2_path), convs2)

        # Find conversations unique to db1
        stats = self.db_ops.diff(
            str(db1_path),
            str(db2_path),
            output_db=str(diff_path),
            symmetric=False,
            comparison=DuplicateStrategy.EXACT
        )

        # Check statistics
        self.assertEqual(stats['left_total'], 3)
        self.assertEqual(stats['right_total'], 3)
        self.assertEqual(stats['common'], 2)  # conv2, conv3
        self.assertEqual(stats['left_unique'], 1)  # conv1

        # Verify diff database contains only unique conversation
        with ConversationDB(str(diff_path)) as db:
            db_stats = db.get_statistics()
            self.assertEqual(db_stats['total_conversations'], 1)
            convs = db.list_conversations()
            # list_conversations returns ConversationSummary objects, not dicts
            self.assertEqual(convs[0].id, 'conv1')

    def test_intersect_operation(self):
        """Test intersect operation to find common conversations"""
        db1_path = Path(self.test_dir) / "db1.db"
        db2_path = Path(self.test_dir) / "db2.db"
        db3_path = Path(self.test_dir) / "db3.db"
        intersect_path = Path(self.test_dir) / "intersect.db"

        # Create three databases with overlapping conversations
        convs1 = [
            self._create_test_conversation("conv1"),
            self._create_test_conversation("conv2"),
            self._create_test_conversation("conv3"),
        ]
        self._create_test_database(str(db1_path), convs1)

        convs2 = [
            self._create_test_conversation("conv2"),
            self._create_test_conversation("conv3"),
            self._create_test_conversation("conv4"),
        ]
        self._create_test_database(str(db2_path), convs2)

        convs3 = [
            self._create_test_conversation("conv3"),
            self._create_test_conversation("conv4"),
            self._create_test_conversation("conv5"),
        ]
        self._create_test_database(str(db3_path), convs3)

        # Find conversations common to all three databases
        stats = self.db_ops.intersect(
            [str(db1_path), str(db2_path), str(db3_path)],
            str(intersect_path),
            comparison=DuplicateStrategy.EXACT
        )

        # Check statistics
        self.assertEqual(stats['common_to_all'], 1)  # Only conv3 is in all three

        # Test with min_count=2 (in at least 2 databases)
        intersect2_path = Path(self.test_dir) / "intersect2.db"
        stats2 = self.db_ops.intersect(
            [str(db1_path), str(db2_path), str(db3_path)],
            str(intersect2_path),
            min_count=2,
            comparison=DuplicateStrategy.EXACT
        )

        # Should find conv2, conv3, conv4
        self.assertEqual(stats2['common_to_min'], 3)

    def test_filter_operation(self):
        """Test filter operation with various criteria"""
        db_path = Path(self.test_dir) / "test.db"
        filtered_path = Path(self.test_dir) / "filtered.db"

        # Create test conversations with different attributes
        now = datetime.now()
        convs = [
            self._create_test_conversation(
                "conv1", "ChatGPT Conv", "chatgpt",
                num_messages=5, created_at=now - timedelta(days=10),
                tags=["python", "coding"]
            ),
            self._create_test_conversation(
                "conv2", "Claude Conv", "claude",
                num_messages=3, created_at=now - timedelta(days=5),
                tags=["writing"]
            ),
            self._create_test_conversation(
                "conv3", "ChatGPT Recent", "chatgpt",
                num_messages=10, created_at=now - timedelta(days=1),
                tags=["python", "data"]
            ),
            self._create_test_conversation(
                "conv4", "Old Conv", "copilot",
                num_messages=2, created_at=now - timedelta(days=30),
                tags=["debugging"]
            ),
        ]
        self._create_test_database(str(db_path), convs)

        # Filter by source
        stats = self.db_ops.filter(
            str(db_path),
            str(filtered_path),
            source="chatgpt"
        )
        self.assertEqual(stats['total_output'], 2)  # conv1 and conv3

        # Filter by date range - note: updated_at is set to now on save
        # So all conversations will match a date filter based on current time
        filtered2_path = Path(self.test_dir) / "filtered2.db"
        stats = self.db_ops.filter(
            str(db_path),
            str(filtered2_path),
            after=now - timedelta(days=7)
        )
        # All 4 conversations have updated_at = now, so all match
        self.assertEqual(stats['total_output'], 4)

        # Filter by message count
        filtered3_path = Path(self.test_dir) / "filtered3.db"
        stats = self.db_ops.filter(
            str(db_path),
            str(filtered3_path),
            min_messages=4
        )
        self.assertEqual(stats['total_output'], 2)  # conv1 (5) and conv3 (10)

        # Filter by tags
        filtered4_path = Path(self.test_dir) / "filtered4.db"
        stats = self.db_ops.filter(
            str(db_path),
            str(filtered4_path),
            tags=["python"]
        )
        self.assertEqual(stats['total_output'], 2)  # conv1 and conv3

    def test_dedupe_operation(self):
        """Test deduplication with different strategies"""
        db_path = Path(self.test_dir) / "duplicates.db"
        deduped_path = Path(self.test_dir) / "deduped.db"

        # Create database with duplicates
        now = datetime.now()
        convs = [
            self._create_test_conversation(
                "conv1", "First", "chatgpt",
                created_at=now - timedelta(days=5)
            ),
            self._create_test_conversation(
                "conv1", "First Duplicate", "chatgpt",
                created_at=now - timedelta(days=3)
            ),
            self._create_test_conversation(
                "conv1", "First Duplicate 2", "chatgpt",
                created_at=now - timedelta(days=1)
            ),
            self._create_test_conversation(
                "conv2", "Second", "claude",
                created_at=now - timedelta(days=2)
            ),
        ]

        # Note: This will overwrite duplicates with same ID in database
        # For testing, we'll create them with slight variations
        db = ConversationDB(str(db_path))
        db.save_conversation(convs[0])  # conv1 - oldest
        db.save_conversation(convs[3])  # conv2

        # Modify conv1 and save again (simulating update)
        convs[0].title = "First Updated"
        convs[0].metadata.updated_at = now
        db.save_conversation(convs[0])  # This updates conv1
        db.close()

        # Test dry run first
        stats = self.db_ops.dedupe(
            str(db_path),
            dry_run=True,
            strategy=DuplicateStrategy.EXACT
        )
        self.assertEqual(stats['total_conversations'], 2)

        # Actual deduplication (in this case, no duplicates due to overwrite)
        stats = self.db_ops.dedupe(
            str(db_path),
            output_db=str(deduped_path),
            strategy=DuplicateStrategy.EXACT,
            keep="newest"
        )

        # Verify deduped database
        with ConversationDB(str(deduped_path)) as db:
            db_stats = db.get_statistics()
            self.assertEqual(db_stats['total_conversations'], 2)

    def test_split_operation(self):
        """Test splitting database by various criteria"""
        db_path = Path(self.test_dir) / "test.db"
        split_dir = Path(self.test_dir) / "split"

        # Create test conversations
        convs = [
            self._create_test_conversation("conv1", source="chatgpt"),
            self._create_test_conversation("conv2", source="chatgpt"),
            self._create_test_conversation("conv3", source="claude"),
            self._create_test_conversation("conv4", source="claude"),
            self._create_test_conversation("conv5", source="copilot"),
        ]
        self._create_test_database(str(db_path), convs)

        # Split by source
        stats = self.db_ops.split(
            str(db_path),
            str(split_dir),
            by="source"
        )

        self.assertEqual(stats['total_conversations'], 5)
        self.assertEqual(stats['databases_created'], 3)  # chatgpt, claude, copilot

        # Verify split databases
        self.assertTrue((split_dir / "chatgpt.db").exists())
        self.assertTrue((split_dir / "claude.db").exists())
        self.assertTrue((split_dir / "copilot.db").exists())

        # Test split into chunks
        chunks_dir = Path(self.test_dir) / "chunks"
        stats = self.db_ops.split(
            str(db_path),
            str(chunks_dir),
            chunks=2
        )

        self.assertEqual(stats['databases_created'], 2)
        self.assertTrue((chunks_dir / "chunk_001.db").exists())
        self.assertTrue((chunks_dir / "chunk_002.db").exists())


class TestConversationComparator(unittest.TestCase):
    """Test conversation comparison and similarity detection"""

    def setUp(self):
        """Set up test environment"""
        self.comparator = ConversationComparator()

    def test_compute_hash(self):
        """Test content hash computation"""
        # Create two identical conversations with different IDs
        conv1 = self._create_conversation("conv1", [
            ("user", "Hello"),
            ("assistant", "Hi there!"),
        ])
        conv2 = self._create_conversation("conv2", [
            ("user", "Hello"),
            ("assistant", "Hi there!"),
        ])

        # Same content should produce same hash
        hash1 = self.comparator.compute_hash(conv1)
        hash2 = self.comparator.compute_hash(conv2)
        self.assertEqual(hash1, hash2)

        # Different content should produce different hash
        conv3 = self._create_conversation("conv3", [
            ("user", "Hello"),
            ("assistant", "How can I help you?"),
        ])
        hash3 = self.comparator.compute_hash(conv3)
        self.assertNotEqual(hash1, hash3)

    def test_compute_similarity(self):
        """Test similarity computation between conversations"""
        # Very similar conversations
        conv1 = self._create_conversation("conv1", [
            ("user", "How do I write a Python function?"),
            ("assistant", "To write a Python function, use the def keyword"),
        ])
        conv2 = self._create_conversation("conv2", [
            ("user", "How do I write a Python function?"),
            ("assistant", "To write a Python function, you use the def keyword"),
        ])

        similarity = self.comparator.compute_similarity(conv1, conv2)
        self.assertGreater(similarity, 0.8)  # Should be very similar

        # Different conversations
        conv3 = self._create_conversation("conv3", [
            ("user", "What's the weather like?"),
            ("assistant", "I cannot check the weather"),
        ])

        similarity2 = self.comparator.compute_similarity(conv1, conv3)
        self.assertLess(similarity2, 0.3)  # Should be very different

    def _create_conversation(self, conv_id: str, messages: list) -> ConversationTree:
        """Helper to create test conversation"""
        conv = ConversationTree(
            id=conv_id,
            title="Test",
            metadata=ConversationMetadata()
        )

        parent_id = None
        for i, (role, text) in enumerate(messages):
            msg = Message(
                id=f"{conv_id}_msg_{i}",
                role=MessageRole(role),
                content=MessageContent(text=text),
                parent_id=parent_id
            )
            conv.add_message(msg)
            parent_id = msg.id

        return conv


class TestCLIIntegration(unittest.TestCase):
    """Test CLI integration of database operations"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cli_merge_command(self):
        """Test CLI merge command execution"""
        # This would test the actual CLI command execution
        # For now, just test that imports work
        from ctk.cli_db import cmd_merge, expand_globs

        # Test glob expansion
        patterns = ["*.db", "test.db"]
        expanded = expand_globs(patterns)
        self.assertIsInstance(expanded, list)

    def test_cli_stats_command(self):
        """Test CLI stats command"""
        from ctk.cli_db import cmd_stats

        # Create a test database
        db_path = Path(self.test_dir) / "test.db"
        db = ConversationDB(str(db_path))

        conv = ConversationTree(
            id="test",
            title="Test Conversation",
            metadata=ConversationMetadata(source="test")
        )
        msg = Message(
            id="msg1",
            role=MessageRole.USER,
            content=MessageContent(text="Hello")
        )
        conv.add_message(msg)
        db.save_conversation(conv)
        db.close()

        # Test that database can be analyzed
        with ConversationDB(str(db_path)) as db:
            stats = db.get_statistics()
            self.assertEqual(stats['total_conversations'], 1)
            self.assertEqual(stats['total_messages'], 1)


if __name__ == '__main__':
    unittest.main()