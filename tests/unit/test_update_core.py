"""Tests for the _update_core shared mutation helper in ctk.core.builtin_tools."""

import pytest

from ctk.core.builtin_tools import _update_core
from ctk.core.database import ConversationDB
from ctk.core.models import ConversationTree, Message, MessageContent, MessageRole

pytestmark = pytest.mark.unit

_CONV_ID = "aaaabbbb-0000-0000-0000-000000000000"
_PREFIX = _CONV_ID[:8]


def _seed_db(db: ConversationDB) -> None:
    tree = ConversationTree(id=_CONV_ID, title="Test")
    tree.add_message(
        Message(
            id="m1",
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
            parent_id=None,
        )
    )
    db.save_conversation(tree)


def test_star_only_stars(tmp_path):
    """_update_core(starred=True) stars the conversation and does not touch pinned/archived."""
    db = ConversationDB(str(tmp_path))
    try:
        _seed_db(db)
        full, changes = _update_core(db, _PREFIX, starred=True)
        assert not full.startswith("Error:")
        assert full == _CONV_ID

        # Starred
        loaded = db.load_conversation(full)
        assert loaded.metadata.starred_at is not None

        # Not pinned, not archived
        assert loaded.metadata.pinned_at is None
        assert loaded.metadata.archived_at is None

        assert changes  # at least one change recorded
    finally:
        db.close()


def test_missing_id_returns_error_sentinel(tmp_path):
    """_update_core with an unknown id returns the Error: sentinel and empty changes."""
    db = ConversationDB(str(tmp_path))
    try:
        full, changes = _update_core(db, "zzzzzzzz", starred=True)
        assert full.startswith("Error:")
        assert changes == []
    finally:
        db.close()


def test_rename(tmp_path):
    """_update_core(title=...) renames the conversation."""
    db = ConversationDB(str(tmp_path))
    try:
        _seed_db(db)
        full, changes = _update_core(db, _PREFIX, title="New Title")
        assert not full.startswith("Error:")

        loaded = db.load_conversation(full)
        assert loaded.title == "New Title"
        assert changes
    finally:
        db.close()


def test_multi_field_applies_all(tmp_path):
    """_update_core with multiple fields applies all of them."""
    db = ConversationDB(str(tmp_path))
    try:
        _seed_db(db)
        full, changes = _update_core(db, _PREFIX, starred=True, pinned=True)
        assert not full.startswith("Error:")

        loaded = db.load_conversation(full)
        assert loaded.metadata.starred_at is not None
        assert loaded.metadata.pinned_at is not None
        assert len(changes) == 2
    finally:
        db.close()


def test_no_fields_is_noop(tmp_path):
    """_update_core with no fields still resolves the id and returns it."""
    db = ConversationDB(str(tmp_path))
    try:
        _seed_db(db)
        full, changes = _update_core(db, _PREFIX)
        assert full == _CONV_ID
        assert changes == []
    finally:
        db.close()
