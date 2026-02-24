"""
Comprehensive tests for the Gemini/Bard conversation importer.

Covers: validation, model detection, import basics, message parsing,
content handling, edge cases, and string input.
"""

import json
from datetime import datetime

import pytest

from ctk.core.models import MessageRole
from ctk.integrations.importers.gemini import GeminiImporter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_turn(role="user", text="Hello", parts=None, **extra):
    """Build a minimal turn/message dict."""
    turn = {"role": role}
    if parts is not None:
        turn["parts"] = parts
    else:
        turn["parts"] = [{"text": text}]
    turn.update(extra)
    return turn


# ===========================================================================
# Validation
# ===========================================================================


class TestGeminiValidation:
    """Tests for GeminiImporter.validate()"""

    @pytest.mark.unit
    def test_validate_json_string_with_conversations(self):
        """JSON string containing 'conversations' key should validate."""
        importer = GeminiImporter()
        data = json.dumps({"conversations": []})
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_json_string_with_messages(self):
        """JSON string containing 'messages' key should validate."""
        importer = GeminiImporter()
        data = json.dumps({"messages": []})
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_json_string_with_turns(self):
        """JSON string containing 'turns' key should validate."""
        importer = GeminiImporter()
        data = json.dumps({"turns": []})
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_json_string_with_conversation_id(self):
        """JSON string containing 'conversation_id' should validate."""
        importer = GeminiImporter()
        data = json.dumps({"conversation_id": "abc123"})
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_dict_with_conversations(self):
        """Dict with 'conversations' key should validate."""
        importer = GeminiImporter()
        assert importer.validate({"conversations": []}) is True

    @pytest.mark.unit
    def test_validate_dict_with_messages(self):
        """Dict with 'messages' key should validate."""
        importer = GeminiImporter()
        assert importer.validate({"messages": []}) is True

    @pytest.mark.unit
    def test_validate_dict_with_turns(self):
        """Dict with 'turns' key should validate."""
        importer = GeminiImporter()
        assert importer.validate({"turns": []}) is True

    @pytest.mark.unit
    def test_validate_dict_with_conversation_id(self):
        """Dict with 'conversation_id' should validate."""
        importer = GeminiImporter()
        assert importer.validate({"conversation_id": "xyz"}) is True

    @pytest.mark.unit
    def test_validate_list_with_gemini_model(self):
        """List whose first item mentions 'model' and 'gemini' should validate."""
        importer = GeminiImporter()
        data = [{"model": "gemini-pro", "turns": []}]
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_list_with_bard(self):
        """List whose first item mentions 'bard' should validate."""
        importer = GeminiImporter()
        data = [{"source": "bard", "turns": []}]
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_invalid_dict(self):
        """Dict without recognised keys should be rejected."""
        importer = GeminiImporter()
        assert importer.validate({"random": "data"}) is False

    @pytest.mark.unit
    def test_validate_plain_string_not_json(self):
        """A plain non-JSON string should be rejected."""
        importer = GeminiImporter()
        assert importer.validate("this is not json") is False

    @pytest.mark.unit
    def test_validate_malformed_json_string(self):
        """Malformed JSON string should be rejected."""
        importer = GeminiImporter()
        assert importer.validate("{bad json:") is False

    @pytest.mark.unit
    def test_validate_empty_list(self):
        """Empty list should be rejected (no sample to inspect)."""
        importer = GeminiImporter()
        assert importer.validate([]) is False

    @pytest.mark.unit
    def test_validate_empty_dict(self):
        """Empty dict should be rejected."""
        importer = GeminiImporter()
        assert importer.validate({}) is False

    @pytest.mark.unit
    def test_validate_integer(self):
        """Non-dict/list/str types should be rejected."""
        importer = GeminiImporter()
        assert importer.validate(42) is False

    @pytest.mark.unit
    def test_validate_none(self):
        """None should be rejected."""
        importer = GeminiImporter()
        assert importer.validate(None) is False

    @pytest.mark.unit
    def test_validate_list_without_gemini_or_bard(self):
        """List with items that don't mention gemini/bard should be rejected."""
        importer = GeminiImporter()
        data = [{"role": "user", "content": "hello"}]
        assert importer.validate(data) is False


# ===========================================================================
# Model Detection
# ===========================================================================


class TestGeminiModelDetection:
    """Tests for GeminiImporter._detect_model()"""

    @pytest.mark.unit
    def test_detect_gemini_pro(self):
        importer = GeminiImporter()
        assert importer._detect_model({"model": "gemini-pro"}) == "Gemini Pro"

    @pytest.mark.unit
    def test_detect_gemini_pro_vision(self):
        importer = GeminiImporter()
        assert (
            importer._detect_model({"model": "gemini-pro-vision"})
            == "Gemini Pro Vision"
        )

    @pytest.mark.unit
    def test_detect_gemini_ultra(self):
        importer = GeminiImporter()
        assert importer._detect_model({"model": "gemini-ultra"}) == "Gemini Ultra"

    @pytest.mark.unit
    def test_detect_gemini_1_5_pro(self):
        importer = GeminiImporter()
        assert importer._detect_model({"model": "gemini-1.5-pro"}) == "Gemini 1.5 Pro"

    @pytest.mark.unit
    def test_detect_gemini_1_5_flash(self):
        importer = GeminiImporter()
        assert (
            importer._detect_model({"model": "gemini-1.5-flash"}) == "Gemini 1.5 Flash"
        )

    @pytest.mark.unit
    def test_detect_bard(self):
        importer = GeminiImporter()
        assert importer._detect_model({"model": "bard"}) == "Bard"

    @pytest.mark.unit
    def test_detect_palm(self):
        importer = GeminiImporter()
        assert importer._detect_model({"model": "palm"}) == "PaLM"

    @pytest.mark.unit
    def test_detect_palm_2(self):
        importer = GeminiImporter()
        assert importer._detect_model({"model": "palm-2"}) == "PaLM 2"

    @pytest.mark.unit
    def test_detect_unknown_model(self):
        """Unknown model string should be returned as-is."""
        importer = GeminiImporter()
        assert (
            importer._detect_model({"model": "some-future-model"})
            == "some-future-model"
        )

    @pytest.mark.unit
    def test_detect_empty_model(self):
        """Empty model string should fall back to 'Gemini'."""
        importer = GeminiImporter()
        assert importer._detect_model({"model": ""}) == "Gemini"

    @pytest.mark.unit
    def test_detect_no_model_field(self):
        """Missing model key should fall back to 'Gemini'."""
        importer = GeminiImporter()
        assert importer._detect_model({}) == "Gemini"

    @pytest.mark.unit
    def test_detect_model_case_insensitive(self):
        """Model detection should be case-insensitive."""
        importer = GeminiImporter()
        assert importer._detect_model({"model": "Gemini-Pro"}) == "Gemini Pro"
        assert importer._detect_model({"model": "GEMINI-ULTRA"}) == "Gemini Ultra"

    @pytest.mark.unit
    def test_detect_model_with_version_suffix(self):
        """Model string containing known key as substring should still match."""
        importer = GeminiImporter()
        # 'gemini-1.5-pro-latest' contains 'gemini-1.5-pro'
        assert (
            importer._detect_model({"model": "gemini-1.5-pro-latest"})
            == "Gemini 1.5 Pro"
        )


# ===========================================================================
# Import – Basic
# ===========================================================================


class TestGeminiImportBasic:
    """Tests for basic import_data scenarios."""

    @pytest.mark.unit
    def test_import_single_conversation_dict(self):
        """Importing a single conversation dict should return one ConversationTree."""
        importer = GeminiImporter()
        data = {
            "conversation_id": "conv_1",
            "title": "My Chat",
            "turns": [
                _make_turn("user", "Hi"),
                _make_turn("model", "Hello!"),
            ],
        }
        result = importer.import_data(data)
        assert len(result) == 1
        assert result[0].id == "conv_1"
        assert result[0].title == "My Chat"

    @pytest.mark.unit
    def test_import_multiple_conversations_in_wrapper(self):
        """Dict with 'conversations' list should import all conversations."""
        importer = GeminiImporter()
        data = {
            "conversations": [
                {
                    "id": "c1",
                    "title": "First",
                    "turns": [_make_turn("user", "A")],
                },
                {
                    "id": "c2",
                    "title": "Second",
                    "turns": [_make_turn("user", "B")],
                },
            ]
        }
        result = importer.import_data(data)
        assert len(result) == 2
        assert result[0].id == "c1"
        assert result[1].id == "c2"

    @pytest.mark.unit
    def test_import_list_of_conversations(self):
        """Passing a bare list should import each element as a conversation."""
        importer = GeminiImporter()
        data = [
            {"id": "l1", "turns": [_make_turn("user", "X")]},
            {"id": "l2", "turns": [_make_turn("user", "Y")]},
        ]
        result = importer.import_data(data)
        assert len(result) == 2

    @pytest.mark.unit
    def test_import_json_string_input(self):
        """import_data should accept a JSON string and parse it."""
        importer = GeminiImporter()
        data = json.dumps(
            {
                "id": "json_str",
                "title": "From String",
                "turns": [_make_turn("user", "Hello from string")],
            }
        )
        result = importer.import_data(data)
        assert len(result) == 1
        assert result[0].id == "json_str"
        assert result[0].title == "From String"

    @pytest.mark.unit
    def test_import_conversation_metadata(self):
        """Metadata should include source, format, model, and standard tags."""
        importer = GeminiImporter()
        data = {
            "id": "meta_1",
            "model": "gemini-pro",
            "turns": [_make_turn("user", "Q")],
        }
        result = importer.import_data(data)
        meta = result[0].metadata
        assert meta.source == "Google Gemini"
        assert meta.format == "gemini"
        assert meta.model == "Gemini Pro"
        assert "google" in meta.tags
        assert "gemini" in meta.tags
        assert "gemini-pro" in meta.tags

    @pytest.mark.unit
    def test_import_id_fallback_to_conversation_id(self):
        """If no 'id', 'conversation_id' should be used."""
        importer = GeminiImporter()
        data = {"conversation_id": "fallback_id", "turns": []}
        result = importer.import_data(data)
        assert result[0].id == "fallback_id"

    @pytest.mark.unit
    def test_import_id_generated_when_missing(self):
        """If neither 'id' nor 'conversation_id', a UUID should be generated."""
        importer = GeminiImporter()
        data = {"turns": [_make_turn("user", "hi")]}
        result = importer.import_data(data)
        assert result[0].id  # Should be a non-empty string (uuid)
        assert len(result[0].id) > 0


# ===========================================================================
# Message Parsing
# ===========================================================================


class TestGeminiMessageParsing:
    """Tests for message/turn parsing within import_data."""

    @pytest.mark.unit
    def test_turns_field(self):
        """Messages should be read from the 'turns' field."""
        importer = GeminiImporter()
        data = {
            "turns": [
                _make_turn("user", "Q1"),
                _make_turn("model", "A1"),
            ],
        }
        result = importer.import_data(data)
        msgs = result[0].get_longest_path()
        assert len(msgs) == 2

    @pytest.mark.unit
    def test_messages_field(self):
        """Messages should be read from the 'messages' field."""
        importer = GeminiImporter()
        data = {
            "messages": [
                _make_turn("user", "Q2"),
                _make_turn("model", "A2"),
            ],
        }
        result = importer.import_data(data)
        msgs = result[0].get_longest_path()
        assert len(msgs) == 2

    @pytest.mark.unit
    def test_author_field_for_role(self):
        """The 'author' field should be preferred over 'role'."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"author": "user", "parts": [{"text": "Hi"}]},
                {"author": "model", "parts": [{"text": "Hey"}]},
            ],
        }
        result = importer.import_data(data)
        msgs = result[0].get_longest_path()
        assert msgs[0].role == MessageRole.USER
        assert msgs[1].role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_role_model_maps_to_assistant(self):
        """role='model' should map to ASSISTANT."""
        importer = GeminiImporter()
        data = {"turns": [_make_turn("model", "reply")]}
        result = importer.import_data(data)
        assert result[0].get_longest_path()[0].role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_role_gemini_maps_to_assistant(self):
        """role='gemini' should map to ASSISTANT."""
        importer = GeminiImporter()
        data = {"turns": [_make_turn("gemini", "reply")]}
        result = importer.import_data(data)
        assert result[0].get_longest_path()[0].role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_role_bard_maps_to_assistant(self):
        """role='bard' should map to ASSISTANT."""
        importer = GeminiImporter()
        data = {"turns": [_make_turn("bard", "reply")]}
        result = importer.import_data(data)
        assert result[0].get_longest_path()[0].role == MessageRole.ASSISTANT

    @pytest.mark.unit
    def test_role_user_maps_to_user(self):
        """role='user' should map to USER."""
        importer = GeminiImporter()
        data = {"turns": [_make_turn("user", "question")]}
        result = importer.import_data(data)
        assert result[0].get_longest_path()[0].role == MessageRole.USER

    @pytest.mark.unit
    def test_role_system_maps_to_system(self):
        """role='system' should map to SYSTEM via MessageRole.from_string."""
        importer = GeminiImporter()
        data = {"turns": [_make_turn("system", "system prompt")]}
        result = importer.import_data(data)
        assert result[0].get_longest_path()[0].role == MessageRole.SYSTEM

    @pytest.mark.unit
    def test_message_id_from_data(self):
        """If 'id' is present in message data, it should be used."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"id": "custom_msg_id", "role": "user", "parts": [{"text": "Hi"}]},
            ],
        }
        result = importer.import_data(data)
        msgs = result[0].get_longest_path()
        assert msgs[0].id == "custom_msg_id"

    @pytest.mark.unit
    def test_message_id_generated_fallback(self):
        """Messages without 'id' should get generated 'msg_<idx>' ids."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"role": "user", "parts": [{"text": "Hi"}]},
                {"role": "model", "parts": [{"text": "Hey"}]},
            ],
        }
        result = importer.import_data(data)
        msgs = result[0].get_longest_path()
        assert msgs[0].id == "msg_0"
        assert msgs[1].id == "msg_1"

    @pytest.mark.unit
    def test_message_parent_chain(self):
        """Messages should form a linear parent chain."""
        importer = GeminiImporter()
        data = {
            "turns": [
                _make_turn("user", "1"),
                _make_turn("model", "2"),
                _make_turn("user", "3"),
            ],
        }
        result = importer.import_data(data)
        msgs = result[0].get_longest_path()
        assert msgs[0].parent_id is None
        assert msgs[1].parent_id == msgs[0].id
        assert msgs[2].parent_id == msgs[1].id

    @pytest.mark.unit
    def test_message_metadata_safety_ratings(self):
        """Safety ratings from message data should be captured in metadata."""
        importer = GeminiImporter()
        ratings = [{"category": "HARM_CATEGORY_HARASSMENT", "probability": "LOW"}]
        data = {
            "turns": [
                {"role": "model", "parts": [{"text": "ok"}], "safety_ratings": ratings},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.metadata["safety_ratings"] == ratings

    @pytest.mark.unit
    def test_message_metadata_candidates_count(self):
        """candidates_count from message data should be captured in metadata."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"role": "model", "parts": [{"text": "ok"}], "candidates_count": 3},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.metadata["candidates_count"] == 3


# ===========================================================================
# Content Handling
# ===========================================================================


class TestGeminiContentParsing:
    """Tests for multimodal content / parts parsing."""

    @pytest.mark.unit
    def test_parts_with_text_dict(self):
        """Parts containing {'text': ...} should be concatenated as text."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"role": "user", "parts": [{"text": "Hello"}, {"text": "World"}]},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == "Hello\nWorld"

    @pytest.mark.unit
    def test_parts_with_plain_string(self):
        """Parts that are plain strings should be treated as text."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"role": "user", "parts": ["raw string part"]},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == "raw string part"

    @pytest.mark.unit
    def test_parts_with_inline_data(self):
        """Parts with 'inline_data' should be stored as media in metadata."""
        importer = GeminiImporter()
        inline = {"inline_data": {"mime_type": "image/png", "data": "base64data=="}}
        data = {
            "turns": [
                {"role": "user", "parts": [inline]},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert "media" in msg.content.metadata
        assert len(msg.content.metadata["media"]) == 1
        assert msg.content.metadata["media"][0] == inline

    @pytest.mark.unit
    def test_parts_mixed_text_and_inline_data(self):
        """Mixed text and inline_data parts should capture both."""
        importer = GeminiImporter()
        inline = {"inline_data": {"mime_type": "image/jpeg", "data": "abc123"}}
        data = {
            "turns": [
                {"role": "user", "parts": [{"text": "Describe this"}, inline]},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == "Describe this"
        assert len(msg.content.metadata["media"]) == 1

    @pytest.mark.unit
    def test_content_field_fallback(self):
        """When no 'parts', the 'content' field should be used for text."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"role": "user", "content": "fallback content"},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == "fallback content"

    @pytest.mark.unit
    def test_text_field_fallback(self):
        """When no 'parts' or 'content', the 'text' field should be used."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"role": "user", "text": "text field value"},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == "text field value"

    @pytest.mark.unit
    def test_empty_parts_list(self):
        """Empty parts list should result in empty text."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"role": "user", "parts": []},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == ""

    @pytest.mark.unit
    def test_parts_stored_on_content_object(self):
        """The raw parts list should be stored on content.parts."""
        importer = GeminiImporter()
        parts = [{"text": "a"}, {"text": "b"}]
        data = {
            "turns": [
                {"role": "user", "parts": parts},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.parts == parts

    @pytest.mark.unit
    def test_multiple_inline_data_parts(self):
        """Multiple inline_data parts should all be captured."""
        importer = GeminiImporter()
        img1 = {"inline_data": {"mime_type": "image/png", "data": "aaa"}}
        img2 = {"inline_data": {"mime_type": "image/jpeg", "data": "bbb"}}
        data = {
            "turns": [
                {"role": "user", "parts": [img1, img2]},
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert len(msg.content.metadata["media"]) == 2


# ===========================================================================
# Edge Cases
# ===========================================================================


class TestGeminiImportEdgeCases:
    """Edge cases and unusual but valid inputs."""

    @pytest.mark.unit
    def test_no_title_defaults(self):
        """Missing title should default to 'Untitled Conversation'."""
        importer = GeminiImporter()
        data = {"turns": [_make_turn("user", "hi")]}
        result = importer.import_data(data)
        assert result[0].title == "Untitled Conversation"

    @pytest.mark.unit
    def test_no_messages_or_turns(self):
        """Conversation with no messages/turns should still import (empty tree)."""
        importer = GeminiImporter()
        data = {"id": "empty_conv"}
        result = importer.import_data(data)
        assert len(result) == 1
        assert result[0].id == "empty_conv"
        assert result[0].get_longest_path() == []

    @pytest.mark.unit
    def test_empty_conversations_list(self):
        """Empty 'conversations' list should return empty result."""
        importer = GeminiImporter()
        data = {"conversations": []}
        result = importer.import_data(data)
        assert len(result) == 0

    @pytest.mark.unit
    def test_unicode_content(self):
        """Unicode characters in content should be preserved."""
        importer = GeminiImporter()
        text = "Bonjour! \u00c7a va? \U0001f600 \u4f60\u597d \u0417\u0434\u0440\u0430\u0432\u0441\u0442\u0432\u0443\u0439\u0442\u0435"
        data = {"turns": [_make_turn("user", text)]}
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == text

    @pytest.mark.unit
    def test_timestamp_parsing(self):
        """ISO timestamp in message should be parsed."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {
                    "role": "user",
                    "parts": [{"text": "hi"}],
                    "timestamp": "2024-06-15T10:30:00",
                },
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.timestamp is not None
        assert msg.timestamp.year == 2024
        assert msg.timestamp.month == 6

    @pytest.mark.unit
    def test_conversation_created_at_timestamp(self):
        """Conversation-level created_at should be parsed into metadata."""
        importer = GeminiImporter()
        data = {
            "created_at": "2024-01-01T00:00:00",
            "turns": [_make_turn("user", "hi")],
        }
        result = importer.import_data(data)
        assert result[0].metadata.created_at.year == 2024

    @pytest.mark.unit
    def test_conversation_updated_at_timestamp(self):
        """Conversation-level updated_at is set but add_message() overwrites it."""
        importer = GeminiImporter()
        # updated_at gets overwritten by add_message(), so just verify it's a datetime
        data = {
            "updated_at": "2025-03-20T12:00:00",
            "turns": [_make_turn("user", "hi")],
        }
        result = importer.import_data(data)
        assert isinstance(result[0].metadata.updated_at, datetime)

    @pytest.mark.unit
    def test_custom_data_language(self):
        """language field should be captured in custom_data."""
        importer = GeminiImporter()
        data = {"language": "en", "turns": [_make_turn("user", "hi")]}
        result = importer.import_data(data)
        assert result[0].metadata.custom_data["language"] == "en"

    @pytest.mark.unit
    def test_custom_data_safety_settings(self):
        """safety_settings field should be captured in custom_data."""
        importer = GeminiImporter()
        settings = [{"category": "HARM_CATEGORY_DANGEROUS", "threshold": "BLOCK_NONE"}]
        data = {"safety_settings": settings, "turns": [_make_turn("user", "hi")]}
        result = importer.import_data(data)
        assert result[0].metadata.custom_data["safety_settings"] == settings

    @pytest.mark.unit
    def test_model_tag_normalised(self):
        """Model name in tags should be lower-case with hyphens for spaces."""
        importer = GeminiImporter()
        data = {"model": "gemini-1.5-flash", "turns": [_make_turn("user", "hi")]}
        result = importer.import_data(data)
        assert "gemini-1.5-flash" in result[0].metadata.tags

    @pytest.mark.unit
    def test_no_content_no_parts_no_text(self):
        """Message with no content, parts, or text should have empty text."""
        importer = GeminiImporter()
        data = {"turns": [{"role": "user"}]}
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == ""

    @pytest.mark.unit
    def test_role_case_insensitive(self):
        """Role matching for model/gemini/bard should be case-insensitive."""
        importer = GeminiImporter()
        for role_str in ["Model", "MODEL", "Gemini", "GEMINI", "Bard", "BARD"]:
            data = {"turns": [_make_turn(role_str, "reply")]}
            result = importer.import_data(data)
            msg = result[0].get_longest_path()[0]
            assert msg.role == MessageRole.ASSISTANT, f"Failed for role: {role_str}"

    @pytest.mark.unit
    def test_large_conversation(self):
        """Importing a conversation with many turns should work correctly."""
        importer = GeminiImporter()
        turns = []
        for i in range(100):
            role = "user" if i % 2 == 0 else "model"
            turns.append(_make_turn(role, f"Message {i}"))
        data = {"turns": turns}
        result = importer.import_data(data)
        msgs = result[0].get_longest_path()
        assert len(msgs) == 100
        # Verify parent chain integrity
        for i in range(1, len(msgs)):
            assert msgs[i].parent_id == msgs[i - 1].id

    @pytest.mark.unit
    def test_import_preserves_conversation_order(self):
        """Conversations should maintain the order they appear in the input."""
        importer = GeminiImporter()
        data = {
            "conversations": [
                {"id": f"conv_{i}", "turns": [_make_turn("user", f"msg {i}")]}
                for i in range(5)
            ]
        }
        result = importer.import_data(data)
        for i, conv in enumerate(result):
            assert conv.id == f"conv_{i}"

    @pytest.mark.unit
    def test_message_timestamp_none_when_missing(self):
        """Message timestamp should be None when not provided."""
        importer = GeminiImporter()
        data = {"turns": [{"role": "user", "parts": [{"text": "hi"}]}]}
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        # parse_timestamp(None) returns None (default=None)
        assert msg.timestamp is None

    @pytest.mark.unit
    def test_plugin_attributes(self):
        """Plugin class attributes should be set correctly."""
        importer = GeminiImporter()
        assert importer.name == "gemini"
        assert "gemini" in importer.supported_formats
        assert "bard" in importer.supported_formats
        assert "google" in importer.supported_formats

    @pytest.mark.unit
    def test_dict_part_without_text_or_inline_data_ignored(self):
        """Dict parts that have neither 'text' nor 'inline_data' should be skipped."""
        importer = GeminiImporter()
        data = {
            "turns": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "keep this"},
                        {"unknown_key": "skip me"},
                    ],
                },
            ],
        }
        result = importer.import_data(data)
        msg = result[0].get_longest_path()[0]
        assert msg.content.text == "keep this"
        assert "media" not in msg.content.metadata
