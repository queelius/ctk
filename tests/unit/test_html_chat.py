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


class TestPathBasedRendering:
    """Test that showConversation uses tree-based path rendering."""

    def test_show_conversation_builds_tree(self):
        """showConversation should instantiate ConversationTree."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "new ConversationTree(" in js
        assert "getDefaultPath" in js

    def test_show_conversation_has_branch_indicator(self):
        """Messages with multiple children should show branch navigation."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "branch-indicator" in js

    def test_message_element_has_data_id(self):
        """Each message div should have data-msg-id for tree navigation."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "data-msg-id" in js or "dataset.msgId" in js

    def test_switch_branch_function_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "switchBranch" in js

    def test_merge_local_branches_on_load(self):
        """localStorage branches should be merged before tree construction."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "chat_branches_" in js
