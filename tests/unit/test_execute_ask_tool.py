import pytest

from ctk.cli import execute_ask_tool
from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)


def _make_conversation(db, conv_id, title="Test conversation"):
    tree = ConversationTree(id=conv_id, title=title)
    tree.add_message(
        Message(
            id="m1",
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
            parent_id=None,
        )
    )
    db.save_conversation(tree)
    return tree


@pytest.fixture
def db():
    database = ConversationDB(":memory:")
    yield database
    database.close()


# All 15 tool branches in execute_ask_tool that resolve a conversation_id via
# _resolve_conversation_id (the helper whose absence used to make every one of
# these silently fail). Tools needing extra args (rename/tag/export) still
# resolve the id first, so an unknown id reports "not found" before any
# missing-arg error, and a valid id never trips the old NameError.
RESOLVING_TOOLS = [
    "star_conversation",
    "unstar_conversation",
    "pin_conversation",
    "unpin_conversation",
    "archive_conversation",
    "unarchive_conversation",
    "rename_conversation",
    "show_conversation_tree",
    "delete_conversation",
    "tag_conversation",
    "remove_tag",
    "export_conversation",
    "duplicate_conversation",
    "list_conversation_paths",
    "auto_tag_conversation",
]


@pytest.mark.parametrize("tool_name", RESOLVING_TOOLS)
def test_resolving_tool_with_valid_prefix_does_not_namerror(db, tool_name):
    conv_id = "abcdef01-0000-0000-0000-000000000000"
    _make_conversation(db, conv_id)
    result = execute_ask_tool(db, tool_name, {"conversation_id": conv_id[:8]})
    # The bug returned: "Error executing <tool>: name '_resolve_conversation_id' ..."
    assert "_resolve_conversation_id" not in result
    assert "is not defined" not in result


@pytest.mark.parametrize("tool_name", RESOLVING_TOOLS)
def test_resolving_tool_with_unknown_id_reports_not_found(db, tool_name):
    result = execute_ask_tool(db, tool_name, {"conversation_id": "zzzzzzzz"})
    lowered = result.lower()
    assert "not found" in lowered or result.startswith("Error:")
    assert "_resolve_conversation_id" not in result
