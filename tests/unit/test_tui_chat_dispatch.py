"""Regression tests for the TUI chat worker -> UI message dispatch.

These guard the bug where worker-to-UI Textual messages named with a leading
underscore (e.g. ``_ChatDone``) derive a double-underscore handler name
(``on__chat_done``) that never matches the defined handler (``on_chat_done``),
so the assistant reply never renders and the turn never clears (the chat looks
permanently stuck). The whole chat-worker path previously had no coverage.
"""

from __future__ import annotations

import inspect

import pytest
from textual.message import Message as TextualMessage

from ctk.core.database import ConversationDB
from ctk.core.models import MessageRole
from ctk.llm.base import ChatResponse
from ctk.llm.base import Message as LLMMessage
from ctk.llm.base import MessageRole as LLMMessageRole
from ctk.llm.base import StreamEvent
from ctk.tui import app as app_module
from ctk.tui.app import CTKApp


pytestmark = [pytest.mark.unit]


def _app_message_classes():
    """Every Textual Message subclass defined in ctk.tui.app itself."""
    return [
        obj
        for _, obj in inspect.getmembers(app_module, inspect.isclass)
        if issubclass(obj, TextualMessage) and obj.__module__ == "ctk.tui.app"
    ]


def test_worker_messages_have_matching_handlers():
    """Each app-level message must derive a handler_name that exists on CTKApp.

    Textual derives ``on_`` + camel_to_snake(class name); a leading underscore
    yields ``on__...`` which silently matches nothing. Name-agnostic so it fails
    while the classes are underscore-prefixed and passes once they are renamed.
    """
    handlers = {
        name
        for name, _ in inspect.getmembers(CTKApp, predicate=callable)
        if name.startswith("on_")
    }
    classes = _app_message_classes()
    assert classes, "expected ctk.tui.app to define Textual Message subclasses"
    offenders = [
        (cls.__name__, cls.handler_name)
        for cls in classes
        if cls.handler_name not in handlers
    ]
    assert not offenders, (
        "Message classes whose derived handler_name has no matching handler on "
        f"CTKApp (their events are silently dropped, so chat never renders): {offenders}"
    )


class _FakeProvider:
    """Synchronous stand-in: returns a fixed reply, no tool calls."""

    model = "fake-model"
    base_url = "http://fake.local"

    def is_available(self) -> bool:
        return True

    def supports_tool_calling(self) -> bool:
        return True

    def chat(self, messages, **kwargs):
        return ChatResponse(
            content="PONG-REPLY",
            model="fake-model",
            finish_reason="stop",
            tool_calls=None,
        )

    def stream_chat(self, messages, **kwargs):
        yield "PONG-REPLY"

    def stream_turn(self, messages, tools=None, **kwargs):
        # Worker now consumes stream_turn; yield a minimal scripted turn.
        yield StreamEvent(kind="text", text="PONG-REPLY")
        yield StreamEvent(kind="done", finish_reason="stop")

    def format_tool_result_message(self, name, result, tool_call_id=None):
        return LLMMessage(role=LLMMessageRole.USER, content=str(result))


async def _wait_turn_done(application, pilot, max_steps: int = 100) -> None:
    for _ in range(max_steps):
        await pilot.pause(0.05)
        if not application._turn_active:
            return


def test_execute_tool_routes_network_by_provider(monkeypatch, tmp_path):
    import ctk.core.network_tools as nt
    from ctk.core.database import ConversationDB
    from ctk.tui.app import CTKApp

    called = {}

    def fake_exec(db, name, args):
        called["name"] = name
        return "ok"

    monkeypatch.setattr(nt, "execute_network_tool", fake_exec)
    db = ConversationDB(str(tmp_path / "db"))
    try:
        app = CTKApp(db=db, provider=None, enable_tools=True)
        assert (
            app._execute_tool("find_similar_conversations", {"conversation_id": "x"})
            == "ok"
        )
        assert called["name"] == "find_similar_conversations"
        assert not hasattr(CTKApp, "_NETWORK_TOOL_NAMES")
    finally:
        db.close()


@pytest.mark.asyncio
async def test_tool_chat_turn_renders_reply_and_clears_turn(tmp_path):
    """The tool-enabled worker must render the assistant reply and end the turn.

    With the dispatch bug, on_chat_assistant_text and on_chat_done never fire:
    the reply is absent and _turn_active stays True (input read-only forever).
    """
    db = ConversationDB(str(tmp_path / "db"))
    application = CTKApp(db=db, provider=_FakeProvider(), enable_tools=True)
    try:
        async with application.run_test() as pilot:
            await pilot.pause()
            user_msg = application._append_user_message("ping")
            application._turn_active = True
            assert application.main is not None
            application.main.set_streaming(True)
            application._chat_worker_with_tools(user_msg.id)

            await _wait_turn_done(application, pilot)

            assert (
                application._turn_active is False
            ), "on_chat_done never fired: the turn never cleared (chat is stuck)"
            assistant_texts = [
                m.content.text
                for m in application._current_tree.message_map.values()
                if m.role == MessageRole.ASSISTANT
            ]
            assert (
                "PONG-REPLY" in assistant_texts
            ), "on_chat_assistant_text never fired: the reply was not rendered"
    finally:
        db.close()
