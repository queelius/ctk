"""OpenAI-compatible LLM provider.

Wraps the official ``openai`` Python SDK. Any endpoint that speaks the
OpenAI chat-completions protocol works here: the real OpenAI API, Azure,
OpenRouter, vLLM, llama.cpp server, LM Studio, and Ollama's
OpenAI-compat mode on port 11434/v1.

This is the single LLM provider shipped with ctk. Earlier versions
maintained hand-rolled clients for Ollama and Anthropic; those have been
removed in favour of this one wrapper.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, List, Optional

from ctk.core.constants import (DEFAULT_TIMEOUT, HEALTH_CHECK_TIMEOUT,
                                MODEL_LIST_TIMEOUT)
from ctk.llm.base import (AuthenticationError, ChatResponse,
                          ContextLengthError, LLMProvider, LLMProviderError,
                          Message, MessageRole, ModelInfo, ModelNotFoundError,
                          RateLimitError)

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """LLM provider backed by the official ``openai`` SDK.

    Configuration keys (all optional except at least one of ``api_key``
    or a truly permissive local ``base_url``):

    * ``api_key`` — bearer token. For local servers that don't check,
      pass any non-empty string or set ``OPENAI_API_KEY=unused``.
    * ``base_url`` — full endpoint URL including the ``/v1`` suffix if
      your server needs it. Defaults to ``https://api.openai.com/v1``.
    * ``model`` — model name. Default ``gpt-3.5-turbo``.
    * ``timeout`` — per-request timeout in seconds.
    * ``organization`` — OpenAI org id (only used against real OpenAI).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.base_url = (config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        self.organization = config.get("organization")
        self.timeout = config.get("timeout", DEFAULT_TIMEOUT)

        if not self.model:
            self.model = "gpt-3.5-turbo"

        # Lazy-imported so `import ctk` doesn't need openai unless chat
        # is actually used.
        from openai import OpenAI

        # Many OpenAI-compatible local servers don't require a real key
        # but the SDK errors if api_key is None. Provide a placeholder
        # so requests go through; auth happens server-side.
        effective_key = self.api_key or "unused"

        self._client = OpenAI(
            api_key=effective_key,
            base_url=self.base_url,
            organization=self.organization,
            timeout=self.timeout,
        )

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _translate_exception(self, exc: Exception) -> LLMProviderError:
        """Map an openai SDK exception onto ctk's error taxonomy."""
        # Import inside the method so `openai` stays a lazy dependency.
        from openai import (APIConnectionError, APITimeoutError,
                            AuthenticationError as OpenAIAuthError,
                            BadRequestError, NotFoundError, RateLimitError as
                            OpenAIRateLimitError)

        if isinstance(exc, OpenAIAuthError):
            return AuthenticationError(f"Authentication failed: {exc}")
        if isinstance(exc, OpenAIRateLimitError):
            return RateLimitError(f"Rate limit exceeded: {exc}")
        if isinstance(exc, NotFoundError):
            return ModelNotFoundError(
                f"Model {self.model!r} not found at {self.base_url}: {exc}"
            )
        if isinstance(exc, BadRequestError):
            msg = str(exc).lower()
            if "context" in msg or "token" in msg:
                return ContextLengthError(f"Context length exceeded: {exc}")
            return LLMProviderError(f"Bad request: {exc}")
        if isinstance(exc, APITimeoutError):
            return LLMProviderError(f"Request timed out after {self.timeout}s")
        if isinstance(exc, APIConnectionError):
            return LLMProviderError(
                f"Cannot connect to LLM endpoint at {self.base_url}: {exc}"
            )
        return LLMProviderError(f"Unexpected OpenAI error: {exc}")

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        messages: List[Message],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        self.validate_messages(messages)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [self._format_message(m) for m in messages],
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        tools = kwargs.pop("tools", None)
        if tools:
            payload["tools"] = self.format_tools_for_api(tools)
            if not stream:
                # Tool-choice is safe to send only when the server will
                # actually drive function-call selection (non-streaming).
                payload["tool_choice"] = kwargs.pop("tool_choice", "auto")

        for key, value in kwargs.items():
            if value is not None:
                payload[key] = value
        return payload

    def chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> ChatResponse:
        payload = self._build_payload(
            messages, temperature, max_tokens, stream=False, **kwargs
        )
        try:
            response = self._client.chat.completions.create(**payload)
        except Exception as exc:
            raise self._translate_exception(exc) from exc

        choice = response.choices[0]
        message = choice.message

        tool_calls: Optional[List[Dict[str, Any]]] = None
        if getattr(message, "tool_calls", None):
            tool_calls = []
            for tc in message.tool_calls:
                # ``arguments`` is a JSON string per the OpenAI spec.
                try:
                    arguments = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Tool-call arguments were not valid JSON: %s", exc
                    )
                    arguments = {}
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": arguments,
                    }
                )

        usage: Optional[Dict[str, int]] = None
        if response.usage is not None:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return ChatResponse(
            content=message.content or "",
            model=response.model,
            finish_reason=choice.finish_reason,
            usage=usage,
            metadata={"provider": "openai", "id": response.id},
            tool_calls=tool_calls,
        )

    def stream_chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        payload = self._build_payload(
            messages, temperature, max_tokens, stream=True, **kwargs
        )
        try:
            stream = self._client.chat.completions.create(**payload)
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    yield piece
        except Exception as exc:
            raise self._translate_exception(exc) from exc

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    def get_models(self) -> List[ModelInfo]:
        try:
            result = self._client.with_options(timeout=MODEL_LIST_TIMEOUT).models.list()
        except Exception as exc:
            raise self._translate_exception(exc) from exc

        models: List[ModelInfo] = []
        for model_data in result.data:
            model_id = model_data.id
            context_window = self._estimate_context_window(model_id)
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    context_window=context_window,
                    supports_streaming=True,
                    supports_system_message=not model_id.startswith("o1-"),
                    # Tools are only reliably supported on gpt-4+ variants
                    # in real OpenAI. Local servers may advertise tools
                    # without genuine support, so we remain conservative.
                    supports_tools=model_id.startswith(("gpt-4", "gpt-5", "o")),
                    metadata={
                        "created": getattr(model_data, "created", None),
                        "owned_by": getattr(model_data, "owned_by", None),
                    },
                )
            )
        models.sort(key=lambda m: m.id)
        return models

    def _estimate_context_window(self, model_id: str) -> int:
        """Best-effort context-window guess from the model id alone.

        Local servers often expose custom model ids (``muse-7b``,
        ``qwen3:32b``…), so we fall back to a conservative default
        rather than pretend to know.
        """
        lowered = model_id.lower()
        if any(t in lowered for t in ("128k", "gpt-4-turbo", "gpt-4o", "gpt-5")):
            return 128_000
        if "32k" in lowered:
            return 32_000
        if "16k" in lowered:
            return 16_000
        if "gpt-4" in lowered:
            return 8_192
        if "gpt-3.5" in lowered:
            return 4_096
        return 4_096

    def _format_message(self, msg: Message) -> Dict[str, Any]:
        formatted: Dict[str, Any] = {
            "role": msg.role.value,
            "content": msg.content,
        }
        # Tool role messages need a tool_call_id to correlate with the
        # assistant's prior tool request.
        if msg.metadata and "tool_call_id" in msg.metadata:
            formatted["tool_call_id"] = msg.metadata["tool_call_id"]
        return formatted

    # ------------------------------------------------------------------
    # Capability probes
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Cheap availability check using the /models endpoint.

        Returns False (not raises) on any failure — callers use this to
        decide whether to even attempt a chat.
        """
        try:
            self._client.with_options(
                timeout=HEALTH_CHECK_TIMEOUT
            ).models.list()
            return True
        except Exception as exc:
            logger.debug("OpenAI endpoint unavailable: %s", exc)
            return False

    def supports_tool_calling(self) -> bool:
        return True

    def format_tools_for_api(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
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
        self,
        tool_name: str,
        tool_result: Any,
        tool_call_id: Optional[str] = None,
    ) -> Message:
        if isinstance(tool_result, str):
            content = tool_result
        elif isinstance(tool_result, dict):
            content = json.dumps(tool_result)
        else:
            content = str(tool_result)

        msg = Message(role=MessageRole.TOOL, content=content)
        if tool_call_id:
            msg.metadata = {"tool_call_id": tool_call_id}
        return msg
