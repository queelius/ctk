"""Tests for HTML export chat/tree features."""
from ctk.integrations.exporters.html import HTMLExporter


class TestConversationTreeJS:
    """Test that ConversationTree JS class is included and correct."""

    def test_javascript_contains_conversation_tree_class(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "class ConversationTree" in js

    def test_conversation_tree_has_required_methods(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        for method in [
            "getChildren",
            "getPathToRoot",
            "getDefaultPath",
            "addMessage",
        ]:
            assert method in js, f"Missing method: {method}"

    def test_conversation_tree_builds_parent_index(self):
        """Verify constructor builds childrenMap from parent_id."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "childrenMap" in js
        assert "parent_id" in js
