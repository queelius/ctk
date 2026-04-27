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
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea


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


class ConfirmModal(ModalScreen[bool]):
    """Yes/No confirmation modal for destructive operations.

    Returns ``True`` if the user confirms, ``False`` (or ``None`` →
    ``False`` via the dismiss default) on cancel. Callers should always
    branch on the truthiness of the result.
    """

    BINDINGS = [
        Binding("escape", "cancel", "cancel"),
        Binding("y", "confirm", "yes", show=False),
        Binding("n", "cancel", "no", show=False),
        Binding("enter", "confirm", "confirm", show=False),
    ]

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }
    ConfirmModal > Vertical {
        background: $panel;
        border: round $error;
        padding: 1 2;
        width: 60;
        height: auto;
    }
    ConfirmModal Label.title {
        color: $error;
        text-style: bold;
        padding: 0 0 1 0;
    }
    ConfirmModal Label.detail {
        padding: 0 0 1 0;
    }
    ConfirmModal Label.hint {
        color: $text-muted;
        padding: 1 0 0 0;
    }
    """

    def __init__(self, title: str, detail: str = "") -> None:
        super().__init__()
        self._title = title
        self._detail = detail

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, classes="title")
            if self._detail:
                yield Label(self._detail, classes="detail")
            yield Label("[y]es / [n]o / Esc to cancel", classes="hint")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class HelpModal(ModalScreen[None]):
    """Three-column help screen: bindings, slash commands, MCP tools.

    Built dynamically from the live registries so it can never drift
    out of sync with what's actually wired up. Includes a one-line
    callout about CTK's fork/branch terminology being inverted from
    git's, since that's the most common surprise.
    """

    BINDINGS = [
        Binding("escape", "close", "close"),
        Binding("q", "close", "close"),
        Binding("ctrl+h", "close", "close"),
    ]

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
    }
    HelpModal > Vertical {
        background: $panel;
        border: round $accent;
        padding: 1 2;
        width: 90%;
        height: 90%;
    }
    HelpModal Label.title {
        color: $accent;
        text-style: bold;
        padding: 0 0 1 0;
    }
    HelpModal VerticalScroll {
        height: 1fr;
    }
    HelpModal .section {
        color: $accent;
        text-style: bold;
        padding: 1 0 0 0;
    }
    HelpModal .callout {
        color: $warning;
        text-style: italic;
        padding: 1 0 1 0;
    }
    HelpModal .hint {
        color: $text-muted;
        padding: 1 0 0 0;
    }
    """

    def __init__(self, bindings: list) -> None:
        super().__init__()
        self._bindings = bindings

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("CTK · Help", classes="title")
            with VerticalScroll():
                yield Static(self._render(), markup=True)
            yield Label("Esc / q / Ctrl+H to close", classes="hint")

    def action_close(self) -> None:
        self.dismiss(None)

    def _render(self) -> str:
        # Imported lazily so this modal stays import-cheap.
        from ctk.core.tools_registry import iter_providers
        from ctk.tui.slash import commands as slash_commands

        out: list[str] = []

        out.append("[bold]Key bindings[/bold]")
        for binding in self._bindings:
            key = getattr(binding, "key", "?")
            description = getattr(binding, "description", "") or getattr(binding, "action", "")
            show = getattr(binding, "show", True)
            if not show:
                continue
            out.append(f"  [cyan]{key:<10}[/cyan] {description}")
        out.append("")

        out.append("[bold]Slash commands[/bold]  (type in the chat input)")
        for cmd in slash_commands().values():
            out.append(f"  [cyan]{cmd.usage:<28}[/cyan] {cmd.summary}")
        out.append("")

        out.append("[bold]MCP tool providers[/bold]  (callable by the LLM)")
        for provider in iter_providers():
            status = "ready" if provider.available else "unavailable"
            out.append(
                f"  [cyan]{provider.name:<16}[/cyan] [{status}] "
                f"{len(provider.tools)} tool"
                f"{'s' if len(provider.tools) != 1 else ''}"
            )
            for tool in provider.tools:
                summary = (tool.get("description") or "").strip().splitlines()[0]
                if len(summary) > 70:
                    summary = summary[:67] + "…"
                out.append(f"      • [dim]{tool['name']}[/dim]  {summary}")
        out.append("")

        out.append("[yellow italic]Note:[/yellow italic] CTK's [cyan]fork[/cyan] and "
                   "[cyan]branch[/cyan] are inverted relative to git. In CTK:")
        out.append("  • [cyan]fork[/cyan]   = snip to focused message (drop later messages + sibling branches)")
        out.append("  • [cyan]branch[/cyan] = duplicate the entire tree under a new id")
        out.append("Both produce a new conversation; only [cyan]branch[/cyan] preserves the full tree.")

        return "\n".join(out)
