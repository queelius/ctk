"""
Tests for OpenAI LLM provider.
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from ctk.integrations.llm.base import (AuthenticationError, ChatResponse,
                                       ContextLengthError, LLMProviderError,
                                       Message, MessageRole,
                                       ModelNotFoundError, RateLimitError)
from ctk.integrations.llm.openai import OpenAIProvider


class TestOpenAIProviderInit:
    """Test OpenAI provider initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        provider = OpenAIProvider({"api_key": "test-key"})

        assert provider.api_key == "test-key"
        assert provider.base_url == "https://api.openai.com"
        assert provider.model == "gpt-3.5-turbo"
        assert provider.timeout == 120

    def test_init_with_custom_values(self):
        """Test initialization with custom configuration."""
        provider = OpenAIProvider(
            {
                "api_key": "custom-key",
                "base_url": "https://custom.api.com",
                "model": "gpt-4",
                "timeout": 60,
                "organization": "org-123",
            }
        )

        assert provider.api_key == "custom-key"
        assert provider.base_url == "https://custom.api.com"
        assert provider.model == "gpt-4"
        assert provider.timeout == 60
        assert provider.organization == "org-123"

    def test_base_url_trailing_slash_stripped(self):
        """Test that trailing slash is stripped from base URL."""
        provider = OpenAIProvider(
            {
                "api_key": "key",
                "base_url": "https://api.example.com/",
            }
        )

        assert provider.base_url == "https://api.example.com"


class TestOpenAIProviderHeaders:
    """Test header generation."""

    def test_get_headers_basic(self):
        """Test basic headers without organization."""
        provider = OpenAIProvider({"api_key": "sk-test123"})
        headers = provider._get_headers()

        assert headers["Authorization"] == "Bearer sk-test123"
        assert headers["Content-Type"] == "application/json"
        assert "OpenAI-Organization" not in headers

    def test_get_headers_with_organization(self):
        """Test headers with organization."""
        provider = OpenAIProvider(
            {
                "api_key": "sk-test123",
                "organization": "org-xyz",
            }
        )
        headers = provider._get_headers()

        assert headers["OpenAI-Organization"] == "org-xyz"


class TestOpenAIProviderChat:
    """Test chat functionality."""

    @pytest.fixture
    def provider(self):
        """Create a provider instance."""
        return OpenAIProvider({"api_key": "test-key", "model": "gpt-4"})

    @pytest.fixture
    def mock_response_success(self):
        """Create a successful mock response."""
        return {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1677858242,
            "model": "gpt-4",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello! How can I help you?",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        }

    def test_chat_success(self, provider, mock_response_success):
        """Test successful chat completion."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = mock_response_success

            messages = [Message(role=MessageRole.USER, content="Hello")]
            response = provider.chat(messages)

            assert isinstance(response, ChatResponse)
            assert response.content == "Hello! How can I help you?"
            assert response.model == "gpt-4"
            assert response.finish_reason == "stop"
            assert response.usage["total_tokens"] == 30

    def test_chat_requires_api_key(self):
        """Test that chat raises error without API key."""
        provider = OpenAIProvider({"model": "gpt-4"})

        with pytest.raises(AuthenticationError):
            provider.chat([Message(role=MessageRole.USER, content="Hello")])

    def test_chat_with_tools(self, provider, mock_response_success):
        """Test chat with tool definitions."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = mock_response_success

            messages = [Message(role=MessageRole.USER, content="Search for cats")]
            tools = [
                {
                    "name": "search",
                    "description": "Search the web",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ]

            provider.chat(messages, tools=tools)

            # Verify tools were passed to API
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "tools" in payload
            assert payload["tools"][0]["function"]["name"] == "search"

    def test_chat_extracts_tool_calls(self, provider):
        """Test extraction of tool calls from response."""
        response_with_tools = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "search",
                                    "arguments": '{"query": "cats"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "model": "gpt-4",
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = response_with_tools

            messages = [Message(role=MessageRole.USER, content="Search")]
            response = provider.chat(messages)

            assert response.tool_calls is not None
            assert len(response.tool_calls) == 1
            assert response.tool_calls[0]["name"] == "search"
            assert response.tool_calls[0]["arguments"] == {"query": "cats"}


class TestOpenAIProviderErrorHandling:
    """Test error handling."""

    @pytest.fixture
    def provider(self):
        return OpenAIProvider({"api_key": "test-key", "model": "gpt-4"})

    def test_authentication_error(self, provider):
        """Test handling of 401 authentication errors."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.status_code = 401
            mock_post.return_value.json.return_value = {
                "error": {"message": "Invalid API key"}
            }

            with pytest.raises(AuthenticationError) as exc_info:
                provider.chat([Message(role=MessageRole.USER, content="Hi")])

            assert "Invalid API key" in str(exc_info.value)

    def test_rate_limit_error(self, provider):
        """Test handling of 429 rate limit errors."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.status_code = 429
            mock_post.return_value.json.return_value = {
                "error": {"message": "Rate limit exceeded"}
            }

            with pytest.raises(RateLimitError):
                provider.chat([Message(role=MessageRole.USER, content="Hi")])

    def test_model_not_found_error(self, provider):
        """Test handling of 404 model not found errors."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.status_code = 404
            mock_post.return_value.json.return_value = {
                "error": {"message": "Model not found"}
            }

            with pytest.raises(ModelNotFoundError):
                provider.chat([Message(role=MessageRole.USER, content="Hi")])

    def test_context_length_error(self, provider):
        """Test handling of context length errors."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.status_code = 400
            mock_post.return_value.json.return_value = {
                "error": {
                    "message": "This model's maximum context length is exceeded",
                    "type": "context_length_exceeded",
                }
            }

            with pytest.raises(ContextLengthError):
                provider.chat([Message(role=MessageRole.USER, content="Hi")])

    def test_connection_error(self, provider):
        """Test handling of connection errors."""
        with patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("Connection failed")

            with pytest.raises(LLMProviderError) as exc_info:
                provider.chat([Message(role=MessageRole.USER, content="Hi")])

            assert "Unexpected error" in str(exc_info.value)


class TestOpenAIProviderStreamChat:
    """Test streaming chat functionality."""

    @pytest.fixture
    def provider(self):
        return OpenAIProvider({"api_key": "test-key", "model": "gpt-4"})

    def test_stream_chat_yields_chunks(self, provider):
        """Test that stream_chat yields content chunks."""
        sse_data = [
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            b'data: {"choices":[{"delta":{"content":" world"}}]}',
            b"data: [DONE]",
        ]

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.iter_lines.return_value = iter(sse_data)
            mock_post.return_value = mock_response

            messages = [Message(role=MessageRole.USER, content="Hi")]
            chunks = list(provider.stream_chat(messages))

            assert chunks == ["Hello", " world"]


class TestOpenAIProviderGetModels:
    """Test model listing functionality."""

    @pytest.fixture
    def provider(self):
        return OpenAIProvider({"api_key": "test-key"})

    def test_get_models_filters_chat_models(self, provider):
        """Test that get_models filters to chat models."""
        mock_response = {
            "data": [
                {"id": "gpt-4", "created": 1234, "owned_by": "openai"},
                {"id": "gpt-3.5-turbo", "created": 1234, "owned_by": "openai"},
                {
                    "id": "davinci-002",
                    "created": 1234,
                    "owned_by": "openai",
                },  # Not a chat model
                {
                    "id": "whisper-1",
                    "created": 1234,
                    "owned_by": "openai",
                },  # Audio model
            ]
        }

        with patch("requests.get") as mock_get:
            mock_get.return_value.ok = True
            mock_get.return_value.json.return_value = mock_response

            models = provider.get_models()

            model_ids = [m.id for m in models]
            assert "gpt-4" in model_ids
            assert "gpt-3.5-turbo" in model_ids
            assert "davinci-002" not in model_ids
            assert "whisper-1" not in model_ids

    def test_get_models_estimates_context_window(self, provider):
        """Test context window estimation based on model name."""
        mock_response = {
            "data": [
                {"id": "gpt-4-turbo", "created": 1234, "owned_by": "openai"},
                {"id": "gpt-4-32k", "created": 1234, "owned_by": "openai"},
                {"id": "gpt-3.5-turbo-16k", "created": 1234, "owned_by": "openai"},
            ]
        }

        with patch("requests.get") as mock_get:
            mock_get.return_value.ok = True
            mock_get.return_value.json.return_value = mock_response

            models = provider.get_models()

            model_map = {m.id: m for m in models}

            assert model_map["gpt-4-turbo"].context_window == 128000
            assert model_map["gpt-4-32k"].context_window == 32000
            assert model_map["gpt-3.5-turbo-16k"].context_window == 16000


class TestOpenAIProviderToolFormatting:
    """Test tool formatting for API."""

    def test_format_tools_for_api(self):
        """Test conversion of generic tools to OpenAI format."""
        provider = OpenAIProvider({"api_key": "key"})

        tools = [
            {
                "name": "get_weather",
                "description": "Get weather for a location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                    },
                    "required": ["location"],
                },
            }
        ]

        formatted = provider.format_tools_for_api(tools)

        assert len(formatted) == 1
        assert formatted[0]["type"] == "function"
        assert formatted[0]["function"]["name"] == "get_weather"
        assert formatted[0]["function"]["description"] == "Get weather for a location"
        assert formatted[0]["function"]["parameters"]["type"] == "object"

    def test_format_tool_result_message(self):
        """Test formatting of tool result as message."""
        provider = OpenAIProvider({"api_key": "key"})

        result = {"temperature": 72, "conditions": "sunny"}
        msg = provider.format_tool_result_message(
            "get_weather",
            result,
            tool_call_id="call_123",
        )

        assert msg.role == MessageRole.TOOL
        assert json.loads(msg.content) == result
        assert msg.metadata["tool_call_id"] == "call_123"


class TestOpenAIProviderAvailability:
    """Test availability checking."""

    def test_is_available_true(self):
        """Test is_available returns True when API is accessible."""
        provider = OpenAIProvider({"api_key": "key"})

        with patch("requests.get") as mock_get:
            mock_get.return_value.ok = True

            assert provider.is_available() is True

    def test_is_available_false_no_key(self):
        """Test is_available returns False without API key."""
        provider = OpenAIProvider({"model": "gpt-4"})

        assert provider.is_available() is False

    def test_is_available_false_on_error(self):
        """Test is_available returns False on connection error."""
        provider = OpenAIProvider({"api_key": "key"})

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError(
                "Connection failed"
            )

            assert provider.is_available() is False

    def test_supports_tool_calling(self):
        """Test that OpenAI provider supports tool calling."""
        provider = OpenAIProvider({"api_key": "key"})

        assert provider.supports_tool_calling() is True
