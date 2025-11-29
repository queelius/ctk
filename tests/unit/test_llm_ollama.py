"""
Comprehensive tests for Ollama LLM provider.

Tests focus on behavior, not implementation:
- Message handling and API formatting
- Error handling (connection, timeout, HTTP errors)
- Tool calling support
- Model listing and info retrieval
- Streaming functionality
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

from ctk.integrations.llm.ollama import OllamaProvider
from ctk.integrations.llm.base import (
    Message,
    MessageRole,
    ChatResponse,
    ModelInfo,
    LLMProviderError,
    ModelNotFoundError,
)


# ==================== Fixtures ====================

@pytest.fixture
def ollama_config() -> Dict[str, Any]:
    """Standard Ollama configuration for testing."""
    return {
        'model': 'llama3.1',
        'base_url': 'http://localhost:11434',
        'timeout': 120
    }


@pytest.fixture
def ollama_provider(ollama_config: Dict[str, Any]) -> OllamaProvider:
    """Ollama provider instance for testing."""
    return OllamaProvider(ollama_config)


@pytest.fixture
def sample_messages() -> List[Message]:
    """Sample messages for testing."""
    return [
        Message(role=MessageRole.SYSTEM, content="You are helpful"),
        Message(role=MessageRole.USER, content="Hello")
    ]


@pytest.fixture
def mock_ollama_chat_response() -> Dict[str, Any]:
    """Mock Ollama API response for chat."""
    return {
        'model': 'llama3.1',
        'message': {
            'role': 'assistant',
            'content': 'Hello! How can I help you today?'
        },
        'done': True,
        'done_reason': 'stop',
        'prompt_eval_count': 15,
        'eval_count': 10
    }


@pytest.fixture
def mock_ollama_models_response() -> Dict[str, Any]:
    """Mock Ollama API response for listing models."""
    return {
        'models': [
            {
                'name': 'llama3.1',
                'size': 4661224224,
                'modified_at': '2024-01-15T12:00:00Z',
                'digest': 'abc123'
            },
            {
                'name': 'mistral',
                'size': 3825819519,
                'modified_at': '2024-01-14T10:00:00Z',
                'digest': 'def456'
            }
        ]
    }


# ==================== Initialization Tests ====================

class TestOllamaProviderInitialization:
    """Test provider initialization and configuration."""

    def test_initialization_with_default_config(self):
        """Given minimal config, provider should use sensible defaults."""
        provider = OllamaProvider({'model': 'llama3.1'})

        assert provider.model == 'llama3.1'
        assert provider.base_url == 'http://localhost:11434'
        assert provider.timeout == 120

    def test_initialization_with_custom_base_url(self):
        """Given custom base_url, provider should use it."""
        provider = OllamaProvider({
            'model': 'mistral',
            'base_url': 'http://custom-host:8080'
        })

        assert provider.base_url == 'http://custom-host:8080'

    def test_initialization_strips_trailing_slash_from_url(self):
        """Given base_url with trailing slash, it should be stripped."""
        provider = OllamaProvider({
            'model': 'llama3.1',
            'base_url': 'http://localhost:11434/'
        })

        assert provider.base_url == 'http://localhost:11434'

    def test_initialization_without_model_raises_error(self):
        """Given config without model, should raise ValueError."""
        with pytest.raises(ValueError, match="Model name is required"):
            OllamaProvider({})

    def test_initialization_with_custom_timeout(self):
        """Given custom timeout, provider should use it."""
        provider = OllamaProvider({
            'model': 'llama3.1',
            'timeout': 60
        })

        assert provider.timeout == 60


# ==================== Chat Tests ====================

class TestOllamaChat:
    """Test chat method behavior."""

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_chat_success(self, mock_post, ollama_provider, sample_messages, mock_ollama_chat_response):
        """Given valid messages, chat should return ChatResponse with content."""
        # Given: Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = mock_ollama_chat_response
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # When: Calling chat
        response = ollama_provider.chat(sample_messages)

        # Then: Should return proper ChatResponse
        assert isinstance(response, ChatResponse)
        assert response.content == 'Hello! How can I help you today?'
        assert response.model == 'llama3.1'
        assert response.finish_reason == 'stop'
        assert response.usage['prompt_tokens'] == 15
        assert response.usage['completion_tokens'] == 10
        assert response.usage['total_tokens'] == 25

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_chat_sends_correct_payload(self, mock_post, ollama_provider, sample_messages):
        """Given messages, chat should send correct API payload."""
        # Given: Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            'model': 'llama3.1',
            'message': {'role': 'assistant', 'content': 'test'}
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # When: Calling chat
        ollama_provider.chat(sample_messages, temperature=0.5, max_tokens=100)

        # Then: Should call API with correct payload
        call_args = mock_post.call_args
        assert call_args[0][0] == 'http://localhost:11434/api/chat'
        payload = call_args[1]['json']
        assert payload['model'] == 'llama3.1'
        assert payload['stream'] is False
        assert payload['options']['temperature'] == 0.5
        assert payload['options']['num_predict'] == 100
        assert len(payload['messages']) == 2

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_chat_with_tools(self, mock_post, ollama_provider, sample_messages):
        """Given tools in kwargs, chat should include them in payload."""
        # Given: Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            'model': 'llama3.1',
            'message': {'role': 'assistant', 'content': 'test'}
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        tools = [{'name': 'search', 'description': 'Search tool'}]

        # When: Calling chat with tools
        ollama_provider.chat(sample_messages, tools=tools)

        # Then: Payload should include tools
        payload = mock_post.call_args[1]['json']
        assert 'tools' in payload
        assert payload['tools'] == tools

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_chat_with_tool_calls_in_response(self, mock_post, ollama_provider, sample_messages):
        """Given response with tool_calls, should include them in ChatResponse."""
        # Given: Mock response with tool calls
        mock_response = Mock()
        mock_response.json.return_value = {
            'model': 'llama3.1',
            'message': {
                'role': 'assistant',
                'content': '',
                'tool_calls': [
                    {
                        'function': {
                            'name': 'search',
                            'arguments': {'query': 'test'}
                        }
                    }
                ]
            }
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # When: Calling chat
        response = ollama_provider.chat(sample_messages)

        # Then: Should include tool calls
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_chat_connection_error(self, mock_post, ollama_provider, sample_messages):
        """Given connection error, should raise LLMProviderError with helpful message."""
        # Given: Mock connection error
        mock_post.side_effect = Exception("Connection refused")

        # Mock to raise ConnectionError instead
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        # When/Then: Should raise with helpful message
        with pytest.raises(LLMProviderError, match="Cannot connect to Ollama"):
            ollama_provider.chat(sample_messages)

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_chat_timeout_error(self, mock_post, ollama_provider, sample_messages):
        """Given timeout, should raise LLMProviderError."""
        # Given: Mock timeout
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        # When/Then: Should raise timeout error
        with pytest.raises(LLMProviderError, match="timed out"):
            ollama_provider.chat(sample_messages)

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_chat_model_not_found(self, mock_post, ollama_provider, sample_messages):
        """Given 404 error, should raise ModelNotFoundError."""
        # Given: Mock 404 error
        import requests
        mock_response = Mock()
        mock_response.status_code = 404
        error = requests.exceptions.HTTPError()
        error.response = mock_response
        mock_post.return_value = mock_response
        mock_response.raise_for_status.side_effect = error

        # When/Then: Should raise ModelNotFoundError
        with pytest.raises(ModelNotFoundError, match="not found"):
            ollama_provider.chat(sample_messages)

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_chat_http_error(self, mock_post, ollama_provider, sample_messages):
        """Given HTTP error (non-404), should raise LLMProviderError."""
        # Given: Mock 500 error
        import requests
        mock_response = Mock()
        mock_response.status_code = 500
        error = requests.exceptions.HTTPError()
        error.response = mock_response
        mock_post.return_value = mock_response
        mock_response.raise_for_status.side_effect = error

        # When/Then: Should raise LLMProviderError
        with pytest.raises(LLMProviderError, match="Ollama API error"):
            ollama_provider.chat(sample_messages)

    def test_chat_empty_messages_raises_error(self, ollama_provider):
        """Given empty message list, should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ollama_provider.chat([])


# ==================== Stream Chat Tests ====================

class TestOllamaStreamChat:
    """Test streaming chat functionality."""

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_stream_chat_yields_chunks(self, mock_post, ollama_provider, sample_messages):
        """Given streaming response, should yield content chunks."""
        # Given: Mock streaming response
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            json.dumps({'message': {'content': 'Hello'}, 'done': False}).encode(),
            json.dumps({'message': {'content': ' there'}, 'done': False}).encode(),
            json.dumps({'message': {'content': '!'}, 'done': True}).encode(),
        ]
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # When: Streaming chat
        chunks = list(ollama_provider.stream_chat(sample_messages))

        # Then: Should yield all content chunks
        assert chunks == ['Hello', ' there', '!']

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_stream_chat_sends_stream_true(self, mock_post, ollama_provider, sample_messages):
        """Given stream_chat call, should set stream=True in payload."""
        # Given: Mock response
        mock_response = Mock()
        mock_response.iter_lines.return_value = []
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # When: Calling stream_chat
        list(ollama_provider.stream_chat(sample_messages))

        # Then: Should have stream=True
        payload = mock_post.call_args[1]['json']
        assert payload['stream'] is True

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_stream_chat_handles_empty_lines(self, mock_post, ollama_provider, sample_messages):
        """Given response with empty lines, should skip them."""
        # Given: Mock response with empty lines
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            b'',  # Empty line
            json.dumps({'message': {'content': 'Hello'}, 'done': False}).encode(),
            b'',  # Another empty line
            json.dumps({'message': {'content': '!'}, 'done': True}).encode(),
        ]
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # When: Streaming
        chunks = list(ollama_provider.stream_chat(sample_messages))

        # Then: Should only yield non-empty content
        assert chunks == ['Hello', '!']

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_stream_chat_connection_error(self, mock_post, ollama_provider, sample_messages):
        """Given connection error during streaming, should raise LLMProviderError."""
        # Given: Mock connection error
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        # When/Then: Should raise connection error
        with pytest.raises(LLMProviderError, match="Cannot connect"):
            list(ollama_provider.stream_chat(sample_messages))

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_stream_chat_timeout_error(self, mock_post, ollama_provider, sample_messages):
        """Given timeout during streaming, should raise LLMProviderError."""
        # Given: Mock timeout
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        # When/Then: Should raise timeout error
        with pytest.raises(LLMProviderError, match="timed out"):
            list(ollama_provider.stream_chat(sample_messages))


# ==================== Model Listing Tests ====================

class TestOllamaGetModels:
    """Test model listing functionality."""

    @patch('ctk.integrations.llm.ollama.requests.get')
    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_get_models_success(self, mock_post, mock_get, ollama_provider, mock_ollama_models_response):
        """Given available models, should return list of ModelInfo."""
        # Given: Mock models response
        mock_response = Mock()
        mock_response.json.return_value = mock_ollama_models_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock show endpoint to skip context window lookup
        mock_post.return_value.ok = False

        # When: Getting models
        models = ollama_provider.get_models()

        # Then: Should return ModelInfo objects
        assert len(models) == 2
        assert all(isinstance(m, ModelInfo) for m in models)
        assert models[0].id == 'llama3.1'
        assert models[0].name == 'llama3.1'
        assert models[0].supports_streaming is True
        assert models[0].metadata['size'] == 4661224224

    @patch('ctk.integrations.llm.ollama.requests.get')
    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_get_models_with_context_window(self, mock_post, mock_get, ollama_provider):
        """Given model with context info, should extract context_window."""
        # Given: Mock with context window info
        mock_get_response = Mock()
        mock_get_response.json.return_value = {
            'models': [{'name': 'llama3.1', 'size': 100}]
        }
        mock_get_response.raise_for_status = Mock()
        mock_get.return_value = mock_get_response

        mock_post_response = Mock()
        mock_post_response.ok = True
        mock_post_response.json.return_value = {
            'model_info': {
                'llama.context_length': 4096
            }
        }
        mock_post.return_value = mock_post_response

        # When: Getting models
        models = ollama_provider.get_models()

        # Then: Should have context window
        assert models[0].context_window == 4096

    @patch('ctk.integrations.llm.ollama.requests.get')
    def test_get_models_connection_error(self, mock_get, ollama_provider):
        """Given connection error, should raise LLMProviderError."""
        # Given: Mock connection error
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        # When/Then: Should raise error
        with pytest.raises(LLMProviderError, match="Cannot connect"):
            ollama_provider.get_models()

    @patch('ctk.integrations.llm.ollama.requests.get')
    def test_get_models_handles_exceptions(self, mock_get, ollama_provider):
        """Given unexpected error, should raise LLMProviderError."""
        # Given: Mock unexpected error
        mock_get.side_effect = Exception("Unexpected")

        # When/Then: Should wrap in LLMProviderError
        with pytest.raises(LLMProviderError, match="Failed to list models"):
            ollama_provider.get_models()


# ==================== Model Info Tests ====================

class TestOllamaGetModelInfo:
    """Test detailed model info retrieval."""

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_get_model_info_success(self, mock_post, ollama_provider):
        """Given valid model name, should return model info dict."""
        # Given: Mock model info response
        mock_response = Mock()
        mock_response.json.return_value = {
            'modelfile': 'FROM llama3.1',
            'parameters': 'temperature 0.7',
            'template': '...'
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # When: Getting model info
        info = ollama_provider.get_model_info('llama3.1')

        # Then: Should return dict
        assert isinstance(info, dict)
        assert 'modelfile' in info

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_get_model_info_not_found(self, mock_post, ollama_provider):
        """Given non-existent model, should return None."""
        # Given: Mock 404 response
        import requests
        mock_response = Mock()
        mock_response.status_code = 404
        error = requests.exceptions.HTTPError()
        error.response = mock_response
        mock_post.return_value = mock_response
        mock_response.raise_for_status.side_effect = error

        # When: Getting info for non-existent model
        info = ollama_provider.get_model_info('nonexistent')

        # Then: Should return None
        assert info is None

    @patch('ctk.integrations.llm.ollama.requests.post')
    def test_get_model_info_connection_error(self, mock_post, ollama_provider):
        """Given connection error, should raise LLMProviderError."""
        # Given: Mock connection error
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError()

        # When/Then: Should raise error
        with pytest.raises(LLMProviderError, match="Cannot connect"):
            ollama_provider.get_model_info('llama3.1')


# ==================== Availability Check Tests ====================

class TestOllamaIsAvailable:
    """Test Ollama availability check."""

    @patch('ctk.integrations.llm.ollama.requests.get')
    def test_is_available_when_running(self, mock_get, ollama_provider):
        """Given Ollama is running, should return True."""
        # Given: Mock successful response
        mock_response = Mock()
        mock_response.ok = True
        mock_get.return_value = mock_response

        # When: Checking availability
        available = ollama_provider.is_available()

        # Then: Should return True
        assert available is True

    @patch('ctk.integrations.llm.ollama.requests.get')
    def test_is_available_when_not_running(self, mock_get, ollama_provider):
        """Given Ollama is not running, should return False."""
        # Given: Mock connection error
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        # When: Checking availability
        available = ollama_provider.is_available()

        # Then: Should return False
        assert available is False

    @patch('ctk.integrations.llm.ollama.requests.get')
    def test_is_available_timeout(self, mock_get, ollama_provider):
        """Given timeout, should return False."""
        # Given: Mock timeout
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        # When: Checking availability
        available = ollama_provider.is_available()

        # Then: Should return False (timeout means not available)
        assert available is False


# ==================== Tool Calling Tests ====================

class TestOllamaToolCalling:
    """Test tool calling support."""

    def test_supports_tool_calling(self, ollama_provider):
        """Ollama should support tool calling."""
        assert ollama_provider.supports_tool_calling() is True

    def test_format_tools_for_api(self, ollama_provider):
        """Given generic tools, should format for Ollama/OpenAI format."""
        # Given: Generic tool definitions
        tools = [
            {
                'name': 'search',
                'description': 'Search the web',
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        'query': {'type': 'string'}
                    }
                }
            }
        ]

        # When: Formatting tools
        formatted = ollama_provider.format_tools_for_api(tools)

        # Then: Should be in OpenAI/Ollama format
        assert len(formatted) == 1
        assert formatted[0]['type'] == 'function'
        assert formatted[0]['function']['name'] == 'search'
        assert formatted[0]['function']['description'] == 'Search the web'
        assert formatted[0]['function']['parameters'] == tools[0]['input_schema']

    def test_format_tool_result_message_with_string(self, ollama_provider):
        """Given string result, should create Message with role TOOL."""
        # When: Formatting string result
        msg = ollama_provider.format_tool_result_message('search', 'Results found')

        # Then: Should be TOOL message
        assert msg.role == MessageRole.TOOL
        assert msg.content == 'Results found'

    def test_format_tool_result_message_with_dict(self, ollama_provider):
        """Given dict result, should JSON-encode it."""
        # When: Formatting dict result
        result = {'status': 'success', 'data': [1, 2, 3]}
        msg = ollama_provider.format_tool_result_message('search', result)

        # Then: Should be JSON string
        assert msg.role == MessageRole.TOOL
        assert 'status' in msg.content
        assert 'success' in msg.content

    def test_format_tool_result_message_with_other_type(self, ollama_provider):
        """Given non-string/dict result, should convert to string."""
        # When: Formatting number
        msg = ollama_provider.format_tool_result_message('count', 42)

        # Then: Should be string
        assert msg.role == MessageRole.TOOL
        assert msg.content == '42'


# ==================== Property Tests ====================

class TestOllamaProperties:
    """Test provider properties."""

    def test_name_property(self, ollama_provider):
        """Provider name should be 'ollama'."""
        assert ollama_provider.name == 'ollama'

    def test_repr(self, ollama_provider):
        """String representation should show model."""
        repr_str = repr(ollama_provider)
        assert 'OllamaProvider' in repr_str
        assert 'llama3.1' in repr_str
