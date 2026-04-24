"""Main pane: message view on top, multi-line input at the bottom."""

from __future__ import annotations

from typing import List, Optional

from rich.markdown import Markdown
from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, TextArea

from ctk.core.models import ConversationTree, Message, MessageRole


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
    """A single message in the scroll view, styled by role."""

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


class MessageView(VerticalScroll):
    """Scrollable message column. ``show_conversation`` replaces contents."""

    def clear(self) -> None:
        for child in list(self.children):
            child.remove()

    def show_empty(self, hint: str = "Select a conversation from the sidebar.") -> None:
        self.clear()
        self.mount(Static(Text(hint, style="dim italic"), classes="message-system"))

    def show_conversation(self, tree: ConversationTree) -> None:
        self.clear()
        messages = tree.get_longest_path()
        if not messages:
            self.show_empty("(conversation is empty)")
            return
        for msg in messages:
            self._mount_message(msg)
        self.scroll_end(animate=False)

    def append_message(self, msg: Message) -> None:
        self._mount_message(msg)
        self.scroll_end(animate=False)

    def _mount_message(self, msg: Message) -> None:
        role_line = Static(_role_label(msg.role), classes="message-role")
        bubble = MessageBubble(msg)
        self.mount(role_line)
        self.mount(bubble)


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
        # Enter submits, shift+enter inserts newline. TextArea's default
        # behavior inserts a newline on Enter, so we intercept first.
        if event.key == "enter" and not event.shift:
            text = self.text.strip()
            if text:
                event.stop()
                event.prevent_default()
                self.post_message(self.Submitted(self, text))
                self.clear()
                return
        # Fall through to TextArea's default handler for everything else.


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
