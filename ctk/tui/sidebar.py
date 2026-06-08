"""Sidebar widget: tabbed conversation browser.

Tabs replace the line-mode VFS virtual directories from the legacy
``ctk chat`` (``/starred/``, ``/pinned/``, ``/tags/``, ``/sources/``,
``/recent/``). Selecting a tab refilters the list in place; the
underlying DataTable still drives selection.

Pagination: most tabs fetch one page (``DEFAULT_PAGE_SIZE`` rows) at
a time using cursor-based keyset pagination. When more pages remain
the header reads ``conversations · N loaded · more (Ctrl+L)``; the
app binds Ctrl+L to ``load_more()``. The "Recent" tab is the one
exception — a fixed 20-row snapshot that never paginates.

Adding a new filter mode means: append a ``(label, mode_key)`` tuple to
``_TAB_DEFS`` and handle the new key in ``_fetch_page``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, cast

from textual.containers import Vertical
from textual.widgets import DataTable, Static, Tab, Tabs

from ctk.core.database import ConversationDB
from ctk.core.models import PaginatedResult


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

    DEFAULT_PAGE_SIZE = 200

    def __init__(self, db: ConversationDB) -> None:
        super().__init__(id="sidebar")
        self._db = db
        self._conversations: List = []
        self._table: DataTable = DataTable(cursor_type="row", zebra_stripes=True)
        # ``Tabs`` builds tabs from positional Tab children at compose time.
        self._tabs = Tabs(*[Tab(label, id=tab_id) for tab_id, label in _TAB_DEFS])
        self._title_label = Static("conversations", id="sidebar-title")
        self._search: Optional[str] = None
        self._mode: str = "all"
        # Cursor pagination state. ``""`` means "first page", ``None``
        # means "no more pages." Reset on mode/search change in
        # ``_reset_and_fetch``.
        self._next_cursor: Optional[str] = ""
        self._has_more: bool = False

    def compose(self):
        yield self._title_label
        yield self._tabs
        yield self._table

    def on_mount(self) -> None:
        self._table.add_columns("", "title", "updated")
        self.refresh_list()

    # ------------------------------------------------------------------
    # Public API used by the app
    # ------------------------------------------------------------------

    def refresh_list(self, search: Optional[str] = None) -> None:
        """Reload from the DB, starting at page 1.

        ``search`` is sticky across mode changes — pass ``""`` (or call
        ``set_search(None)`` first) to clear it. Always resets the
        pagination cursor; use ``load_more()`` to fetch the next page
        once results are showing.
        """
        if search is not None:
            self._search = search or None
        self._reset_and_fetch()

    def set_mode(self, mode: str) -> None:
        """Change the filter mode (one of the tab ids). Resets pagination."""
        self._mode = mode
        self._reset_and_fetch()

    def load_more(self) -> int:
        """Fetch the next page (if any) and append to the table.

        Returns the number of rows added, so the caller can show a
        notification ("loaded 200 more") or skip the binding when
        there's nothing left.
        """
        if not self._has_more or self._next_cursor is None:
            return 0
        page = self._fetch_page(cursor=self._next_cursor)
        added = self._merge_page(page)
        self._update_title()
        return added

    def has_more(self) -> bool:
        return self._has_more

    def loaded_count(self) -> int:
        return len(self._conversations)

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
    # Internal: cursor-driven fetch + table rendering
    # ------------------------------------------------------------------

    def _reset_and_fetch(self) -> None:
        """Wipe the table and load the first page from the current filter."""
        self._next_cursor = ""
        self._has_more = False
        self._conversations = []
        self._table.clear()
        page = self._fetch_page(cursor="")
        self._merge_page(page)
        if self._conversations:
            self._table.move_cursor(row=0)
        self._update_title()

    # Mode -> extra filter kwargs for ``list_conversations``. "all" (and
    # any unknown mode) maps to no filters; "recent" is handled separately
    # because it isn't a paginated view.
    _MODE_FILTERS: Dict[str, Dict[str, Any]] = {
        "all": {},
        "starred": {"starred": True},
        "pinned": {"pinned": True},
        "archived": {"archived": True, "include_archived": True},
    }

    def _fetch_page(self, cursor: str) -> PaginatedResult:
        """Run the right cursor-mode DB query for the current mode + search."""
        ps = self.DEFAULT_PAGE_SIZE
        # Search overlay overrides the tab -- searching against the
        # whole DB is more useful than searching within a single tab.
        if self._search:
            # cursor is always provided, so db returns PaginatedResult.
            return cast(
                PaginatedResult,
                self._db.search_conversations(
                    self._search, cursor=cursor, page_size=ps
                ),
            )

        if self._mode == "recent":
            # "Recent" is a fixed 20-row snapshot, not a paginated view:
            # always fetch page 1 and drop has_more/next_cursor so
            # load_more() stays a no-op on this tab.
            recent = cast(
                PaginatedResult,
                self._db.list_conversations(cursor="", page_size=20),
            )
            return PaginatedResult(items=recent.items, next_cursor=None, has_more=False)

        filters = self._MODE_FILTERS.get(self._mode, {})
        # cursor is always provided, so db returns PaginatedResult.
        return cast(
            PaginatedResult,
            self._db.list_conversations(cursor=cursor, page_size=ps, **filters),
        )

    def _merge_page(self, page: PaginatedResult) -> int:
        """Append page items to the table; update cursor / has_more."""
        added = 0
        for conv in page.items:
            updated = getattr(conv, "updated_at", None)
            updated_str = updated.strftime("%Y-%m-%d") if updated else ""
            self._table.add_row(
                _flags(conv),
                _title(conv),
                updated_str,
                key=str(getattr(conv, "id", "")),
            )
            self._conversations.append(conv)
            added += 1
        self._next_cursor = page.next_cursor
        self._has_more = page.has_more
        return added

    def _update_title(self) -> None:
        """Reflect pagination state in the sidebar header."""
        n = len(self._conversations)
        if self._has_more:
            self._title_label.update(f"conversations · {n} loaded · more (Ctrl+L)")
        elif n > 0:
            self._title_label.update(f"conversations · {n}")
        else:
            self._title_label.update("conversations")

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
