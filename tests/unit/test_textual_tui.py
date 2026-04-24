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
