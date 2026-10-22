"""Regression test: in-place dedupe deletes whole conversations, not just rows (2.20.1)."""

import pytest
from sqlalchemy import text

from ctk.core.database import ConversationDB
from ctk.core.db_operations import DatabaseOperations, DuplicateStrategy
from ctk.core.models import ConversationTree, Message, MessageContent, MessageRole

pytestmark = pytest.mark.unit


def _conv(conv_id):
    tree = ConversationTree(id=conv_id, title="same")
    tree.metadata.tags = ["dup"]
    tree.add_message(
        Message(id="m1", role=MessageRole.USER, content=MessageContent(text="hello"))
    )
    tree.add_message(
        Message(
            id="m2",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="hi there"),
            parent_id="m1",
        )
    )
    return tree


def _count(db, table):
    with db.engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()


def test_in_place_hash_dedupe_leaves_no_orphans(tmp_path):
    path = str(tmp_path / "db")
    with ConversationDB(path) as db:
        db.save_conversation(_conv("a"))
        db.save_conversation(_conv("b"))
        db.save_similarity("a", "b", 1.0, "cosine", "tfidf")

    stats = DatabaseOperations().dedupe(path, strategy=DuplicateStrategy.HASH)

    assert stats["conversations_removed"] == 1
    with ConversationDB(path) as db:
        assert _count(db, "conversations") == 1
        assert _count(db, "messages") == 2
        assert _count(db, "conversation_tags") == 1
        assert _count(db, "similarities") == 0
        assert db.get_statistics()["total_messages"] == 2
