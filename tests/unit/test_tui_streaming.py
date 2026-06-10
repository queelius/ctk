"""Pilot tests for the streaming chat turn: thinking block, live bubbles,
elapsed indicator, cancellation, and in-stream errors."""

from __future__ import annotations

import pytest
from textual.widgets import Static

from ctk.core.database import ConversationDB
from ctk.core.models import MessageRole
from ctk.llm.base import Message as LLMMessage
from ctk.llm.base import MessageRole as LLMMessageRole
from ctk.llm.base import StreamEvent
from ctk.tui.app import CTKApp
from ctk.tui.main_pane import ThinkingBlock

pytestmark = [pytest.mark.unit]


class TestThinkingBlock:
    def test_appends_and_reports_text(self):
        block = ThinkingBlock()
        block.append_reasoning("step one ")
        block.append_reasoning("step two")
        assert block.reasoning_text == "step one step two"
        assert not block.folded

    def test_fold_and_toggle(self):
        block = ThinkingBlock()
        block.append_reasoning("hmm")
        block.fold()
        assert block.folded
        block.action_expand_collapse()
        assert not block.folded


class ScriptedProvider:
    """stream_turn yields scripted event turns; each call pops the next turn."""

    model = "scripted"
    base_url = "http://fake.local"

    def __init__(self, turns):
        self._turns = list(turns)

    def is_available(self):
        return True

    def supports_tool_calling(self):
        return True

    def stream_turn(self, messages, tools=None, **kwargs):
        for event in self._turns.pop(0):
            yield event

    def format_tool_result_message(self, name, result, tool_call_id=None):
        return LLMMessage(role=LLMMessageRole.USER, content=str(result))


async def _drive_turn(app, pilot, text="ping", max_steps=200):
    user_msg = app._append_user_message(text)
    app._turn_active = True
    app.main.set_streaming(True)
    app._active_worker = app._chat_worker_with_tools(user_msg.id)
    for _ in range(max_steps):
        await pilot.pause(0.05)
        if not app._turn_active:
            break


def _assistant_messages(app):
    return [
        m
        for m in app._current_tree.message_map.values()
        if m.role == MessageRole.ASSISTANT
    ]


@pytest.mark.asyncio
async def test_text_streams_and_persists(tmp_path):
    provider = ScriptedProvider(
        [
            [
                StreamEvent(kind="text", text="Hel"),
                StreamEvent(kind="text", text="lo"),
                StreamEvent(kind="done", finish_reason="stop"),
            ]
        ]
    )
    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            msgs = _assistant_messages(app)
            assert [m.content.text for m in msgs] == ["Hello"]
            assert app._turn_active is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_reasoning_streams_folds_on_text_and_persists(tmp_path):
    provider = ScriptedProvider(
        [
            [
                StreamEvent(kind="reasoning", text="thinking..."),
                StreamEvent(kind="text", text="Answer"),
                StreamEvent(kind="done", finish_reason="stop"),
            ]
        ]
    )
    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            from ctk.tui.main_pane import ThinkingBlock

            blocks = list(app.query(ThinkingBlock))
            assert len(blocks) == 1
            assert blocks[0].folded  # folded when the answer began
            msg = _assistant_messages(app)[0]
            assert msg.content.text == "Answer"
            assert len(msg.content.reasoning) == 1
            assert msg.content.reasoning[0].text == "thinking..."
    finally:
        db.close()


@pytest.mark.asyncio
async def test_reasoning_only_turn_stays_expanded_and_is_the_reply(tmp_path):
    provider = ScriptedProvider(
        [
            [
                StreamEvent(kind="reasoning", text="only thoughts"),
                StreamEvent(kind="done", finish_reason="stop"),
            ]
        ]
    )
    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            from ctk.tui.main_pane import ThinkingBlock

            blocks = list(app.query(ThinkingBlock))
            assert len(blocks) == 1
            assert not blocks[0].folded  # the reasoning IS the reply
            msg = _assistant_messages(app)[0]
            assert msg.content.text == "only thoughts"  # never-blank fallback
            assert msg.content.reasoning[0].text == "only thoughts"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_tool_loop_streams_two_turns(tmp_path, monkeypatch):
    provider = ScriptedProvider(
        [
            [
                StreamEvent(kind="reasoning", text="need a tool"),
                StreamEvent(
                    kind="tool_calls",
                    tool_calls=[{"id": "t1", "name": "list_tags", "arguments": {}}],
                ),
                StreamEvent(kind="done", finish_reason="tool_calls"),
            ],
            [
                StreamEvent(kind="text", text="Done!"),
                StreamEvent(kind="done", finish_reason="stop"),
            ],
        ]
    )
    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    monkeypatch.setattr(app, "_execute_tool", lambda name, args: "tool-ok")
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            texts = [m.content.text for m in _assistant_messages(app)]
            assert "Done!" in texts
            assert app._turn_active is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_error_renders_in_transcript(tmp_path):
    class ExplodingProvider(ScriptedProvider):
        def stream_turn(self, messages, tools=None, **kwargs):
            raise RuntimeError("endpoint exploded")
            yield  # pragma: no cover

    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=ExplodingProvider([]), enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            assert app._turn_active is False
            error_nodes = list(app.query(".message-error"))
            assert error_nodes, "provider error must render in the transcript"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_escape_cancels_inflight_turn(tmp_path):
    class SlowProvider(ScriptedProvider):
        def stream_turn(self, messages, tools=None, **kwargs):
            import time as _t

            for i in range(200):
                _t.sleep(0.02)
                yield StreamEvent(kind="reasoning", text=f"step{i} ")
            yield StreamEvent(kind="done", finish_reason="stop")

    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=SlowProvider([]), enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            user_msg = app._append_user_message("ping")
            app._turn_active = True
            app.main.set_streaming(True)
            app._active_worker = app._chat_worker_with_tools(user_msg.id)
            await pilot.pause(0.3)  # let some reasoning stream
            app.action_cancel_turn_or_dismiss()
            for _ in range(100):
                await pilot.pause(0.05)
                if not app._turn_active:
                    break
            assert app._turn_active is False
            cancelled_nodes = [
                n
                for n in app.query(Static)
                if "cancelled" in str(getattr(n, "content", ""))
            ]
            assert cancelled_nodes, "a (cancelled) marker must be appended"
    finally:
        db.close()
