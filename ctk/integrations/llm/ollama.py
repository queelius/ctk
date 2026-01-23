"""
Ollama LLM provider implementation.
"""

import json
from typing import Any, Dict, Iterator, List, Optional

import requests

from ctk.integrations.llm.base import (ChatResponse, LLMProvider,
                                       LLMProviderError, Message, MessageRole,
                                       ModelInfo, ModelNotFoundError)


class OllamaProvider(LLMProvider):
    """
    Ollama provider for local LLM inference.

    Requires Ollama to be running locally (default: http://localhost:11434)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Ollama provider.

        Args:
            config: Configuration dict with keys:
                - base_url: Ollama API URL (default: http://localhost:11434)
                - model: Model name (e.g., 'llama3.1', 'mistral')
                - timeout: Request timeout in seconds (default: 120)
        """
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434").rstrip("/")
        self.timeout = config.get("timeout", 120)

        if not self.model:
            raise ValueError("Model name is required for Ollama provider")

    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatResponse:
        """
        Send messages and get response from Ollama.

        Args:
            messages: List of Message objects
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate (Ollama: num_predict)
            **kwargs: Additional Ollama parameters (top_p, top_k, etc.)

        Returns:
            ChatResponse object

        Raises:
            LLMProviderError: On API errors
        """
        self.validate_messages(messages)

        # Convert messages to Ollama format
        ollama_messages = [msg.to_dict() for msg in messages]

        # Build request payload
        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        # Extract tools before adding other kwargs to options
        tools = kwargs.pop("tools", None)
        if tools:
            payload["tools"] = tools

        # Add remaining options
        payload["options"].update(kwargs)

        try:
            response = requests.post(
                f"{self.base_url}/api/chat", json=payload, timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()

            # Extract tool calls if present
            tool_calls = None
            message = result.get("message", {})
            if "tool_calls" in message:
                tool_calls = message["tool_calls"]

            return ChatResponse(
                content=message.get("content", ""),
                model=result.get("model", self.model),
                finish_reason=result.get("done_reason"),
                usage={
                    "prompt_tokens": result.get("prompt_eval_count", 0),
                    "completion_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0)
                    + result.get("eval_count", 0),
                },
                metadata=result,
                tool_calls=tool_calls,
            )

        except requests.exceptions.ConnectionError:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Try: ollama serve"
            )
        except requests.exceptions.Timeout:
            raise LLMProviderError(f"Request timed out after {self.timeout}s")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ModelNotFoundError(
                    f"Model '{self.model}' not found. "
                    f"Pull it with: ollama pull {self.model}"
                )
            raise LLMProviderError(f"Ollama API error: {e}")
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
        Stream response from Ollama token by token.

        Args:
            messages: List of Message objects
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Ollama parameters

        Yields:
            Text chunks as they arrive

        Raises:
            LLMProviderError: On API errors
        """
        self.validate_messages(messages)

        # Convert messages to Ollama format
        ollama_messages = [msg.to_dict() for msg in messages]

        # Build request payload
        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        # Extract tools before adding other kwargs to options
        tools = kwargs.pop("tools", None)
        if tools:
            payload["tools"] = tools

        # Add remaining options
        payload["options"].update(kwargs)

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()

            # Stream response line by line
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if "message" in chunk and "content" in chunk["message"]:
                        yield chunk["message"]["content"]

                    # Check if done
                    if chunk.get("done"):
                        break

        except requests.exceptions.ConnectionError:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self.base_url}. " "Is Ollama running?"
            )
        except requests.exceptions.Timeout:
            raise LLMProviderError(f"Request timed out after {self.timeout}s")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ModelNotFoundError(
                    f"Model '{self.model}' not found. "
                    f"Pull it with: ollama pull {self.model}"
                )
            raise LLMProviderError(f"Ollama API error: {e}")
        except Exception as e:
            raise LLMProviderError(f"Unexpected error: {e}")

    def get_models(self) -> List[ModelInfo]:
        """
        List available models from Ollama.

        Returns:
            List of ModelInfo objects

        Raises:
            LLMProviderError: On API errors
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()

            result = response.json()
            models = []

            for model_data in result.get("models", []):
                # Extract context window from model details if available
                context_window = None

                # Try to get model info for max context window
                try:
                    show_response = requests.post(
                        f"{self.base_url}/api/show",
                        json={"name": model_data["name"]},
                        timeout=5,
                    )
                    if show_response.ok:
                        show_data = show_response.json()
                        # Get max context from model_info (e.g., llama.context_length)
                        if "model_info" in show_data:
                            model_info = show_data["model_info"]
                            # Look for context_length in model_info
                            for key, value in model_info.items():
                                if "context_length" in key.lower():
                                    try:
                                        context_window = int(value)
                                        break
                                    except:
                                        pass
                except:
                    pass  # context_window remains None if we can't get it

                models.append(
                    ModelInfo(
                        id=model_data["name"],
                        name=model_data["name"],
                        context_window=context_window,
                        supports_streaming=True,
                        supports_system_message=True,
                        supports_tools=False,  # Basic models don't support tools
                        metadata={
                            "size": model_data.get("size"),
                            "modified": model_data.get("modified_at"),
                            "digest": model_data.get("digest"),
                        },
                    )
                )

            return models

        except requests.exceptions.ConnectionError:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self.base_url}. " "Is Ollama running?"
            )
        except Exception as e:
            raise LLMProviderError(f"Failed to list models: {e}")

    def get_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific model.

        Args:
            model_name: Name of the model

        Returns:
            Dict with model information or None if not found

        Raises:
            LLMProviderError: On API errors
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/show",
                json={"name": model_name},
                timeout=self.timeout,
            )
            response.raise_for_status()

            return response.json()

        except requests.exceptions.ConnectionError:
            raise LLMProviderError(
                f"Cannot connect to Ollama at {self.base_url}. " "Is Ollama running?"
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None  # Model not found
            raise LLMProviderError(f"Failed to get model info: {e}")
        except Exception as e:
            raise LLMProviderError(f"Failed to get model info: {e}")

    def is_available(self) -> bool:
        """
        Check if Ollama is running and accessible.

        Returns:
            True if Ollama is available, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.ok
        except:
            return False

    def supports_tool_calling(self) -> bool:
        """Ollama supports tool calling for compatible models"""
        return True

    def format_tools_for_api(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert generic tool definitions to Ollama format.

        Args:
            tools: List of dicts with 'name', 'description', 'input_schema'

        Returns:
            List in Ollama/OpenAI format
        """
        formatted = []
        for tool in tools:
            formatted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                }
            )
        return formatted

    def format_tool_result_message(
        self, tool_name: str, tool_result: Any, tool_call_id: Optional[str] = None
    ) -> Message:
        """
        Format a tool result as a message for Ollama.

        Args:
            tool_name: Name of the tool
            tool_result: Result from tool execution
            tool_call_id: ID of the tool call

        Returns:
            Message with role='tool'
        """
        # Convert result to string if needed
        if isinstance(tool_result, str):
            content = tool_result
        elif isinstance(tool_result, dict):
            import json

            content = json.dumps(tool_result)
        else:
            content = str(tool_result)

        return Message(role=MessageRole.TOOL, content=content)

    def extract_tool_calls(
        self, response: ChatResponse
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Extract tool calls from response, with detection for hallucinated tool calls.

        Some smaller models (llama3.2, qwen, etc.) output text that looks like tool calls
        instead of making proper API tool calls. This method detects those patterns.

        Args:
            response: ChatResponse object

        Returns:
            List of tool calls or None
        """
        import re

        # First, check for proper tool calls
        if response.tool_calls:
            return response.tool_calls

        # No proper tool calls - check if model hallucinated tool call patterns
        content = response.content or ""

        # Patterns that indicate hallucinated tool calls
        hallucination_patterns = [
            r"<\|python_tag\|>",  # Llama internal token leak
            r"<tool_call>",  # Generic tool call tag
            r"<\|start_tool\|>",  # Some models use this
            r'"function":\s*{\s*"name"',  # JSON tool call format
            r"```(?:json|plaintext)?\s*\n?\s*(?:search_|list_|get_)\w+\s*\(",  # Code block with function call
            r"(?:search_|list_|get_|execute_)\w+\s*\(\s*(?:query|id|limit)",  # Function call syntax
            r'"id":\s*"conv_\d',  # Fake conversation IDs
        ]

        for pattern in hallucination_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                # Log warning - model is trying to call tools but not using API
                import sys

                print(
                    f"\n⚠️  WARNING: Model is hallucinating tool calls!", file=sys.stderr
                )
                print(
                    f"   The model output fake tool calls/results instead of using the API.",
                    file=sys.stderr,
                )
                print(
                    f"   This model ({self.model}) may not support function calling properly.",
                    file=sys.stderr,
                )
                print(
                    f"   Try: ctk chat --no-tools  (to disable tools)", file=sys.stderr
                )
                print(
                    f"   Or use a larger model with better tool support.\n",
                    file=sys.stderr,
                )
                break

        return None
