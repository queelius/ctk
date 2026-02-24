"""
Tests for Anthropic LLM provider.
"""

import json
from unittest.mock import Mock, patch

import pytest

from ctk.integrations.llm.anthropic import AnthropicProvider
from ctk.integrations.llm.base import (AuthenticationError, ChatResponse,
                                       ContextLengthError, LLMProviderError,
                                       Message, MessageRole,
                                       ModelNotFoundError, RateLimitError)


class TestAnthropicProviderInit:
    """Test Anthropic provider initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        provider = AnthropicProvider({"api_key": "test-key"})

        assert provider.api_key == "test-key"
        assert provider.base_url == "https://api.anthropic.com"
        assert provider.model == "claude-3-haiku-20240307"
        assert provider.timeout == 120
        assert provider.default_max_tokens == 4096

    def test_init_with_custom_values(self):
        """Test initialization with custom configuration."""
        provider = AnthropicProvider(
            {
                "api_key": "custom-key",
                "base_url": "https://custom.api.com",
                "model": "claude-3-opus-20240229",
                "timeout": 60,
                "max_tokens": 8192,
            }
        )

        assert provider.api_key == "custom-key"
        assert provider.base_url == "https://custom.api.com"
        assert provider.model == "claude-3-opus-20240229"
        assert provider.timeout == 60
        assert provider.default_max_tokens == 8192


class TestAnthropicProviderHeaders:
    """Test header generation."""

    def test_get_headers(self):
        """Test header generation."""
        provider = AnthropicProvider({"api_key": "sk-ant-test123"})
        headers = provider._get_headers()

        assert headers["x-api-key"] == "sk-ant-test123"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["Content-Type"] == "application/json"


class TestAnthropicProviderChat:
    """Test chat functionality."""

    @pytest.fixture
    def provider(self):
        """Create a provider instance."""
        return AnthropicProvider(
            {"api_key": "test-key", "model": "claude-3-haiku-20240307"}
        )

    @pytest.fixture
    def mock_response_success(self):
        """Create a successful mock response."""
        return {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello! How can I help you?"}],
            "model": "claude-3-haiku-20240307",
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 20,
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
            assert response.model == "claude-3-haiku-20240307"
            assert response.finish_reason == "end_turn"
            assert response.usage["total_tokens"] == 30

    def test_chat_requires_api_key(self):
        """Test that chat raises error without API key."""
        provider = AnthropicProvider({"model": "claude-3-haiku-20240307"})

        with pytest.raises(AuthenticationError):
            provider.chat([Message(role=MessageRole.USER, content="Hello")])

    def test_chat_separates_system_message(self, provider, mock_response_success):
        """Test that system messages are separated from chat messages."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = mock_response_success

            messages = [
                Message(role=MessageRole.SYSTEM, content="You are helpful"),
                Message(role=MessageRole.USER, content="Hello"),
            ]

            provider.chat(messages)

            # Verify system message is passed separately
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["system"] == "You are helpful"
            # Chat messages should not include system
            assert len(payload["messages"]) == 1
            assert payload["messages"][0]["role"] == "user"

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
            assert payload["tools"][0]["name"] == "search"

    def test_chat_extracts_tool_use(self, provider):
        """Test extraction of tool_use blocks from response."""
        response_with_tools = {
            "content": [
                {"type": "text", "text": "Let me search for that."},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "search",
                    "input": {"query": "cats"},
                },
            ],
            "model": "claude-3-haiku-20240307",
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 20},
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
            assert response.tool_calls[0]["id"] == "toolu_123"

    def test_chat_temperature_capped_at_1(self, provider, mock_response_success):
        """Test that temperature is capped at 1.0 for Anthropic."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.json.return_value = mock_response_success

            messages = [Message(role=MessageRole.USER, content="Hi")]
            provider.chat(messages, temperature=2.0)

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["temperature"] == 1.0


class TestAnthropicProviderErrorHandling:
    """Test error handling."""

    @pytest.fixture
    def provider(self):
        return AnthropicProvider(
            {"api_key": "test-key", "model": "claude-3-haiku-20240307"}
        )

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


class TestAnthropicProviderStreamChat:
    """Test streaming chat functionality."""

    @pytest.fixture
    def provider(self):
        return AnthropicProvider(
            {"api_key": "test-key", "model": "claude-3-haiku-20240307"}
        )

    def test_stream_chat_yields_chunks(self, provider):
        """Test that stream_chat yields content chunks."""
        sse_data = [
            b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}',
            b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}',
            b'data: {"type":"message_stop"}',
        ]

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.iter_lines.return_value = iter(sse_data)
            mock_post.return_value = mock_response

            messages = [Message(role=MessageRole.USER, content="Hi")]
            chunks = list(provider.stream_chat(messages))

            assert chunks == ["Hello", " world"]


class TestAnthropicProviderGetModels:
    """Test model listing functionality."""

    def test_get_models_returns_known_models(self):
        """Test that get_models returns known Claude models."""
        provider = AnthropicProvider({"api_key": "test-key"})

        models = provider.get_models()

        # Should have several known models
        assert len(models) > 0

        model_ids = [m.id for m in models]
        assert "claude-3-haiku-20240307" in model_ids
        assert "claude-3-sonnet-20240229" in model_ids
        assert "claude-3-opus-20240229" in model_ids

    def test_get_models_context_windows(self):
        """Test that models have correct context windows."""
        provider = AnthropicProvider({"api_key": "test-key"})

        models = provider.get_models()

        for model in models:
            # All Claude 3 models have 200k context
            assert model.context_window == 200000

    def test_get_models_tool_support(self):
        """Test that models have tool support marked correctly."""
        provider = AnthropicProvider({"api_key": "test-key"})

        models = provider.get_models()

        for model in models:
            # All Claude 3 models support tools
            assert model.supports_tools is True


class TestAnthropicProviderToolFormatting:
    """Test tool formatting for API."""

    def test_format_tools_for_api(self):
        """Test conversion of generic tools to Anthropic format."""
        provider = AnthropicProvider({"api_key": "key"})

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
        # Anthropic format is different from OpenAI
        assert formatted[0]["name"] == "get_weather"
        assert formatted[0]["description"] == "Get weather for a location"
        assert formatted[0]["input_schema"]["type"] == "object"

    def test_format_tool_result_message(self):
        """Test formatting of tool result as message."""
        provider = AnthropicProvider({"api_key": "key"})

        result = {"temperature": 72, "conditions": "sunny"}
        msg = provider.format_tool_result_message(
            "get_weather",
            result,
            tool_call_id="toolu_123",
        )

        assert msg.role == MessageRole.USER  # Anthropic uses user role for tool results
        assert json.loads(msg.content) == result
        assert msg.metadata["tool_use_id"] == "toolu_123"


class TestAnthropicProviderAvailability:
    """Test availability checking."""

    def test_is_available_true_with_key(self):
        """Test is_available returns True when API key is set."""
        provider = AnthropicProvider({"api_key": "key"})

        assert provider.is_available() is True

    def test_is_available_false_no_key(self):
        """Test is_available returns False without API key."""
        provider = AnthropicProvider({"model": "claude-3-haiku-20240307"})

        assert provider.is_available() is False

    def test_supports_tool_calling(self):
        """Test that Anthropic provider supports tool calling."""
        provider = AnthropicProvider({"api_key": "key"})

        assert provider.supports_tool_calling() is True


class TestAnthropicProviderMessageFormatting:
    """Test message formatting for API."""

    def test_format_message_user(self):
        """Test formatting of user message."""
        provider = AnthropicProvider({"api_key": "key"})

        msg = Message(role=MessageRole.USER, content="Hello")
        formatted = provider._format_message(msg)

        assert formatted["role"] == "user"
        assert formatted["content"] == "Hello"

    def test_format_message_assistant(self):
        """Test formatting of assistant message."""
        provider = AnthropicProvider({"api_key": "key"})

        msg = Message(role=MessageRole.ASSISTANT, content="Hi there")
        formatted = provider._format_message(msg)

        assert formatted["role"] == "assistant"
        assert formatted["content"] == "Hi there"

    def test_format_message_tool_becomes_user(self):
        """Test that tool messages become user messages for Anthropic."""
        provider = AnthropicProvider({"api_key": "key"})

        msg = Message(role=MessageRole.TOOL, content="tool result")
        formatted = provider._format_message(msg)

        # Anthropic expects tool results as user messages
        assert formatted["role"] == "user"
