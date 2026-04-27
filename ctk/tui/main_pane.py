"""Main pane: message view on top, multi-line input at the bottom."""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.markdown import Markdown
from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TextArea

from ctk.core.models import ConversationTree, Message, MessageContent, MessageRole


def _role_label(role: MessageRole) -> Text:
    mapping = {
        MessageRole.USER: ("you",        "bold cyan"),
        MessageRole.ASSISTANT: ("bot",   "bold green"),
        MessageRole.SYSTEM: ("system",   "dim italic"),
        MessageRole.TOOL: ("tool",       "bold yellow"),
    }
    name, style = mapping.get(role, (str(role), "bold"))
    return Text(name, style=style)


class MessageBubble(Static):
    """A single message in the scroll view, styled by role.

    Bubbles are focusable so j/k or arrow keys can move the selection
    cursor between messages — the parent app uses the focused bubble's
    ``message_id`` to drive fork/branch actions. Made focusable via
    ``can_focus = True`` rather than overriding ``__init__`` flags so
    the existing test that mounts these unchanged still works.
    """

    can_focus = True

    def __init__(self, msg: Message) -> None:
        klass = {
            MessageRole.USER: "message-user",
            MessageRole.ASSISTANT: "message-assistant",
            MessageRole.SYSTEM: "message-system",
        }.get(msg.role, "message-assistant")
        body = msg.content.get_text() if hasattr(msg.content, "get_text") else str(
            msg.content
        )
        # Render as markdown for assistant output (code fences etc.); keep
        # user/system as plain text to avoid surprise rendering.
        if msg.role == MessageRole.ASSISTANT:
            renderable = Markdown(body or "")
        else:
            renderable = Text(body or "")
        super().__init__(renderable, classes=klass)
        self._msg = msg

    @property
    def message_id(self) -> str:
        """The ctk Message id this bubble represents."""
        return self._msg.id


class BranchIndicator(Static):
    """A "Branch N of M ◀ ▶" inline indicator under a branching message.

    Stored on the parent message id so the app can find it again to
    update the highlighted sibling. The actual sibling switching is
    driven by ``MessageView.switch_sibling`` which rebuilds the path
    and re-renders.
    """

    def __init__(self, parent_id: str, position: int, total: int) -> None:
        super().__init__(classes="branch-indicator")
        self.parent_id = parent_id
        self.update(self._render_label(position, total))

    @staticmethod
    def _render_label(position: int, total: int) -> Text:
        # NOTE: do NOT name this ``_render`` — Textual's Widget base
        # class uses ``_render`` internally during the paint cycle and
        # collisions silently break the widget.
        text = Text()
        text.append("  ⤳ branch ", style="dim italic")
        text.append(f"{position + 1}", style="bold cyan")
        text.append(f" of {total}  ", style="dim")
        text.append("[ ] to switch", style="dim italic")
        return text


class MessageView(VerticalScroll):
    """Scrollable message column.

    Tracks the **current path** as state rather than recomputing
    ``get_longest_path()`` each render, so sibling switching can
    rewrite the tail of the path without losing the prefix.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The conversation we're displaying and the linear path through it.
        self._tree: Optional[ConversationTree] = None
        self._path: List[Message] = []
        # Directory used to resolve relative image URLs (e.g. the
        # ``media/`` folder ChatGPT exports place next to
        # ``conversations.json``). Set by the App after construction
        # because it depends on the database path.
        self._media_root: Optional[str] = None

    def set_media_root(self, root: Optional[str]) -> None:
        """Set the directory used to resolve relative image URLs."""
        self._media_root = root

    @property
    def current_path(self) -> List[Message]:
        return list(self._path)

    @property
    def current_tree(self) -> Optional[ConversationTree]:
        return self._tree

    def clear(self) -> None:
        for child in list(self.children):
            child.remove()

    def show_empty(self, hint: str = "Select a conversation from the sidebar.") -> None:
        self.clear()
        self._tree = None
        self._path = []
        self.mount(Static(Text(hint, style="dim italic"), classes="message-system"))

    def show_conversation(self, tree: ConversationTree) -> None:
        self._tree = tree
        self._path = list(tree.get_longest_path())
        self._render_path()

    def append_message(self, msg: Message) -> None:
        """Append a single message to the displayed path AND the state."""
        self._path.append(msg)
        self._mount_message(msg, is_last_in_path=True)
        self.scroll_end(animate=False)

    def switch_sibling(self, parent_id: str, direction: int) -> bool:
        """Switch to the next/prev sibling under ``parent_id`` in the path.

        Rebuilds the tail of the current path: keeps everything up to
        and including ``parent_id``, then picks the new sibling, then
        extends down its first-leaf greedy path.

        Returns True if the path actually changed (there were siblings
        to move to), False otherwise.
        """
        if self._tree is None:
            return False
        # Locate parent in current path.
        parent_index = next(
            (i for i, m in enumerate(self._path) if m.id == parent_id), None
        )
        if parent_index is None or parent_index + 1 >= len(self._path):
            return False
        siblings = self._tree.get_children(parent_id)
        if len(siblings) < 2:
            return False
        current_child_id = self._path[parent_index + 1].id
        current_pos = next(
            (i for i, s in enumerate(siblings) if s.id == current_child_id), 0
        )
        new_pos = (current_pos + direction) % len(siblings)
        if new_pos == current_pos:
            return False
        new_child = siblings[new_pos]
        # Truncate after parent and rebuild greedy path from new_child.
        self._path = self._path[: parent_index + 1] + self._extend_path(
            new_child
        )
        self._render_path()
        return True

    def _extend_path(self, start: Message) -> List[Message]:
        """Greedy descent from ``start``: pick the first child each step."""
        assert self._tree is not None
        path = [start]
        cursor = start
        while True:
            kids = self._tree.get_children(cursor.id)
            if not kids:
                break
            cursor = kids[0]
            path.append(cursor)
        return path

    def _render_path(self) -> None:
        self.clear()
        if not self._path:
            self.show_empty("(conversation is empty)")
            return
        for i, msg in enumerate(self._path):
            self._mount_message(msg, is_last_in_path=(i == len(self._path) - 1))
        self.scroll_end(animate=False)

    def _mount_message(self, msg: Message, is_last_in_path: bool = False) -> None:
        role_line = Static(_role_label(msg.role), classes="message-role")
        bubble = MessageBubble(msg)
        self.mount(role_line)
        self.mount(bubble)
        # Mount any image attachments below the bubble. Lazy-import so
        # the image stack stays out of the codepath for text-only
        # conversations (which is most of them) and so missing
        # textual-image at install time degrades to a graceful warning
        # rather than an import error.
        images = getattr(msg.content, "images", None)
        if images:
            try:
                from ctk.tui.images import build_image_widgets

                for widget in build_image_widgets(
                    images, media_root=self._media_root
                ):
                    self.mount(widget)
            except ImportError:
                # textual-image not installed; show a minimal fallback
                # so the user at least knows attachments existed.
                for img in images:
                    label = (
                        img.caption
                        or img.url
                        or img.path
                        or f"(embedded {img.mime_type or 'image'})"
                    )
                    self.mount(
                        Static(f"[image] {label}", classes="message-system")
                    )
        # Show a branch indicator under any message with siblings beyond
        # the one currently picked. We render it AFTER the bubble whose
        # *child* in the path has siblings — i.e., this is the parent of
        # a branching point. Skip on the last message because there's no
        # next-in-path child to indicate.
        if is_last_in_path or self._tree is None:
            return
        siblings = self._tree.get_children(msg.id)
        if len(siblings) < 2:
            return
        # Find which sibling is currently in the path.
        next_in_path_id = None
        path_ids = [m.id for m in self._path]
        idx = path_ids.index(msg.id)
        if idx + 1 < len(self._path):
            next_in_path_id = self._path[idx + 1].id
        position = next(
            (i for i, s in enumerate(siblings) if s.id == next_in_path_id), 0
        )
        self.mount(
            BranchIndicator(msg.id, position=position, total=len(siblings))
        )


class ChatInput(TextArea):
    """Multi-line input for the user's next message.

    Enter submits; Shift+Enter inserts a newline. The parent app listens
    for ``Submitted`` events via ``on_chat_input_submitted``.
    """

    class Submitted(TextArea.Changed):
        """Fired when the user hits Enter to submit the current buffer."""

        def __init__(self, text_area: "ChatInput", text: str) -> None:
            super().__init__(text_area)
            self.text = text

    def __init__(self) -> None:
        super().__init__(id="input-area", language=None, show_line_numbers=False)

    def _on_key(self, event) -> None:
        # Textual encodes modifier combos in the key string itself:
        # plain "enter" submits; "shift+enter" (or ctrl+enter) inserts a
        # newline via TextArea's default handler. The Key event has no
        # `.shift` attribute — rely on the string key instead.
        if event.key == "enter":
            text = self.text.strip()
            if text:
                event.stop()
                event.prevent_default()
                self.post_message(self.Submitted(self, text))
                self.clear()
                return
        # Fall through to TextArea's default handler for everything else
        # (including shift+enter, which inserts a newline).


class MainPane(Vertical):
    """Main pane composed of a message view plus chat input."""

    def __init__(self) -> None:
        super().__init__(id="main")
        self._header = Static("", id="main-header")
        self._messages = MessageView(id="messages")
        self._input = ChatInput()

    def compose(self):
        yield self._header
        yield self._messages
        yield self._input

    def on_mount(self) -> None:
        self._messages.show_empty()
        self.set_header("no conversation loaded")

    def set_header(self, text: str) -> None:
        self._header.update(Text(text, style="bold cyan"))

    @property
    def messages(self) -> MessageView:
        return self._messages

    @property
    def input(self) -> ChatInput:
        return self._input

    def set_streaming(self, streaming: bool) -> None:
        """Visually indicate a streaming response is in progress."""
        if streaming:
            self._input.add_class("streaming")
            self._input.read_only = True
        else:
            self._input.remove_class("streaming")
            self._input.read_only = False
