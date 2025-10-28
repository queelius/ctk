"""
Base LLM provider abstraction for CTK chat integration.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Iterator, Any
from dataclasses import dataclass, field
from enum import Enum


class MessageRole(Enum):
    """Standard message roles across all providers"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"  # For function calling (future MCP support)


@dataclass
class Message:
    """Standardized message format"""
    role: MessageRole
    content: str
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API calls"""
        return {
            "role": self.role.value,
            "content": self.content
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create Message from dict"""
        return cls(
            role=MessageRole(data['role']),
            content=data['content'],
            metadata=data.get('metadata')
        )


@dataclass
class ModelInfo:
    """Information about an LLM model"""
    id: str
    name: str
    context_window: int
    supports_streaming: bool = True
    supports_system_message: bool = True
    supports_tools: bool = False
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ChatResponse:
    """Standardized response from LLM"""
    content: str
    model: str
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None  # tokens used
    metadata: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None  # Tool calls requested by LLM


class LLMProvider(ABC):
    """
    Base class for all LLM providers.

    Implements a standard interface for chat interactions across
    different LLM providers (Ollama, OpenAI, Anthropic, etc.)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with configuration.

        Args:
            config: Provider-specific configuration (API keys, endpoints, etc.)
        """
        self.config = config
        self.model = config.get('model')

    @abstractmethod
    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """
        Send messages and get response (blocking).

        Args:
            messages: List of Message objects
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            ChatResponse object

        Raises:
            LLMProviderError: On API errors, network issues, etc.
        """
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        Stream response token by token.

        Args:
            messages: List of Message objects
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Yields:
            Text chunks as they arrive

        Raises:
            LLMProviderError: On API errors, network issues, etc.
        """
        pass

    @abstractmethod
    def get_models(self) -> List[ModelInfo]:
        """
        List available models for this provider.

        Returns:
            List of ModelInfo objects

        Raises:
            LLMProviderError: On API errors
        """
        pass

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific model.

        Args:
            model_name: Name/ID of the model

        Returns:
            Dict with model information (provider-specific format) or None if not found

        Raises:
            LLMProviderError: On API errors
        """
        # Default implementation - providers should override
        return None

    def validate_messages(self, messages: List[Message]) -> None:
        """
        Validate message list before sending to API.

        Checks:
        - At least one message
        - Alternating user/assistant (if required by provider)
        - System message placement (if required)

        Raises:
            ValueError: If messages are invalid
        """
        if not messages:
            raise ValueError("Messages list cannot be empty")

        # Provider-specific validation can be overridden

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Default implementation: rough estimate (4 chars per token).
        Providers should override with their specific tokenizers.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        return len(text) // 4

    def supports_tool_calling(self) -> bool:
        """
        Check if this provider supports tool/function calling.

        Returns:
            True if tool calling is supported
        """
        return False

    def format_tools_for_api(self, tools: List[Dict[str, Any]]) -> Any:
        """
        Convert generic tool definitions to provider-specific format.

        Args:
            tools: List of tool defs with 'name', 'description', 'input_schema'

        Returns:
            Provider-specific tool format (varies by provider)
        """
        raise NotImplementedError("This provider does not support tool calling")

    def extract_tool_calls(self, response: ChatResponse) -> Optional[List[Dict[str, Any]]]:
        """
        Extract tool calls from a chat response.

        Args:
            response: ChatResponse object

        Returns:
            List of tool calls or None if no tools were called.
            Each tool call should have: {'name': str, 'arguments': dict, 'id': str}
        """
        return response.tool_calls

    def format_tool_result_message(self, tool_name: str, tool_result: Any, tool_call_id: Optional[str] = None) -> Message:
        """
        Format a tool result as a message to send back to the LLM.

        Args:
            tool_name: Name of the tool that was called
            tool_result: Result from the tool
            tool_call_id: ID of the tool call (if applicable)

        Returns:
            Message object formatted for this provider
        """
        raise NotImplementedError("This provider does not support tool calling")

    def truncate_context(
        self,
        messages: List[Message],
        max_tokens: int
    ) -> List[Message]:
        """
        Truncate message context to fit within token limit.

        Strategy: Keep system message, keep last N messages that fit.

        Args:
            messages: Full message list
            max_tokens: Maximum token budget

        Returns:
            Truncated message list
        """
        # Simple implementation - can be overridden
        system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM]
        other_msgs = [m for m in messages if m.role != MessageRole.SYSTEM]

        result = system_msgs.copy()
        current_tokens = sum(self.count_tokens(m.content) for m in system_msgs)

        # Add messages from the end until we hit the limit
        for msg in reversed(other_msgs):
            msg_tokens = self.count_tokens(msg.content)
            if current_tokens + msg_tokens > max_tokens:
                break
            result.insert(len(system_msgs), msg)
            current_tokens += msg_tokens

        return result

    @property
    def name(self) -> str:
        """Provider name (e.g., 'ollama', 'openai')"""
        return self.__class__.__name__.replace('Provider', '').lower()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model})"


# ==================== Exceptions ====================

class LLMProviderError(Exception):
    """Base exception for LLM provider errors"""
    pass


class AuthenticationError(LLMProviderError):
    """API authentication failed"""
    pass


class RateLimitError(LLMProviderError):
    """Rate limit exceeded"""
    pass


class ModelNotFoundError(LLMProviderError):
    """Requested model not available"""
    pass


class ContextLengthError(LLMProviderError):
    """Context length exceeded"""
    pass
