"""Regression tests: a chat turn belongs to the conversation it started in.

Before 2.20.1 nothing bound an in-flight turn to its conversation. The worker
result handlers applied to whatever ``_current_tree`` was when they arrived, so
switching the sidebar (or pressing Ctrl+N) mid-turn lost the turn's messages or
filed the reply into the wrong conversation, and tree-mutating actions could
rewrite the conversation underneath its own streaming reply.

The provider here is gated: it streams a first token, then blocks on a
``threading.Event`` until the test releases it, so the test can act while the
turn is provably in flight.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)
from ctk.llm.base import Message as LLMMessage
from ctk.llm.base import MessageRole as LLMMessageRole
from ctk.llm.base import StreamEvent
from ctk.tui.app import CTKApp
from ctk.tui.modals import ConfirmModal

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

QUESTION = "question for A"
REPLY = "REPLY-A"


class GatedProvider:
    """Streams ``REP``, blocks until ``gate`` is set, then streams ``LY-A``."""

    model = "gated"
    base_url = "http://fake.local"

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.started = threading.Event()
        self.histories = []

    def is_available(self):
        return True

    def supports_tool_calling(self):
        return True

    def stream_turn(self, messages, tools=None, **kwargs):
        self.histories.append([m.content for m in messages])
        yield StreamEvent(kind="text", text=REPLY[:3])
        self.started.set()
        self.gate.wait(10)
        yield StreamEvent(kind="text", text=REPLY[3:])
        yield StreamEvent(kind="done", finish_reason="stop")

    def stream_chat(self, messages, **kwargs):
        self.histories.append([m.content for m in messages])
        yield REPLY[:3]
        self.started.set()
        self.gate.wait(10)
        yield REPLY[3:]

    def format_tool_result_message(self, name, result, tool_call_id=None):
        return LLMMessage(role=LLMMessageRole.USER, content=str(result))


def _seed(db: ConversationDB, n: int = 2) -> None:
    for i in range(n):
        tree = ConversationTree(
            id=str(uuid.uuid4()),
            title=f"conv {i}",
            metadata=ConversationMetadata(
                created_at=datetime.now(),
                updated_at=datetime.now(),
                model="test-model",
            ),
        )
        u = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.USER,
            content=MessageContent(text=f"hello {i}"),
            timestamp=datetime.now(),
        )
        tree.add_message(u)
        tree.add_message(
            Message(
                id=str(uuid.uuid4()),
                role=MessageRole.ASSISTANT,
                content=MessageContent(text=f"hi {i}"),
                parent_id=u.id,
                timestamp=datetime.now(),
            )
        )
        db.save_conversation(tree)


def _snapshot(tree: ConversationTree):
    return sorted(
        (m.id, m.role.value, m.content.text, m.parent_id)
        for m in tree.message_map.values()
    )


@pytest.fixture
def db(tmp_path):
    database = ConversationDB(str(tmp_path / "db"))
    _seed(database)
    try:
        yield database
    finally:
        database.close()


async def _open_row(app, pilot, row: int) -> str:
    app.sidebar._table.move_cursor(row=row)
    await pilot.pause()
    app._open_selected()
    await pilot.pause()
    return app._current_tree.id


async def _submit(app, pilot, text: str = QUESTION) -> None:
    app.main.input.focus()
    await pilot.pause()
    app.main.input.text = text
    await pilot.press("enter")


async def _wait(pilot, predicate, steps: int = 200) -> None:
    for _ in range(steps):
        if predicate():
            return
        await pilot.pause(0.02)
    raise AssertionError("condition never became true")


async def _start_turn_in_a(app, pilot, provider):
    """Open row 0 (A), submit QUESTION, wait until the turn is mid-stream."""
    await pilot.pause()
    a_id = await _open_row(app, pilot, 0)
    await _submit(app, pilot)
    await _wait(pilot, provider.started.is_set)
    await pilot.pause(0.05)
    assert app._turn_active
    return a_id


async def _finish_turn(app, pilot, provider) -> None:
    provider.gate.set()
    await _wait(pilot, lambda: not app._turn_active)
    await pilot.pause(0.05)


def _user_and_reply(tree: ConversationTree):
    users = [
        m
        for m in tree.message_map.values()
        if m.role == MessageRole.USER and m.content.text == QUESTION
    ]
    replies = [
        m
        for m in tree.message_map.values()
        if m.role == MessageRole.ASSISTANT and m.content.text == REPLY
    ]
    return users, replies


def _assert_turn_persisted(db: ConversationDB, conv_id: str) -> None:
    tree = db.load_conversation(conv_id)
    assert tree is not None, "the turn's conversation must be saved"
    users, replies = _user_and_reply(tree)
    assert len(users) == 1, "the user message must be persisted in its own conv"
    assert len(replies) == 1, "the reply must be persisted in its own conv"
    assert replies[0].parent_id == users[0].id, "reply must answer the user msg"


@pytest.mark.parametrize("tools", [True, False], ids=["tools", "no-tools"])
async def test_switching_conversation_mid_turn_keeps_turn_in_origin(db, tools):
    provider = GatedProvider()
    app = CTKApp(db=db, provider=provider, enable_tools=tools)
    try:
        async with app.run_test() as pilot:
            a_id = await _start_turn_in_a(app, pilot, provider)
            b_id = await _open_row(app, pilot, 1)
            assert b_id != a_id
            b_before = _snapshot(db.load_conversation(b_id))

            await _finish_turn(app, pilot, provider)

            _assert_turn_persisted(db, a_id)
            assert (
                _snapshot(db.load_conversation(b_id)) == b_before
            ), "conversation B must be untouched by A's turn"
            assert app._current_tree.id == b_id, "view must stay on B"
            assert _snapshot(app._current_tree) == b_before
            assert QUESTION in provider.histories[0]
    finally:
        provider.gate.set()


@pytest.mark.parametrize("tools", [True, False], ids=["tools", "no-tools"])
async def test_new_conversation_mid_turn_keeps_turn_in_origin(db, tools):
    provider = GatedProvider()
    app = CTKApp(db=db, provider=provider, enable_tools=tools)
    try:
        async with app.run_test() as pilot:
            a_id = await _start_turn_in_a(app, pilot, provider)
            app.action_new_conversation()
            await pilot.pause()
            assert app._current_tree is None

            await _finish_turn(app, pilot, provider)

            _assert_turn_persisted(db, a_id)
    finally:
        provider.gate.set()


@pytest.mark.parametrize("tools", [True, False], ids=["tools", "no-tools"])
async def test_reply_parent_survives_switching_away_and_back(db, tools):
    provider = GatedProvider()
    app = CTKApp(db=db, provider=provider, enable_tools=tools)
    try:
        async with app.run_test() as pilot:
            a_id = await _start_turn_in_a(app, pilot, provider)
            await _open_row(app, pilot, 1)
            # Back to A (row 0; the sidebar is not refreshed mid-turn).
            assert await _open_row(app, pilot, 0) == a_id
            users, _ = _user_and_reply(app._current_tree)
            assert users, "re-opening A mid-turn must show its pending user msg"
            # One live object: the displayed tree is the one the turn writes to.
            assert app._current_tree is app._turn.tree

            await _finish_turn(app, pilot, provider)

            _assert_turn_persisted(db, a_id)
    finally:
        provider.gate.set()


@pytest.mark.parametrize("tools", [True, False], ids=["tools", "no-tools"])
async def test_reply_parent_is_user_msg_even_if_tail_moves(db, tmp_path, tools):
    """An attachment appended mid-turn must not steal the reply's parent."""
    provider = GatedProvider()
    app = CTKApp(db=db, provider=provider, enable_tools=tools)
    attachment = tmp_path / "notes.txt"
    attachment.write_text("some notes")
    try:
        async with app.run_test() as pilot:
            a_id = await _start_turn_in_a(app, pilot, provider)
            app._on_file_attached(a_id, str(attachment))
            await pilot.pause()

            await _finish_turn(app, pilot, provider)

            _assert_turn_persisted(db, a_id)
    finally:
        provider.gate.set()


@pytest.mark.parametrize(
    "action",
    [
        "action_delete_subtree_at_focus",
        "action_promote_path_at_focus",
        "action_fork_at_focus",
        "action_branch_at_focus",
        "action_extract_subtree_at_focus",
    ],
)
async def test_tree_mutations_on_turn_tree_are_refused_mid_turn(db, action):
    provider = GatedProvider()
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    try:
        async with app.run_test() as pilot:
            a_id = await _start_turn_in_a(app, pilot, provider)
            # Give A a sibling branch so promote has something to drop.
            tree = app._current_tree
            root = tree.root_message_ids[0]
            tree.add_message(
                Message(
                    id=str(uuid.uuid4()),
                    role=MessageRole.ASSISTANT,
                    content=MessageContent(text="sibling"),
                    parent_id=root,
                    timestamp=datetime.now(),
                )
            )
            before = _snapshot(tree)
            conv_count = len(db.list_conversations())
            app._focused_message_id = lambda: root

            getattr(app, action)()
            await pilot.pause()

            assert not isinstance(app.screen, ConfirmModal), "must refuse, not ask"
            assert app._current_tree is tree
            assert tree.id == a_id, "fork/branch must not re-id the turn's tree"
            assert _snapshot(tree) == before
            assert len(db.list_conversations()) == conv_count

            await _finish_turn(app, pilot, provider)
            _assert_turn_persisted(db, a_id)
    finally:
        provider.gate.set()


async def test_tree_mutations_on_other_conversation_allowed_mid_turn(db):
    provider = GatedProvider()
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    try:
        async with app.run_test() as pilot:
            a_id = await _start_turn_in_a(app, pilot, provider)
            await _open_row(app, pilot, 1)
            target = app._current_tree.root_message_ids[0]
            app._focused_message_id = lambda: target

            app.action_delete_subtree_at_focus()
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            app.screen.dismiss(False)
            await pilot.pause()

            await _finish_turn(app, pilot, provider)
            _assert_turn_persisted(db, a_id)
    finally:
        provider.gate.set()
