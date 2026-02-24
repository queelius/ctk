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


class TestChatSettings:
    """Test that AI Chat settings are in the settings modal."""

    def _get_html(self):
        exporter = HTMLExporter()
        return exporter._generate_html([], stats={}, theme="light")

    def test_settings_modal_has_chat_section(self):
        html = self._get_html()
        assert "AI Chat" in html

    def test_settings_has_endpoint_input(self):
        html = self._get_html()
        assert "chatEndpoint" in html

    def test_settings_has_model_input(self):
        html = self._get_html()
        assert "chatModel" in html

    def test_settings_has_temperature_input(self):
        html = self._get_html()
        assert "chatTemperature" in html

    def test_settings_has_system_prompt_input(self):
        html = self._get_html()
        assert "chatSystemPrompt" in html

    def test_default_endpoint_value(self):
        html = self._get_html()
        assert "localhost:11434" in html


class TestChatInputComponents:
    """Test chat input UI components."""

    def test_assistant_messages_have_reply_button(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "Reply" in js

    def test_quick_continue_input_function_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "createQuickContinueInput" in js

    def test_send_chat_message_function_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "sendChatMessage" in js

    def test_inline_reply_input_function_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "createInlineReplyInput" in js

    def test_chat_message_persistence(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "saveChatBranch" in js

    def test_error_handling_messages(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "MODEL_NOT_CONFIGURED" in js

    def test_stop_button_aborts_stream(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "chatClient.abort" in js


class TestHTMLExportIntegration:
    """Integration tests verifying the full HTML export includes chat features."""

    def test_full_export_contains_all_chat_components(self):
        """A full HTML export should contain all chat-related components."""
        exporter = HTMLExporter()
        html = exporter.export_conversations([])
        # JS classes
        assert "class ConversationTree" in html
        assert "class ChatClient" in html
        # CSS
        assert ".branch-indicator" in html
        assert ".chat-input-area" in html
        # Settings
        assert "chatEndpoint" in html
        assert "chatModel" in html
        # Functions
        assert "sendChatMessage" in html
        assert "createQuickContinueInput" in html

    def test_export_with_conversations_includes_parent_id(self, sample_conversation):
        """Exported message data should include parent_id for tree construction."""
        exporter = HTMLExporter()
        conv_data, stats = exporter._prepare_data([sample_conversation])
        assert len(conv_data) == 1
        messages = conv_data[0]["messages"]
        assert len(messages) == 4
        # First message has no parent
        root_msgs = [m for m in messages if m["parent_id"] is None]
        assert len(root_msgs) == 1
        assert root_msgs[0]["id"] == "msg_001"
        # All other messages have parent_id set
        child_msgs = [m for m in messages if m["parent_id"] is not None]
        assert len(child_msgs) == 3
        # Verify parent chain: msg_002 -> msg_001, msg_003 -> msg_002, msg_004 -> msg_003
        by_id = {m["id"]: m for m in messages}
        assert by_id["msg_002"]["parent_id"] == "msg_001"
        assert by_id["msg_003"]["parent_id"] == "msg_002"
        assert by_id["msg_004"]["parent_id"] == "msg_003"

    def test_export_with_branching_conversation(self, branching_conversation):
        """Branching conversations should export all messages with correct parent links."""
        exporter = HTMLExporter()
        conv_data, stats = exporter._prepare_data([branching_conversation])
        assert len(conv_data) == 1
        messages = conv_data[0]["messages"]
        # Should have all 5 messages (including both branches)
        assert len(messages) == 5
        by_id = {m["id"]: m for m in messages}
        # Both branch responses should reference the same parent
        assert by_id["msg_002a"]["parent_id"] == "msg_001"
        assert by_id["msg_002b"]["parent_id"] == "msg_001"
        # Continuation from first branch
        assert by_id["msg_003"]["parent_id"] == "msg_002a"
        assert by_id["msg_004"]["parent_id"] == "msg_003"

    def test_branching_conversation_full_html_output(self, branching_conversation):
        """Full HTML export of branching conversation should contain tree JS and data."""
        exporter = HTMLExporter()
        html = exporter.export_conversations([branching_conversation])
        # JS tree class is present
        assert "class ConversationTree" in html
        # Conversation data is embedded
        assert "msg_002a" in html
        assert "msg_002b" in html
        # Branch indicator support is present
        assert "branch-indicator" in html
        assert "switchBranch" in html

    def test_export_preserves_conversation_metadata(self, sample_conversation):
        """Export should preserve conversation id, title, source, model, and tags."""
        exporter = HTMLExporter()
        conv_data, stats = exporter._prepare_data([sample_conversation])
        conv = conv_data[0]
        assert conv["id"] == "conv_001"
        assert conv["title"] == "Test Conversation"
        assert conv["source"] == "test"
        assert conv["model"] == "test-model"
        assert "test" in conv["tags"]
        assert "sample" in conv["tags"]
        assert conv["message_count"] == 4

    def test_export_stats_are_computed(
        self, sample_conversation, branching_conversation
    ):
        """Stats should aggregate counts across multiple conversations."""
        exporter = HTMLExporter()
        conv_data, stats = exporter._prepare_data(
            [sample_conversation, branching_conversation]
        )
        assert stats["total_conversations"] == 2
        assert stats["total_messages"] == 9  # 4 + 5
        assert "test" in stats["sources"]
        assert stats["sources"]["test"] == 2

    def test_export_root_message_ids_included(self, branching_conversation):
        """Export data should include root_message_ids for tree construction."""
        exporter = HTMLExporter()
        conv_data, stats = exporter._prepare_data([branching_conversation])
        conv = conv_data[0]
        assert "root_message_ids" in conv
        assert "msg_001" in conv["root_message_ids"]

    def test_full_html_is_valid_document(self):
        """The exported HTML should be a complete, well-formed document."""
        exporter = HTMLExporter()
        html = exporter.export_conversations([])
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<script>" in html or "<script " in html
        assert "<style>" in html or "<style " in html

    def test_export_message_roles_are_strings(self, sample_conversation):
        """Message roles should be serialized as string values, not enum objects."""
        exporter = HTMLExporter()
        conv_data, stats = exporter._prepare_data([sample_conversation])
        messages = conv_data[0]["messages"]
        for msg in messages:
            assert isinstance(msg["role"], str)
            assert msg["role"] in ("user", "assistant", "system", "tool")
