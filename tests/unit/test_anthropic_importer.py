"""
Comprehensive edge case tests for the Anthropic importer.

Tests cover validation, model detection, basic import, content parsing,
and edge cases for the AnthropicImporter class.
"""

import json
from datetime import datetime

import pytest

from ctk.core.models import ContentType, MessageRole
from ctk.integrations.importers.anthropic import AnthropicImporter


class TestAnthropicValidation:
    """Tests for AnthropicImporter.validate()"""

    @pytest.mark.unit
    def test_validate_dict_with_chat_messages(self):
        """Dict with chat_messages field should be accepted"""
        importer = AnthropicImporter()
        data = {"chat_messages": [{"text": "hi", "sender": "human"}]}
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_dict_with_empty_chat_messages(self):
        """Dict with empty chat_messages list should still be accepted"""
        importer = AnthropicImporter()
        data = {"chat_messages": []}
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_dict_with_messages_and_uuid(self):
        """Dict with messages + uuid should be accepted"""
        importer = AnthropicImporter()
        data = {
            "uuid": "abc-123",
            "messages": [{"text": "hello", "sender": "human"}],
        }
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_dict_with_messages_and_name(self):
        """Dict with messages + name (no uuid) should be accepted"""
        importer = AnthropicImporter()
        data = {
            "name": "Test Conversation",
            "messages": [{"text": "hello", "sender": "human"}],
        }
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_dict_with_uuid_and_sender_in_messages(self):
        """Dict with uuid + sender pattern in messages should be accepted"""
        importer = AnthropicImporter()
        data = {
            "uuid": "abc-123",
            "messages": [{"sender": "human", "text": "hello"}],
        }
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_list_of_valid_dicts(self):
        """List of valid dicts should be accepted (checks first element)"""
        importer = AnthropicImporter()
        data = [
            {"chat_messages": [{"text": "hi", "sender": "human"}]},
            {"chat_messages": [{"text": "bye", "sender": "human"}]},
        ]
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_json_string_input(self):
        """JSON string encoding valid data should be accepted"""
        importer = AnthropicImporter()
        raw = {"uuid": "test-uuid", "chat_messages": []}
        data = json.dumps(raw)
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_invalid_json_string(self):
        """Invalid JSON string should be rejected"""
        importer = AnthropicImporter()
        assert importer.validate("{not valid json}}}") is False

    @pytest.mark.unit
    def test_validate_empty_dict(self):
        """Empty dict should be rejected"""
        importer = AnthropicImporter()
        assert importer.validate({}) is False

    @pytest.mark.unit
    def test_validate_dict_without_required_fields(self):
        """Dict without chat_messages, messages, uuid, or name should be rejected"""
        importer = AnthropicImporter()
        assert importer.validate({"random": "data", "other": 42}) is False

    @pytest.mark.unit
    def test_validate_empty_list(self):
        """Empty list should be rejected"""
        importer = AnthropicImporter()
        assert importer.validate([]) is False

    @pytest.mark.unit
    def test_validate_non_dict_non_list(self):
        """Non-dict/non-list types should be rejected"""
        importer = AnthropicImporter()
        assert importer.validate(42) is False
        assert importer.validate(None) is False
        assert importer.validate(True) is False

    @pytest.mark.unit
    def test_validate_plain_string_not_json(self):
        """Plain string that is not JSON should be rejected"""
        importer = AnthropicImporter()
        assert importer.validate("just a string") is False

    @pytest.mark.unit
    def test_validate_uuid_with_sender_in_string_repr(self):
        """Dict with uuid and sender somewhere in its string representation"""
        importer = AnthropicImporter()
        # uuid present, no messages list, but sender appears in str(sample)
        data = {"uuid": "abc-123", "sender": "human", "text": "hello"}
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_uuid_without_sender_no_messages(self):
        """Dict with uuid but no sender indicator should be rejected"""
        importer = AnthropicImporter()
        data = {"uuid": "abc-123", "text": "hello"}
        assert importer.validate(data) is False

    @pytest.mark.unit
    def test_validate_json_string_with_list(self):
        """JSON string encoding a list of valid dicts should be accepted"""
        importer = AnthropicImporter()
        raw = [{"chat_messages": [{"text": "hi"}]}]
        data = json.dumps(raw)
        assert importer.validate(data) is True


class TestAnthropicModelDetection:
    """Tests for AnthropicImporter._detect_model()"""

    @pytest.mark.unit
    def test_detect_claude_3_opus(self):
        """claude-3-opus model string should map to Claude 3 Opus"""
        importer = AnthropicImporter()
        conv_data = {"model": "claude-3-opus-20240229"}
        assert importer._detect_model(conv_data) == "Claude 3 Opus"

    @pytest.mark.unit
    def test_detect_claude_3_sonnet(self):
        """claude-3-sonnet model string should map to Claude 3 Sonnet"""
        importer = AnthropicImporter()
        conv_data = {"model": "claude-3-sonnet-20240229"}
        assert importer._detect_model(conv_data) == "Claude 3 Sonnet"

    @pytest.mark.unit
    def test_detect_claude_3_haiku(self):
        """claude-3-haiku model string should map to Claude 3 Haiku"""
        importer = AnthropicImporter()
        conv_data = {"model": "claude-3-haiku-20240307"}
        assert importer._detect_model(conv_data) == "Claude 3 Haiku"

    @pytest.mark.unit
    def test_detect_claude_35_sonnet(self):
        """claude-3.5-sonnet model string should map to Claude 3.5 Sonnet"""
        importer = AnthropicImporter()
        conv_data = {"model": "claude-3.5-sonnet-20240620"}
        assert importer._detect_model(conv_data) == "Claude 3.5 Sonnet"

    @pytest.mark.unit
    def test_detect_claude_2(self):
        """claude-2 model string should map to Claude 2"""
        importer = AnthropicImporter()
        conv_data = {"model": "claude-2"}
        assert importer._detect_model(conv_data) == "Claude 2"

    @pytest.mark.unit
    def test_detect_claude_2_1(self):
        """claude-2.1 model string should map to Claude 2.1"""
        importer = AnthropicImporter()
        conv_data = {"model": "claude-2.1"}
        assert importer._detect_model(conv_data) == "Claude 2.1"

    @pytest.mark.unit
    def test_detect_claude_instant(self):
        """claude-instant model string should map to Claude Instant"""
        importer = AnthropicImporter()
        conv_data = {"model": "claude-instant-1.2"}
        assert importer._detect_model(conv_data) == "Claude Instant 1.2"

    @pytest.mark.unit
    def test_detect_claude_instant_bare(self):
        """Bare claude-instant model string should map to Claude Instant"""
        importer = AnthropicImporter()
        conv_data = {"model": "claude-instant"}
        assert importer._detect_model(conv_data) == "Claude Instant"

    @pytest.mark.unit
    def test_detect_unknown_model_returns_as_is(self):
        """Unknown model string should be returned unchanged"""
        importer = AnthropicImporter()
        conv_data = {"model": "some-custom-model"}
        assert importer._detect_model(conv_data) == "some-custom-model"

    @pytest.mark.unit
    def test_detect_empty_model_returns_default(self):
        """Empty model string should return 'Claude'"""
        importer = AnthropicImporter()
        conv_data = {"model": ""}
        assert importer._detect_model(conv_data) == "Claude"

    @pytest.mark.unit
    def test_detect_missing_model_returns_default(self):
        """Missing model key should return 'Claude'"""
        importer = AnthropicImporter()
        conv_data = {}
        assert importer._detect_model(conv_data) == "Claude"

    @pytest.mark.unit
    def test_detect_model_from_messages(self):
        """Model detected from message-level model field when conv-level is absent"""
        importer = AnthropicImporter()
        conv_data = {
            "messages": [
                {"text": "hi", "model": "claude-3-opus-20240229"},
                {"text": "hello", "model": "claude-3-opus-20240229"},
            ]
        }
        assert importer._detect_model(conv_data) == "Claude 3 Opus"

    @pytest.mark.unit
    def test_detect_model_conv_level_takes_precedence(self):
        """Conv-level model should take precedence over message-level model"""
        importer = AnthropicImporter()
        conv_data = {
            "model": "claude-3-haiku-20240307",
            "messages": [
                {"text": "hi", "model": "claude-3-opus-20240229"},
            ],
        }
        assert importer._detect_model(conv_data) == "Claude 3 Haiku"

    @pytest.mark.unit
    def test_detect_model_case_insensitive(self):
        """Model detection should be case insensitive"""
        importer = AnthropicImporter()
        conv_data = {"model": "Claude-3-Opus-20240229"}
        assert importer._detect_model(conv_data) == "Claude 3 Opus"


class TestAnthropicImportBasic:
    """Tests for basic import_data() functionality"""

    @pytest.mark.unit
    def test_import_single_conversation_with_chat_messages(self):
        """Import a single conversation using chat_messages field"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-001",
            "name": "Test Chat",
            "model": "claude-3-opus-20240229",
            "chat_messages": [
                {"uuid": "msg-1", "text": "Hello", "sender": "human"},
                {"uuid": "msg-2", "text": "Hi there!", "sender": "assistant"},
            ],
        }
        conversations = importer.import_data(data)

        assert len(conversations) == 1
        conv = conversations[0]
        assert conv.id == "conv-001"
        assert conv.title == "Test Chat"
        assert len(conv.message_map) == 2

    @pytest.mark.unit
    def test_import_multiple_conversations_list(self):
        """Import multiple conversations from a list"""
        importer = AnthropicImporter()
        data = [
            {
                "uuid": "conv-1",
                "name": "Chat 1",
                "chat_messages": [{"uuid": "m1", "text": "Hello", "sender": "human"}],
            },
            {
                "uuid": "conv-2",
                "name": "Chat 2",
                "chat_messages": [{"uuid": "m2", "text": "Goodbye", "sender": "human"}],
            },
        ]
        conversations = importer.import_data(data)

        assert len(conversations) == 2
        assert conversations[0].id == "conv-1"
        assert conversations[0].title == "Chat 1"
        assert conversations[1].id == "conv-2"
        assert conversations[1].title == "Chat 2"

    @pytest.mark.unit
    def test_import_json_string_input(self):
        """Import from a JSON string"""
        importer = AnthropicImporter()
        raw = {
            "uuid": "conv-json",
            "name": "JSON Input",
            "chat_messages": [
                {"uuid": "m1", "text": "Hello from JSON", "sender": "human"},
            ],
        }
        data = json.dumps(raw)
        conversations = importer.import_data(data)

        assert len(conversations) == 1
        assert conversations[0].id == "conv-json"
        messages = conversations[0].get_longest_path()
        assert messages[0].content.text == "Hello from JSON"

    @pytest.mark.unit
    def test_import_metadata_fields(self):
        """Verify metadata: source, format, tags"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-meta",
            "name": "Metadata Test",
            "model": "claude-3-opus-20240229",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        assert conv.metadata.source == "Claude"
        assert conv.metadata.format == "anthropic"
        assert "anthropic" in conv.metadata.tags
        assert "claude" in conv.metadata.tags
        # Model-specific tag should be present for non-default model
        assert "claude-3-opus" in conv.metadata.tags

    @pytest.mark.unit
    def test_import_metadata_tags_default_model(self):
        """When model is 'Claude' (default), no model-specific tag is added"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-default-model",
            "name": "Default Model",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        # Only "anthropic" and "claude" tags, no extra model tag
        assert conv.metadata.tags == ["anthropic", "claude"]

    @pytest.mark.unit
    def test_import_uuid_as_conversation_id(self):
        """uuid field should become the conversation id"""
        importer = AnthropicImporter()
        data = {
            "uuid": "specific-uuid-123",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert conversations[0].id == "specific-uuid-123"

    @pytest.mark.unit
    def test_import_id_fallback_when_no_uuid(self):
        """When uuid is absent, the id field should be used"""
        importer = AnthropicImporter()
        data = {
            "id": "fallback-id-456",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert conversations[0].id == "fallback-id-456"

    @pytest.mark.unit
    def test_import_name_as_title(self):
        """name field should become the conversation title"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-title",
            "name": "My Important Chat",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert conversations[0].title == "My Important Chat"

    @pytest.mark.unit
    def test_import_title_fallback_when_no_name(self):
        """When name is absent, title field should be used"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-fallback-title",
            "title": "Fallback Title",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert conversations[0].title == "Fallback Title"

    @pytest.mark.unit
    def test_import_messages_linear_chain(self):
        """Messages should form a linear chain via parent_id"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-chain",
            "chat_messages": [
                {"uuid": "m1", "text": "First", "sender": "human"},
                {"uuid": "m2", "text": "Second", "sender": "assistant"},
                {"uuid": "m3", "text": "Third", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        # First message is root (no parent)
        assert conv.message_map["m1"].parent_id is None
        # Second message's parent is first
        assert conv.message_map["m2"].parent_id == "m1"
        # Third message's parent is second
        assert conv.message_map["m3"].parent_id == "m2"

    @pytest.mark.unit
    def test_import_message_roles(self):
        """Sender field should map correctly to MessageRole"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-roles",
            "chat_messages": [
                {"uuid": "m1", "text": "Hi", "sender": "human"},
                {"uuid": "m2", "text": "Hello", "sender": "assistant"},
            ],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        assert conv.message_map["m1"].role == MessageRole.USER
        assert conv.message_map["m2"].role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_import_created_at_updated_at(self):
        """created_at and updated_at should be parsed into metadata"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-timestamps",
            "created_at": "2024-06-15T10:30:00Z",
            "updated_at": "2024-06-15T11:00:00Z",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        assert isinstance(conv.metadata.created_at, datetime)
        assert conv.metadata.created_at.year == 2024
        assert conv.metadata.created_at.month == 6
        assert conv.metadata.created_at.day == 15
        # updated_at gets overwritten by add_message/tree creation, just check it's a datetime
        assert isinstance(conv.metadata.updated_at, datetime)

    @pytest.mark.unit
    def test_import_uses_messages_field_fallback(self):
        """When chat_messages is absent, messages field should be used"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-messages-field",
            "messages": [
                {"uuid": "m1", "text": "From messages field", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        messages = conv.get_longest_path()
        assert len(messages) == 1
        assert messages[0].content.text == "From messages field"


class TestAnthropicContentParsing:
    """Tests for content field parsing in import_data()"""

    @pytest.mark.unit
    def test_text_field_simple(self):
        """Simple text field should be extracted as content.text"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-text",
            "chat_messages": [
                {"uuid": "m1", "text": "Hello world", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.content.text == "Hello world"

    @pytest.mark.unit
    def test_content_field_as_string(self):
        """Content field as a string should be used as text"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-content-str",
            "chat_messages": [
                {"uuid": "m1", "content": "String content", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.content.text == "String content"

    @pytest.mark.unit
    def test_content_field_as_list_with_text_parts(self):
        """Content field as list of text parts should be joined"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-content-list",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {"type": "text", "text": "Part one"},
                        {"type": "text", "text": "Part two"},
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert "Part one" in msg.content.text
        assert "Part two" in msg.content.text
        assert msg.content.text == "Part one\nPart two"

    @pytest.mark.unit
    def test_content_list_with_string_parts(self):
        """Content list containing plain strings should be collected as text"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-str-parts",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": ["Hello", "World"],
                    "sender": "human",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.content.text == "Hello\nWorld"

    @pytest.mark.unit
    def test_content_list_with_image_base64(self):
        """Content list with image part using base64 source"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-img-b64",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": "abc123base64data",
                            },
                        }
                    ],
                    "sender": "human",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert len(msg.content.images) == 1
        assert msg.content.images[0].data == "abc123base64data"
        assert msg.content.images[0].mime_type == "image/jpeg"
        assert msg.content.images[0].type == ContentType.IMAGE

    @pytest.mark.unit
    def test_content_list_with_image_base64_default_mime(self):
        """Image with base64 source but missing media_type should default to image/png"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-img-default",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "data": "somedata",
                            },
                        }
                    ],
                    "sender": "human",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert len(msg.content.images) == 1
        assert msg.content.images[0].mime_type == "image/png"

    @pytest.mark.unit
    def test_content_list_with_image_url(self):
        """Content list with image part using URL source"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-img-url",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "url": "https://example.com/image.png",
                            },
                        }
                    ],
                    "sender": "human",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert len(msg.content.images) == 1
        assert msg.content.images[0].url == "https://example.com/image.png"

    @pytest.mark.unit
    def test_content_list_with_tool_use(self):
        """Content list with tool_use blocks should create ToolCall objects"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-tool-use",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {"type": "text", "text": "Let me search for that."},
                        {
                            "type": "tool_use",
                            "id": "tool-call-1",
                            "name": "search",
                            "input": {"query": "python docs"},
                        },
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert len(msg.content.tool_calls) == 1
        tc = msg.content.tool_calls[0]
        assert tc.id == "tool-call-1"
        assert tc.name == "search"
        assert tc.arguments == {"query": "python docs"}
        assert "Let me search for that." in msg.content.text

    @pytest.mark.unit
    def test_content_list_with_tool_result_completed(self):
        """Content list with tool_result should update matching ToolCall status"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-tool-result",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tc-1",
                            "name": "calculator",
                            "input": {"expression": "2+2"},
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "tc-1",
                            "content": "4",
                        },
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert len(msg.content.tool_calls) == 1
        tc = msg.content.tool_calls[0]
        assert tc.id == "tc-1"
        assert tc.result == "4"
        assert tc.status == "completed"

    @pytest.mark.unit
    def test_content_list_with_tool_result_error(self):
        """Content list with tool_result error should set status to failed"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-tool-error",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tc-err",
                            "name": "web_fetch",
                            "input": {"url": "https://bad.example"},
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "tc-err",
                            "content": "Connection refused",
                            "is_error": True,
                        },
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        tc = msg.content.tool_calls[0]
        assert tc.status == "failed"
        assert tc.error == "Connection refused"

    @pytest.mark.unit
    def test_attachments_image_file_uses_add_image(self):
        """Attachments with image extensions should be added via add_image()"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-attach-img",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "See this image",
                    "sender": "human",
                    "attachments": [
                        {"file_name": "screenshot.png", "file_type": "image/png"}
                    ],
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert len(msg.content.images) == 1
        assert msg.content.images[0].path == "screenshot.png"
        assert msg.content.images[0].mime_type == "image/png"
        assert msg.content.images[0].type == ContentType.IMAGE

    @pytest.mark.unit
    def test_attachments_image_various_extensions(self):
        """All supported image extensions (.png, .jpg, .jpeg, .gif, .webp) should be recognized"""
        importer = AnthropicImporter()
        extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
        for ext in extensions:
            data = {
                "uuid": f"conv-ext-{ext}",
                "chat_messages": [
                    {
                        "uuid": "m1",
                        "text": "image",
                        "sender": "human",
                        "attachments": [
                            {
                                "file_name": f"photo{ext}",
                                "file_type": f"image/{ext.lstrip('.')}",
                            }
                        ],
                    },
                ],
            }
            conversations = importer.import_data(data)
            msg = conversations[0].message_map["m1"]
            assert len(msg.content.images) == 1, f"Failed for extension {ext}"

    @pytest.mark.unit
    def test_attachments_document_file(self):
        """Non-image attachments should be added to documents list"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-attach-doc",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "Here is a PDF",
                    "sender": "human",
                    "attachments": [
                        {"file_name": "report.pdf", "file_type": "application/pdf"}
                    ],
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert len(msg.content.documents) == 1
        doc = msg.content.documents[0]
        assert doc.path == "report.pdf"
        assert doc.mime_type == "application/pdf"
        assert doc.type == ContentType.DOCUMENT

    @pytest.mark.unit
    def test_attachments_text_appended_to_content(self):
        """Attachment file names should be appended as text summary"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-attach-text",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "Check these files",
                    "sender": "human",
                    "attachments": [
                        {"file_name": "image.png"},
                        {"file_name": "report.pdf"},
                    ],
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert "Attachments:" in msg.content.text
        assert "image.png" in msg.content.text
        assert "report.pdf" in msg.content.text

    @pytest.mark.unit
    def test_attachments_missing_file_name_uses_unknown(self):
        """Attachment without file_name should use 'Unknown' in text summary"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-attach-unknown",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "Some text",
                    "sender": "human",
                    "attachments": [{"file_type": "application/octet-stream"}],
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert "Attachments:" in msg.content.text
        assert "Unknown" in msg.content.text

    @pytest.mark.unit
    def test_mixed_text_and_tool_use_parts(self):
        """Message with both text and tool_use parts should have both"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-mixed",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {"type": "text", "text": "Analyzing..."},
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "analyze",
                            "input": {"data": "test"},
                        },
                        {"type": "text", "text": "Done!"},
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert "Analyzing..." in msg.content.text
        assert "Done!" in msg.content.text
        assert len(msg.content.tool_calls) == 1
        assert msg.content.tool_calls[0].name == "analyze"

    @pytest.mark.unit
    def test_content_list_parts_stored(self):
        """Raw content list should be stored in content.parts"""
        importer = AnthropicImporter()
        raw_parts = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        data = {
            "uuid": "conv-parts",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": raw_parts,
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert msg.content.parts == raw_parts

    @pytest.mark.unit
    def test_content_list_empty_text_parts(self):
        """Content list with no text parts should produce empty string text"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-text",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "data": "data123",
                            },
                        }
                    ],
                    "sender": "human",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.content.text == ""

    @pytest.mark.unit
    def test_unknown_part_type_stored_in_metadata(self):
        """Dict parts with unknown type should be stored in content.metadata.attachments"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-unknown-part",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {"type": "text", "text": "Hello"},
                        {
                            "type": "custom_widget",
                            "data": {"key": "value"},
                        },
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        # Unknown part types are stored in metadata.attachments via the else clause
        assert "attachments" in msg.content.metadata
        assert len(msg.content.metadata["attachments"]) == 1
        assert msg.content.metadata["attachments"][0]["type"] == "custom_widget"

    @pytest.mark.unit
    def test_tool_result_unmatched_no_crash(self):
        """tool_result with no matching tool_use_id should not crash"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-unmatched-tool-result",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "nonexistent-id",
                            "content": "result data",
                        },
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        # No tool_calls exist, so the for loop doesn't execute, and
        # the tool_result is silently ignored (no crash)
        assert len(msg.content.tool_calls) == 0

    @pytest.mark.unit
    def test_text_field_takes_priority_over_content(self):
        """When both text and content fields are present, text field is used"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-priority",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "From text field",
                    "content": "From content field",
                    "sender": "human",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        # text field is checked first (if "text" in msg_data)
        assert msg.content.text == "From text field"

    @pytest.mark.unit
    def test_multiple_tool_use_and_results(self):
        """Multiple tool_use blocks with corresponding tool_results"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-multi-tools",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {"type": "text", "text": "Running tools..."},
                        {
                            "type": "tool_use",
                            "id": "tc-a",
                            "name": "search",
                            "input": {"q": "cats"},
                        },
                        {
                            "type": "tool_use",
                            "id": "tc-b",
                            "name": "fetch",
                            "input": {"url": "https://example.com"},
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "tc-a",
                            "content": "Found: cats",
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "tc-b",
                            "content": "Page content",
                        },
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert len(msg.content.tool_calls) == 2
        tc_a = next(tc for tc in msg.content.tool_calls if tc.id == "tc-a")
        tc_b = next(tc for tc in msg.content.tool_calls if tc.id == "tc-b")
        assert tc_a.result == "Found: cats"
        assert tc_a.status == "completed"
        assert tc_b.result == "Page content"
        assert tc_b.status == "completed"

    @pytest.mark.unit
    def test_image_source_non_dict_ignored(self):
        """Image part with non-dict source should not add an image"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-img-bad-source",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "image",
                            "source": "not-a-dict",
                        }
                    ],
                    "sender": "human",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert len(msg.content.images) == 0

    @pytest.mark.unit
    def test_tool_use_with_empty_input(self):
        """tool_use with missing input should default to empty dict"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-tool-no-input",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "tc-empty",
                            "name": "no_args_tool",
                        },
                    ],
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.content.tool_calls[0].arguments == {}


class TestAnthropicEdgeCases:
    """Tests for edge cases and boundary conditions"""

    @pytest.mark.unit
    def test_empty_messages_list(self):
        """Conversation with empty messages list should produce empty tree"""
        importer = AnthropicImporter()
        data = {"uuid": "empty-conv", "name": "Empty", "chat_messages": []}
        conversations = importer.import_data(data)

        assert len(conversations) == 1
        assert len(conversations[0].message_map) == 0

    @pytest.mark.unit
    def test_unicode_content(self):
        """Unicode content should be preserved correctly"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-unicode",
            "name": "Unicode Test",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "Hello in Japanese: \u3053\u3093\u306b\u3061\u306f \u2603 \u2764 \ud83d\ude00",
                    "sender": "human",
                },
                {
                    "uuid": "m2",
                    "text": "\u4f60\u597d\u4e16\u754c! \u00c9\u00e8\u00ea\u00eb \u00fc\u00f6\u00e4",
                    "sender": "assistant",
                },
            ],
        }
        conversations = importer.import_data(data)
        messages = conversations[0].get_longest_path()

        assert "\u3053\u3093\u306b\u3061\u306f" in messages[0].content.text
        assert "\u4f60\u597d\u4e16\u754c" in messages[1].content.text

    @pytest.mark.unit
    def test_missing_timestamps(self):
        """Messages without created_at should still import (timestamp defaults)"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-ts",
            "chat_messages": [
                {"uuid": "m1", "text": "No timestamp", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        # timestamp should be None since parse_timestamp(None) returns None by default
        # and the Message dataclass defaults timestamp to datetime.now() only when not provided
        # Here msg_data.get("created_at") is None, so parse_timestamp returns None
        assert msg.timestamp is None

    @pytest.mark.unit
    def test_missing_uuid_generates_id(self):
        """Conversation without uuid or id should generate one"""
        importer = AnthropicImporter()
        data = {
            "name": "No UUID",
            "chat_messages": [
                {"text": "hello", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        # Should have a generated UUID
        assert conv.id is not None
        assert len(conv.id) > 0

    @pytest.mark.unit
    def test_missing_name_and_title(self):
        """Conversation without name or title should default to 'Untitled Conversation'"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-name",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert conversations[0].title == "Untitled Conversation"

    @pytest.mark.unit
    def test_custom_data_project_uuid(self):
        """project_uuid should be stored in custom_data"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-project",
            "project_uuid": "proj-abc-123",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert conversations[0].metadata.custom_data["project_uuid"] == "proj-abc-123"

    @pytest.mark.unit
    def test_custom_data_account_as_dict(self):
        """Account as a dict should extract account.uuid into custom_data"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-account-dict",
            "account": {"uuid": "acct-uuid-456", "name": "Test User"},
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert conversations[0].metadata.custom_data["account_uuid"] == "acct-uuid-456"

    @pytest.mark.unit
    def test_custom_data_account_uuid_string(self):
        """When account is not a dict, account_uuid field should be used"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-account-str",
            "account": "not-a-dict",
            "account_uuid": "acct-string-789",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert (
            conversations[0].metadata.custom_data["account_uuid"] == "acct-string-789"
        )

    @pytest.mark.unit
    def test_custom_data_account_missing(self):
        """Missing account and account_uuid should result in None"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-account",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert conversations[0].metadata.custom_data["account_uuid"] is None

    @pytest.mark.unit
    def test_custom_data_summary(self):
        """Summary field should be stored in custom_data"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-summary",
            "summary": "A conversation about testing.",
            "chat_messages": [],
        }
        conversations = importer.import_data(data)
        assert (
            conversations[0].metadata.custom_data["summary"]
            == "A conversation about testing."
        )

    @pytest.mark.unit
    def test_message_metadata_files(self):
        """Files in message data should be stored in message metadata"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-files",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "With files",
                    "sender": "human",
                    "files": [
                        {"name": "code.py", "size": 1024},
                    ],
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.metadata["files"] == [{"name": "code.py", "size": 1024}]

    @pytest.mark.unit
    def test_message_metadata_feedback(self):
        """Feedback in message data should be stored in message metadata"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-feedback",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "Good answer",
                    "sender": "assistant",
                    "feedback": {"rating": "positive", "comment": "helpful"},
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.metadata["feedback"] == {"rating": "positive", "comment": "helpful"}

    @pytest.mark.unit
    def test_message_metadata_no_files_defaults_empty(self):
        """Missing files field should default to empty list in metadata"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-files",
            "chat_messages": [
                {"uuid": "m1", "text": "No files", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.metadata["files"] == []

    @pytest.mark.unit
    def test_message_metadata_no_feedback_defaults_none(self):
        """Missing feedback field should default to None in metadata"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-feedback",
            "chat_messages": [
                {"uuid": "m1", "text": "No feedback", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.metadata["feedback"] is None

    @pytest.mark.unit
    def test_message_id_generated_when_missing(self):
        """Messages without uuid or id should get generated msg_<idx> id"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-msg-id",
            "chat_messages": [
                {"text": "First message", "sender": "human"},
                {"text": "Second message", "sender": "assistant"},
            ],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        # Generated IDs should be msg_0, msg_1
        assert "msg_0" in conv.message_map
        assert "msg_1" in conv.message_map

    @pytest.mark.unit
    def test_message_role_from_role_field_fallback(self):
        """When sender is absent, role field should be used as fallback"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-role-fallback",
            "chat_messages": [
                {"uuid": "m1", "text": "Hello", "role": "user"},
                {"uuid": "m2", "text": "Hi", "role": "assistant"},
            ],
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        assert conv.message_map["m1"].role == MessageRole.USER
        assert conv.message_map["m2"].role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_message_role_defaults_to_user(self):
        """When both sender and role are absent, should default to user"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-role",
            "chat_messages": [
                {"uuid": "m1", "text": "No role specified"},
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.role == MessageRole.USER

    @pytest.mark.unit
    def test_human_sender_maps_to_user_role(self):
        """Sender 'human' should map to MessageRole.USER"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-human",
            "chat_messages": [
                {"uuid": "m1", "text": "Hi", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.role == MessageRole.USER

    @pytest.mark.unit
    def test_message_timestamp_parsing(self):
        """Message created_at should be parsed into timestamp"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-msg-ts",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "Timed message",
                    "sender": "human",
                    "created_at": "2024-03-15T14:30:00Z",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert isinstance(msg.timestamp, datetime)
        assert msg.timestamp.year == 2024
        assert msg.timestamp.month == 3
        assert msg.timestamp.day == 15

    @pytest.mark.unit
    def test_large_conversation_ordering(self):
        """Many messages should maintain correct linear ordering"""
        importer = AnthropicImporter()
        messages_data = []
        for i in range(50):
            sender = "human" if i % 2 == 0 else "assistant"
            messages_data.append(
                {
                    "uuid": f"m-{i}",
                    "text": f"Message {i}",
                    "sender": sender,
                }
            )

        data = {
            "uuid": "conv-large",
            "chat_messages": messages_data,
        }
        conversations = importer.import_data(data)
        conv = conversations[0]

        assert len(conv.message_map) == 50
        path = conv.get_longest_path()
        assert len(path) == 50
        # Verify ordering
        for i, msg in enumerate(path):
            assert msg.content.text == f"Message {i}"

    @pytest.mark.unit
    def test_attachment_with_empty_file_name_not_added_as_doc(self):
        """Attachment with empty file_name should not be added as document"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-empty-fname",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "With empty attachment",
                    "sender": "human",
                    "attachments": [{"file_name": "", "file_type": "application/pdf"}],
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        # Empty file_name means not an image extension match, and the elif checks
        # if file_name is truthy -- empty string is falsy, so not added as document
        assert len(msg.content.images) == 0
        assert len(msg.content.documents) == 0

    @pytest.mark.unit
    def test_multiple_image_and_document_attachments(self):
        """Multiple attachments should be split between images and documents"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-multi-attach",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "text": "Multiple files",
                    "sender": "human",
                    "attachments": [
                        {"file_name": "photo.jpg", "file_type": "image/jpeg"},
                        {"file_name": "data.csv", "file_type": "text/csv"},
                        {"file_name": "diagram.png", "file_type": "image/png"},
                        {"file_name": "readme.txt", "file_type": "text/plain"},
                    ],
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]

        assert len(msg.content.images) == 2  # .jpg and .png
        assert len(msg.content.documents) == 2  # .csv and .txt
        assert "Attachments:" in msg.content.text

    @pytest.mark.unit
    def test_text_field_with_none_value(self):
        """Message with text field set to None should handle gracefully"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-none-text",
            "chat_messages": [
                {"uuid": "m1", "text": None, "sender": "human"},
            ],
        }
        # "text" in msg_data is True (key exists), so content.text = None
        # This should not crash
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        assert msg.content.text is None

    @pytest.mark.unit
    def test_no_text_no_content_fields(self):
        """Message with neither text nor content should have empty content"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-no-content",
            "chat_messages": [
                {"uuid": "m1", "sender": "human"},
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        # Neither "text" nor "content" branch executes; content.text stays default None
        assert msg.content.text is None

    @pytest.mark.unit
    def test_plugin_attributes(self):
        """Verify plugin class attributes are set correctly"""
        importer = AnthropicImporter()
        assert importer.name == "anthropic"
        assert importer.description == "Import Claude conversation exports"
        assert importer.version == "1.0.0"
        assert "claude" in importer.supported_formats
        assert "anthropic" in importer.supported_formats

    @pytest.mark.unit
    def test_content_list_with_image_missing_source(self):
        """Image part with missing source should not crash"""
        importer = AnthropicImporter()
        data = {
            "uuid": "conv-img-no-source",
            "chat_messages": [
                {
                    "uuid": "m1",
                    "content": [
                        {"type": "image"},
                    ],
                    "sender": "human",
                },
            ],
        }
        conversations = importer.import_data(data)
        msg = conversations[0].message_map["m1"]
        # source defaults to {} which is a dict, but has no "type" == "base64"
        # and no "url", so no image is added
        assert len(msg.content.images) == 0
