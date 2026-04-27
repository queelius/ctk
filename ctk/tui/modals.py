"""Modal dialogs for the Textual TUI.

Each modal is a small ``ModalScreen`` that captures input and posts a
result back to the app via ``self.dismiss(value)``. Keeping them
together prevents one modal's CSS from leaking into another's by
accident, and makes the bindings table at the top of ``app.py`` more
discoverable.
"""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea


class SystemPromptModal(ModalScreen[Optional[str]]):
    """Edit the conversation's system prompt.

    Returns the new text on save, or ``None`` if cancelled. The empty
    string is a meaningful "clear the prompt" value, so callers must
    distinguish ``None`` (cancel) from ``""`` (clear).
    """

    BINDINGS = [
        Binding("escape", "cancel", "cancel"),
        Binding("ctrl+s", "save", "save"),
    ]

    DEFAULT_CSS = """
    SystemPromptModal {
        align: center middle;
    }
    SystemPromptModal > Vertical {
        background: $panel;
        border: round $accent;
        padding: 1 2;
        width: 80;
        height: 24;
    }
    SystemPromptModal Label {
        color: $accent;
        text-style: bold;
        padding: 0 0 1 0;
    }
    SystemPromptModal TextArea {
        height: 1fr;
    }
    """

    def __init__(self, initial: str = "") -> None:
        super().__init__()
        self._initial = initial
        self._textarea: Optional[TextArea] = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("System prompt  (Ctrl+S to save · Esc to cancel)")
            self._textarea = TextArea(self._initial, language=None)
            yield self._textarea

    def on_mount(self) -> None:
        if self._textarea is not None:
            self._textarea.focus()

    def action_save(self) -> None:
        if self._textarea is None:
            self.dismiss(None)
            return
        self.dismiss(self._textarea.text)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FilePathModal(ModalScreen[Optional[str]]):
    """Single-line modal that prompts for a file path.

    Returns the entered path (whitespace-trimmed) on Enter, or ``None``
    on Escape. Path resolution / file reading is the caller's
    responsibility — keeping this modal dumb makes it reusable for
    "save export here" too.
    """

    BINDINGS = [
        Binding("escape", "cancel", "cancel"),
    ]

    DEFAULT_CSS = """
    FilePathModal {
        align: center middle;
    }
    FilePathModal > Vertical {
        background: $panel;
        border: round $accent;
        padding: 1 2;
        width: 70;
        height: 7;
    }
    FilePathModal Label {
        color: $accent;
        text-style: bold;
        padding: 0 0 1 0;
    }
    """

    def __init__(self, prompt: str = "Path:", initial: str = "") -> None:
        super().__init__()
        self._prompt = prompt
        self._initial = initial
        self._input: Optional[Input] = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._prompt)
            self._input = Input(value=self._initial, placeholder="/path/to/file")
            yield self._input

    def on_mount(self) -> None:
        if self._input is not None:
            self._input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        if not text:
            self.dismiss(None)
            return
        self.dismiss(text)

    def action_cancel(self) -> None:
        self.dismiss(None)
