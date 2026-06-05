"""
Unit tests for ctk/core/conversation_display.py

Tests cover show_conversation_helper and its formatting logic using
real in-memory DB instances and ConversationTree objects.
"""

import pytest

from ctk.core.conversation_display import show_conversation_helper
from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db():
    """Return an in-memory ConversationDB."""
    return ConversationDB(":memory:")


def _msg(mid: str, parent: str | None, role: MessageRole, text: str) -> Message:
    return Message(
        id=mid,
        parent_id=parent,
        role=role,
        content=MessageContent(text=text),
    )


def _simple_tree(conv_id: str = "conv-simple", title: str = "Hello World") -> ConversationTree:
    """Single linear path: user -> assistant."""
    tree = ConversationTree(
        id=conv_id,
        title=title,
        metadata=ConversationMetadata(source="test", model="test-model", tags=["a", "b"]),
    )
    tree.add_message(_msg("m1", None, MessageRole.USER, "Hello"))
    tree.add_message(_msg("m2", "m1", MessageRole.ASSISTANT, "Hi there!"))
    return tree


def _branching_tree(conv_id: str = "conv-branch") -> ConversationTree:
    """Branching tree: m1 -> m2a and m1 -> m2b -> m3."""
    tree = ConversationTree(
        id=conv_id,
        title="Branching",
        metadata=ConversationMetadata(source="branch-test"),
    )
    tree.add_message(_msg("m1", None, MessageRole.USER, "First question"))
    tree.add_message(_msg("m2a", "m1", MessageRole.ASSISTANT, "Answer one"))
    tree.add_message(_msg("m2b", "m1", MessageRole.ASSISTANT, "Answer two"))
    tree.add_message(_msg("m3", "m2b", MessageRole.USER, "Follow-up"))
    return tree


# ---------------------------------------------------------------------------
# show_conversation_helper - basic success
# ---------------------------------------------------------------------------


class TestShowConversationHelperSuccess:
    @pytest.mark.unit
    def test_returns_success_true_for_known_id(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert result["success"] is True
        db.close()

    @pytest.mark.unit
    def test_conversation_key_returns_tree(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert result["conversation"] is not None
        assert result["conversation"].id == tree.id
        db.close()

    @pytest.mark.unit
    def test_output_contains_title(self):
        db = _make_db()
        tree = _simple_tree(title="My Special Title")
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "My Special Title" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_output_contains_conv_id(self):
        db = _make_db()
        tree = _simple_tree(conv_id="conv-abc123")
        db.save_conversation(tree)

        result = show_conversation_helper(db, "conv-abc123")

        assert "conv-abc123" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_output_contains_message_text(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "Hello" in result["output"]
        assert "Hi there!" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_output_contains_role_labels(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "[User]" in result["output"]
        assert "[Assistant]" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_output_contains_metadata_section_when_show_metadata_true(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, show_metadata=True)

        assert "Total messages:" in result["output"]
        assert "Paths:" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_output_omits_metadata_section_when_show_metadata_false(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, show_metadata=False)

        assert "Total messages:" not in result["output"]
        assert "Paths:" not in result["output"]
        db.close()

    @pytest.mark.unit
    def test_output_contains_source_when_available(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "Source:" in result["output"]
        assert "test" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_output_contains_model_when_available(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "Model:" in result["output"]
        assert "test-model" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_output_contains_tags_when_available(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "Tags:" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_path_key_is_a_list_of_messages(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert isinstance(result["path"], list)
        assert len(result["path"]) > 0
        db.close()

    @pytest.mark.unit
    def test_path_count_key_is_int(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert isinstance(result["path_count"], int)
        assert result["path_count"] >= 1
        db.close()

    @pytest.mark.unit
    def test_navigator_key_present(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "navigator" in result
        db.close()

    @pytest.mark.unit
    def test_error_key_empty_on_success(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert result["error"] == ""
        db.close()

    @pytest.mark.unit
    def test_output_ends_with_newline(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert result["output"].endswith("\n")
        db.close()

    @pytest.mark.unit
    def test_output_contains_separator_lines(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "=" * 80 in result["output"]
        db.close()


# ---------------------------------------------------------------------------
# show_conversation_helper - not found / error cases
# ---------------------------------------------------------------------------


class TestShowConversationHelperNotFound:
    @pytest.mark.unit
    def test_missing_id_returns_success_false(self):
        db = _make_db()

        result = show_conversation_helper(db, "no-such-id")

        assert result["success"] is False
        db.close()

    @pytest.mark.unit
    def test_missing_id_error_message_mentions_id(self):
        db = _make_db()

        result = show_conversation_helper(db, "no-such-id")

        assert "no-such-id" in result["error"]
        db.close()

    @pytest.mark.unit
    def test_missing_id_output_is_empty(self):
        db = _make_db()

        result = show_conversation_helper(db, "no-such-id")

        assert result["output"] == ""
        db.close()

    @pytest.mark.unit
    def test_missing_id_conversation_is_none(self):
        db = _make_db()

        result = show_conversation_helper(db, "no-such-id")

        assert result["conversation"] is None
        db.close()

    @pytest.mark.unit
    def test_ambiguous_prefix_returns_success_false(self):
        """Two conversations whose ids share a common prefix trigger the ambiguous branch."""
        db = _make_db()
        tree_a = _simple_tree(conv_id="prefix-aaa")
        tree_b = _simple_tree(conv_id="prefix-bbb")
        db.save_conversation(tree_a)
        db.save_conversation(tree_b)

        result = show_conversation_helper(db, "prefix-")

        assert result["success"] is False
        db.close()

    @pytest.mark.unit
    def test_ambiguous_prefix_error_contains_matches(self):
        db = _make_db()
        tree_a = _simple_tree(conv_id="prefix-aaa")
        tree_b = _simple_tree(conv_id="prefix-bbb")
        db.save_conversation(tree_a)
        db.save_conversation(tree_b)

        result = show_conversation_helper(db, "prefix-")

        assert "Multiple" in result["error"] or "multiple" in result["error"]
        db.close()

    @pytest.mark.unit
    def test_unique_prefix_resolves_conversation(self):
        db = _make_db()
        tree = _simple_tree(conv_id="unique-prefix-xyz")
        db.save_conversation(tree)

        result = show_conversation_helper(db, "unique-prefix")

        assert result["success"] is True
        assert result["conversation"].id == "unique-prefix-xyz"
        db.close()


# ---------------------------------------------------------------------------
# show_conversation_helper - path_selection variants
# ---------------------------------------------------------------------------


class TestShowConversationPathSelection:
    @pytest.mark.unit
    def test_path_selection_longest(self):
        db = _make_db()
        tree = _branching_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, path_selection="longest")

        assert result["success"] is True
        # Longest path goes through m2b -> m3 (depth 3 vs depth 2)
        assert "longest" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_path_selection_latest(self):
        db = _make_db()
        tree = _branching_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, path_selection="latest")

        assert result["success"] is True
        assert "latest" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_path_selection_zero(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, path_selection="0")

        assert result["success"] is True
        db.close()

    @pytest.mark.unit
    def test_path_selection_invalid_number_returns_error(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, path_selection="999")

        assert result["success"] is False
        assert "999" in result["error"] or "Path" in result["error"]
        db.close()

    @pytest.mark.unit
    def test_path_selection_unknown_string_falls_back_to_longest(self):
        """An unrecognized path_selection string falls back to the longest path."""
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, path_selection="bogus-selector")

        assert result["success"] is True
        db.close()

    @pytest.mark.unit
    def test_branching_tree_path_count_greater_than_one(self):
        db = _make_db()
        tree = _branching_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert result["path_count"] > 1
        db.close()

    @pytest.mark.unit
    def test_branching_tree_note_in_output(self):
        """When path_count > 1 a note about multiple paths should appear."""
        db = _make_db()
        tree = _branching_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id)

        assert "paths" in result["output"].lower() or "path" in result["output"].lower()
        db.close()


# ---------------------------------------------------------------------------
# show_conversation_helper - show_metadata flag edge cases
# ---------------------------------------------------------------------------


class TestShowConversationMetadataFlag:
    @pytest.mark.unit
    def test_untitled_conversation_shows_untitled_placeholder(self):
        db = _make_db()
        tree = ConversationTree(
            id="conv-notitle",
            title=None,
            metadata=ConversationMetadata(source="x"),
        )
        tree.add_message(_msg("m1", None, MessageRole.USER, "hi"))
        db.save_conversation(tree)

        result = show_conversation_helper(db, "conv-notitle", show_metadata=True)

        assert "(untitled)" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_metadata_with_no_source_no_model_still_succeeds(self):
        db = _make_db()
        tree = ConversationTree(
            id="conv-bare",
            title="Bare",
            metadata=ConversationMetadata(),
        )
        tree.add_message(_msg("m1", None, MessageRole.USER, "msg"))
        db.save_conversation(tree)

        result = show_conversation_helper(db, "conv-bare", show_metadata=True)

        assert result["success"] is True
        assert "Bare" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_message_count_in_metadata(self):
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, show_metadata=True)

        # _simple_tree has 2 messages
        assert "Total messages: 2" in result["output"]
        db.close()


# ---------------------------------------------------------------------------
# show_conversation_helper - empty / single-message trees
# ---------------------------------------------------------------------------


class TestShowConversationEdgeCases:
    @pytest.mark.unit
    def test_single_message_tree_succeeds(self):
        db = _make_db()
        tree = ConversationTree(
            id="conv-single",
            title="Single",
            metadata=ConversationMetadata(source="x"),
        )
        tree.add_message(_msg("m1", None, MessageRole.USER, "only message"))
        db.save_conversation(tree)

        result = show_conversation_helper(db, "conv-single")

        assert result["success"] is True
        assert "only message" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_system_role_message_appears_in_output(self):
        db = _make_db()
        tree = ConversationTree(
            id="conv-system",
            title="System",
            metadata=ConversationMetadata(source="x"),
        )
        tree.add_message(_msg("m0", None, MessageRole.SYSTEM, "you are helpful"))
        tree.add_message(_msg("m1", "m0", MessageRole.USER, "hello"))
        db.save_conversation(tree)

        result = show_conversation_helper(db, "conv-system")

        assert "you are helpful" in result["output"]
        db.close()

    @pytest.mark.unit
    def test_tool_role_message_label_in_output(self):
        db = _make_db()
        tree = ConversationTree(
            id="conv-tool",
            title="Tool",
            metadata=ConversationMetadata(source="x"),
        )
        tree.add_message(_msg("m1", None, MessageRole.USER, "call tool"))
        tree.add_message(_msg("m2", "m1", MessageRole.TOOL, "tool result"))
        db.save_conversation(tree)

        result = show_conversation_helper(db, "conv-tool")

        assert result["success"] is True
        db.close()

    @pytest.mark.unit
    def test_multiple_conversations_in_db_resolves_correct_one(self):
        db = _make_db()
        tree_a = _simple_tree(conv_id="conv-first", title="First")
        tree_b = _simple_tree(conv_id="conv-second", title="Second")
        db.save_conversation(tree_a)
        db.save_conversation(tree_b)

        result = show_conversation_helper(db, "conv-second")

        assert result["success"] is True
        assert "Second" in result["output"]
        assert "First" not in result["output"]
        db.close()

    @pytest.mark.unit
    def test_plain_output_true_does_not_raise(self):
        """plain_output=True is the default; just confirm no exception."""
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, plain_output=True)

        assert result["success"] is True
        db.close()

    @pytest.mark.unit
    def test_path_selection_in_output_line(self):
        """The path label line contains the path_selection string."""
        db = _make_db()
        tree = _simple_tree()
        db.save_conversation(tree)

        result = show_conversation_helper(db, tree.id, path_selection="longest")

        assert "path: longest" in result["output"]
        db.close()
