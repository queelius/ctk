"""Sidebar widget: scrollable conversation list."""

from __future__ import annotations

from typing import List, Optional

from textual.containers import Vertical
from textual.widgets import DataTable, Static

from ctk.core.database import ConversationDB


def _flags(conv) -> str:
    """Render star/pin/archive flags as a compact glyph string."""
    parts = []
    if getattr(conv, "starred_at", None) or getattr(conv, "starred", False):
        parts.append("⭐")
    if getattr(conv, "pinned_at", None) or getattr(conv, "pinned", False):
        parts.append("📌")
    if getattr(conv, "archived_at", None) or getattr(conv, "archived", False):
        parts.append("📁")
    return "".join(parts) or " "


def _title(conv) -> str:
    title = getattr(conv, "title", None) or "(untitled)"
    # Sidebar is narrow; trim so rows don't wrap and break the layout.
    return title if len(title) <= 32 else title[:30] + "…"


class ConversationList(Vertical):
    """Sidebar listing conversations from the database.

    Fires a ``DataTable.RowSelected`` event via the underlying table; the
    app subscribes and loads the selected conversation into the main pane.
    """

    DEFAULT_LIMIT = 200

    def __init__(self, db: ConversationDB) -> None:
        super().__init__(id="sidebar")
        self._db = db
        self._conversations: List = []
        self._table = DataTable(cursor_type="row", zebra_stripes=True)

    def compose(self):
        yield Static("conversations", id="sidebar-title")
        yield self._table

    def on_mount(self) -> None:
        self._table.add_columns("", "title", "updated")
        self.refresh_list()

    def refresh_list(self, search: Optional[str] = None) -> None:
        """Reload rows from the DB, optionally filtered by a search string."""
        self._table.clear()
        if search:
            self._conversations = self._db.search_conversations(
                search, limit=self.DEFAULT_LIMIT
            )
        else:
            self._conversations = self._db.list_conversations(
                limit=self.DEFAULT_LIMIT
            )

        for conv in self._conversations:
            updated = getattr(conv, "updated_at", None)
            updated_str = updated.strftime("%Y-%m-%d") if updated else ""
            self._table.add_row(
                _flags(conv),
                _title(conv),
                updated_str,
                key=str(getattr(conv, "id", "")),
            )

        if self._conversations:
            # Focus the first row so ↓/↑/j/k work immediately.
            self._table.move_cursor(row=0)

    def selected_conversation_id(self) -> Optional[str]:
        """Return the conversation id under the cursor, if any."""
        if not self._conversations:
            return None
        try:
            row_key = self._table.coordinate_to_cell_key(
                self._table.cursor_coordinate
            ).row_key
            return row_key.value if row_key else None
        except Exception:
            return None

    def focus_table(self) -> None:
        """Move focus to the table so arrow keys drive selection."""
        self._table.focus()
