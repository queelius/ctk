"""Guards the assistant-tool_calls round-trip on strict OpenAI-spec servers.

Two failure modes this test catches:

(a) _format_message never emitted tool_calls on the assistant message, so
    the wire history had TOOL-role messages whose preceding assistant message
    lacked tool_calls: strict servers 400 on this.

(b) When the assistant turn had NO text (pure tool call), the worker
    skipped appending the assistant message entirely, leaving orphan TOOL
    messages with no preceding assistant message at all.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from ctk.llm.base import Message, MessageRole, StreamEvent
from ctk.llm.base import Message as LLMMessage
from ctk.llm.base import MessageRole as LLMMessageRole
from ctk.llm.openai import OpenAIProvider

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# (a) Unit tests for _format_message
# ---------------------------------------------------------------------------

def _make_provider() -> OpenAIProvider:
    """Build a provider without needing a real API key or endpoint."""
    import unittest.mock as mock

    with mock.patch("openai.OpenAI"):
        return OpenAIProvider(
            {
                "api_key": "fake-key",
                "base_url": "http://fake.local/v1",
                "model": "gpt-test",
            }
        )


_TOOL_CALL_PAYLOAD = [
    {
        "id": "call_1",
        "type": "function",
        "function": {
            "name": "search_conversations",
            "arguments": "{}",
        },
    }
]


def test_format_message_assistant_with_tool_calls():
    """Assistant message carrying tool_calls metadata emits tool_calls in wire dict."""
    provider = _make_provider()
    msg = Message(
        role=MessageRole.ASSISTANT,
        content="",
        metadata={"tool_calls": _TOOL_CALL_PAYLOAD},
    )
    formatted = provider._format_message(msg)
    assert "tool_calls" in formatted, "tool_calls must appear in the wire dict"
    assert formatted["tool_calls"][0]["id"] == "call_1"
    assert formatted["tool_calls"][0]["type"] == "function"
    assert formatted["tool_calls"][0]["function"]["name"] == "search_conversations"


def test_format_message_assistant_empty_content_with_tool_calls():
    """Empty content is allowed when tool_calls is present (OpenAI accepts content=None)."""
    provider = _make_provider()
    msg = Message(
        role=MessageRole.ASSISTANT,
        content="",
        metadata={"tool_calls": _TOOL_CALL_PAYLOAD},
    )
    formatted = provider._format_message(msg)
    # content may be "" or None - both are accepted by strict OpenAI
    assert "tool_calls" in formatted
    assert formatted["role"] == "assistant"


def test_format_message_tool_role_carries_tool_call_id():
    """TOOL-role message must carry tool_call_id so the server can match it."""
    provider = _make_provider()
    msg = Message(
        role=MessageRole.TOOL,
        content="result text",
        metadata={"tool_call_id": "call_1"},
    )
    formatted = provider._format_message(msg)
    assert formatted["tool_call_id"] == "call_1"
    assert formatted["role"] == "tool"


def test_format_message_assistant_without_tool_calls_unchanged():
    """Normal assistant message (no tool_calls metadata) is unaffected."""
    provider = _make_provider()
    msg = Message(role=MessageRole.ASSISTANT, content="hello")
    formatted = provider._format_message(msg)
    assert formatted["content"] == "hello"
    assert "tool_calls" not in formatted


# ---------------------------------------------------------------------------
# (b) TUI worker history-assembly: empty-text tool turn keeps assistant message
# ---------------------------------------------------------------------------

class _ToolProvider:
    """Two-turn scripted provider: first turn is pure tool call (no text),
    second turn is a plain text reply.  Mirrors the failing scenario.

    Stores a snapshot of the history received on each call so we can
    assert on what was assembled between turns.
    """

    model = "fake-model"
    base_url = "http://fake.local"

    def __init__(self):
        self._call_count = 0
        self.received_histories: List[List[LLMMessage]] = []

    def is_available(self) -> bool:
        return True

    def supports_tool_calling(self) -> bool:
        return True

    def stream_turn(self, messages, tools=None, **kwargs):
        self._call_count += 1
        self.received_histories.append(list(messages))
        if self._call_count == 1:
            # First turn: NO text, pure tool call
            yield StreamEvent(
                kind="tool_calls",
                tool_calls=[{"id": "call_99", "name": "list_tags", "arguments": {}}],
            )
            yield StreamEvent(kind="done", finish_reason="tool_calls")
        else:
            # Second turn: plain reply
            yield StreamEvent(kind="text", text="Done!")
            yield StreamEvent(kind="done", finish_reason="stop")

    def format_tool_result_message(
        self, name: str, result: str, tool_call_id: Optional[str] = None
    ) -> LLMMessage:
        msg = LLMMessage(role=LLMMessageRole.TOOL, content=str(result))
        if tool_call_id:
            msg.metadata = {"tool_call_id": tool_call_id}
        return msg


@pytest.mark.asyncio
async def test_empty_text_tool_turn_appends_assistant_message(tmp_path, monkeypatch):
    """An assistant turn with NO text but with tool_calls must still put an
    assistant LLMMessage into history (carrying metadata.tool_calls) BEFORE
    the TOOL-role result messages.

    Before the fix the assistant message was silently dropped when turn_text
    was empty, leaving orphan TOOL messages - strict OpenAI endpoints 400.

    We verify by checking the history the provider receives on turn 2; it
    must contain an ASSISTANT message with tool_calls metadata preceding a
    TOOL message with a matching tool_call_id.
    """
    from ctk.core.database import ConversationDB
    from ctk.tui.app import CTKApp

    db = ConversationDB(str(tmp_path / "db"))
    provider = _ToolProvider()
    app = CTKApp(db=db, provider=provider, enable_tools=True)

    monkeypatch.setattr(app, "_execute_tool", lambda name, args: "tool-result")

    try:
        async with app.run_test() as pilot:
            await pilot.pause()

            user_msg = app._append_user_message("ping")
            app._turn_active = True
            app.main.set_streaming(True)
            app._active_worker = app._chat_worker_with_tools(user_msg.id)

            for _ in range(200):
                await pilot.pause(0.05)
                if not app._turn_active:
                    break

            assert app._turn_active is False, "turn must complete"

    finally:
        db.close()

    # The provider must have been called twice (tool turn + final answer).
    assert provider._call_count == 2, (
        f"Expected 2 calls to stream_turn, got {provider._call_count}"
    )

    # The history fed into the second turn must contain an ASSISTANT message
    # with tool_calls metadata BEFORE the TOOL-role result message.
    second_history = provider.received_histories[1]
    assistant_msgs = [
        m for m in second_history if m.role == LLMMessageRole.ASSISTANT
    ]
    assert assistant_msgs, (
        "No assistant LLMMessage was appended to history for the empty-text tool turn. "
        "Strict OpenAI servers will 400 because TOOL messages have no preceding "
        "assistant tool_calls."
    )

    last_assistant = assistant_msgs[-1]
    assert last_assistant.metadata is not None, (
        "Assistant message for tool turn must carry metadata"
    )
    assert "tool_calls" in last_assistant.metadata, (
        "Assistant message must carry tool_calls in metadata"
    )
    tc = last_assistant.metadata["tool_calls"][0]
    assert tc["id"] == "call_99", f"Expected call_99, got {tc['id']!r}"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "list_tags"

    # The TOOL result must come AFTER the assistant message
    asst_idx = next(
        i
        for i, m in enumerate(second_history)
        if m.role == LLMMessageRole.ASSISTANT
        and m.metadata
        and "tool_calls" in m.metadata
    )
    tool_msgs = [
        (i, m)
        for i, m in enumerate(second_history)
        if m.role == LLMMessageRole.TOOL
    ]
    assert tool_msgs, "expected at least one TOOL message in history"
    for tool_idx, tool_msg in tool_msgs:
        assert tool_idx > asst_idx, (
            "TOOL message must come after the assistant tool_calls message"
        )
        assert tool_msg.metadata and tool_msg.metadata.get("tool_call_id") == "call_99"
