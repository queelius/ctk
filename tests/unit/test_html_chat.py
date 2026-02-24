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


class TestChatClientJS:
    """Test that ChatClient JS class is included."""

    def test_chat_client_class_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "class ChatClient" in js

    def test_chat_client_has_send_method(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "sendMessage" in js

    def test_chat_client_has_abort(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "AbortController" in js

    def test_chat_client_uses_streaming(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "stream" in js
        assert "chat/completions" in js

    def test_chat_client_reads_settings_from_preferences(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "preferences.chat" in js


class TestChatCSS:
    """Test that CSS includes styles for chat components."""

    def test_css_has_branch_indicator_styles(self):
        exporter = HTMLExporter()
        css = exporter._get_css()
        assert ".branch-indicator" in css

    def test_css_has_chat_input_styles(self):
        exporter = HTMLExporter()
        css = exporter._get_css()
        assert ".chat-input-area" in css

    def test_css_has_chat_message_styles(self):
        exporter = HTMLExporter()
        css = exporter._get_css()
        assert ".chat-message" in css

    def test_css_has_streaming_indicator(self):
        exporter = HTMLExporter()
        css = exporter._get_css()
        assert ".streaming" in css
