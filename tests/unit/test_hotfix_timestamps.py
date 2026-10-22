"""Regression tests: a conversation's updated_at survives save and load (2.20.1)."""

from datetime import datetime

import pytest
from sqlalchemy import text

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)

pytestmark = pytest.mark.unit

STAMP = datetime(2024, 1, 1, 10, 0, 0)


def _tree(conv_id="c1", updated_at=STAMP, n_messages=2, title="t"):
    tree = ConversationTree(
        id=conv_id,
        title=title,
        metadata=ConversationMetadata(
            created_at=datetime(2023, 12, 31), updated_at=None
        ),
    )
    parent = None
    for i in range(n_messages):
        msg = Message(
            id=f"m{i}",
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=MessageContent(text=f"msg {i}"),
            parent_id=parent,
        )
        tree.add_message(msg)
        parent = msg.id
    tree.metadata.updated_at = updated_at  # add_message stamps now(); override
    return tree


def _stored_updated_at(db, conv_id):
    with db.engine.connect() as conn:
        raw = conn.execute(
            text("SELECT updated_at FROM conversations WHERE id = :i"), {"i": conv_id}
        ).scalar()
    return datetime.fromisoformat(str(raw))


@pytest.fixture
def db(tmp_path):
    db = ConversationDB(str(tmp_path / "db"))
    yield db
    db.close()


class TestSavePreservesUpdatedAt:
    @pytest.mark.parametrize("n_messages", [0, 3])
    def test_new_conversation(self, db, n_messages):
        db.save_conversation(_tree(n_messages=n_messages))
        assert _stored_updated_at(db, "c1") == STAMP

    def test_resave_with_new_value(self, db):
        db.save_conversation(_tree())
        later = datetime(2024, 6, 1, 12, 30)
        db.save_conversation(_tree(updated_at=later))
        assert _stored_updated_at(db, "c1") == later

    def test_resave_unchanged_value(self, db):
        db.save_conversation(_tree())
        db.save_conversation(_tree())
        assert _stored_updated_at(db, "c1") == STAMP


class TestLoadPreservesUpdatedAt:
    def test_load_returns_stored_value(self, db):
        db.save_conversation(_tree())
        assert db.load_conversation("c1").metadata.updated_at == STAMP

    def test_load_save_roundtrip_is_stable(self, db):
        db.save_conversation(_tree())
        db.save_conversation(db.load_conversation("c1"))
        assert _stored_updated_at(db, "c1") == STAMP


class TestMergeNewestUsesRealTimestamps:
    def test_newest_version_wins(self, tmp_path):
        from ctk.core.db_operations import DatabaseOperations, MergeStrategy

        old_dir, new_dir, out_dir = (str(tmp_path / n) for n in ("a", "b", "out"))
        with ConversationDB(old_dir) as a:
            a.save_conversation(_tree(title="old", updated_at=datetime(2024, 1, 1)))
        with ConversationDB(new_dir) as b:
            b.save_conversation(_tree(title="new", updated_at=datetime(2025, 1, 1)))

        for order in ([old_dir, new_dir], [new_dir, old_dir]):
            DatabaseOperations().merge(order, out_dir, strategy=MergeStrategy.NEWEST)
            with ConversationDB(out_dir) as out:
                assert out.load_conversation("c1").title == "new", order


def _page_ids(db, page_size):
    ids, cursor = [], ""
    while True:
        page = db.list_conversations(cursor=cursor, page_size=page_size)
        ids += [c.id for c in page.items]
        if not page.has_more:
            return ids
        cursor = page.next_cursor


class TestCursorPaginationSubSecond:
    def test_same_second_rows_all_paged(self, db):
        base = datetime(2024, 1, 1, 10, 0, 0)
        for i, micro in enumerate([0, 250000, 500000, 750000]):
            db.save_conversation(
                _tree(conv_id=f"c{i}", updated_at=base.replace(microsecond=micro))
            )

        ids = _page_ids(db, page_size=1)

        assert ids == ["c3", "c2", "c1", "c0"]

    def test_star_writes_orm_format_timestamp(self, db):
        db.save_conversation(_tree())
        db.star_conversation("c1")
        with db.engine.connect() as conn:
            raw = conn.execute(text("SELECT updated_at FROM conversations")).scalar()
        assert len(raw) == len("2024-01-01 10:00:00.000000"), raw


class TestLegacyTimestampMigration:
    def test_whole_second_values_normalized_and_paged(self, tmp_path):
        from ctk.core.migrations import MIGRATIONS

        path = tmp_path / "legacy"
        db = ConversationDB(str(path))
        for i in range(3):
            db.save_conversation(_tree(conv_id=f"c{i}"))
        # Simulate rows stamped by the old func.now() defaults, then roll the
        # schema version back so the normalization migration runs on reopen.
        with db.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE conversations SET updated_at = '2024-01-01 10:00:00',"
                    " created_at = '2024-01-01 09:00:00'"
                )
            )
            conn.execute(text(f"PRAGMA user_version = {MIGRATIONS[-1].version - 1}"))
        db.close()

        db = ConversationDB(str(path))
        try:
            with db.engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT created_at, updated_at FROM conversations")
                ).fetchall()
            assert all(len(v) == 26 for row in rows for v in row), rows
            assert _page_ids(db, page_size=1) == ["c2", "c1", "c0"]
        finally:
            db.close()
