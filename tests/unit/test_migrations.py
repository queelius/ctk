# tests/unit/test_migrations.py
import sqlite3
import pytest
from sqlalchemy import text

from ctk.core.database import ConversationDB
from ctk.core.db_models import ConversationModel
from ctk.core.migrations import MIGRATIONS

pytestmark = pytest.mark.unit

# The conversations columns that existed before versioning (no slug/summary,
# no is_branching). Kept STATIC on purpose so the drift guard fails when a
# future ORM column has no migration. Update ONLY when adding a baseline col.
LEGACY_CONVERSATIONS_DDL = """
CREATE TABLE conversations (
    id VARCHAR PRIMARY KEY,
    title VARCHAR,
    created_at DATETIME,
    updated_at DATETIME,
    version VARCHAR,
    format VARCHAR,
    source VARCHAR,
    model VARCHAR,
    project VARCHAR,
    starred_at DATETIME,
    pinned_at DATETIME,
    archived_at DATETIME,
    metadata_json JSON
)
"""


def _make_legacy_db(dirpath):
    """Create a pre-versioning conversations.db at user_version 0."""
    dbfile = dirpath / "conversations.db"
    conn = sqlite3.connect(str(dbfile))
    conn.executescript(LEGACY_CONVERSATIONS_DDL)
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    return dbfile


def _conv_columns(db):
    with db.engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(conversations)")).fetchall()
    return {row[1] for row in rows}


def test_opening_legacy_db_upgrades_in_place(tmp_path):
    _make_legacy_db(tmp_path)
    db = ConversationDB(str(tmp_path))
    try:
        cols = _conv_columns(db)
        assert "slug" in cols and "summary" in cols
        with db.engine.connect() as conn:
            uv = conn.execute(text("PRAGMA user_version")).scalar()
            idx = conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_conv_slug'"
                )
            ).fetchone()
        assert uv == MIGRATIONS[-1].version
        assert idx is not None
    finally:
        db.close()


def test_drift_guard_migrated_schema_matches_orm(tmp_path):
    _make_legacy_db(tmp_path)
    db = ConversationDB(str(tmp_path))
    try:
        migrated = _conv_columns(db)
        declared = {c.name for c in ConversationModel.__table__.columns}
        missing = declared - migrated
        assert not missing, (
            f"ORM columns with no migration path from legacy schema: {missing}. "
            "Add a Migration step in ctk/core/migrations.py for each."
        )
    finally:
        db.close()


def test_legacy_db_save_round_trips_after_upgrade(tmp_path):
    import uuid
    from datetime import datetime
    from ctk.core.models import (
        ConversationMetadata,
        ConversationTree,
        Message,
        MessageContent,
        MessageRole,
    )

    _make_legacy_db(tmp_path)
    db = ConversationDB(str(tmp_path))
    try:
        tree = ConversationTree(
            id=str(uuid.uuid4()),
            title="after upgrade",
            metadata=ConversationMetadata(
                created_at=datetime.now(), updated_at=datetime.now()
            ),
        )
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.USER,
                content=MessageContent(text="hi"),
                timestamp=datetime.now(),
            )
        )
        db.save_conversation(tree)
        loaded = db.load_conversation(tree.id)
        assert loaded is not None and loaded.title == "after upgrade"
    finally:
        db.close()


def test_indexes_serve_slug_and_listing(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        with db.engine.connect() as conn:
            slug_plan = conn.execute(
                text("EXPLAIN QUERY PLAN SELECT id FROM conversations WHERE slug = 'x'")
            ).fetchall()
            slug_text = " ".join(str(r) for r in slug_plan)
            assert "idx_conv_slug" in slug_text, slug_text

            list_plan = conn.execute(
                text(
                    "EXPLAIN QUERY PLAN SELECT id FROM conversations "
                    "WHERE archived_at IS NULL ORDER BY updated_at DESC, id LIMIT 51"
                )
            ).fetchall()
            list_text = " ".join(str(r) for r in list_plan)
            assert "idx_conv_list" in list_text, list_text
            assert "USE TEMP B-TREE" not in list_text.upper(), list_text
    finally:
        db.close()


def test_migration_4_converges_stale_list_index(tmp_path):
    """DB at user_version 3 with the old idx_conv_list shape gets converged by migration 4."""
    # Step 1: create a fully-migrated DB (ends at user_version 4 normally).
    db = ConversationDB(str(tmp_path))
    db.close()

    # Step 2: rewind it to look like a DB at user_version 3 with the old index shape.
    dbfile = str(tmp_path / "conversations.db")
    conn = sqlite3.connect(dbfile)
    conn.execute("DROP INDEX IF EXISTS idx_conv_list")
    conn.execute(
        "CREATE INDEX idx_conv_list "
        "ON conversations(updated_at DESC, id) WHERE archived_at IS NULL"
    )
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()

    # Step 3: reopen; migration 4 must fire and rebuild the index.
    db2 = ConversationDB(str(tmp_path))
    try:
        with db2.engine.connect() as c:
            row = c.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='index' AND name='idx_conv_list'"
                )
            ).fetchone()
        assert row is not None, "idx_conv_list index not found after migration 4"
        index_sql = row[0]
        assert (
            "archived_at" in index_sql
        ), f"migration 4 did not rebuild idx_conv_list with archived_at; got: {index_sql}"
    finally:
        db2.close()


def test_failed_migration_raises_and_does_not_advance_version(tmp_path, monkeypatch):
    import ctk.core.migrations as m

    _make_legacy_db(tmp_path)

    def boom(conn):
        raise RuntimeError("simulated DDL failure")

    bad = m.Migration(version=999, name="boom", apply=boom)
    monkeypatch.setattr(m, "MIGRATIONS", m.MIGRATIONS + [bad])
    with pytest.raises(m.MigrationError):
        ConversationDB(str(tmp_path))
    # version stayed at the last good migration, not 999
    conn = sqlite3.connect(str(tmp_path / "conversations.db"))
    uv = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert uv < 999
