"""Guard tests for the update_conversation builtin tool (Task 5, C2)."""

import pytest

import ctk.core.builtin_tools  # noqa: F401 -- ensures handlers are registered
from ctk.core.builtin_tools import execute_builtin_tool
from ctk.core.database import ConversationDB
from ctk.core.models import ConversationTree, ConversationMetadata

pytestmark = pytest.mark.unit


def _make_db():
    """Return a fresh in-memory ConversationDB with one saved conversation."""
    db = ConversationDB(":memory:")
    tree = ConversationTree(
        id="aaaaaaaa-0000-0000-0000-000000000001",
        title="Test conversation",
        metadata=ConversationMetadata(),
    )
    db.save_conversation(tree)
    return db, tree.id


# ---------------------------------------------------------------------------
# multi-field: starred=True, title="X" -> both applied, summary returned
# ---------------------------------------------------------------------------


def test_multi_field_update_returns_summary():
    db, conv_id = _make_db()
    prefix = conv_id[:8]
    result = execute_builtin_tool(
        db,
        "update_conversation",
        {"conversation_id": prefix, "starred": True, "title": "X"},
    )
    assert "Starred" in result
    assert 'Title set to "X"' in result
    assert result.startswith("Updated")


def test_multi_field_applies_to_db():
    db, conv_id = _make_db()
    prefix = conv_id[:8]
    execute_builtin_tool(
        db,
        "update_conversation",
        {"conversation_id": prefix, "starred": True, "title": "New Name"},
    )
    convs = db.list_conversations(starred=True)
    found = [c for c in convs if c.id == conv_id]
    assert found, "conversation should be starred after update"
    assert found[0].title == "New Name"


# ---------------------------------------------------------------------------
# no-op: conversation_id only, no other fields -> "No changes specified"
# ---------------------------------------------------------------------------


def test_no_fields_returns_no_changes():
    db, conv_id = _make_db()
    result = execute_builtin_tool(
        db,
        "update_conversation",
        {"conversation_id": conv_id[:8]},
    )
    assert result == "No changes specified"


# ---------------------------------------------------------------------------
# tri-state false applies: archived=False clears the archived flag
# ---------------------------------------------------------------------------


def test_false_archived_clears_flag():
    db, conv_id = _make_db()
    # First archive the conversation
    db.archive_conversation(conv_id, archive=True)
    # Verify it's archived
    archived = db.list_conversations(archived=True, include_archived=True)
    assert any(c.id == conv_id for c in archived)

    # Now unarchive via update_conversation with archived=False
    result = execute_builtin_tool(
        db,
        "update_conversation",
        {"conversation_id": conv_id[:8], "archived": False},
    )
    assert "Unarchived" in result

    # Should no longer appear in archived list
    still_archived = db.list_conversations(archived=True, include_archived=True)
    assert not any(c.id == conv_id for c in still_archived)


def test_false_starred_is_applied_not_ignored():
    db, conv_id = _make_db()
    # Star the conversation first
    db.star_conversation(conv_id, star=True)
    starred_before = db.list_conversations(starred=True)
    assert any(c.id == conv_id for c in starred_before)

    # Unstar via update_conversation with starred=False
    result = execute_builtin_tool(
        db,
        "update_conversation",
        {"conversation_id": conv_id[:8], "starred": False},
    )
    assert "Unstarred" in result

    # Should no longer be starred
    starred_after = db.list_conversations(starred=True)
    assert not any(c.id == conv_id for c in starred_after)


# ---------------------------------------------------------------------------
# miss: non-existent id returns "Error:" prefix
# ---------------------------------------------------------------------------


def test_miss_returns_error_prefix():
    db, _ = _make_db()
    result = execute_builtin_tool(
        db,
        "update_conversation",
        {"conversation_id": "zzzzzzzz"},
    )
    assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# empty conversation_id returns "Error:" prefix
# ---------------------------------------------------------------------------


def test_empty_id_returns_error():
    db, _ = _make_db()
    result = execute_builtin_tool(
        db,
        "update_conversation",
        {"conversation_id": ""},
    )
    assert result.startswith("Error:")
