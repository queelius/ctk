"""Top-level Textual app for ``ctk tui``.

Composes the sidebar conversation list and the chat main pane, wires key
bindings, and runs LLM streaming in a worker so the UI stays responsive.

Design notes:

* The sidebar is the source of truth for "which conversation is open".
  Selecting a row in the sidebar triggers ``_open_conversation`` which
  reloads from the DB.
* Chat streaming runs in a Textual worker (``@work``) using the provider's
  ``stream_chat`` iterator. Tokens post messages back to the main thread
  which appends them to a live assistant bubble.
* On stream completion the full conversation tree is saved back to the
  DB, the sidebar is refreshed to surface the new ``updated_at``, and
  the newly-modified conversation is re-selected.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message as TextualMessage
from textual.widgets import DataTable, Footer, Header, Input, Static

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)
from ctk.llm.base import LLMProvider
from ctk.llm.base import Message as LLMMessage
from ctk.llm.base import MessageRole as LLMMessageRole
from ctk.tui.main_pane import ChatInput, MainPane, MessageBubble
from ctk.tui.sidebar import ConversationList


class _StreamToken(TextualMessage):
    """Internal message posted for each streamed assistant token."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class _StreamDone(TextualMessage):
    """Internal message posted when a stream finishes (or errors)."""

    def __init__(self, error: Optional[str] = None) -> None:
        super().__init__()
        self.error = error


class CTKApp(App):
    """Full-screen ctk browse + chat UI."""

    CSS_PATH = "styles.tcss"
    TITLE = "ctk"
    SUB_TITLE = "conversations"

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("slash", "focus_search", "search"),
        Binding("escape", "dismiss_search", "cancel search", show=False),
        Binding("ctrl+r", "refresh", "refresh"),
        Binding("ctrl+s", "toggle_star", "star"),
        Binding("ctrl+n", "new_conversation", "new chat"),
    ]

    def __init__(
        self,
        db: ConversationDB,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        super().__init__()
        self.db = db
        self.provider = provider
        self.sidebar: Optional[ConversationList] = None
        self.main: Optional[MainPane] = None
        self._search_input: Optional[Input] = None
        self._status: Optional[Static] = None
        self._current_tree: Optional[ConversationTree] = None
        self._streaming_bubble: Optional[MessageBubble] = None
        self._streaming_buffer: str = ""

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            self.sidebar = ConversationList(self.db)
            yield self.sidebar
            self.main = MainPane()
            yield self.main
        self._search_input = Input(placeholder="search…", id="search-overlay")
        yield self._search_input
        self._status = Static(self._status_text(), id="status")
        yield self._status
        yield Footer()

    def on_mount(self) -> None:
        assert self.sidebar is not None
        self.sidebar.focus_table()
        self._refresh_status()

    # ------------------------------------------------------------------
    # Sidebar selection -> main pane
    # ------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        # Cursor motion in the sidebar updates the main pane eagerly so
        # the user sees a preview without pressing Enter.
        self._open_selected()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._open_selected()
        assert self.main is not None
        self.main.input.focus()

    def _open_selected(self) -> None:
        assert self.sidebar is not None
        assert self.main is not None
        conv_id = self.sidebar.selected_conversation_id()
        if not conv_id:
            return
        tree = self.db.load_conversation(conv_id)
        if tree is None:
            self.main.messages.show_empty("(conversation not found)")
            self._current_tree = None
            return
        self._current_tree = tree
        self.main.messages.show_conversation(tree)
        self.main.set_header(self._header_for(tree))
        self._refresh_status()

    def _header_for(self, tree: ConversationTree) -> str:
        bits = [tree.title or "(untitled)"]
        meta = tree.metadata
        if meta and meta.model:
            bits.append(meta.model)
        msg_count = len(tree.message_map)
        bits.append(f"{msg_count} msg")
        return "  •  ".join(bits)

    # ------------------------------------------------------------------
    # Search overlay
    # ------------------------------------------------------------------

    def action_focus_search(self) -> None:
        assert self._search_input is not None
        self._search_input.add_class("visible")
        self._search_input.focus()

    def action_dismiss_search(self) -> None:
        assert self._search_input is not None
        self._search_input.remove_class("visible")
        self._search_input.value = ""
        if self.sidebar:
            self.sidebar.refresh_list()
            self.sidebar.focus_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input is not self._search_input:
            return
        query = (event.value or "").strip()
        assert self.sidebar is not None
        self.sidebar.refresh_list(search=query or None)
        self._search_input.remove_class("visible")
        self.sidebar.focus_table()

    # ------------------------------------------------------------------
    # Chat input -> LLM streaming
    # ------------------------------------------------------------------

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        if self.provider is None:
            self.notify("No LLM provider configured — run `ctk tui` with one set.",
                        severity="warning")
            return
        if self._streaming_bubble is not None:
            self.notify("A response is still streaming.", severity="warning")
            return

        assert self.main is not None

        user_msg = self._append_user_message(event.text)
        # Start an empty assistant bubble that the stream worker fills in.
        assistant_msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.ASSISTANT,
            content=MessageContent(text=""),
            parent_id=user_msg.id,
            timestamp=datetime.now(),
        )
        if self._current_tree is not None:
            self._current_tree.add_message(assistant_msg)

        self._streaming_buffer = ""
        bubble = MessageBubble(assistant_msg)
        self._streaming_bubble = bubble
        self.main.messages.mount(Static(Text("bot", style="bold green"),
                                        classes="message-role"))
        self.main.messages.mount(bubble)
        self.main.messages.scroll_end(animate=False)
        self.main.set_streaming(True)
        self._refresh_status()

        self._stream_worker(self._llm_history_for(self._current_tree))

    def _append_user_message(self, text: str) -> Message:
        assert self.main is not None
        # Ensure we always have a tree — if nothing is selected, create one.
        if self._current_tree is None:
            tree = ConversationTree(
                id=str(uuid.uuid4()),
                title=text[:60],
                metadata=ConversationMetadata(
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    model=getattr(self.provider, "model", None) if self.provider else None,
                ),
            )
            self._current_tree = tree
            self.main.set_header(self._header_for(tree))

        parent_id = None
        if self._current_tree.message_map:
            path = self._current_tree.get_longest_path()
            if path:
                parent_id = path[-1].id

        user_msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.USER,
            content=MessageContent(text=text),
            parent_id=parent_id,
            timestamp=datetime.now(),
        )
        self._current_tree.add_message(user_msg)
        self.main.messages.append_message(user_msg)
        return user_msg

    def _llm_history_for(self, tree: Optional[ConversationTree]) -> List[LLMMessage]:
        if tree is None:
            return []
        # Map ctk core MessageRole → llm.base.MessageRole. We only pass
        # user/assistant/system upstream — tool roles need explicit handling
        # and are out of scope for this MVP.
        role_map = {
            MessageRole.USER: LLMMessageRole.USER,
            MessageRole.ASSISTANT: LLMMessageRole.ASSISTANT,
            MessageRole.SYSTEM: LLMMessageRole.SYSTEM,
        }
        history: List[LLMMessage] = []
        for msg in tree.get_longest_path():
            llm_role = role_map.get(msg.role)
            if llm_role is None:
                continue  # skip tool/function/tool_result roles in MVP
            body = (
                msg.content.get_text()
                if hasattr(msg.content, "get_text")
                else str(msg.content)
            )
            if not body:
                continue
            history.append(LLMMessage(role=llm_role, content=body))
        return history

    @work(thread=True, exclusive=True)
    def _stream_worker(self, history: List[LLMMessage]) -> None:
        """Worker thread: pulls tokens from ``stream_chat`` and posts them."""
        try:
            assert self.provider is not None
            for chunk in self.provider.stream_chat(history):
                if chunk:
                    self.post_message(_StreamToken(chunk))
        except Exception as exc:  # pragma: no cover — surfaces any provider error
            self.post_message(_StreamDone(error=str(exc)))
            return
        self.post_message(_StreamDone())

    def on_stream_token(self, event: _StreamToken) -> None:
        # Custom Textual messages dispatch to ``on_<snake_case_name>``.
        if self._streaming_bubble is None:
            return
        self._streaming_buffer += event.text
        self._update_streaming_bubble(self._streaming_buffer)

    def on_stream_done(self, event: _StreamDone) -> None:
        assert self.main is not None
        self.main.set_streaming(False)
        if event.error:
            self.notify(f"Stream error: {event.error}", severity="error")
        # Persist the final assistant content into the tree and save.
        if self._streaming_bubble is not None and self._current_tree is not None:
            # The bubble's message is the last assistant message we added.
            final_text = self._streaming_buffer
            path = self._current_tree.get_longest_path()
            if path and path[-1].role == MessageRole.ASSISTANT:
                path[-1].content = MessageContent(text=final_text)
            self._safe_save(self._current_tree)

        self._streaming_bubble = None
        self._streaming_buffer = ""
        if self.sidebar is not None:
            self.sidebar.refresh_list()
        self._refresh_status()

    def _update_streaming_bubble(self, text: str) -> None:
        assert self.main is not None
        if self._streaming_bubble is None:
            return
        from rich.markdown import Markdown

        # Replace the bubble's renderable as tokens arrive.
        self._streaming_bubble.update(Markdown(text))
        self.main.messages.scroll_end(animate=False)

    def _safe_save(self, tree: ConversationTree) -> None:
        try:
            self.db.save_conversation(tree)
        except Exception as exc:  # pragma: no cover
            self.notify(f"Failed to save: {exc}", severity="error")

    # ------------------------------------------------------------------
    # Misc actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        if self.sidebar is not None:
            self.sidebar.refresh_list()
        self._refresh_status()

    def action_toggle_star(self) -> None:
        if self.sidebar is None or self._current_tree is None:
            return
        conv_id = self._current_tree.id
        # Flip based on current metadata.
        starred = bool(
            getattr(self._current_tree.metadata, "starred_at", None)
        )
        self.db.star_conversation(conv_id, star=not starred)
        self.sidebar.refresh_list()

    def action_new_conversation(self) -> None:
        # Drop the current tree; next message will seed a new one.
        self._current_tree = None
        if self.main is not None:
            self.main.messages.show_empty("New conversation — type a message to begin.")
            self.main.set_header("new conversation")
            self.main.input.focus()

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _status_text(self) -> Text:
        text = Text()
        if self.provider is not None:
            text.append("model: ", style="dim")
            text.append(
                getattr(self.provider, "model", "?") or "?", style="bold magenta"
            )
        else:
            text.append("browse-only (no provider)", style="dim")
        if self._current_tree is not None:
            text.append("   ", style="")
            text.append(self._current_tree.id[:8], style="dim")
        if self._streaming_bubble is not None:
            text.append("   streaming…", style="bold yellow")
        return text

    def _refresh_status(self) -> None:
        if self._status is not None:
            self._status.update(self._status_text())


def run(
    db_path: str,
    provider: Optional[LLMProvider] = None,
) -> None:
    """Launch the Textual TUI against ``db_path``.

    This is a thin wrapper kept out of ``__init__`` so importing
    ``ctk.tui`` doesn't eagerly open the DB.
    """
    db = ConversationDB(db_path)
    try:
        app = CTKApp(db=db, provider=provider)
        app.run()
    finally:
        db.close()
