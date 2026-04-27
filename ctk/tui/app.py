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

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

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
from ctk.tui.modals import FilePathModal, SystemPromptModal
from ctk.tui.sidebar import ConversationList

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker → UI thread messages
#
# Workers run in threads via @work; they post these messages back to the UI
# thread so all widget mutations happen on the event loop. Each message
# class corresponds to one of the dispatch hooks below
# (``on_<class_snake_case>``).
# ---------------------------------------------------------------------------


class _StreamToken(TextualMessage):
    """One streamed assistant token (no-tools fast path only)."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class _StreamDone(TextualMessage):
    """A streaming response finished (or errored)."""

    def __init__(self, error: Optional[str] = None) -> None:
        super().__init__()
        self.error = error


class _ChatAssistantText(TextualMessage):
    """A complete assistant text block from a non-streaming response.

    Used in the tool-calling path where we can't stream because we need
    the full response to extract tool_calls. ``final`` indicates whether
    this is the last assistant turn (no further tool calls coming).
    """

    def __init__(self, text: str, final: bool) -> None:
        super().__init__()
        self.text = text
        self.final = final


class _ChatToolCall(TextualMessage):
    """A tool call about to execute or just completed.

    ``status`` is one of ``"started"``, ``"ok"``, ``"error"``. The
    UI renders a small panel for each call so the user can see what
    the model is doing.
    """

    def __init__(
        self,
        name: str,
        args: Dict[str, Any],
        status: str,
        result: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.args = args
        self.status = status
        self.result = result


class _ChatDone(TextualMessage):
    """The whole assistant turn (including any tool loops) finished."""

    def __init__(self, error: Optional[str] = None) -> None:
        super().__init__()
        self.error = error


def _truncate(text: str, limit: int) -> str:
    """Trim ``text`` to ``limit`` chars with an ellipsis suffix."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _short_args(args: Dict[str, Any]) -> str:
    """Render tool args as a compact ``key=value, …`` string for inline display."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 30:
            s = s[:27] + "…"
        parts.append(f"{k}={s}")
    return ", ".join(parts)


def _infer_media_root(db: ConversationDB) -> Optional[str]:
    """Guess where relative image URLs should be resolved against.

    ChatGPT exports place images in ``media/<uuid>.{png,webp}`` next to
    ``conversations.json``. After importing into a sibling
    ``conversations.db``, those relative URLs are still recorded in
    the DB. Returning the DB's parent directory makes the typical
    import-and-go workflow Just Work without the user setting anything.
    """
    import os as _os

    try:
        # ConversationDB exposes its underlying path via ``db_dir``;
        # fall back to ``db_path`` for older instances. Either way we
        # want the directory the DB lives in.
        path = getattr(db, "db_dir", None) or getattr(db, "db_path", None)
        if path is None:
            return None
        path = str(path)
        if _os.path.isdir(path):
            return path
        return _os.path.dirname(path) or None
    except Exception:
        return None


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
        Binding("ctrl+f", "fork_at_focus", "fork (truncate)"),
        Binding("ctrl+b", "branch_at_focus", "branch (preserve)"),
        Binding("left_square_bracket", "prev_sibling", "prev branch", show=False),
        Binding("right_square_bracket", "next_sibling", "next branch", show=False),
        Binding("ctrl+g", "edit_system_prompt", "system prompt"),
        Binding("ctrl+o", "attach_file", "attach file"),
    ]

    def __init__(
        self,
        db: ConversationDB,
        provider: Optional[LLMProvider] = None,
        enable_tools: bool = True,
        media_root: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.db = db
        self.provider = provider
        # Where to look for relative image URLs (e.g. ChatGPT exports
        # store images at media/<uuid>.webp relative to conversations.json).
        # If unset, infer from the DB's parent directory: imports are
        # typically extracted next to the resulting SQLite file.
        self.media_root = media_root or _infer_media_root(db)
        # Distinguish three states the status bar cares about:
        #   - tools_supported: provider.supports_tool_calling() is True
        #   - tools_requested: caller didn't pass --no-tools
        #   - enable_tools: both of the above
        # The split lets the status bar say "tools disabled" when the
        # user explicitly turned them off, vs. just hiding the badge
        # when the provider doesn't support them anyway.
        self._tools_supported = (
            provider is not None and provider.supports_tool_calling()
        )
        self._tools_requested = enable_tools
        self.enable_tools = self._tools_supported and self._tools_requested
        self.sidebar: Optional[ConversationList] = None
        self.main: Optional[MainPane] = None
        self._search_input: Optional[Input] = None
        self._status: Optional[Static] = None
        self._current_tree: Optional[ConversationTree] = None
        self._streaming_bubble: Optional[MessageBubble] = None
        self._streaming_buffer: str = ""
        # Set when an assistant turn (text or text+tools) is in flight,
        # so we can ignore double-submits and reflect the state in the UI.
        self._turn_active: bool = False

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
        # Tell the message view how to resolve relative image URLs.
        # Done here (post-mount) rather than in __init__ because main
        # is constructed by compose() after __init__ completes.
        if self.main is not None:
            self.main.messages.set_media_root(self.media_root)

    def on_unmount(self) -> None:
        # Clean up temp files written for base64-embedded images.
        # Lazy-import keeps text-only sessions from paying the cost.
        try:
            from ctk.tui.images import cleanup_temp_files

            cleanup_temp_files()
        except ImportError:
            pass

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
            self.notify(
                "Chat disabled: no reachable LLM endpoint. "
                "Fix your config (`ctk config set providers.openai.base_url …`) "
                "or re-run with --base-url.",
                severity="warning",
            )
            return
        if self._turn_active:
            self.notify("A response is still in flight.", severity="warning")
            return

        assert self.main is not None

        user_msg = self._append_user_message(event.text)
        self._turn_active = True
        self.main.set_streaming(True)

        if self.enable_tools:
            # Tool-aware path: non-streaming, executes any tool calls, loops.
            self._chat_worker_with_tools(user_msg.id)
        else:
            # Fast path: stream tokens straight into a single bubble.
            self._start_streaming_bubble(user_msg.id)
            self._stream_worker(self._llm_history_for(self._current_tree))

    def _start_streaming_bubble(self, parent_id: str) -> None:
        """Set up an empty assistant bubble for the streaming worker to fill."""
        assert self.main is not None
        assistant_msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.ASSISTANT,
            content=MessageContent(text=""),
            parent_id=parent_id,
            timestamp=datetime.now(),
        )
        if self._current_tree is not None:
            self._current_tree.add_message(assistant_msg)

        self._streaming_buffer = ""
        bubble = MessageBubble(assistant_msg)
        self._streaming_bubble = bubble
        self.main.messages.mount(
            Static(Text("bot", style="bold green"), classes="message-role")
        )
        self.main.messages.mount(bubble)
        self.main.messages.scroll_end(animate=False)
        self._refresh_status()

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

    # ------------------------------------------------------------------
    # Tool-aware chat path
    # ------------------------------------------------------------------
    #
    # When tools are enabled we can't stream — the openai SDK only
    # surfaces tool_calls on the final non-streaming response, and
    # reassembling them from streaming deltas is fiddly. The worker
    # below uses the blocking ``provider.chat()`` and loops until the
    # model returns a turn with no tool calls.
    #
    # All tool execution happens inside the worker thread (calling
    # ``execute_ask_tool`` which is synchronous). The UI gets discrete
    # update messages for each phase so widgets are mounted on the main
    # thread, which Textual requires.

    _MAX_TOOL_TURNS: int = 6

    @work(thread=True, exclusive=True)
    def _chat_worker_with_tools(self, parent_msg_id: str) -> None:
        """Run a tool-enabled chat turn.

        ``parent_msg_id`` is the user message we're responding to. It's
        passed through so the assistant message we ultimately store has
        a correct parent_id even though tree mutation happens on the UI
        thread (in the message handlers).

        Snapshot semantics: ``history`` is captured once at worker
        start. If the user opens Ctrl+G to edit the system prompt or
        Ctrl+O to attach a file mid-turn, those changes are persisted
        to the tree but do NOT influence the in-flight LLM call. They
        take effect on the next user message. This is intentional —
        re-loading the tree per loop iteration would let the modal
        race with the model and produce incoherent histories.
        """
        from ctk.core.tools import get_ask_tools  # lazy: tests don't need it

        try:
            assert self.provider is not None

            history = self._llm_history_for(self._current_tree)
            tools = get_ask_tools(include_pass_through=False)

            for _turn in range(self._MAX_TOOL_TURNS):
                response = self.provider.chat(history, tools=tools)
                content = response.content or ""
                tool_calls = response.tool_calls or []

                if content:
                    self.post_message(
                        _ChatAssistantText(content, final=not tool_calls)
                    )
                    history.append(
                        LLMMessage(
                            role=LLMMessageRole.ASSISTANT, content=content
                        )
                    )

                if not tool_calls:
                    self.post_message(_ChatDone())
                    return

                for tc in tool_calls:
                    name = tc["name"]
                    args = tc.get("arguments") or {}
                    self.post_message(
                        _ChatToolCall(name=name, args=args, status="started")
                    )
                    try:
                        result = self._execute_tool(name, args)
                        self.post_message(
                            _ChatToolCall(
                                name=name, args=args, status="ok", result=result
                            )
                        )
                    except Exception as exc:
                        self.post_message(
                            _ChatToolCall(
                                name=name,
                                args=args,
                                status="error",
                                result=str(exc),
                            )
                        )
                        result = f"Tool error: {exc}"

                    # Feed the result back to the model so the next loop
                    # iteration can react to it.
                    history.append(
                        self.provider.format_tool_result_message(
                            name, result, tool_call_id=tc.get("id")
                        )
                    )

            # Bailed out of the loop without a tool-call-free turn — tell
            # the user so they don't think the model is still thinking.
            self.post_message(
                _ChatDone(
                    error=(
                        f"Tool loop exceeded {self._MAX_TOOL_TURNS} turns; "
                        "stopping. The model may be stuck calling tools."
                    )
                )
            )
        except Exception as exc:  # pragma: no cover
            self.post_message(_ChatDone(error=str(exc)))

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """Run a CTK tool, returning its result as a string.

        Currently delegates to ``ctk.cli.execute_ask_tool`` which holds
        the canonical dispatch logic. Kept as a single seam so a future
        refactor can swap the executor (e.g., MCP-based) without
        changing the worker.
        """
        from ctk.cli import execute_ask_tool

        # ``use_rich`` would print to stdout, which the TUI swallows.
        # The tool registry returns strings either way.
        return execute_ask_tool(self.db, name, args, use_rich=False)

    # ----- UI thread handlers for chat-with-tools messages -------------

    def on_chat_assistant_text(self, event: _ChatAssistantText) -> None:
        """Mount an assistant text bubble for a non-streaming turn.

        Persistence is intentionally NOT done here — ``on_chat_done``
        owns the single save call so a final-turn message doesn't get
        written twice (once here on ``event.final``, once again in
        ``on_chat_done``). Whether this turn is final affects nothing
        in this handler today; kept on the message type for callers
        who may need it later.
        """
        if self.main is None:
            return
        if self._current_tree is not None:
            parent_id = None
            path = self._current_tree.get_longest_path()
            if path:
                parent_id = path[-1].id
            assistant_msg = Message(
                id=str(uuid.uuid4()),
                role=MessageRole.ASSISTANT,
                content=MessageContent(text=event.text),
                parent_id=parent_id,
                timestamp=datetime.now(),
            )
            self._current_tree.add_message(assistant_msg)
            self.main.messages.mount(
                Static(Text("bot", style="bold green"), classes="message-role")
            )
            self.main.messages.append_message(assistant_msg)

    def on_chat_tool_call(self, event: _ChatToolCall) -> None:
        """Render a tool call panel inline in the message stream."""
        if self.main is None:
            return
        text = Text()
        if event.status == "started":
            text.append("⚙  ", style="bold yellow")
            text.append(f"{event.name}", style="bold cyan")
            text.append(f"({_short_args(event.args)})", style="dim")
        elif event.status == "ok":
            text.append("✓  ", style="bold green")
            text.append(f"{event.name} → ", style="bold cyan")
            text.append(_truncate(event.result or "", 200), style="")
        else:  # error
            text.append("✗  ", style="bold red")
            text.append(f"{event.name} failed: ", style="bold red")
            text.append(_truncate(event.result or "", 200), style="dim")
        self.main.messages.mount(Static(text, classes="message-tool"))
        self.main.messages.scroll_end(animate=False)

    def on_chat_done(self, event: _ChatDone) -> None:
        if self.main is not None:
            self.main.set_streaming(False)
        self._turn_active = False
        if event.error:
            self.notify(event.error, severity="error")
        if self._current_tree is not None:
            self._safe_save(self._current_tree)
        if self.sidebar is not None:
            self.sidebar.refresh_list()
        self._refresh_status()

    def on_stream_token(self, event: _StreamToken) -> None:
        # Custom Textual messages dispatch to ``on_<snake_case_name>``.
        if self._streaming_bubble is None:
            return
        self._streaming_buffer += event.text
        self._update_streaming_bubble(self._streaming_buffer)

    def on_stream_done(self, event: _StreamDone) -> None:
        assert self.main is not None
        self.main.set_streaming(False)
        self._turn_active = False
        if event.error:
            self.notify(f"Stream error: {event.error}", severity="error")
        # Persist the final assistant content into the tree and save.
        if self._streaming_bubble is not None and self._current_tree is not None:
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

    def action_edit_system_prompt(self) -> None:
        """Edit (or create) the conversation's system prompt via a modal.

        Captures the conversation id at modal-open time and re-resolves
        the tree at callback time. This prevents a race where the user
        switches conversations in the sidebar while the modal is open
        and the new prompt lands on the wrong tree.
        """
        if self._current_tree is None:
            # Lazily create a tree so the user can set a prompt before
            # sending the first message.
            self._current_tree = ConversationTree(
                id=str(uuid.uuid4()),
                title="(new conversation)",
                metadata=ConversationMetadata(
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    model=getattr(self.provider, "model", None)
                    if self.provider
                    else None,
                ),
            )
        target_id = self._current_tree.id
        existing = self._existing_system_prompt(self._current_tree)
        self.push_screen(
            SystemPromptModal(initial=existing or ""),
            lambda result: self._on_system_prompt_saved(target_id, result),
        )

    def _existing_system_prompt(
        self, tree: ConversationTree
    ) -> Optional[str]:
        """Return the text of the first SYSTEM message in the path, if any."""
        for msg in tree.get_longest_path():
            if msg.role == MessageRole.SYSTEM:
                if hasattr(msg.content, "get_text"):
                    return msg.content.get_text()
                return str(msg.content)
        return None

    def _resolve_tree(self, tree_id: str) -> Optional[ConversationTree]:
        """Find the tree that matches ``tree_id`` at callback time.

        The user may have switched conversations between modal-open and
        modal-close. Prefer the in-memory ``_current_tree`` if its id
        still matches; otherwise reload from the DB. Returns None if
        the tree no longer exists.
        """
        if (
            self._current_tree is not None
            and self._current_tree.id == tree_id
        ):
            return self._current_tree
        try:
            return self.db.load_conversation(tree_id)
        except Exception:
            return None

    def _on_system_prompt_saved(
        self, tree_id: str, new_text: Optional[str]
    ) -> None:
        if new_text is None:
            return  # cancelled
        target = self._resolve_tree(tree_id)
        if target is None:
            self.notify(
                "Conversation no longer available; system prompt not saved.",
                severity="warning",
            )
            return
        self._set_system_prompt(target, new_text)
        self._safe_save(target)
        # Only refresh the visible pane if the user is still looking at
        # the conversation we modified.
        if (
            self.main is not None
            and self._current_tree is not None
            and self._current_tree.id == tree_id
        ):
            self.main.messages.show_conversation(target)
            self.main.set_header(self._header_for(target))
        self.notify("System prompt saved.")

    def _set_system_prompt(self, tree: ConversationTree, text: str) -> None:
        """Insert / update / clear the leading SYSTEM message.

        Empty text removes the SYSTEM message entirely. A non-empty
        value either updates the existing one or inserts a new SYSTEM
        message at the root and re-parents the existing root onto it.
        """
        # Find an existing SYSTEM message at the top of the tree.
        existing: Optional[Message] = None
        for root_id in tree.root_message_ids:
            msg = tree.message_map.get(root_id)
            if msg is not None and msg.role == MessageRole.SYSTEM:
                existing = msg
                break

        if not text.strip():
            # Caller asked to clear. Remove the SYSTEM root and re-link
            # any of its children up so they become roots.
            if existing is not None:
                children = tree.get_children(existing.id)
                if not children:
                    # Edge case: SYSTEM is the only message. Removing it
                    # would leave root_message_ids empty and break every
                    # subsequent path lookup. Bail out without mutating.
                    logger.debug(
                        "Skipping SYSTEM clear: it is the only message "
                        "in the tree (would leave the tree empty)."
                    )
                    return
                tree.message_map.pop(existing.id, None)
                if existing.id in tree.root_message_ids:
                    tree.root_message_ids.remove(existing.id)
                for child in children:
                    child.parent_id = None
                    if child.id not in tree.root_message_ids:
                        tree.root_message_ids.append(child.id)
                tree._invalidate_paths_cache()
            return

        if existing is not None:
            existing.content = MessageContent(text=text)
            tree._invalidate_paths_cache()
            return

        # Insert a new SYSTEM message as the new root, with the old roots
        # re-parented onto it.
        sys_msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.SYSTEM,
            content=MessageContent(text=text),
            parent_id=None,
            timestamp=datetime.now(),
        )
        tree.message_map[sys_msg.id] = sys_msg
        old_roots = list(tree.root_message_ids)
        tree.root_message_ids = [sys_msg.id]
        for old_root_id in old_roots:
            old_root = tree.message_map.get(old_root_id)
            if old_root is not None:
                old_root.parent_id = sys_msg.id
        tree._invalidate_paths_cache()

    def action_attach_file(self) -> None:
        """Prompt for a file path and inject its contents as a SYSTEM message.

        Captures the conversation id at modal-open time so a sidebar
        switch during the modal doesn't attach the file to the wrong
        tree. If no tree is loaded, defers tree creation until the
        callback so the title can include the basename.
        """
        target_id = (
            self._current_tree.id if self._current_tree is not None else None
        )
        self.push_screen(
            FilePathModal(prompt="Attach file (path will be read as text):"),
            lambda result: self._on_file_attached(target_id, result),
        )

    def _on_file_attached(
        self, target_id: Optional[str], path_str: Optional[str]
    ) -> None:
        if not path_str:
            return
        import os

        path = os.path.expanduser(path_str)
        if not os.path.isfile(path):
            self.notify(f"File not found: {path}", severity="error")
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as exc:
            self.notify(f"Could not read {path}: {exc}", severity="error")
            return

        # Resolve the target conversation. None target_id means we
        # opened the modal with no tree loaded; create one now.
        if target_id is None:
            target = ConversationTree(
                id=str(uuid.uuid4()),
                title=f"chat with {os.path.basename(path)}",
                metadata=ConversationMetadata(
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    model=getattr(self.provider, "model", None)
                    if self.provider
                    else None,
                ),
            )
            # If user is still looking at "no tree", adopt the new one.
            if self._current_tree is None:
                self._current_tree = target
        else:
            target = self._resolve_tree(target_id)
            if target is None:
                self.notify(
                    f"Conversation no longer available; {os.path.basename(path)} "
                    "not attached.",
                    severity="warning",
                )
                return

        # Append the file as a SYSTEM message at the END of the current
        # path (NOT at the root) so it acts as in-line context for the
        # next user message rather than a global preamble.
        parent_id = None
        path_msgs = target.get_longest_path()
        if path_msgs:
            parent_id = path_msgs[-1].id
        attach_msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.SYSTEM,
            content=MessageContent(
                text=f"[Attached file: {path}]\n\n{content}\n\n[End of file: {path}]"
            ),
            parent_id=parent_id,
            timestamp=datetime.now(),
        )
        target.add_message(attach_msg)
        self._safe_save(target)

        # Only update the visible pane if the user is still on this tree.
        if (
            self.main is not None
            and self._current_tree is not None
            and self._current_tree.id == target.id
        ):
            self.main.messages.append_message(attach_msg)
            self.main.set_header(self._header_for(self._current_tree))
        self.notify(
            f"Attached {os.path.basename(path)} "
            f"({len(content)} chars, {len(content.splitlines())} lines)."
        )

    def action_prev_sibling(self) -> None:
        """Switch to the previous sibling under the focused message."""
        self._switch_sibling(direction=-1)

    def action_next_sibling(self) -> None:
        """Switch to the next sibling under the focused message."""
        self._switch_sibling(direction=+1)

    def _switch_sibling(self, direction: int) -> None:
        if self.main is None:
            return
        target_id = self._focused_message_id()
        if target_id is None:
            self.notify(
                "Focus a message first (Tab/Shift+Tab between messages).",
                severity="warning",
            )
            return
        if not self.main.messages.switch_sibling(target_id, direction):
            self.notify("No siblings to switch to here.", severity="information")

    def action_fork_at_focus(self) -> None:
        """Fork the current conversation at the focused message.

        Truncates the tree to the ancestor chain of the focus target —
        descendants and sibling branches are dropped. Same semantics as
        the legacy ``/fork`` command, with ``Ctrl+F`` instead of slash.
        """
        self._fork_or_branch(preserve_tree=False)

    def action_branch_at_focus(self) -> None:
        """Branch the current conversation at the focused message.

        Keeps the full tree in memory and gives the conversation a new
        id, so saving creates a sibling rather than overwriting. Same
        semantics as the legacy ``/branch``.
        """
        self._fork_or_branch(preserve_tree=True)

    def _fork_or_branch(self, preserve_tree: bool) -> None:
        if self._current_tree is None:
            self.notify("No conversation loaded.", severity="warning")
            return
        target_id = self._focused_message_id()
        if target_id is None:
            self.notify(
                "Focus a message first (Tab/Shift+Tab to move between messages).",
                severity="warning",
            )
            return
        target = self._current_tree.message_map.get(target_id)
        if target is None:
            self.notify("Focused message no longer exists.", severity="warning")
            return

        # Save the current state under the OLD id before we mutate.
        self._safe_save(self._current_tree)

        if not preserve_tree:
            self._truncate_tree_to_message(self._current_tree, target_id)

        old_id = self._current_tree.id
        new_id = str(uuid.uuid4())
        self._current_tree.id = new_id
        old_title = self._current_tree.title or "(untitled)"
        verb = "Branch" if preserve_tree else "Fork"
        self._current_tree.title = f"{verb} of {old_title}"

        # Re-render the message view so it reflects the (possibly
        # pruned) tree under the new id.
        if self.main is not None:
            self.main.messages.show_conversation(self._current_tree)
            self.main.set_header(self._header_for(self._current_tree))

        self.notify(
            f"{verb}ed at {target_id[:8]} — new id {new_id[:8]} "
            f"(old: {old_id[:8]})"
        )
        if self.sidebar is not None:
            self.sidebar.refresh_list()

    def _focused_message_id(self) -> Optional[str]:
        """Return the message_id of a currently focused MessageBubble, if any."""
        focused = self.focused
        if isinstance(focused, MessageBubble):
            return focused.message_id
        return None

    @staticmethod
    def _truncate_tree_to_message(
        tree: ConversationTree, target_id: str
    ) -> None:
        """Prune ``tree`` so only ancestors of target_id (plus target) remain.

        Mirrors the helper in ``ctk/chat/tui.py`` so both UIs share the
        same fork semantics. We can't import the legacy helper directly
        because that module pulls in heavy chat-mode dependencies the
        Textual app doesn't need.
        """
        target = tree.message_map.get(target_id)
        if target is None:
            return
        keep = {target.id}
        cursor: Optional[Message] = target
        while cursor is not None and cursor.parent_id:
            parent = tree.message_map.get(cursor.parent_id)
            if parent is None:
                break
            keep.add(parent.id)
            cursor = parent

        # Drop everything else from the message_map and from
        # root_message_ids (the path walker keys off both).
        tree.message_map = {
            mid: msg for mid, msg in tree.message_map.items() if mid in keep
        }
        tree.root_message_ids = [
            r for r in tree.root_message_ids if r in keep
        ]
        # Invalidate the cached path traversal so subsequent renders see
        # the pruned set.
        tree._invalidate_paths_cache()

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
            if self.enable_tools:
                text.append("  · tools", style="dim cyan")
            elif self._tools_supported and not self._tools_requested:
                # Tools work here but the user said --no-tools; surface
                # that explicitly so a missing badge isn't ambiguous.
                text.append("  · tools off", style="dim italic")
        else:
            text.append("browse-only · chat disabled", style="dim italic")
        if self._current_tree is not None:
            text.append("   ", style="")
            text.append(self._current_tree.id[:8], style="dim")
        if self._turn_active:
            text.append("   thinking…", style="bold yellow")
        return text

    def _refresh_status(self) -> None:
        if self._status is not None:
            self._status.update(self._status_text())


def _detect_image_protocol_eagerly() -> None:
    """Force textual-image's terminal-protocol detection to run NOW.

    textual-image probes the terminal for Sixel and Kitty TGP support
    by sending an OSC escape sequence and waiting briefly for a reply.
    The detection runs at *import time* of ``textual_image.renderable``.
    Once the Textual app starts, its input thread captures stdin and
    the OSC reply gets stolen — so any later import locks in the
    halfcell fallback even on terminals that fully support TGP/Sixel.

    Calling this from ``run()`` (before ``app.run()``) ensures the
    detection happens while we still own stdin. Failures are swallowed
    so users without textual-image installed still get the rest of
    the TUI; image rendering just degrades to caption-only.
    """
    try:
        import textual_image.renderable  # noqa: F401  (import for side effect)
    except Exception:
        # Not installed, or terminal probe blew up. Either way the
        # message view's lazy import will hit the same exception path
        # and degrade gracefully.
        pass


def run(
    db_path: str,
    provider: Optional[LLMProvider] = None,
    enable_tools: bool = True,
) -> None:
    """Launch the Textual TUI against ``db_path``.

    This is a thin wrapper kept out of ``__init__`` so importing
    ``ctk.tui`` doesn't eagerly open the DB.
    """
    _detect_image_protocol_eagerly()
    db = ConversationDB(db_path)
    try:
        app = CTKApp(db=db, provider=provider, enable_tools=enable_tools)
        app.run()
    finally:
        db.close()
