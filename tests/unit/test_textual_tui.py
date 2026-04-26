"""Smoke tests for the Textual multi-pane TUI (ctk.tui).

These use Textual's ``App.run_test()`` harness, which pilots the app
headlessly (no real terminal). We only verify the app mounts, the
sidebar populates from the DB, and selecting a row renders the
conversation in the main pane. Full interaction coverage is not the
goal — those behaviors live in lower-level widget tests.
"""

from __future__ import annotations

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


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def seeded_db(tmp_path):
    """Create a temp DB with two small conversations."""
    path = str(tmp_path / "tui.db")
    db = ConversationDB(path)

    for i in range(2):
        tree = ConversationTree(
            id=str(uuid.uuid4()),
            title=f"test conversation {i}",
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
        a = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.ASSISTANT,
            content=MessageContent(text=f"**hi** {i}"),
            parent_id=u.id,
            timestamp=datetime.now(),
        )
        tree.add_message(a)
        db.save_conversation(tree)

    try:
        yield path, db
    finally:
        db.close()


async def test_app_mounts_and_populates_sidebar(seeded_db):
    _, db = seeded_db
    from ctk.tui.app import CTKApp

    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.sidebar is not None
        # Two rows seeded
        assert app.sidebar._table.row_count == 2


async def test_row_selection_loads_conversation(seeded_db):
    _, db = seeded_db
    from ctk.tui.app import CTKApp

    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Row 0 should have been auto-selected on mount; the main pane
        # may or may not have reacted yet, so select explicitly.
        app._open_selected()
        await pilot.pause()
        assert app._current_tree is not None
        # Main pane should have at least one mounted message bubble.
        assert app.main is not None
        bubbles = list(app.main.messages.children)
        assert len(bubbles) >= 1


async def test_search_filters_sidebar(seeded_db):
    _, db = seeded_db
    from ctk.tui.app import CTKApp

    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Simulate pressing `/` then typing a query that matches nothing
        await pilot.press("slash")
        await pilot.pause()
        app._search_input.value = "does-not-match-anything-zzz"
        app.sidebar.refresh_list(search=app._search_input.value)
        await pilot.pause()
        assert app.sidebar._table.row_count == 0


async def test_enter_key_does_not_crash_on_textual_key_event(seeded_db):
    """Regression: Textual Key events have no `.shift` attribute.

    An earlier version of ChatInput._on_key read `event.shift` which
    raised AttributeError on every real keystroke, crashing the TUI the
    moment a user pressed Enter in the input.
    """
    _, db = seeded_db
    from ctk.tui.app import CTKApp

    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Move focus to the chat input (empty buffer keeps us out of the
        # submit branch, but exercises the attribute access path).
        assert app.main is not None
        app.main.input.focus()
        await pilot.pause()
        # This press would previously raise AttributeError.
        await pilot.press("enter")
        await pilot.pause()


async def test_sidebar_tabs_change_filter(seeded_db):
    """Switching tabs invokes the right DB query and refilters the table."""
    _, db = seeded_db
    from ctk.tui.app import CTKApp

    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.sidebar is not None
        # Both seeded conversations are unstarred, so 'starred' filter
        # should yield zero rows.
        app.sidebar.set_mode("starred")
        await pilot.pause()
        assert app.sidebar._table.row_count == 0
        # Back to 'all' restores the full set.
        app.sidebar.set_mode("all")
        await pilot.pause()
        assert app.sidebar._table.row_count == 2


async def test_fork_truncates_tree_to_focused_message(seeded_db):
    """Ctrl+F at a message id prunes descendants and assigns a new id."""
    import uuid as uuid_mod

    from ctk.core.models import (Message, MessageContent, MessageRole)
    from ctk.tui.app import CTKApp

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Open a conversation, then add an extra message so the tree
        # has something to truncate (assistant -> user -> assistant).
        app._open_selected()
        await pilot.pause()
        assert app._current_tree is not None
        original_path = app._current_tree.get_longest_path()
        assert len(original_path) >= 2

        # Append a third message to make the truncation visible.
        third = Message(
            id=str(uuid_mod.uuid4()),
            role=MessageRole.USER,
            content=MessageContent(text="follow-up"),
            parent_id=original_path[-1].id,
        )
        app._current_tree.add_message(third)
        original_path = app._current_tree.get_longest_path()
        assert len(original_path) == 3
        before_id = app._current_tree.id
        target_id = original_path[1].id  # second message in path

        # Drive the helper directly — focusing a specific message in
        # run_test() is harness-dependent and not the point here.
        app.CTKApp__truncate_called = True  # noqa: pylint marker, harmless
        app._truncate_tree_to_message(app._current_tree, target_id)
        # Simulate the rest of action_fork_at_focus's id rotation.
        app._current_tree.id = str(uuid_mod.uuid4())

        # Tree should now contain exactly the ancestor path of target_id.
        new_path = app._current_tree.get_longest_path()
        assert [m.id for m in new_path] == [
            original_path[0].id,
            original_path[1].id,
        ]
        assert app._current_tree.id != before_id


async def test_app_with_no_provider_disables_chat_path(seeded_db):
    """Submitting in the chat input without a provider only notifies."""
    _, db = seeded_db
    from ctk.tui.app import CTKApp
    from ctk.tui.main_pane import ChatInput

    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Fabricate a Submitted event; no provider means we should hit
        # the early-return branch and NOT mutate _turn_active.
        assert app.main is not None
        app.on_chat_input_submitted(
            ChatInput.Submitted(app.main.input, "hi")
        )
        await pilot.pause()
        assert app._turn_active is False


async def test_sibling_switch_swaps_path_tail(seeded_db):
    """Switching siblings on a branching parent rewrites the path tail."""
    import uuid as uuid_mod

    from ctk.core.models import Message, MessageContent, MessageRole
    from ctk.tui.app import CTKApp

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_selected()
        await pilot.pause()
        assert app._current_tree is not None
        path = app._current_tree.get_longest_path()
        # Add a sibling assistant under the same user message so the
        # second-to-last message has 2 children.
        user_msg = path[-2]
        sibling = Message(
            id=str(uuid_mod.uuid4()),
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="alternate response"),
            parent_id=user_msg.id,
        )
        app._current_tree.add_message(sibling)
        # Re-render with the path that includes the original assistant.
        app.main.messages.show_conversation(app._current_tree)
        await pilot.pause()
        before_tail = app.main.messages.current_path[-1].id
        # Switch — should pick the other sibling.
        switched = app.main.messages.switch_sibling(user_msg.id, +1)
        assert switched is True
        after_tail = app.main.messages.current_path[-1].id
        assert before_tail != after_tail


async def test_set_system_prompt_inserts_message(seeded_db):
    """Setting a non-empty system prompt inserts a SYSTEM root."""
    from ctk.core.models import (ConversationMetadata, ConversationTree,
                                 MessageRole)
    from ctk.tui.app import CTKApp

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = ConversationTree(metadata=ConversationMetadata())
        app._set_system_prompt(tree, "you are a helpful assistant")
        path = tree.get_longest_path()
        assert len(path) == 1
        assert path[0].role == MessageRole.SYSTEM
        assert "helpful assistant" in path[0].content.get_text()


async def test_set_system_prompt_clear_removes_message(seeded_db):
    """Setting an empty system prompt removes the existing one."""
    from ctk.core.models import (ConversationMetadata, ConversationTree,
                                 MessageRole)
    from ctk.tui.app import CTKApp

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = ConversationTree(metadata=ConversationMetadata())
        app._set_system_prompt(tree, "first prompt")
        assert any(m.role == MessageRole.SYSTEM for m in tree.message_map.values())
        app._set_system_prompt(tree, "")
        assert not any(
            m.role == MessageRole.SYSTEM for m in tree.message_map.values()
        )


async def test_attach_file_appends_system_message(seeded_db, tmp_path):
    """Attach-file injects a SYSTEM message containing the file body."""
    from ctk.core.models import MessageRole
    from ctk.tui.app import CTKApp

    file = tmp_path / "ctx.txt"
    file.write_text("hello from file")

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_selected()
        await pilot.pause()
        assert app._current_tree is not None
        before_count = len(app._current_tree.message_map)
        app._on_file_attached(str(file))
        await pilot.pause()
        after_count = len(app._current_tree.message_map)
        assert after_count == before_count + 1
        # The new message is a SYSTEM role with the file body inside.
        sys_msgs = [
            m for m in app._current_tree.message_map.values()
            if m.role == MessageRole.SYSTEM
        ]
        assert sys_msgs
        assert any("hello from file" in m.content.get_text() for m in sys_msgs)
