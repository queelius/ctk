"""
OpenAI LLM provider implementation.
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


class OpenAIProvider(LLMProvider):
    """
    OpenAI GPT provider with streaming and tool calling support.

    Supports GPT-3.5, GPT-4, and other OpenAI models.
    Also compatible with OpenAI-compatible APIs (e.g., Azure, local proxies).
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize OpenAI provider.

        Args:
            config: Configuration dict with keys:
                - api_key: OpenAI API key (required)
                - base_url: API base URL (default: https://api.openai.com)
                - model: Model name (default: gpt-3.5-turbo)
                - timeout: Request timeout in seconds (default: 120)
                - organization: Optional organization ID
        """
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.openai.com").rstrip("/")
        self.api_key = config.get("api_key")
        self.organization = config.get("organization")
        self.timeout = config.get("timeout", 120)

        if not self.model:
            self.model = "gpt-3.5-turbo"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        return headers

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
        elif "context_length" in error_type or "context_length" in error_msg.lower():
            raise ContextLengthError(f"Context length exceeded: {error_msg}")
        else:
            raise LLMProviderError(f"OpenAI API error ({response.status_code}): {error_msg}")

    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatResponse:
        """
        Send messages and get response from OpenAI.

        Args:
            messages: List of Message objects
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI parameters (top_p, tools, etc.)

        Returns:
            ChatResponse object

        Raises:
            LLMProviderError: On API errors
        """
        if not self.api_key:
            raise AuthenticationError(
                "OpenAI API key not set. Set api_key in config or OPENAI_API_KEY env var."
            )

        self.validate_messages(messages)

        # Build request payload
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [self._format_message(m) for m in messages],
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        # Handle tools
        tools = kwargs.pop("tools", None)
        if tools:
            payload["tools"] = self.format_tools_for_api(tools)
            # Allow model to decide when to call tools
            payload["tool_choice"] = kwargs.pop("tool_choice", "auto")

        # Add any additional kwargs
        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )

            if not response.ok:
                self._handle_error_response(response)

            result = response.json()
            choice = result["choices"][0]
            message = choice["message"]

            # Extract tool calls if present
            tool_calls = None
            if "tool_calls" in message:
                tool_calls = []
                for tc in message["tool_calls"]:
                    tool_calls.append({
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"]),
                    })

            return ChatResponse(
                content=message.get("content", ""),
                model=result.get("model", self.model),
                finish_reason=choice.get("finish_reason"),
                usage=result.get("usage"),
                metadata=result,
                tool_calls=tool_calls,
            )

        except requests.exceptions.ConnectionError:
            raise LLMProviderError(
                f"Cannot connect to OpenAI API at {self.base_url}. "
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
        Stream response from OpenAI token by token.

        Args:
            messages: List of Message objects
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI parameters

        Yields:
            Text chunks as they arrive

        Raises:
            LLMProviderError: On API errors
        """
        if not self.api_key:
            raise AuthenticationError(
                "OpenAI API key not set. Set api_key in config or OPENAI_API_KEY env var."
            )

        self.validate_messages(messages)

        # Build request payload
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [self._format_message(m) for m in messages],
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

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
                f"{self.base_url}/v1/chat/completions",
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
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue

        except requests.exceptions.ConnectionError:
            raise LLMProviderError(
                f"Cannot connect to OpenAI API at {self.base_url}. "
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
        List available models from OpenAI.

        Returns:
            List of ModelInfo objects

        Raises:
            LLMProviderError: On API errors
        """
        if not self.api_key:
            raise AuthenticationError("OpenAI API key not set")

        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers=self._get_headers(),
                timeout=30,
            )

            if not response.ok:
                self._handle_error_response(response)

            result = response.json()
            models = []

            # Filter to chat models (gpt-*)
            for model_data in result.get("data", []):
                model_id = model_data.get("id", "")
                if model_id.startswith(("gpt-", "o1-", "chatgpt-")):
                    # Estimate context window based on model name
                    context_window = self._estimate_context_window(model_id)

                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=model_id,
                            context_window=context_window,
                            supports_streaming=True,
                            supports_system_message=not model_id.startswith("o1-"),
                            supports_tools=model_id.startswith("gpt-4"),
                            metadata={
                                "created": model_data.get("created"),
                                "owned_by": model_data.get("owned_by"),
                            },
                        )
                    )

            # Sort by model ID for consistent ordering
            models.sort(key=lambda m: m.id)
            return models

        except requests.exceptions.ConnectionError:
            raise LLMProviderError("Cannot connect to OpenAI API")
        except (AuthenticationError, RateLimitError):
            raise
        except LLMProviderError:
            raise
        except Exception as e:
            raise LLMProviderError(f"Failed to list models: {e}")

    def _estimate_context_window(self, model_id: str) -> int:
        """Estimate context window based on model name."""
        model_lower = model_id.lower()
        if "128k" in model_lower or "gpt-4-turbo" in model_lower or "gpt-4o" in model_lower:
            return 128000
        elif "32k" in model_lower:
            return 32000
        elif "16k" in model_lower:
            return 16000
        elif "gpt-4" in model_lower:
            return 8192
        elif "gpt-3.5" in model_lower:
            return 4096
        else:
            return 4096  # Default

    def _format_message(self, msg: Message) -> Dict[str, Any]:
        """Format a Message for the OpenAI API."""
        return {
            "role": msg.role.value,
            "content": msg.content,
        }

    def is_available(self) -> bool:
        """
        Check if OpenAI API is accessible.

        Returns:
            True if API is available, False otherwise
        """
        if not self.api_key:
            return False

        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers=self._get_headers(),
                timeout=5,
            )
            return response.ok
        except:
            return False

    def supports_tool_calling(self) -> bool:
        """OpenAI supports tool calling for GPT-4 models."""
        return True

    def format_tools_for_api(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert generic tool definitions to OpenAI format.

        Args:
            tools: List of dicts with 'name', 'description', 'input_schema'

        Returns:
            List in OpenAI format
        """
        formatted = []
        for tool in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        return formatted

    def format_tool_result_message(
        self, tool_name: str, tool_result: Any, tool_call_id: Optional[str] = None
    ) -> Message:
        """
        Format a tool result as a message for OpenAI.

        Args:
            tool_name: Name of the tool
            tool_result: Result from tool execution
            tool_call_id: ID of the tool call (required for OpenAI)

        Returns:
            Message with role='tool'
        """
        # Convert result to string if needed
        if isinstance(tool_result, str):
            content = tool_result
        elif isinstance(tool_result, dict):
            content = json.dumps(tool_result)
        else:
            content = str(tool_result)

        msg = Message(role=MessageRole.TOOL, content=content)
        # OpenAI requires tool_call_id in the message
        if tool_call_id:
            msg.metadata = {"tool_call_id": tool_call_id}
        return msg
