"""Sidebar widget: tabbed conversation browser.

Tabs replace the line-mode VFS virtual directories from the legacy
``ctk chat`` (``/starred/``, ``/pinned/``, ``/tags/``, ``/sources/``,
``/recent/``). Selecting a tab refilters the list in place; the
underlying DataTable still drives selection.

Adding a new filter mode means: append a ``(label, mode_key)`` tuple to
``_TAB_DEFS`` and handle the new key in ``_apply_filter``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from textual.containers import Vertical
from textual.widgets import DataTable, Static, Tabs, Tab

from ctk.core.database import ConversationDB


def _flags(conv) -> str:
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
    return title if len(title) <= 32 else title[:30] + "…"


# Tab id -> (label, filter_mode). Order is the strip order.
_TAB_DEFS: List[Tuple[str, str]] = [
    ("all", "All"),
    ("starred", "⭐ Starred"),
    ("pinned", "📌 Pinned"),
    ("recent", "Recent"),
    ("archived", "📁 Archived"),
]


class ConversationList(Vertical):
    """Sidebar tab strip + scrollable conversation table.

    Selection events on the underlying ``DataTable`` bubble up as
    standard Textual messages; the parent app handles them via
    ``on_data_table_row_*`` hooks.
    """

    DEFAULT_LIMIT = 200

    def __init__(self, db: ConversationDB) -> None:
        super().__init__(id="sidebar")
        self._db = db
        self._conversations: List = []
        self._table = DataTable(cursor_type="row", zebra_stripes=True)
        # ``Tabs`` builds tabs from positional Tab children at compose time.
        self._tabs = Tabs(
            *[Tab(label, id=tab_id) for tab_id, label in _TAB_DEFS]
        )
        self._search: Optional[str] = None
        self._mode: str = "all"

    def compose(self):
        yield Static("conversations", id="sidebar-title")
        yield self._tabs
        yield self._table

    def on_mount(self) -> None:
        self._table.add_columns("", "title", "updated")
        self.refresh_list()

    # ------------------------------------------------------------------
    # Public API used by the app
    # ------------------------------------------------------------------

    def refresh_list(self, search: Optional[str] = None) -> None:
        """Reload rows from the DB.

        ``search`` is sticky across mode changes — pass ``""`` (or call
        ``set_search(None)`` first) to clear it.
        """
        if search is not None:
            self._search = search or None
        self._conversations = self._apply_filter()
        self._populate_table()

    def set_mode(self, mode: str) -> None:
        """Change the filter mode (one of the tab ids)."""
        self._mode = mode
        self.refresh_list()

    def selected_conversation_id(self) -> Optional[str]:
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
        self._table.focus()

    # ------------------------------------------------------------------
    # Internal: filter dispatch + table rendering
    # ------------------------------------------------------------------

    def _apply_filter(self):
        """Run the right DB query for the current mode + search string."""
        # Search overlay overrides the tab — searching against the
        # whole DB is more useful than searching within a single tab.
        if self._search:
            return self._db.search_conversations(
                self._search, limit=self.DEFAULT_LIMIT
            )

        if self._mode == "all":
            return self._db.list_conversations(limit=self.DEFAULT_LIMIT)
        if self._mode == "starred":
            return self._db.list_conversations(
                starred=True, limit=self.DEFAULT_LIMIT
            )
        if self._mode == "pinned":
            return self._db.list_conversations(
                pinned=True, limit=self.DEFAULT_LIMIT
            )
        if self._mode == "archived":
            return self._db.list_conversations(
                archived=True,
                include_archived=True,
                limit=self.DEFAULT_LIMIT,
            )
        if self._mode == "recent":
            # ``list_conversations`` is already ordered by updated_at DESC,
            # so "recent" is just a smaller slice. Keeping it as a tab
            # mostly serves as a discoverable shortcut.
            return self._db.list_conversations(limit=20)

        # Unknown mode — fall back to all.
        return self._db.list_conversations(limit=self.DEFAULT_LIMIT)

    def _populate_table(self) -> None:
        self._table.clear()
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
            self._table.move_cursor(row=0)

    # ------------------------------------------------------------------
    # Tab activation
    # ------------------------------------------------------------------

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        # ``Tabs`` fires this on initial mount too; both paths are fine.
        if event.tab is None:
            return
        new_mode = event.tab.id or "all"
        if new_mode != self._mode:
            self.set_mode(new_mode)
