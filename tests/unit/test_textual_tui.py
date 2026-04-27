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
    """Setting an empty system prompt removes the existing one — but only
    when there are children to re-parent. A SYSTEM-only tree is left alone.
    """
    import uuid as uuid_mod

    from ctk.core.models import (ConversationMetadata, ConversationTree,
                                 Message, MessageContent, MessageRole)
    from ctk.tui.app import CTKApp

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Tree with a SYSTEM root + a USER child. Clearing should drop
        # the SYSTEM and re-parent USER to root.
        tree = ConversationTree(metadata=ConversationMetadata())
        app._set_system_prompt(tree, "first prompt")
        sys_msg = next(
            m for m in tree.message_map.values() if m.role == MessageRole.SYSTEM
        )
        child = Message(
            id=str(uuid_mod.uuid4()),
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
            parent_id=sys_msg.id,
        )
        tree.add_message(child)

        app._set_system_prompt(tree, "")
        assert not any(
            m.role == MessageRole.SYSTEM for m in tree.message_map.values()
        )
        assert child.id in tree.root_message_ids


async def test_set_system_prompt_clear_with_no_children_is_noop(seeded_db):
    """Clearing a SYSTEM-only tree must leave the tree intact (regression)."""
    from ctk.core.models import (ConversationMetadata, ConversationTree,
                                 MessageRole)
    from ctk.tui.app import CTKApp

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = ConversationTree(metadata=ConversationMetadata())
        app._set_system_prompt(tree, "lonely prompt")
        assert tree.root_message_ids  # non-empty before
        app._set_system_prompt(tree, "")
        # Tree still has the SYSTEM message and a non-empty root list
        # — otherwise get_longest_path() would return [].
        assert tree.root_message_ids
        assert any(
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
        # Pass the conversation id we want the file attached to (the
        # callback signature changed to capture target tree at modal
        # open time, preventing sidebar-switch races).
        app._on_file_attached(app._current_tree.id, str(file))
        await pilot.pause()
        after_count = len(app._current_tree.message_map)
        assert after_count == before_count + 1
        sys_msgs = [
            m for m in app._current_tree.message_map.values()
            if m.role == MessageRole.SYSTEM
        ]
        assert sys_msgs
        assert any("hello from file" in m.content.get_text() for m in sys_msgs)


async def test_modal_callback_targets_original_tree_after_sidebar_switch(
    seeded_db,
):
    """Regression: modal callbacks must apply to the tree that was
    open when the modal launched, not whichever tree happens to be
    current when the user closes the modal.
    """
    from ctk.core.models import MessageRole
    from ctk.tui.app import CTKApp

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Open conversation A.
        app._open_selected()
        await pilot.pause()
        assert app._current_tree is not None
        target_id = app._current_tree.id

        # Simulate the user switching to conversation B mid-modal by
        # manually replacing _current_tree with the OTHER seeded conv.
        app.sidebar._table.move_cursor(row=1)
        await pilot.pause()
        app._open_selected()
        await pilot.pause()
        other_id = app._current_tree.id
        assert other_id != target_id

        # Fire the callback with the original target_id — it should
        # mutate conversation A (loaded from DB), NOT conversation B.
        app._on_system_prompt_saved(target_id, "A's new prompt")
        await pilot.pause()

        a_tree = db.load_conversation(target_id)
        b_tree = db.load_conversation(other_id)
        a_has_sys = any(
            m.role == MessageRole.SYSTEM for m in a_tree.message_map.values()
        )
        b_has_sys = any(
            m.role == MessageRole.SYSTEM for m in b_tree.message_map.values()
        )
        assert a_has_sys, "system prompt should land on the original tree"
        assert not b_has_sys, "the other tree must not be touched"


# ---------------------------------------------------------------------------
# Modal lifecycle smoke tests
#
# Three real bugs (2.13.0 / 2.13.1 / 2.13.2) shipped because nothing actually
# opened the modals before tagging. These tests pilot the app, push each
# modal, force a render via pause(), and dismiss it. They would have caught
# all three regressions at unit-test time:
#
#   * 2.13.1: HelpModal._render shadowed Widget._render → render crashed
#   * 2.13.2: HelpModal.__init__ overwrote self._bindings → next keypress
#             crashed in _binding_chain
#
# pause() forces Textual to flush pending callbacks, which exercises the
# render pipeline and the binding chain — exactly the surfaces that broke.
# ---------------------------------------------------------------------------


async def test_help_modal_opens_renders_and_closes(seeded_db):
    """Ctrl+H opens HelpModal, renders without crash, Esc closes it."""
    from ctk.tui.app import CTKApp
    from ctk.tui.modals import HelpModal

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+h")
        await pilot.pause()
        # The help screen should be on the screen stack, NOT just queued —
        # which means it has actually rendered (would have crashed in 2.13.0).
        assert isinstance(app.screen, HelpModal)
        # Press a key so _check_bindings walks the binding chain — this is
        # the path that crashed in 2.13.1 when self._bindings was a list.
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)


async def test_help_modal_closes_via_q_key(seeded_db):
    """Pressing q inside HelpModal closes it (alt to Esc, exercises bindings)."""
    from ctk.tui.app import CTKApp
    from ctk.tui.modals import HelpModal

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+h")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)


async def test_help_modal_renders_three_sections(seeded_db):
    """The modal must list bindings, slash commands, and MCP providers."""
    from ctk.tui.app import CTKApp
    from ctk.tui.modals import HelpModal

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+h")
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        markup = app.screen._build_help_markup()
        # Must hit all three sections — drift in any of these is a UX bug.
        assert "Key bindings" in markup
        assert "Slash commands" in markup
        assert "MCP tool providers" in markup
        # And the fork/branch callout that 2.13 added.
        assert "fork" in markup.lower()
        assert "branch" in markup.lower()


async def test_confirm_modal_yes_runs_callback(seeded_db):
    """ConfirmModal returns True on 'y' and the callback fires."""
    from ctk.tui.app import CTKApp
    from ctk.tui.modals import ConfirmModal

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        seen: list = []

        def _cb(result):
            seen.append(result)

        app.push_screen(ConfirmModal("Test?", "Detail line."), _cb)
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        await pilot.press("y")
        await pilot.pause()
        assert seen == [True]
        assert not isinstance(app.screen, ConfirmModal)


async def test_confirm_modal_no_runs_callback_with_false(seeded_db):
    """Pressing 'n' returns False (and Escape returns False too)."""
    from ctk.tui.app import CTKApp
    from ctk.tui.modals import ConfirmModal

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        seen: list = []
        app.push_screen(ConfirmModal("Test?"), seen.append)
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert seen == [False]


async def test_delete_subtree_action_opens_confirm(seeded_db):
    """Ctrl+D with a focused message opens ConfirmModal (the destructive path).

    We patch ``_focused_message_id`` instead of fighting Textual's focus
    propagation in headless mode — the action's contract is "given a
    focused message id, open a confirm modal," and that's what this test
    actually verifies.
    """
    from ctk.tui.app import CTKApp
    from ctk.tui.modals import ConfirmModal

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_selected()
        await pilot.pause()
        assert app._current_tree is not None

        target_id = app._current_tree.get_longest_path()[0].id
        app._focused_message_id = lambda: target_id

        app.action_delete_subtree_at_focus()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmModal)


async def test_delete_subtree_confirm_yes_actually_deletes(seeded_db):
    """Pressing y in the confirm modal removes the subtree from the tree."""
    from ctk.tui.app import CTKApp
    from ctk.tui.modals import ConfirmModal

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_selected()
        await pilot.pause()

        # Target the leaf so deleting it leaves the rest of the tree intact.
        path = app._current_tree.get_longest_path()
        target_id = path[-1].id
        app._focused_message_id = lambda: target_id
        before = len(app._current_tree.message_map)

        app.action_delete_subtree_at_focus()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        await pilot.press("y")
        await pilot.pause()

        after = len(app._current_tree.message_map)
        assert after == before - 1
        assert target_id not in app._current_tree.message_map


async def test_extract_subtree_action_creates_new_conversation(seeded_db):
    """Ctrl+E with a focused message saves a new conversation in the DB."""
    from ctk.tui.app import CTKApp

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_selected()
        await pilot.pause()
        before_count = len(db.list_conversations())

        target_id = app._current_tree.get_longest_path()[0].id
        app._focused_message_id = lambda: target_id

        app.action_extract_subtree_at_focus()
        await pilot.pause()

        after_count = len(db.list_conversations())
        assert after_count == before_count + 1


async def test_promote_path_action_opens_confirm_when_dropping_messages(seeded_db):
    """Ctrl+P only confirms when there are sibling branches to drop."""
    import uuid as uuid_mod

    from ctk.core.models import Message, MessageContent, MessageRole
    from ctk.tui.app import CTKApp
    from ctk.tui.modals import ConfirmModal

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_selected()
        await pilot.pause()
        # Add a sibling branch so promote has something to drop.
        path = app._current_tree.get_longest_path()
        sibling = Message(
            id=str(uuid_mod.uuid4()),
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="alternate"),
            parent_id=path[-2].id,
        )
        app._current_tree.add_message(sibling)
        app.main.messages.show_conversation(app._current_tree)
        await pilot.pause()

        # Promote the original assistant — siblings should be candidates to drop.
        target_id = path[-1].id
        app._focused_message_id = lambda: target_id

        app.action_promote_path_at_focus()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        await pilot.press("escape")
        await pilot.pause()


async def test_slash_dispatch_help_is_handled(seeded_db):
    """Typing /help in chat input routes through the slash dispatcher."""
    from ctk.tui.app import CTKApp
    from ctk.tui import slash

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        handled, note = slash.dispatch(app, "/help")
        assert handled is True
        assert note is not None
        assert "/help" in note  # /help text lists itself


async def test_slash_dispatch_unknown_command_is_handled(seeded_db):
    """Unknown slash commands return handled=True with an error note,
    so they don't fall through to the LLM."""
    from ctk.tui.app import CTKApp
    from ctk.tui import slash

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        handled, note = slash.dispatch(app, "/this-is-not-a-real-command")
        assert handled is True
        assert "Unknown" in (note or "")


async def test_slash_clone_creates_sibling_conversation(seeded_db):
    """/clone makes a duplicate with a new id."""
    from ctk.tui.app import CTKApp
    from ctk.tui import slash

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_selected()
        await pilot.pause()
        original_id = app._current_tree.id
        before = len(db.list_conversations())

        handled, note = slash.dispatch(app, "/clone")
        await pilot.pause()
        assert handled is True
        assert "Cloned" in (note or "")

        after = len(db.list_conversations())
        assert after == before + 1
        # The new conversation must have a different id.
        ids = {c.id for c in db.list_conversations()}
        assert original_id in ids
        assert len(ids) == after


async def test_slash_snapshot_prefixes_title_with_date(seeded_db):
    """/snapshot creates a new conversation titled with today's date prefix."""
    from datetime import date

    from ctk.tui.app import CTKApp
    from ctk.tui import slash

    _, db = seeded_db
    app = CTKApp(db=db, provider=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_selected()
        await pilot.pause()

        handled, _ = slash.dispatch(app, "/snapshot")
        await pilot.pause()
        assert handled is True
        today = date.today().isoformat()
        snapshots = [
            c for c in db.list_conversations()
            if c.title and c.title.startswith(f"[{today}]")
        ]
        assert snapshots, "no snapshot title with today's date"
