"""
Anthropic Claude LLM provider implementation.
"""

import json
from typing import Any, Dict, Iterator, List, Optional

import requests

from ctk.integrations.llm.base import (
    AuthenticationError,
    ChatResponse,
    ContextLengthError,
    LLMProvider,
    LLMProviderError,
    Message,
    MessageRole,
    ModelInfo,
    ModelNotFoundError,
    RateLimitError,
)


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude provider with streaming and tool calling support.

    Supports Claude 3 family (Haiku, Sonnet, Opus) and future models.
    """

    # Known Claude models with their context windows
    KNOWN_MODELS = {
        "claude-3-opus-20240229": {"context": 200000, "tools": True},
        "claude-3-sonnet-20240229": {"context": 200000, "tools": True},
        "claude-3-haiku-20240307": {"context": 200000, "tools": True},
        "claude-3-5-sonnet-20240620": {"context": 200000, "tools": True},
        "claude-3-5-sonnet-20241022": {"context": 200000, "tools": True},
        "claude-3-5-haiku-20241022": {"context": 200000, "tools": True},
        "claude-sonnet-4-20250514": {"context": 200000, "tools": True},
        "claude-opus-4-20250514": {"context": 200000, "tools": True},
    }

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Anthropic provider.

        Args:
            config: Configuration dict with keys:
                - api_key: Anthropic API key (required)
                - base_url: API base URL (default: https://api.anthropic.com)
                - model: Model name (default: claude-3-haiku-20240307)
                - timeout: Request timeout in seconds (default: 120)
                - max_tokens: Default max tokens for responses (default: 4096)
        """
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.anthropic.com").rstrip("/")
        self.api_key = config.get("api_key")
        self.timeout = config.get("timeout", 120)
        self.default_max_tokens = config.get("max_tokens", 4096)
        self.api_version = "2023-06-01"

        if not self.model:
            self.model = "claude-3-haiku-20240307"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "Content-Type": "application/json",
        }

    def _handle_error_response(self, response: requests.Response) -> None:
        """Handle API error responses with appropriate exceptions."""
        try:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", response.text)
            error_type = error_data.get("error", {}).get("type", "")
        except (json.JSONDecodeError, KeyError):
            error_msg = response.text
            error_type = ""

        if response.status_code == 401:
            raise AuthenticationError(f"Invalid API key: {error_msg}")
        elif response.status_code == 429:
            raise RateLimitError(f"Rate limit exceeded: {error_msg}")
        elif response.status_code == 404:
            raise ModelNotFoundError(f"Model '{self.model}' not found: {error_msg}")
        elif "context" in error_type.lower() or "too long" in error_msg.lower():
            raise ContextLengthError(f"Context length exceeded: {error_msg}")
        else:
            raise LLMProviderError(f"Anthropic API error ({response.status_code}): {error_msg}")

    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatResponse:
        """
        Send messages and get response from Anthropic.

        Args:
            messages: List of Message objects
            temperature: Sampling temperature (0.0-1.0 for Anthropic)
            max_tokens: Maximum tokens to generate (required by Anthropic)
            **kwargs: Additional Anthropic parameters (top_p, tools, etc.)

        Returns:
            ChatResponse object

        Raises:
            LLMProviderError: On API errors
        """
        if not self.api_key:
            raise AuthenticationError(
                "Anthropic API key not set. Set api_key in config or ANTHROPIC_API_KEY env var."
            )

        self.validate_messages(messages)

        # Separate system message from chat messages (Anthropic requires this)
        system_message = None
        chat_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_message = msg.content
            else:
                chat_messages.append(self._format_message(msg))

        # Build request payload
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "temperature": min(temperature, 1.0),  # Anthropic caps at 1.0
        }

        if system_message:
            payload["system"] = system_message

        # Handle tools
        tools = kwargs.pop("tools", None)
        if tools:
            payload["tools"] = self.format_tools_for_api(tools)

        # Add any additional kwargs
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )

            if not response.ok:
                self._handle_error_response(response)

            result = response.json()

            # Extract content - Anthropic returns content blocks
            content = ""
            tool_calls = None

            for block in result.get("content", []):
                if block["type"] == "text":
                    content += block["text"]
                elif block["type"] == "tool_use":
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append({
                        "id": block["id"],
                        "name": block["name"],
                        "arguments": block["input"],
                    })

            return ChatResponse(
                content=content,
                model=result.get("model", self.model),
                finish_reason=result.get("stop_reason"),
                usage={
                    "prompt_tokens": result.get("usage", {}).get("input_tokens", 0),
                    "completion_tokens": result.get("usage", {}).get("output_tokens", 0),
                    "total_tokens": (
                        result.get("usage", {}).get("input_tokens", 0)
                        + result.get("usage", {}).get("output_tokens", 0)
                    ),
                },
                metadata=result,
                tool_calls=tool_calls,
            )

        except requests.exceptions.ConnectionError:
            raise LLMProviderError(
                f"Cannot connect to Anthropic API at {self.base_url}. "
                "Check your internet connection."
            )
        except requests.exceptions.Timeout:
            raise LLMProviderError(f"Request timed out after {self.timeout}s")
        except (AuthenticationError, RateLimitError, ModelNotFoundError, ContextLengthError):
            raise
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"Unexpected error: {e}")

    def stream_chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Iterator[str]:
        """
        Stream response from Anthropic token by token.

        Args:
            messages: List of Message objects
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Anthropic parameters

        Yields:
            Text chunks as they arrive

        Raises:
            LLMProviderError: On API errors
        """
        if not self.api_key:
            raise AuthenticationError(
                "Anthropic API key not set. Set api_key in config or ANTHROPIC_API_KEY env var."
            )

        self.validate_messages(messages)

        # Separate system message from chat messages
        system_message = None
        chat_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_message = msg.content
            else:
                chat_messages.append(self._format_message(msg))

        # Build request payload
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "temperature": min(temperature, 1.0),
            "stream": True,
        }

        if system_message:
            payload["system"] = system_message

        # Handle tools - note: tool calls work differently in streaming mode
        tools = kwargs.pop("tools", None)
        if tools:
            payload["tools"] = self.format_tools_for_api(tools)

        # Add any additional kwargs
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self._get_headers(),
                json=payload,
                stream=True,
                timeout=self.timeout,
            )

            if not response.ok:
                self._handle_error_response(response)

            # Process Server-Sent Events
            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        data = line_str[6:]
                        try:
                            event = json.loads(data)
                            event_type = event.get("type", "")

                            if event_type == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")

                            elif event_type == "message_stop":
                                break

                        except json.JSONDecodeError:
                            continue

        except requests.exceptions.ConnectionError:
            raise LLMProviderError(
                f"Cannot connect to Anthropic API at {self.base_url}. "
                "Check your internet connection."
            )
        except requests.exceptions.Timeout:
            raise LLMProviderError(f"Request timed out after {self.timeout}s")
        except (AuthenticationError, RateLimitError, ModelNotFoundError, ContextLengthError):
            raise
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"Unexpected error: {e}")

    def get_models(self) -> List[ModelInfo]:
        """
        List available Claude models.

        Note: Anthropic doesn't have a public models list endpoint,
        so we return known models.

        Returns:
            List of ModelInfo objects
        """
        models = []

        for model_id, info in self.KNOWN_MODELS.items():
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    context_window=info["context"],
                    supports_streaming=True,
                    supports_system_message=True,
                    supports_tools=info["tools"],
                    metadata={"provider": "anthropic"},
                )
            )

        # Sort by model ID for consistent ordering
        models.sort(key=lambda m: m.id)
        return models

    def _format_message(self, msg: Message) -> Dict[str, Any]:
        """Format a Message for the Anthropic API."""
        # Map roles to Anthropic format
        role = msg.role.value
        if role == "tool":
            role = "user"  # Tool results are sent as user messages in Anthropic

        return {
            "role": role,
            "content": msg.content,
        }

    def is_available(self) -> bool:
        """
        Check if Anthropic API is accessible.

        Returns:
            True if API key is set, False otherwise
        """
        # Anthropic doesn't have a lightweight health check endpoint
        # Just verify we have an API key
        return bool(self.api_key)

    def supports_tool_calling(self) -> bool:
        """Anthropic Claude 3 models support tool calling."""
        return True

    def format_tools_for_api(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert generic tool definitions to Anthropic format.

        Args:
            tools: List of dicts with 'name', 'description', 'input_schema'

        Returns:
            List in Anthropic format
        """
        formatted = []
        for tool in tools:
            formatted.append({
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
            })
        return formatted

    def format_tool_result_message(
        self, tool_name: str, tool_result: Any, tool_call_id: Optional[str] = None
    ) -> Message:
        """
        Format a tool result as a message for Anthropic.

        Args:
            tool_name: Name of the tool
            tool_result: Result from tool execution
            tool_call_id: ID of the tool call (required for Anthropic)

        Returns:
            Message with role='user' containing tool_result block
        """
        # Convert result to string if needed
        if isinstance(tool_result, str):
            content = tool_result
        elif isinstance(tool_result, dict):
            content = json.dumps(tool_result)
        else:
            content = str(tool_result)

        # Anthropic expects tool results as user messages with special content
        # For simplicity, we return a basic message - the caller should
        # format it properly for the API
        msg = Message(role=MessageRole.USER, content=content)
        if tool_call_id:
            msg.metadata = {"tool_use_id": tool_call_id}
        return msg
