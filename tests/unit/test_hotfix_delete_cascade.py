"""Regression tests: deleting a conversation removes its analysis rows (2.20.1)."""

import pytest
from sqlalchemy import text

from ctk.core.database import ConversationDB
from ctk.core.models import ConversationTree

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path):
    db = ConversationDB(str(tmp_path / "db"))
    for conv_id in ("a", "b", "c"):
        db.save_conversation(ConversationTree(id=conv_id, title=conv_id))
    yield db
    db.close()


def _count(db, sql):
    with db.engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


@pytest.mark.parametrize("victim", ["a", "b"])  # as conversation1 and conversation2
def test_delete_conversation_with_similarities(db, victim):
    db.save_similarity("a", "b", 0.9, "cosine", "tfidf")
    db.save_similarity("b", "c", 0.5, "cosine", "tfidf")

    assert db.delete_conversation(victim) is True

    assert db.load_conversation(victim) is None
    remaining = _count(
        db,
        "SELECT count(*) FROM similarities "
        f"WHERE conversation1_id = '{victim}' OR conversation2_id = '{victim}'",
    )
    assert remaining == 0


def test_delete_keeps_unrelated_similarities(db):
    db.save_similarity("a", "b", 0.9, "cosine", "tfidf")
    db.save_similarity("b", "c", 0.5, "cosine", "tfidf")

    db.delete_conversation("a")

    assert _count(db, "SELECT count(*) FROM similarities") == 1
