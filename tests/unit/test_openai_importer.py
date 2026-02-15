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

from ctk.core.models import MessageContent, ToolCall
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
