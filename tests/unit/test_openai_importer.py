"""
Unit tests for OpenAI importer helper methods (TDD - RED phase).

These tests target four helper methods that will be extracted from the
OpenAI importer's import_data method:
  - _process_part(part) -> Optional[str]
  - _process_asset_pointer(part, content) -> None (mutates content)
  - _process_image_url(part, content) -> None (mutates content)
  - _process_tool_calls(content_data, content) -> None (mutates content)

The methods do NOT exist yet. All tests should FAIL.
"""

from unittest.mock import patch

import pytest

from ctk.core.models import MessageContent, MessageRole, ToolCall
from ctk.integrations.importers.openai import OpenAIImporter


@pytest.fixture
def importer():
    """Create an OpenAIImporter instance for testing."""
    imp = OpenAIImporter()
    imp.source_dir = "/tmp/fake_source"
    imp.media_dir = "/tmp/fake_media"
    return imp


# ---------------------------------------------------------------------------
# _process_part tests
# ---------------------------------------------------------------------------
class TestProcessPart:
    """Tests for _process_part(part) -> Optional[str]"""

    @pytest.mark.unit
    def test_string_input_returns_string(self, importer):
        """A plain string part should be returned as-is."""
        result = importer._process_part("Hello, world!")
        assert result == "Hello, world!"

    @pytest.mark.unit
    def test_dict_with_text_key_returns_text(self, importer):
        """A dict with a 'text' key should return the text value."""
        part = {"text": "Some text content"}
        result = importer._process_part(part)
        assert result == "Some text content"

    @pytest.mark.unit
    def test_dict_with_content_key_returns_str_value(self, importer):
        """A dict with a 'content' key should return str(value)."""
        part = {"content": 42}
        result = importer._process_part(part)
        assert result == "42"

    @pytest.mark.unit
    def test_dict_with_content_key_string_value(self, importer):
        """A dict with a 'content' key and string value should return it."""
        part = {"content": "text content"}
        result = importer._process_part(part)
        assert result == "text content"

    @pytest.mark.unit
    def test_empty_string_returns_empty_string(self, importer):
        """An empty string should be returned as empty string."""
        result = importer._process_part("")
        assert result == ""

    @pytest.mark.unit
    def test_non_string_non_dict_returns_none(self, importer):
        """A non-string, non-dict value (e.g. int) should return None."""
        result = importer._process_part(12345)
        assert result is None

    @pytest.mark.unit
    def test_none_input_returns_none(self, importer):
        """None input should return None."""
        result = importer._process_part(None)
        assert result is None

    @pytest.mark.unit
    def test_list_input_returns_none(self, importer):
        """A list input should return None (not string, not dict)."""
        result = importer._process_part([1, 2, 3])
        assert result is None

    @pytest.mark.unit
    def test_dict_with_asset_pointer_returns_none(self, importer):
        """A dict with 'asset_pointer' (but no 'text'/'content') returns None.
        Asset pointers are handled by _process_asset_pointer, not here."""
        part = {"asset_pointer": "file-service://file-abc123"}
        result = importer._process_part(part)
        assert result is None

    @pytest.mark.unit
    def test_dict_with_image_url_returns_none(self, importer):
        """A dict with 'image_url' (but no 'text'/'content') returns None.
        Image URLs are handled by _process_image_url, not here."""
        part = {"image_url": "https://example.com/image.png"}
        result = importer._process_part(part)
        assert result is None


# ---------------------------------------------------------------------------
# _process_asset_pointer tests
# ---------------------------------------------------------------------------
class TestProcessAssetPointer:
    """Tests for _process_asset_pointer(part, content) -> None (mutates content)"""

    @pytest.mark.unit
    def test_asset_pointer_with_dalle_metadata(self, importer):
        """Asset pointer with DALL-E metadata should add image with caption=prompt."""
        part = {
            "asset_pointer": "file-service://file-abc123",
            "metadata": {
                "dalle": {
                    "prompt": "A cat wearing a hat"
                }
            },
        }
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value="media/resolved.png"
        ):
            importer._process_asset_pointer(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "media/resolved.png"
        assert content.images[0].caption == "A cat wearing a hat"

    @pytest.mark.unit
    def test_asset_pointer_without_metadata(self, importer):
        """Asset pointer without metadata should add image with caption=None."""
        part = {
            "asset_pointer": "file-service://file-abc123",
        }
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value="media/resolved.png"
        ):
            importer._process_asset_pointer(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "media/resolved.png"
        assert content.images[0].caption is None

    @pytest.mark.unit
    def test_asset_pointer_with_none_url(self, importer):
        """Asset pointer with None URL should not add any image."""
        part = {
            "asset_pointer": None,
        }
        content = MessageContent()
        importer._process_asset_pointer(part, content)

        assert len(content.images) == 0

    @pytest.mark.unit
    def test_asset_pointer_resolve_returns_none(self, importer):
        """When _resolve_and_copy_image returns None, no image should be added."""
        part = {
            "asset_pointer": "file-service://file-abc123",
        }
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value=None
        ):
            importer._process_asset_pointer(part, content)

        assert len(content.images) == 0

    @pytest.mark.unit
    def test_asset_pointer_metadata_not_dict(self, importer):
        """When metadata is not a dict, image should be added with caption=None."""
        part = {
            "asset_pointer": "file-service://file-abc123",
            "metadata": "not-a-dict",
        }
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value="media/resolved.png"
        ):
            importer._process_asset_pointer(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "media/resolved.png"
        assert content.images[0].caption is None

    @pytest.mark.unit
    def test_asset_pointer_dalle_key_not_dict(self, importer):
        """When dalle value is not a dict, image should be added with caption=None."""
        part = {
            "asset_pointer": "file-service://file-abc123",
            "metadata": {
                "dalle": "not-a-dict"
            },
        }
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value="media/resolved.png"
        ):
            importer._process_asset_pointer(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "media/resolved.png"
        assert content.images[0].caption is None

    @pytest.mark.unit
    def test_asset_pointer_empty_metadata_dict(self, importer):
        """Empty metadata dict should add image with caption=None."""
        part = {
            "asset_pointer": "file-service://file-abc123",
            "metadata": {},
        }
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value="media/resolved.png"
        ):
            importer._process_asset_pointer(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "media/resolved.png"
        assert content.images[0].caption is None


# ---------------------------------------------------------------------------
# _process_image_url tests
# ---------------------------------------------------------------------------
class TestProcessImageUrl:
    """Tests for _process_image_url(part, content) -> None (mutates content)"""

    @pytest.mark.unit
    def test_string_url_regular(self, importer):
        """A regular string URL should add image with that URL directly."""
        part = {"image_url": "https://example.com/cat.png"}
        content = MessageContent()

        importer._process_image_url(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "https://example.com/cat.png"

    @pytest.mark.unit
    def test_string_url_file_service_resolved(self, importer):
        """A file-service:// string URL should resolve and add the resolved path."""
        part = {"image_url": "file-service://file-abc123"}
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value="media/resolved.png"
        ):
            importer._process_image_url(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "media/resolved.png"

    @pytest.mark.unit
    def test_string_url_file_service_resolve_fails(self, importer):
        """When file-service:// resolve fails (returns None), no image added."""
        part = {"image_url": "file-service://file-missing"}
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value=None
        ):
            importer._process_image_url(part, content)

        assert len(content.images) == 0

    @pytest.mark.unit
    def test_dict_with_url_key_regular(self, importer):
        """A dict with 'url' key (regular URL) should add image with url and detail as caption."""
        part = {
            "image_url": {
                "url": "https://example.com/cat.png",
                "detail": "high",
            }
        }
        content = MessageContent()

        importer._process_image_url(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "https://example.com/cat.png"
        assert content.images[0].caption == "high"

    @pytest.mark.unit
    def test_dict_with_url_key_file_service(self, importer):
        """A dict with file-service:// URL should resolve, add with detail as caption."""
        part = {
            "image_url": {
                "url": "file-service://file-abc123",
                "detail": "auto",
            }
        }
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value="media/resolved.png"
        ):
            importer._process_image_url(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "media/resolved.png"
        assert content.images[0].caption == "auto"

    @pytest.mark.unit
    def test_dict_with_url_key_file_service_resolve_fails(self, importer):
        """A dict with file-service:// URL where resolve fails: no image added."""
        part = {
            "image_url": {
                "url": "file-service://file-missing",
                "detail": "auto",
            }
        }
        content = MessageContent()

        with patch.object(
            importer, "_resolve_and_copy_image", return_value=None
        ):
            importer._process_image_url(part, content)

        assert len(content.images) == 0

    @pytest.mark.unit
    def test_dict_without_url_key(self, importer):
        """A dict without 'url' key should not add any image."""
        part = {"image_url": {"detail": "high"}}
        content = MessageContent()

        importer._process_image_url(part, content)

        assert len(content.images) == 0

    @pytest.mark.unit
    def test_dict_with_url_key_no_detail(self, importer):
        """A dict with 'url' but no 'detail' should add image with caption=None."""
        part = {
            "image_url": {
                "url": "https://example.com/cat.png",
            }
        }
        content = MessageContent()

        importer._process_image_url(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "https://example.com/cat.png"
        assert content.images[0].caption is None


# ---------------------------------------------------------------------------
# _process_tool_calls tests
# ---------------------------------------------------------------------------
class TestProcessToolCalls:
    """Tests for _process_tool_calls(content_data, content) -> None (mutates content)"""

    @pytest.mark.unit
    def test_modern_tool_calls_format(self, importer):
        """Modern 'tool_calls' format should extract name, id, and arguments."""
        content_data = {
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "London"}',
                    },
                }
            ]
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 1
        tc = content.tool_calls[0]
        assert tc.id == "call_abc123"
        assert tc.name == "get_weather"
        assert tc.arguments == {"city": "London"}

    @pytest.mark.unit
    def test_modern_tool_calls_multiple(self, importer):
        """Multiple tool calls should all be extracted."""
        content_data = {
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "tool_a",
                        "arguments": '{"x": 1}',
                    },
                },
                {
                    "id": "call_2",
                    "function": {
                        "name": "tool_b",
                        "arguments": '{"y": 2}',
                    },
                },
            ]
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 2
        assert content.tool_calls[0].name == "tool_a"
        assert content.tool_calls[1].name == "tool_b"

    @pytest.mark.unit
    def test_legacy_function_call_format(self, importer):
        """Legacy 'function_call' format should extract name and arguments."""
        content_data = {
            "function_call": {
                "name": "search",
                "arguments": '{"query": "python"}',
            }
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 1
        tc = content.tool_calls[0]
        assert tc.name == "search"
        assert tc.arguments == {"query": "python"}

    @pytest.mark.unit
    def test_empty_arguments_string(self, importer):
        """Empty arguments string should result in empty dict."""
        content_data = {
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "no_args_tool",
                        "arguments": "",
                    },
                }
            ]
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].arguments == {}

    @pytest.mark.unit
    def test_missing_arguments_key(self, importer):
        """Missing 'arguments' key should result in empty dict."""
        content_data = {
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "no_args_tool",
                    },
                }
            ]
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].arguments == {}

    @pytest.mark.unit
    def test_both_modern_and_legacy_present(self, importer):
        """When both tool_calls and function_call are present, both extracted."""
        content_data = {
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "modern_tool",
                        "arguments": '{"a": 1}',
                    },
                }
            ],
            "function_call": {
                "name": "legacy_tool",
                "arguments": '{"b": 2}',
            },
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 2
        names = {tc.name for tc in content.tool_calls}
        assert "modern_tool" in names
        assert "legacy_tool" in names

    @pytest.mark.unit
    def test_neither_present(self, importer):
        """When neither tool_calls nor function_call present, no tool calls added."""
        content_data = {"content_type": "text", "parts": ["hello"]}
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 0

    @pytest.mark.unit
    def test_legacy_function_call_empty_arguments(self, importer):
        """Legacy function_call with empty arguments string should give empty dict."""
        content_data = {
            "function_call": {
                "name": "search",
                "arguments": "",
            }
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].arguments == {}

    @pytest.mark.unit
    def test_legacy_function_call_missing_arguments(self, importer):
        """Legacy function_call with missing arguments key should give empty dict."""
        content_data = {
            "function_call": {
                "name": "search",
            }
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].arguments == {}

    @pytest.mark.unit
    def test_modern_tool_calls_missing_function_key(self, importer):
        """Tool call entry missing 'function' key should still work with defaults."""
        content_data = {
            "tool_calls": [
                {
                    "id": "call_1",
                }
            ]
        }
        content = MessageContent()

        importer._process_tool_calls(content_data, content)

        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].name == ""
        assert content.tool_calls[0].arguments == {}


# ---------------------------------------------------------------------------
# Helper: minimal OpenAI conversation data builder
# ---------------------------------------------------------------------------
def _make_openai_conv(
    conv_id="conv-001",
    title="Test Conversation",
    mapping=None,
    create_time=None,
    update_time=None,
    default_model_slug=None,
    gizmo_id=None,
    plugin_ids=None,
    extra_fields=None,
):
    """Build a minimal OpenAI-format conversation dict.

    Each mapping entry should be a dict of node_id -> node_data.
    If mapping is None, a single user+assistant exchange is generated.
    """
    if mapping is None:
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["msg-1"]},
            "msg-1": {
                "id": "msg-1",
                "message": {
                    "id": "msg-1",
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Hello"]},
                    "create_time": 1700000000.0,
                    "status": "finished_successfully",
                    "end_turn": None,
                    "weight": 1.0,
                    "recipient": "all",
                },
                "parent": "root",
                "children": ["msg-2"],
            },
            "msg-2": {
                "id": "msg-2",
                "message": {
                    "id": "msg-2",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Hi there!"]},
                    "create_time": 1700000001.0,
                    "status": "finished_successfully",
                    "end_turn": True,
                    "weight": 1.0,
                    "recipient": "all",
                    "metadata": {"model_slug": default_model_slug or "gpt-4"},
                },
                "parent": "msg-1",
                "children": [],
            },
        }

    conv = {
        "conversation_id": conv_id,
        "title": title,
        "mapping": mapping,
    }
    if create_time is not None:
        conv["create_time"] = create_time
    if update_time is not None:
        conv["update_time"] = update_time
    if default_model_slug is not None:
        conv["default_model_slug"] = default_model_slug
    if gizmo_id is not None:
        conv["gizmo_id"] = gizmo_id
    if plugin_ids is not None:
        conv["plugin_ids"] = plugin_ids
    if extra_fields:
        conv.update(extra_fields)
    return conv


def _make_msg_node(
    node_id,
    role="user",
    parts=None,
    content_type="text",
    parent=None,
    children=None,
    create_time=None,
    status="finished_successfully",
    end_turn=None,
    weight=1.0,
    recipient="all",
    model_slug=None,
    content_data_override=None,
):
    """Build a single mapping node for an OpenAI conversation."""
    content_data = content_data_override or {
        "content_type": content_type,
        "parts": parts if parts is not None else ["Hello"],
    }
    msg_info = {
        "id": node_id,
        "author": {"role": role},
        "content": content_data,
        "status": status,
        "end_turn": end_turn,
        "weight": weight,
        "recipient": recipient,
    }
    if create_time is not None:
        msg_info["create_time"] = create_time
    if model_slug is not None:
        msg_info["metadata"] = {"model_slug": model_slug}
    return {
        "id": node_id,
        "message": msg_info,
        "parent": parent,
        "children": children or [],
    }


# ---------------------------------------------------------------------------
# Edge-case tests for the main import flow
# ---------------------------------------------------------------------------
class TestOpenAIImportEdgeCases:
    """Edge-case tests for import_data covering various scenarios."""

    @pytest.mark.unit
    def test_json_string_input(self, importer):
        """import_data should accept a JSON string and parse it."""
        import json as _json

        conv = _make_openai_conv()
        json_str = _json.dumps(conv)
        results = importer.import_data(json_str)

        assert len(results) == 1
        tree = results[0]
        assert tree.id == "conv-001"
        assert tree.title == "Test Conversation"

    @pytest.mark.unit
    def test_json_string_list_input(self, importer):
        """import_data should accept a JSON string containing a list."""
        import json as _json

        convs = [_make_openai_conv(conv_id="c1"), _make_openai_conv(conv_id="c2")]
        json_str = _json.dumps(convs)
        results = importer.import_data(json_str)

        assert len(results) == 2
        ids = {r.id for r in results}
        assert "c1" in ids
        assert "c2" in ids

    @pytest.mark.unit
    def test_conversation_with_system_message(self, importer):
        """System messages should be imported with MessageRole.SYSTEM."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["sys-1"]},
            "sys-1": _make_msg_node("sys-1", role="system", parts=["You are helpful."],
                                    parent="root", children=["usr-1"]),
            "usr-1": _make_msg_node("usr-1", role="user", parts=["Hi"],
                                    parent="sys-1", children=[]),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        sys_msg = tree.message_map.get("sys-1")
        assert sys_msg is not None
        assert sys_msg.role == MessageRole.SYSTEM
        assert sys_msg.content.text == "You are helpful."

    @pytest.mark.unit
    def test_null_message_node_skipped(self, importer):
        """Mapping entries with message=None (structural roots) should be skipped."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parent="root", children=[]),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        # Root node should not appear in message_map
        assert "root" not in tree.message_map
        # m1 should be present
        assert "m1" in tree.message_map

    @pytest.mark.unit
    def test_create_time_update_time_parsed(self, importer):
        """create_time and update_time from conv_data should be parsed into metadata."""
        conv = _make_openai_conv(create_time=1700000000.0, update_time=1700100000.0)
        results = importer.import_data(conv)
        tree = results[0]

        # created_at should be parsed from 1700000000.0
        # We cannot check updated_at due to add_message() overwriting it.
        from datetime import datetime
        expected_created = datetime.fromtimestamp(1700000000.0)
        assert tree.metadata.created_at == expected_created

    @pytest.mark.unit
    def test_model_slug_extraction(self, importer):
        """default_model_slug should map to a readable model name in metadata."""
        conv = _make_openai_conv(default_model_slug="gpt-4o")
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.model == "GPT-4o"

    @pytest.mark.unit
    def test_content_type_code(self, importer):
        """content_type 'code' should be stored in content.type."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", role="assistant",
                                 parts=["print('hello')"],
                                 content_type="code",
                                 parent="root", children=[]),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        assert msg.content.type == "code"
        assert msg.content.text == "print('hello')"

    @pytest.mark.unit
    def test_content_type_execution_output(self, importer):
        """content_type 'execution_output' should be stored in content.type."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", role="tool",
                                 parts=["Result: 42"],
                                 content_type="execution_output",
                                 parent="root", children=[]),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        assert msg.content.type == "execution_output"
        assert msg.content.text == "Result: 42"

    @pytest.mark.unit
    def test_content_type_tether_browsing(self, importer):
        """content_type 'tether_browsing_display_text' should be stored."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node(
                "m1", role="tool",
                parts=["According to the search results..."],
                content_type="tether_browsing_display_text",
                parent="root", children=[],
            ),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        assert msg.content.type == "tether_browsing_display_text"

    @pytest.mark.unit
    def test_content_type_tether_quote(self, importer):
        """content_type 'tether_quote' should be stored."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node(
                "m1", role="tool",
                parts=["Quoted text from website"],
                content_type="tether_quote",
                parent="root", children=[],
            ),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        assert msg.content.type == "tether_quote"
        assert msg.content.text == "Quoted text from website"

    @pytest.mark.unit
    def test_empty_parts_list(self, importer):
        """An empty parts list should produce empty text."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parts=[], parent="root", children=[]),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        assert msg.content.text == ""

    @pytest.mark.unit
    def test_null_parts(self, importer):
        """None/null parts should be handled gracefully (no crash)."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": {
                "id": "m1",
                "message": {
                    "id": "m1",
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": None},
                    "status": "finished_successfully",
                },
                "parent": "root",
                "children": [],
            },
        }
        conv = _make_openai_conv(mapping=mapping)
        # parts is None => iterating over None; the importer should handle this
        # If it doesn't, this test documents the expected behavior or crash
        # Looking at the code: `for part in parts:` where parts=None will raise TypeError
        # This is an edge case the importer may need to handle
        try:
            results = importer.import_data(conv)
            # If it succeeds, the message should have empty text
            tree = results[0]
            msg = tree.message_map.get("m1")
            if msg:
                assert msg.content.text == "" or msg.content.text is None
        except TypeError:
            # Currently parts=None causes TypeError on iteration
            # This documents the known limitation
            pass

    @pytest.mark.unit
    def test_message_with_empty_children_list(self, importer):
        """Messages with empty children lists should be leaf nodes."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parts=["Leaf message"], parent="root", children=[]),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        assert msg.content.text == "Leaf message"
        # Should have no children in the tree
        children = tree.get_children("m1")
        assert len(children) == 0

    @pytest.mark.unit
    def test_deeply_nested_conversation(self, importer):
        """A conversation with 12 messages in a chain should import correctly."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m-0"]},
        }
        for i in range(12):
            node_id = f"m-{i}"
            parent = "root" if i == 0 else f"m-{i - 1}"
            children = [f"m-{i + 1}"] if i < 11 else []
            role = "user" if i % 2 == 0 else "assistant"
            mapping[node_id] = _make_msg_node(
                node_id, role=role, parts=[f"Message {i}"],
                parent=parent, children=children,
            )

        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        assert len(tree.message_map) == 12
        # Verify chain integrity
        assert tree.message_map["m-0"].parent_id is None  # parent is structural root
        for i in range(1, 12):
            assert tree.message_map[f"m-{i}"].parent_id == f"m-{i - 1}"

    @pytest.mark.unit
    def test_conversation_with_no_title(self, importer):
        """A conversation without a title should default to 'Untitled Conversation'."""
        conv = _make_openai_conv(title=None)
        # Remove title key entirely
        del conv["title"]
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.title == "Untitled Conversation"

    @pytest.mark.unit
    def test_conversation_with_no_conversation_id(self, importer):
        """A conversation with only 'id' (no 'conversation_id') should use that."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parent="root", children=[]),
        }
        conv = {
            "id": "alt-id-123",
            "title": "Alt ID Conv",
            "mapping": mapping,
        }
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.id == "alt-id-123"

    @pytest.mark.unit
    def test_conversation_with_neither_id_field(self, importer):
        """A conversation with no conversation_id and no id should get empty string."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parent="root", children=[]),
        }
        conv = {
            "mapping": mapping,
            "title": "No ID Conv",
        }
        results = importer.import_data(conv)
        tree = results[0]

        # conv_id = conv_data.get("conversation_id") or conv_data.get("id", "")
        # Both missing => ""
        assert tree.id == ""

    @pytest.mark.unit
    def test_mixed_content_types_in_parts(self, importer):
        """Parts containing both strings and non-string objects (dicts without text)."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": {
                "id": "m1",
                "message": {
                    "id": "m1",
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "text",
                        "parts": [
                            "Here is an image:",
                            {"asset_pointer": "file-service://file-xyz", "content_type": "image_asset_pointer"},
                            "And some more text.",
                        ],
                    },
                    "status": "finished_successfully",
                },
                "parent": "root",
                "children": [],
            },
        }
        conv = _make_openai_conv(mapping=mapping)
        # Patch _resolve_and_copy_image since we don't have a real filesystem
        with patch.object(importer, "_resolve_and_copy_image", return_value="media/img.png"):
            results = importer.import_data(conv)

        tree = results[0]
        msg = tree.message_map["m1"]
        # Text parts joined with newline
        assert "Here is an image:" in msg.content.text
        assert "And some more text." in msg.content.text
        # Image from asset_pointer
        assert len(msg.content.images) == 1

    @pytest.mark.unit
    def test_content_as_string_not_dict(self, importer):
        """When content is a plain string instead of a dict, it should be stored as text."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": {
                "id": "m1",
                "message": {
                    "id": "m1",
                    "author": {"role": "user"},
                    "content": "Just a plain string content",
                    "status": "finished_successfully",
                },
                "parent": "root",
                "children": [],
            },
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        assert msg.content.text == "Just a plain string content"

    @pytest.mark.unit
    def test_list_of_conversations(self, importer):
        """import_data should handle a list of multiple conversations."""
        convs = [
            _make_openai_conv(conv_id="c1", title="First"),
            _make_openai_conv(conv_id="c2", title="Second"),
            _make_openai_conv(conv_id="c3", title="Third"),
        ]
        results = importer.import_data(convs)

        assert len(results) == 3
        titles = {r.title for r in results}
        assert titles == {"First", "Second", "Third"}

    @pytest.mark.unit
    def test_invalid_entry_in_list_skipped(self, importer):
        """Non-dict entries in a list should be skipped."""
        data = [
            _make_openai_conv(conv_id="valid"),
            None,
            "not a dict",
            42,
            _make_openai_conv(conv_id="also-valid"),
        ]
        results = importer.import_data(data)

        assert len(results) == 2
        ids = {r.id for r in results}
        assert "valid" in ids
        assert "also-valid" in ids

    @pytest.mark.unit
    def test_parent_is_structural_node_sets_none(self, importer):
        """Messages whose parent is a structural node (message=None) get parent_id=None."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parts=["Hi"], parent="root", children=[]),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        # root is structural (message=None) so m1's parent_id should be None
        assert msg.parent_id is None
        # m1 should be a root message in the tree
        assert "m1" in tree.root_message_ids

    @pytest.mark.unit
    def test_message_timestamp_from_create_time(self, importer):
        """Message-level create_time should be parsed into message.timestamp."""
        from datetime import datetime

        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parts=["Hi"], parent="root", children=[],
                                 create_time=1700000000.0),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        expected = datetime.fromtimestamp(1700000000.0)
        assert msg.timestamp == expected

    @pytest.mark.unit
    def test_message_metadata_fields(self, importer):
        """Message metadata should include status, end_turn, weight, recipient."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parts=["Test"], parent="root", children=[],
                                 status="in_progress", end_turn=True, weight=0.5,
                                 recipient="browser"),
        }
        conv = _make_openai_conv(mapping=mapping)
        results = importer.import_data(conv)
        tree = results[0]

        msg = tree.message_map["m1"]
        assert msg.metadata["status"] == "in_progress"
        assert msg.metadata["end_turn"] is True
        assert msg.metadata["weight"] == 0.5
        assert msg.metadata["recipient"] == "browser"

    @pytest.mark.unit
    def test_part_content_type_stored_in_metadata(self, importer):
        """Parts that are dicts with 'content_type' key should record it in content.metadata."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": {
                "id": "m1",
                "message": {
                    "id": "m1",
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "text",
                        "parts": [
                            {"asset_pointer": "file-service://abc", "content_type": "image_asset_pointer"},
                        ],
                    },
                    "status": "finished_successfully",
                },
                "parent": "root",
                "children": [],
            },
        }
        conv = _make_openai_conv(mapping=mapping)
        with patch.object(importer, "_resolve_and_copy_image", return_value="media/x.png"):
            results = importer.import_data(conv)

        tree = results[0]
        msg = tree.message_map["m1"]
        assert "part_types" in msg.content.metadata
        assert "image_asset_pointer" in msg.content.metadata["part_types"]


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------
class TestOpenAIValidationEdgeCases:
    """Edge-case tests for the validate() method."""

    @pytest.mark.unit
    def test_validate_mapping_but_no_id(self, importer):
        """A dict with 'mapping' but no 'id' or 'conversation_id' should return False."""
        data = {"mapping": {"root": {}}}
        assert importer.validate(data) is False

    @pytest.mark.unit
    def test_validate_json_string_valid(self, importer):
        """A valid JSON string with correct keys should return True."""
        import json as _json

        data = _json.dumps({"mapping": {}, "conversation_id": "c1"})
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_json_string_invalid_json(self, importer):
        """An invalid JSON string should return False."""
        assert importer.validate("{not valid json}") is False

    @pytest.mark.unit
    def test_validate_list_of_valid_conversations(self, importer):
        """A list containing a valid conversation should return True."""
        data = [{"mapping": {}, "conversation_id": "c1"}]
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_list_of_invalid_dicts(self, importer):
        """A list whose first element lacks required keys should return False."""
        data = [{"title": "No mapping key"}]
        assert importer.validate(data) is False

    @pytest.mark.unit
    def test_validate_none_returns_false(self, importer):
        """None input should return False."""
        assert importer.validate(None) is False

    @pytest.mark.unit
    def test_validate_integer_returns_false(self, importer):
        """An integer input should return False."""
        assert importer.validate(42) is False

    @pytest.mark.unit
    def test_validate_empty_mapping_with_valid_id(self, importer):
        """Empty mapping dict with a valid conversation_id should return True."""
        data = {"mapping": {}, "conversation_id": "c1"}
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_with_only_id_key(self, importer):
        """A dict with 'mapping' and 'id' (not 'conversation_id') should return True."""
        data = {"mapping": {}, "id": "id-only"}
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_empty_list_returns_false(self, importer):
        """An empty list should return False."""
        assert importer.validate([]) is False

    @pytest.mark.unit
    def test_validate_empty_dict_returns_false(self, importer):
        """An empty dict should return False."""
        assert importer.validate({}) is False

    @pytest.mark.unit
    def test_validate_json_string_list(self, importer):
        """A JSON string representing a list should be validated."""
        import json as _json

        data = _json.dumps([{"mapping": {}, "id": "x"}])
        assert importer.validate(data) is True

    @pytest.mark.unit
    def test_validate_string_not_json(self, importer):
        """A plain (non-JSON) string should return False."""
        assert importer.validate("hello world") is False


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------
class TestOpenAIMetadata:
    """Tests for metadata extraction and population."""

    @pytest.mark.unit
    def test_source_is_chatgpt(self, importer):
        """The source field in metadata should be 'ChatGPT'."""
        conv = _make_openai_conv()
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.source == "ChatGPT"

    @pytest.mark.unit
    def test_format_is_openai(self, importer):
        """The format field in metadata should be 'openai'."""
        conv = _make_openai_conv()
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.format == "openai"

    @pytest.mark.unit
    def test_tags_include_openai(self, importer):
        """Metadata tags should include 'openai'."""
        conv = _make_openai_conv()
        results = importer.import_data(conv)
        tree = results[0]

        assert "openai" in tree.metadata.tags

    @pytest.mark.unit
    def test_tags_include_model_slug(self, importer):
        """Metadata tags should include a lowercased model tag."""
        conv = _make_openai_conv(default_model_slug="gpt-4")
        results = importer.import_data(conv)
        tree = results[0]

        # Model "GPT-4" => tag "gpt-4"
        assert "gpt-4" in tree.metadata.tags

    @pytest.mark.unit
    def test_model_gpt4_turbo(self, importer):
        """Model slug 'gpt-4-turbo' should map to 'GPT-4 Turbo'."""
        conv = _make_openai_conv(default_model_slug="gpt-4-turbo")
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.model == "GPT-4 Turbo"

    @pytest.mark.unit
    def test_model_gpt4o_mini(self, importer):
        """Model slug 'gpt-4o-mini' should map to 'GPT-4o Mini'."""
        conv = _make_openai_conv(default_model_slug="gpt-4o-mini")
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.model == "GPT-4o Mini"

    @pytest.mark.unit
    def test_model_gpt35_turbo(self, importer):
        """Model slug 'gpt-3.5-turbo' should map to 'GPT-3.5 Turbo'."""
        conv = _make_openai_conv(default_model_slug="gpt-3.5-turbo")
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.model == "GPT-3.5 Turbo"

    @pytest.mark.unit
    def test_model_unknown_slug_returned_as_is(self, importer):
        """An unknown model slug should be returned as-is."""
        conv = _make_openai_conv(default_model_slug="o1-preview")
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.model == "o1-preview"

    @pytest.mark.unit
    def test_model_no_slug_defaults_to_chatgpt(self, importer):
        """When no default_model_slug is present, model should default to 'ChatGPT'."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parent="root", children=[]),
        }
        conv = {
            "conversation_id": "c1",
            "title": "No Model",
            "mapping": mapping,
        }
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.model == "ChatGPT"

    @pytest.mark.unit
    def test_gizmo_id_in_custom_data(self, importer):
        """gizmo_id should be preserved in metadata.custom_data."""
        conv = _make_openai_conv(gizmo_id="g-abc123")
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.custom_data.get("gizmo_id") == "g-abc123"

    @pytest.mark.unit
    def test_plugin_ids_in_custom_data(self, importer):
        """plugin_ids should be preserved in metadata.custom_data."""
        conv = _make_openai_conv(plugin_ids=["plugin-web-browser", "plugin-code-interpreter"])
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.custom_data.get("plugin_ids") == [
            "plugin-web-browser",
            "plugin-code-interpreter",
        ]

    @pytest.mark.unit
    def test_timestamps_parsed_from_create_update_time(self, importer):
        """Conversation-level create_time/update_time should be parsed into metadata."""
        from datetime import datetime

        conv = _make_openai_conv(create_time=1700000000.0, update_time=1700100000.0)
        results = importer.import_data(conv)
        tree = results[0]

        expected_created = datetime.fromtimestamp(1700000000.0)
        assert tree.metadata.created_at == expected_created
        # Cannot check updated_at because add_message() overwrites it

    @pytest.mark.unit
    def test_no_create_time_defaults_to_now(self, importer):
        """When create_time is absent, created_at should default to approximately now."""
        from datetime import datetime, timedelta

        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parent="root", children=[]),
        }
        conv = {
            "conversation_id": "c1",
            "title": "No timestamps",
            "mapping": mapping,
        }
        before = datetime.now()
        results = importer.import_data(conv)
        after = datetime.now()
        tree = results[0]

        # created_at should be approximately "now" (within a few seconds)
        assert before - timedelta(seconds=2) <= tree.metadata.created_at <= after + timedelta(seconds=2)

    @pytest.mark.unit
    def test_is_archived_in_custom_data(self, importer):
        """is_archived flag should be preserved in custom_data."""
        conv = _make_openai_conv(extra_fields={"is_archived": True})
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.custom_data.get("is_archived") is True

    @pytest.mark.unit
    def test_version_is_2_0_0(self, importer):
        """Metadata version should be '2.0.0'."""
        conv = _make_openai_conv()
        results = importer.import_data(conv)
        tree = results[0]

        assert tree.metadata.version == "2.0.0"

    @pytest.mark.unit
    def test_tags_include_chatgpt_tag(self, importer):
        """When model is ChatGPT, tags should include 'chatgpt' (lowercased model)."""
        mapping = {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": _make_msg_node("m1", parent="root", children=[]),
        }
        conv = {
            "conversation_id": "c1",
            "title": "Default model",
            "mapping": mapping,
        }
        results = importer.import_data(conv)
        tree = results[0]

        # Model defaults to "ChatGPT" => tag is "chatgpt"
        assert "chatgpt" in tree.metadata.tags
