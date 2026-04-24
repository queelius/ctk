"""Tests for the OpenAI-compatible LLM provider.

This file used to mock ``requests`` against the hand-rolled HTTP
implementation. The provider was rewritten in 2.10.0 to wrap the
official ``openai`` SDK, so these tests mock the SDK client directly —
a smaller surface and a more stable contract.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ctk.llm.base import (AuthenticationError, ChatResponse,
                          ContextLengthError, LLMProviderError, Message,
                          MessageRole, ModelNotFoundError, RateLimitError)
from ctk.llm.openai import OpenAIProvider


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_chat_response(
    content: str,
    finish_reason: str = "stop",
    tool_calls=None,
    model: str = "gpt-3.5-turbo",
    response_id: str = "resp-1",
):
    """Build a stand-in for an openai ChatCompletion response object."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_tokens=5, completion_tokens=7, total_tokens=12)
    return SimpleNamespace(
        choices=[choice], model=model, usage=usage, id=response_id
    )


def _make_models_response(ids):
    return SimpleNamespace(
        data=[SimpleNamespace(id=i, created=0, owned_by="test") for i in ids]
    )


def _make_chat_stream(chunks):
    """Yield mock streaming chunks mirroring the openai SDK shape."""
    for piece in chunks:
        delta = SimpleNamespace(content=piece)
        choice = SimpleNamespace(delta=delta, finish_reason=None)
        yield SimpleNamespace(choices=[choice])


@pytest.fixture
def mock_openai():
    """Patch ``openai.OpenAI`` to return a MagicMock and yield it."""
    mock_client = MagicMock()
    with patch("openai.OpenAI", return_value=mock_client):
        yield mock_client


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestOpenAIProviderInit:
    def test_defaults(self, mock_openai):
        provider = OpenAIProvider({"api_key": "test-key"})
        assert provider.api_key == "test-key"
        assert provider.base_url == "https://api.openai.com/v1"
        assert provider.model == "gpt-3.5-turbo"
        assert provider.timeout == 120

    def test_overrides(self, mock_openai):
        provider = OpenAIProvider(
            {
                "api_key": "k",
                "base_url": "http://muse.local:8080/v1",
                "model": "muse-7b",
                "timeout": 60,
            }
        )
        assert provider.base_url == "http://muse.local:8080/v1"
        assert provider.model == "muse-7b"
        assert provider.timeout == 60

    def test_missing_api_key_still_constructs(self, mock_openai):
        # Local endpoints don't enforce auth; the SDK gets a placeholder
        # so we don't crash in __init__.
        provider = OpenAIProvider({"base_url": "http://local/v1"})
        assert provider.api_key is None


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


class TestOpenAIProviderChat:
    def test_returns_chat_response(self, mock_openai):
        mock_openai.chat.completions.create.return_value = _make_chat_response("hi")
        provider = OpenAIProvider({"api_key": "k"})

        response = provider.chat([Message(role=MessageRole.USER, content="hello")])

        assert isinstance(response, ChatResponse)
        assert response.content == "hi"
        assert response.finish_reason == "stop"
        assert response.usage == {
            "prompt_tokens": 5,
            "completion_tokens": 7,
            "total_tokens": 12,
        }

    def test_extracts_tool_calls(self, mock_openai):
        tool_call = SimpleNamespace(
            id="tc-1",
            function=SimpleNamespace(
                name="get_weather", arguments='{"city": "SF"}'
            ),
        )
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "", tool_calls=[tool_call]
        )
        provider = OpenAIProvider({"api_key": "k"})

        response = provider.chat([Message(role=MessageRole.USER, content="w?")])

        assert response.tool_calls == [
            {"id": "tc-1", "name": "get_weather", "arguments": {"city": "SF"}}
        ]

    def test_tool_call_with_bad_json_degrades_to_empty_dict(self, mock_openai):
        tool_call = SimpleNamespace(
            id="tc-1",
            function=SimpleNamespace(name="x", arguments="not json"),
        )
        mock_openai.chat.completions.create.return_value = _make_chat_response(
            "", tool_calls=[tool_call]
        )
        provider = OpenAIProvider({"api_key": "k"})

        response = provider.chat([Message(role=MessageRole.USER, content="w?")])

        # We log and fall back to {} rather than raising, so the caller
        # always gets a structured tool_calls list.
        assert response.tool_calls == [
            {"id": "tc-1", "name": "x", "arguments": {}}
        ]


# ---------------------------------------------------------------------------
# stream_chat()
# ---------------------------------------------------------------------------


class TestOpenAIProviderStreamChat:
    def test_yields_chunks(self, mock_openai):
        mock_openai.chat.completions.create.return_value = _make_chat_stream(
            ["Hel", "lo", "!"]
        )
        provider = OpenAIProvider({"api_key": "k"})

        chunks = list(
            provider.stream_chat([Message(role=MessageRole.USER, content="hi")])
        )

        assert chunks == ["Hel", "lo", "!"]


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


def _instantiate_sdk_exc(cls, msg: str):
    """Construct a bare SDK exception for raising in tests.

    The openai SDK exception hierarchy has wildly varying __init__
    signatures (some need a real httpx.Response, some don't). We skip
    __init__ entirely via ``__new__`` — the provider only checks
    ``isinstance`` against the class, not any instance state.
    """
    exc = cls.__new__(cls)
    # Set ``args`` so ``str(exc)`` still renders a useful message.
    exc.args = (msg,)
    return exc


class TestOpenAIProviderErrorHandling:
    @pytest.mark.parametrize(
        "sdk_exc_name, ctk_exc",
        [
            ("AuthenticationError", AuthenticationError),
            ("RateLimitError", RateLimitError),
            ("NotFoundError", ModelNotFoundError),
            ("APIConnectionError", LLMProviderError),
            ("APITimeoutError", LLMProviderError),
        ],
    )
    def test_sdk_exceptions_translate(self, mock_openai, sdk_exc_name, ctk_exc):
        import openai

        sdk_exc_cls = getattr(openai, sdk_exc_name)
        mock_openai.chat.completions.create.side_effect = _instantiate_sdk_exc(
            sdk_exc_cls, "boom"
        )
        provider = OpenAIProvider({"api_key": "k"})

        with pytest.raises(ctk_exc):
            provider.chat([Message(role=MessageRole.USER, content="hi")])

    def test_context_length_in_bad_request(self, mock_openai):
        import openai

        mock_openai.chat.completions.create.side_effect = _instantiate_sdk_exc(
            openai.BadRequestError, "context length 8192 exceeded"
        )
        provider = OpenAIProvider({"api_key": "k"})

        with pytest.raises(ContextLengthError):
            provider.chat([Message(role=MessageRole.USER, content="hi")])


# ---------------------------------------------------------------------------
# get_models() + is_available()
# ---------------------------------------------------------------------------


class TestOpenAIProviderModels:
    def test_get_models(self, mock_openai):
        mock_openai.with_options.return_value = mock_openai
        mock_openai.models.list.return_value = _make_models_response(
            ["gpt-4", "gpt-3.5-turbo", "embedding-001"]
        )
        provider = OpenAIProvider({"api_key": "k"})

        models = provider.get_models()
        ids = [m.id for m in models]

        # All models are returned; ordering is alphabetical.
        assert ids == sorted(ids)
        assert "gpt-4" in ids

    def test_get_models_estimates_context_window(self, mock_openai):
        mock_openai.with_options.return_value = mock_openai
        mock_openai.models.list.return_value = _make_models_response(
            ["gpt-4-turbo", "gpt-3.5-turbo", "custom-local"]
        )
        provider = OpenAIProvider({"api_key": "k"})

        models = {m.id: m for m in provider.get_models()}
        assert models["gpt-4-turbo"].context_window == 128_000
        assert models["gpt-3.5-turbo"].context_window == 4_096

    def test_is_available_true(self, mock_openai):
        mock_openai.with_options.return_value = mock_openai
        mock_openai.models.list.return_value = _make_models_response(["gpt-4"])
        provider = OpenAIProvider({"api_key": "k"})
        assert provider.is_available() is True

    def test_is_available_false_on_error(self, mock_openai):
        mock_openai.with_options.return_value = mock_openai
        mock_openai.models.list.side_effect = RuntimeError("dead")
        provider = OpenAIProvider({"api_key": "k"})
        assert provider.is_available() is False


# ---------------------------------------------------------------------------
# Tool formatting helpers
# ---------------------------------------------------------------------------


class TestOpenAIProviderToolFormat:
    def test_format_tools_for_api(self, mock_openai):
        provider = OpenAIProvider({"api_key": "k"})

        tools = [
            {
                "name": "get_weather",
                "description": "Fetch weather for a city",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                },
            }
        ]
        formatted = provider.format_tools_for_api(tools)

        assert formatted == [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Fetch weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            }
        ]

    def test_format_tool_result_message(self, mock_openai):
        provider = OpenAIProvider({"api_key": "k"})
        msg = provider.format_tool_result_message(
            "get_weather", {"temp": 72}, tool_call_id="tc-1"
        )
        assert msg.role == MessageRole.TOOL
        assert msg.metadata == {"tool_call_id": "tc-1"}
        # Dict results are JSON-encoded in the message content.
        assert "72" in msg.content
