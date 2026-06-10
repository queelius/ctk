"""
Unit tests for reasoning block rendering in the Markdown exporter.
"""

import pytest

from ctk.core.models import (
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
    ReasoningBlock,
)
from ctk.core.plugin import registry


class TestMarkdownReasoningExport:
    """Test that reasoning blocks are rendered as a quoted section in markdown output."""

    @pytest.mark.unit
    def test_markdown_export_includes_reasoning_section(self):
        """Reasoning blocks should appear as a quoted section before the visible reply."""
        tree = ConversationTree(id="md-1", title="MD")
        content = MessageContent(text="The answer is 4.")
        content.reasoning.append(
            ReasoningBlock(text="2+2 must be 4", summary="Arithmetic")
        )
        tree.add_message(
            Message(
                id="m1", role=MessageRole.ASSISTANT, content=content, parent_id=None
            )
        )
        registry.discover_plugins()
        out = registry.get_exporter("markdown").export_conversations([tree])
        assert "Reasoning" in out
        assert "2+2 must be 4" in out
        assert out.index("2+2 must be 4") < out.index("The answer is 4.")

    @pytest.mark.unit
    def test_markdown_export_no_reasoning_no_section(self):
        """Messages without reasoning should not include a Reasoning header."""
        tree = ConversationTree(id="md-2", title="MD no reasoning")
        content = MessageContent(text="Plain reply.")
        tree.add_message(
            Message(
                id="m2", role=MessageRole.ASSISTANT, content=content, parent_id=None
            )
        )
        registry.discover_plugins()
        out = registry.get_exporter("markdown").export_conversations([tree])
        assert "Reasoning" not in out

    @pytest.mark.unit
    def test_markdown_export_reasoning_summary_rendered(self):
        """Summary label from a ReasoningBlock should appear in the output."""
        tree = ConversationTree(id="md-3", title="MD summary")
        content = MessageContent(text="Done.")
        content.reasoning.append(
            ReasoningBlock(text="Detailed thinking here", summary="Overview")
        )
        tree.add_message(
            Message(
                id="m3", role=MessageRole.ASSISTANT, content=content, parent_id=None
            )
        )
        registry.discover_plugins()
        out = registry.get_exporter("markdown").export_conversations([tree])
        assert "Overview" in out
        assert "Detailed thinking here" in out

    @pytest.mark.unit
    def test_markdown_export_multiple_reasoning_blocks(self):
        """All reasoning blocks should appear in order before the reply text."""
        tree = ConversationTree(id="md-4", title="MD multi")
        content = MessageContent(text="Final answer.")
        content.reasoning.append(ReasoningBlock(text="First thought"))
        content.reasoning.append(ReasoningBlock(text="Second thought"))
        tree.add_message(
            Message(
                id="m4", role=MessageRole.ASSISTANT, content=content, parent_id=None
            )
        )
        registry.discover_plugins()
        out = registry.get_exporter("markdown").export_conversations([tree])
        assert "First thought" in out
        assert "Second thought" in out
        # Both appear before the reply
        assert out.index("First thought") < out.index("Final answer.")
        assert out.index("Second thought") < out.index("Final answer.")
