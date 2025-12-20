"""
View system for CTK - composable, non-destructive conversation views.

Views provide filtered, ordered, annotated perspectives on conversations
without modifying the underlying data. They follow SICP principles:
- Abstraction: Views abstract over raw conversation data
- Closure: Combining views produces views (union, intersect, subtract)
- Composition: Complex views built from simple primitives
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union, Literal
from datetime import datetime
from enum import Enum


class ViewSelectionType(Enum):
    """How a view selects its conversations."""
    ITEMS = "items"           # Explicit list of conversation IDs
    QUERY = "query"           # Dynamic query against database
    UNION = "union"           # Union of other views
    INTERSECT = "intersect"   # Intersection of other views
    SUBTRACT = "subtract"     # Set difference (A - B)


class PathSelection(Enum):
    """How to select paths within a conversation tree."""
    DEFAULT = "default"       # Longest path (default behavior)
    ALL = "all"               # Entire tree
    EXPLICIT = "explicit"     # Explicit path specified


@dataclass
class TreePath:
    """
    Specification for selecting a path or subtree within a conversation.

    Examples:
        TreePath()                          # Default (longest path)
        TreePath(path="m1/m3/m47")          # Explicit path to leaf
        TreePath(subtree="m23")             # Subtree rooted at m23
        TreePath(selection=PathSelection.ALL)  # Entire tree
    """
    selection: PathSelection = PathSelection.DEFAULT
    path: Optional[str] = None       # e.g., "m1/m3/m47"
    subtree: Optional[str] = None    # Root of subtree to include

    @classmethod
    def default(cls) -> 'TreePath':
        return cls(selection=PathSelection.DEFAULT)

    @classmethod
    def from_path(cls, path: str) -> 'TreePath':
        return cls(selection=PathSelection.EXPLICIT, path=path)

    @classmethod
    def from_subtree(cls, root: str) -> 'TreePath':
        return cls(selection=PathSelection.EXPLICIT, subtree=root)

    @classmethod
    def all(cls) -> 'TreePath':
        return cls(selection=PathSelection.ALL)


@dataclass
class ContentSnapshot:
    """
    Optional snapshot of conversation state when added to view.
    Used for drift detection, not data storage.
    """
    hash: str                        # Content hash for drift detection
    title: Optional[str] = None      # Title at snapshot time
    message_count: Optional[int] = None
    captured_at: Optional[datetime] = None


@dataclass
class ViewItem:
    """
    A single item in a view - a reference to a conversation with optional overrides.

    Overrides (title, description, note) exist only in the view context
    and don't modify the underlying conversation.
    """
    id: str                                    # Conversation ID

    # Metadata overrides (view-local, don't touch original)
    title: Optional[str] = None                # Override display title
    description: Optional[str] = None          # Override description
    note: Optional[str] = None                 # Annotation/commentary

    # Tree selection
    tree_path: TreePath = field(default_factory=TreePath.default)

    # Change tracking (optional)
    snapshot: Optional[ContentSnapshot] = None
    added_at: Optional[datetime] = None


@dataclass
class ViewSection:
    """
    A section marker in a narrative view.
    Provides structure and context between conversation items.
    """
    title: str
    note: Optional[str] = None


# Union type for sequence items (conversation or section)
SequenceItem = Union[ViewItem, ViewSection]


@dataclass
class ViewQuery:
    """
    Query specification for dynamic view selection.
    All fields are optional filters (AND-ed together).
    """
    tags: Optional[List[str]] = None           # Must have these tags
    source: Optional[str] = None               # e.g., "ChatGPT", "Claude"
    model: Optional[str] = None                # e.g., "gpt-4", "claude-3"
    starred: Optional[bool] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    updated_after: Optional[datetime] = None
    updated_before: Optional[datetime] = None
    title_contains: Optional[str] = None       # Title search
    content_contains: Optional[str] = None     # Full-text search


@dataclass
class ViewOrder:
    """Ordering specification for view results."""
    field: str = "created_at"                  # Field to sort by
    descending: bool = True                    # Sort direction

    @classmethod
    def parse(cls, spec: str) -> 'ViewOrder':
        """Parse order spec like 'created_at desc' or 'title asc'."""
        parts = spec.strip().split()
        field = parts[0] if parts else "created_at"
        descending = len(parts) < 2 or parts[1].lower() in ('desc', 'descending')
        return cls(field=field, descending=descending)

    def __str__(self) -> str:
        direction = "desc" if self.descending else "asc"
        return f"{self.field} {direction}"


@dataclass
class ViewComposition:
    """
    Composition of multiple views via set operations.
    """
    operation: Literal["union", "intersect", "subtract"]
    view_names: List[str]  # Names of views to compose


@dataclass
class ExportHints:
    """
    Optional hints for exporters consuming this view.
    These don't affect view semantics, just export behavior.
    """
    format: Optional[str] = None               # Preferred format
    draft: bool = False                        # Mark as draft
    date_prefix: bool = True                   # Include date in filenames


@dataclass
class View:
    """
    A view specification - a composable, non-destructive lens over conversations.

    A view can select conversations by:
    1. Explicit items list (curated)
    2. Query (dynamic)
    3. Composition of other views (union, intersect, subtract)

    Views support:
    - Metadata overrides (titles, descriptions, notes)
    - Tree path selection (for branching conversations)
    - Ordering
    - Narrative sections
    - Change tracking
    """
    # Identity
    name: str
    description: Optional[str] = None
    author: Optional[str] = None
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    version: int = 1

    # Selection (exactly one of these should be set)
    items: Optional[List[SequenceItem]] = None      # Explicit list
    query: Optional[ViewQuery] = None                # Dynamic query
    composition: Optional[ViewComposition] = None    # Set operation on views

    # Additional filtering (applied after selection)
    where: Optional[ViewQuery] = None

    # Ordering
    order: Optional[ViewOrder] = None

    # Limits
    limit: Optional[int] = None

    # Options
    track_changes: bool = False
    skip_missing: bool = True

    # Export hints
    export: Optional[ExportHints] = None

    @property
    def selection_type(self) -> ViewSelectionType:
        """Determine how this view selects conversations."""
        if self.items is not None:
            return ViewSelectionType.ITEMS
        elif self.query is not None:
            return ViewSelectionType.QUERY
        elif self.composition is not None:
            op = self.composition.operation
            if op == "union":
                return ViewSelectionType.UNION
            elif op == "intersect":
                return ViewSelectionType.INTERSECT
            elif op == "subtract":
                return ViewSelectionType.SUBTRACT
        # Default to empty items list
        return ViewSelectionType.ITEMS

    def get_items(self) -> List[ViewItem]:
        """Get only ViewItem entries (filter out sections)."""
        if self.items is None:
            return []
        return [item for item in self.items if isinstance(item, ViewItem)]

    def get_sections(self) -> List[ViewSection]:
        """Get only ViewSection entries."""
        if self.items is None:
            return []
        return [item for item in self.items if isinstance(item, ViewSection)]


@dataclass
class EvaluatedViewItem:
    """
    A view item after evaluation - includes resolved conversation data.
    """
    item: ViewItem                             # Original view item
    conversation: Any                          # Resolved ConversationTree
    effective_title: str                       # Title (override or original)
    effective_description: Optional[str]       # Description (override or original)
    index: int                                 # Position in view
    section: Optional[str] = None              # Current section (if any)
    drift_detected: bool = False               # Content changed since snapshot


@dataclass
class EvaluatedView:
    """
    A view after evaluation against a database.
    Contains resolved conversation references ready for use.
    """
    view: View                                 # Original view spec
    items: List[EvaluatedViewItem]             # Resolved items
    missing_ids: List[str] = field(default_factory=list)  # IDs not found
    drift_count: int = 0                       # Number of items with drift
    evaluated_at: datetime = field(default_factory=datetime.now)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    @property
    def conversations(self):
        """Get just the conversations (for export compatibility)."""
        return [item.conversation for item in self.items]


# =============================================================================
# YAML Serialization / Deserialization
# =============================================================================

def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse datetime from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try ISO format first
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            pass
        # Try date only
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            pass
    return None


def _parse_tree_path(value: Any) -> TreePath:
    """Parse tree path specification."""
    if value is None:
        return TreePath.default()
    if isinstance(value, str):
        if value == "default" or value == "longest":
            return TreePath.default()
        elif value == "all":
            return TreePath.all()
        elif value.startswith("subtree:"):
            return TreePath.from_subtree(value[8:])
        else:
            # Assume explicit path like "m1/m3/m47"
            return TreePath.from_path(value)
    if isinstance(value, dict):
        if "subtree" in value:
            return TreePath.from_subtree(value["subtree"])
        elif "path" in value:
            return TreePath.from_path(value["path"])
    return TreePath.default()


def _parse_view_item(data: Dict[str, Any]) -> ViewItem:
    """Parse a single view item from YAML dict."""
    snapshot = None
    if "snapshot" in data:
        snap_data = data["snapshot"]
        snapshot = ContentSnapshot(
            hash=snap_data.get("hash", ""),
            title=snap_data.get("title"),
            message_count=snap_data.get("message_count"),
            captured_at=_parse_datetime(snap_data.get("captured_at"))
        )

    return ViewItem(
        id=data["id"],
        title=data.get("title"),
        description=data.get("description"),
        note=data.get("note"),
        tree_path=_parse_tree_path(data.get("path")),
        snapshot=snapshot,
        added_at=_parse_datetime(data.get("added_at"))
    )


def _parse_view_section(data: Dict[str, Any]) -> ViewSection:
    """Parse a section marker from YAML dict."""
    return ViewSection(
        title=data.get("section", data.get("title", "Untitled Section")),
        note=data.get("note")
    )


def _parse_sequence_item(data: Any) -> Optional[SequenceItem]:
    """Parse a sequence item (either ViewItem or ViewSection)."""
    if not isinstance(data, dict):
        return None
    if "section" in data:
        return _parse_view_section(data)
    elif "id" in data:
        return _parse_view_item(data)
    return None


def _parse_query(data: Optional[Dict[str, Any]]) -> Optional[ViewQuery]:
    """Parse query specification from YAML dict."""
    if data is None:
        return None
    return ViewQuery(
        tags=data.get("tags"),
        source=data.get("source"),
        model=data.get("model"),
        starred=data.get("starred"),
        pinned=data.get("pinned"),
        archived=data.get("archived"),
        created_after=_parse_datetime(data.get("created_after")),
        created_before=_parse_datetime(data.get("created_before")),
        updated_after=_parse_datetime(data.get("updated_after")),
        updated_before=_parse_datetime(data.get("updated_before")),
        title_contains=data.get("title_contains"),
        content_contains=data.get("content_contains")
    )


def _parse_composition(data: Dict[str, Any]) -> Optional[ViewComposition]:
    """Parse composition (union/intersect/subtract) from YAML."""
    for op in ("union", "intersect", "subtract"):
        if op in data:
            view_names = data[op]
            if isinstance(view_names, list):
                return ViewComposition(operation=op, view_names=view_names)
    return None


def _parse_export_hints(data: Optional[Dict[str, Any]]) -> Optional[ExportHints]:
    """Parse export hints from YAML dict."""
    if data is None:
        return None
    return ExportHints(
        format=data.get("format"),
        draft=data.get("draft", False),
        date_prefix=data.get("date_prefix", True)
    )


def parse_view(data: Dict[str, Any]) -> View:
    """
    Parse a View from a YAML dictionary.

    Args:
        data: Dictionary from YAML parsing

    Returns:
        View object
    """
    # Parse items/sequence
    items = None
    items_data = data.get("items") or data.get("sequence")
    if items_data:
        items = []
        for item_data in items_data:
            item = _parse_sequence_item(item_data)
            if item:
                items.append(item)

    # Parse order
    order = None
    if "order" in data:
        order_val = data["order"]
        if isinstance(order_val, str):
            if order_val == "manual":
                order = None  # Manual = use items order
            else:
                order = ViewOrder.parse(order_val)
        elif isinstance(order_val, dict):
            order = ViewOrder(
                field=order_val.get("field", "created_at"),
                descending=order_val.get("descending", True)
            )

    return View(
        name=data.get("name", "unnamed"),
        description=data.get("description"),
        author=data.get("author"),
        created=_parse_datetime(data.get("created")),
        updated=_parse_datetime(data.get("updated")),
        version=data.get("version", 1),
        items=items,
        query=_parse_query(data.get("select") or data.get("query")),
        composition=_parse_composition(data),
        where=_parse_query(data.get("where")),
        order=order,
        limit=data.get("limit"),
        track_changes=data.get("track_changes", False),
        skip_missing=data.get("skip_missing", True),
        export=_parse_export_hints(data.get("export"))
    )


def load_view(path: str) -> View:
    """
    Load a View from a YAML file.

    Args:
        path: Path to YAML file

    Returns:
        View object
    """
    import yaml
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return parse_view(data)


def _serialize_tree_path(tree_path: TreePath) -> Optional[str]:
    """Serialize TreePath to YAML-friendly format."""
    if tree_path.selection == PathSelection.DEFAULT:
        return None  # Omit default
    elif tree_path.selection == PathSelection.ALL:
        return "all"
    elif tree_path.path:
        return tree_path.path
    elif tree_path.subtree:
        return f"subtree:{tree_path.subtree}"
    return None


def _serialize_view_item(item: ViewItem) -> Dict[str, Any]:
    """Serialize ViewItem to YAML-friendly dict."""
    result: Dict[str, Any] = {"id": item.id}

    if item.title:
        result["title"] = item.title
    if item.description:
        result["description"] = item.description
    if item.note:
        result["note"] = item.note

    path_str = _serialize_tree_path(item.tree_path)
    if path_str:
        result["path"] = path_str

    if item.added_at:
        result["added_at"] = item.added_at.isoformat()

    if item.snapshot:
        result["snapshot"] = {
            "hash": item.snapshot.hash,
        }
        if item.snapshot.title:
            result["snapshot"]["title"] = item.snapshot.title
        if item.snapshot.message_count:
            result["snapshot"]["message_count"] = item.snapshot.message_count
        if item.snapshot.captured_at:
            result["snapshot"]["captured_at"] = item.snapshot.captured_at.isoformat()

    return result


def _serialize_section(section: ViewSection) -> Dict[str, Any]:
    """Serialize ViewSection to YAML-friendly dict."""
    result: Dict[str, Any] = {"section": section.title}
    if section.note:
        result["note"] = section.note
    return result


def _serialize_query(query: ViewQuery) -> Dict[str, Any]:
    """Serialize ViewQuery to YAML-friendly dict."""
    result: Dict[str, Any] = {}
    if query.tags:
        result["tags"] = query.tags
    if query.source:
        result["source"] = query.source
    if query.model:
        result["model"] = query.model
    if query.starred is not None:
        result["starred"] = query.starred
    if query.pinned is not None:
        result["pinned"] = query.pinned
    if query.archived is not None:
        result["archived"] = query.archived
    if query.created_after:
        result["created_after"] = query.created_after.isoformat()
    if query.created_before:
        result["created_before"] = query.created_before.isoformat()
    if query.updated_after:
        result["updated_after"] = query.updated_after.isoformat()
    if query.updated_before:
        result["updated_before"] = query.updated_before.isoformat()
    if query.title_contains:
        result["title_contains"] = query.title_contains
    if query.content_contains:
        result["content_contains"] = query.content_contains
    return result


def serialize_view(view: View) -> Dict[str, Any]:
    """
    Serialize a View to a YAML-friendly dictionary.

    Args:
        view: View object

    Returns:
        Dictionary suitable for YAML dumping
    """
    result: Dict[str, Any] = {"name": view.name}

    if view.description:
        result["description"] = view.description
    if view.author:
        result["author"] = view.author
    if view.created:
        result["created"] = view.created.isoformat()
    if view.updated:
        result["updated"] = view.updated.isoformat()
    if view.version != 1:
        result["version"] = view.version

    # Selection
    if view.items:
        result["items"] = []
        for item in view.items:
            if isinstance(item, ViewItem):
                result["items"].append(_serialize_view_item(item))
            elif isinstance(item, ViewSection):
                result["items"].append(_serialize_section(item))

    if view.query:
        result["select"] = _serialize_query(view.query)

    if view.composition:
        result[view.composition.operation] = view.composition.view_names

    # Filtering
    if view.where:
        result["where"] = _serialize_query(view.where)

    # Ordering
    if view.order:
        result["order"] = str(view.order)

    # Limits
    if view.limit:
        result["limit"] = view.limit

    # Options
    if view.track_changes:
        result["track_changes"] = True
    if not view.skip_missing:
        result["skip_missing"] = False

    # Export hints
    if view.export:
        export_dict: Dict[str, Any] = {}
        if view.export.format:
            export_dict["format"] = view.export.format
        if view.export.draft:
            export_dict["draft"] = True
        if not view.export.date_prefix:
            export_dict["date_prefix"] = False
        if export_dict:
            result["export"] = export_dict

    return result


def save_view(view: View, path: str) -> None:
    """
    Save a View to a YAML file.

    Args:
        view: View object
        path: Path to YAML file
    """
    import yaml
    data = serialize_view(view)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


# =============================================================================
# View Evaluation
# =============================================================================

import hashlib


def _compute_content_hash(conversation: Any) -> str:
    """Compute a hash of conversation content for drift detection."""
    # Get all message content
    content_parts = []
    if hasattr(conversation, 'message_map'):
        for msg_id, msg in sorted(conversation.message_map.items()):
            if hasattr(msg, 'content') and msg.content:
                text = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)
                content_parts.append(f"{msg_id}:{text}")

    content_str = "\n".join(content_parts)
    return hashlib.sha256(content_str.encode('utf-8')).hexdigest()[:16]


def _matches_query(conversation: Any, query: ViewQuery) -> bool:
    """Check if a conversation matches query criteria."""
    meta = conversation.metadata if hasattr(conversation, 'metadata') else None

    # Tags filter
    if query.tags:
        conv_tags = set(meta.tags) if meta and meta.tags else set()
        if not set(query.tags).issubset(conv_tags):
            return False

    # Source filter
    if query.source:
        conv_source = meta.source if meta else None
        if conv_source != query.source:
            return False

    # Model filter
    if query.model:
        conv_model = meta.model if meta else None
        if not conv_model or query.model not in conv_model:
            return False

    # Starred filter
    if query.starred is not None:
        is_starred = bool(meta.starred_at) if meta else False
        if is_starred != query.starred:
            return False

    # Pinned filter
    if query.pinned is not None:
        is_pinned = bool(meta.pinned_at) if meta else False
        if is_pinned != query.pinned:
            return False

    # Archived filter
    if query.archived is not None:
        is_archived = bool(meta.archived_at) if meta else False
        if is_archived != query.archived:
            return False

    # Date filters
    created = meta.created_at if meta else None
    if query.created_after and created:
        if created < query.created_after:
            return False
    if query.created_before and created:
        if created > query.created_before:
            return False

    updated = meta.updated_at if meta else None
    if query.updated_after and updated:
        if updated < query.updated_after:
            return False
    if query.updated_before and updated:
        if updated > query.updated_before:
            return False

    # Title search
    if query.title_contains:
        title = conversation.title or ""
        if query.title_contains.lower() not in title.lower():
            return False

    # Content search (expensive - do last)
    if query.content_contains:
        found = False
        search_term = query.content_contains.lower()
        if hasattr(conversation, 'message_map'):
            for msg in conversation.message_map.values():
                if hasattr(msg, 'content') and msg.content:
                    text = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)
                    if search_term in text.lower():
                        found = True
                        break
        if not found:
            return False

    return True


def _sort_conversations(
    conversations: List[Any],
    order: Optional[ViewOrder]
) -> List[Any]:
    """Sort conversations according to order specification."""
    if not order:
        return conversations

    def get_sort_key(conv):
        meta = conv.metadata if hasattr(conv, 'metadata') else None

        if order.field == "created_at":
            return meta.created_at if meta and meta.created_at else datetime.min
        elif order.field == "updated_at":
            return meta.updated_at if meta and meta.updated_at else datetime.min
        elif order.field == "title":
            return (conv.title or "").lower()
        elif order.field == "message_count":
            return len(conv.message_map) if hasattr(conv, 'message_map') else 0
        else:
            return meta.created_at if meta and meta.created_at else datetime.min

    return sorted(conversations, key=get_sort_key, reverse=order.descending)


class ViewEvaluator:
    """
    Evaluates views against a database to produce resolved conversation lists.

    The evaluator handles:
    - Explicit item lists
    - Dynamic queries
    - View composition (union, intersect, subtract)
    - Filtering and ordering
    - Drift detection
    """

    def __init__(self, db: Any, view_loader: Optional[callable] = None):
        """
        Initialize evaluator.

        Args:
            db: ConversationDB instance
            view_loader: Optional callable to load views by name (for composition)
        """
        self.db = db
        self.view_loader = view_loader
        self._view_cache: Dict[str, View] = {}

    def evaluate(self, view: View) -> EvaluatedView:
        """
        Evaluate a view against the database.

        Args:
            view: View specification to evaluate

        Returns:
            EvaluatedView with resolved conversations
        """
        # Step 1: Get initial conversation set based on selection type
        conversations = self._resolve_selection(view)

        # Step 2: Apply additional filters
        if view.where:
            conversations = [c for c in conversations if _matches_query(c, view.where)]

        # Step 3: Apply ordering (unless using manual order from items)
        if view.order and view.selection_type != ViewSelectionType.ITEMS:
            conversations = _sort_conversations(conversations, view.order)

        # Step 4: Apply limit
        if view.limit and len(conversations) > view.limit:
            conversations = conversations[:view.limit]

        # Step 5: Build evaluated items
        evaluated_items = []
        missing_ids = []
        drift_count = 0
        current_section = None

        if view.selection_type == ViewSelectionType.ITEMS and view.items:
            # For explicit items, maintain order and include sections
            conv_map = {c.id: c for c in conversations}

            for idx, item in enumerate(view.items):
                if isinstance(item, ViewSection):
                    current_section = item.title
                    continue

                if isinstance(item, ViewItem):
                    conv = conv_map.get(item.id)
                    if conv is None:
                        if view.skip_missing:
                            missing_ids.append(item.id)
                            continue
                        else:
                            raise ValueError(f"Conversation not found: {item.id}")

                    # Check for drift
                    drift = False
                    if view.track_changes and item.snapshot:
                        current_hash = _compute_content_hash(conv)
                        if current_hash != item.snapshot.hash:
                            drift = True
                            drift_count += 1

                    # Determine effective title/description
                    effective_title = item.title or conv.title or f"Conversation {conv.id[:8]}"
                    effective_desc = item.description
                    if not effective_desc and hasattr(conv, 'metadata') and conv.metadata:
                        effective_desc = getattr(conv.metadata, 'description', None)

                    evaluated_items.append(EvaluatedViewItem(
                        item=item,
                        conversation=conv,
                        effective_title=effective_title,
                        effective_description=effective_desc,
                        index=len(evaluated_items),
                        section=current_section,
                        drift_detected=drift
                    ))
        else:
            # For query/composition results, create simple items
            for idx, conv in enumerate(conversations):
                item = ViewItem(id=conv.id)
                evaluated_items.append(EvaluatedViewItem(
                    item=item,
                    conversation=conv,
                    effective_title=conv.title or f"Conversation {conv.id[:8]}",
                    effective_description=None,
                    index=idx,
                    section=None,
                    drift_detected=False
                ))

        return EvaluatedView(
            view=view,
            items=evaluated_items,
            missing_ids=missing_ids,
            drift_count=drift_count
        )

    def _resolve_selection(self, view: View) -> List[Any]:
        """Resolve the initial set of conversations based on selection type."""
        selection_type = view.selection_type

        if selection_type == ViewSelectionType.ITEMS:
            return self._resolve_items(view)
        elif selection_type == ViewSelectionType.QUERY:
            return self._resolve_query(view)
        elif selection_type in (ViewSelectionType.UNION, ViewSelectionType.INTERSECT, ViewSelectionType.SUBTRACT):
            return self._resolve_composition(view)
        else:
            return []

    def _resolve_items(self, view: View) -> List[Any]:
        """Resolve explicit item list."""
        if not view.items:
            return []

        conversations = []
        for item in view.items:
            if isinstance(item, ViewItem):
                conv = self.db.load_conversation(item.id)
                if conv:
                    conversations.append(conv)
        return conversations

    def _resolve_query(self, view: View) -> List[Any]:
        """Resolve query-based selection."""
        if not view.query:
            return []

        # Get all conversations (we'll filter in Python for flexibility)
        # In production, this could be optimized with SQL
        all_convs = []
        for conv_info in self.db.list_conversations(limit=None):
            conv = self.db.load_conversation(conv_info.id)
            if conv and _matches_query(conv, view.query):
                all_convs.append(conv)

        return all_convs

    def _resolve_composition(self, view: View) -> List[Any]:
        """Resolve view composition (union, intersect, subtract)."""
        if not view.composition:
            return []

        # Load and evaluate referenced views
        evaluated_views = []
        for view_name in view.composition.view_names:
            ref_view = self._load_view(view_name)
            if ref_view:
                evaluated = self.evaluate(ref_view)
                evaluated_views.append(evaluated)

        if not evaluated_views:
            return []

        # Perform set operation
        op = view.composition.operation

        if op == "union":
            # Union: all conversations from all views (deduplicated)
            seen_ids = set()
            result = []
            for ev in evaluated_views:
                for item in ev.items:
                    if item.conversation.id not in seen_ids:
                        seen_ids.add(item.conversation.id)
                        result.append(item.conversation)
            return result

        elif op == "intersect":
            # Intersection: only conversations in ALL views
            if not evaluated_views:
                return []
            id_sets = [set(item.conversation.id for item in ev.items) for ev in evaluated_views]
            common_ids = id_sets[0]
            for ids in id_sets[1:]:
                common_ids &= ids

            # Return from first view to maintain order
            return [item.conversation for item in evaluated_views[0].items
                    if item.conversation.id in common_ids]

        elif op == "subtract":
            # Difference: A - B - C - ...
            if not evaluated_views:
                return []
            base_convs = {item.conversation.id: item.conversation
                         for item in evaluated_views[0].items}
            for ev in evaluated_views[1:]:
                for item in ev.items:
                    base_convs.pop(item.conversation.id, None)
            return list(base_convs.values())

        return []

    def _load_view(self, name: str) -> Optional[View]:
        """Load a view by name (for composition)."""
        if name in self._view_cache:
            return self._view_cache[name]

        if self.view_loader:
            view = self.view_loader(name)
            if view:
                self._view_cache[name] = view
                return view

        return None


def evaluate_view(view: View, db: Any, view_loader: Optional[callable] = None) -> EvaluatedView:
    """
    Convenience function to evaluate a view.

    Args:
        view: View specification
        db: ConversationDB instance
        view_loader: Optional callable to load views by name

    Returns:
        EvaluatedView with resolved conversations
    """
    evaluator = ViewEvaluator(db, view_loader)
    return evaluator.evaluate(view)


# =============================================================================
# View Storage (views/ directory management)
# =============================================================================

from pathlib import Path
import os


class ViewStore:
    """
    Manages view files in a views/ directory alongside a database.

    Views are stored as YAML files in:
        <db_path>/views/<view_name>.yaml

    The ViewStore provides:
    - CRUD operations for views
    - Listing and searching views
    - View evaluation with automatic composition support
    """

    def __init__(self, db_path: str):
        """
        Initialize ViewStore.

        Args:
            db_path: Path to database directory (views stored in <db_path>/views/)
        """
        self.db_path = Path(db_path)
        self.views_dir = self.db_path / "views"

    def ensure_views_dir(self) -> Path:
        """Ensure views directory exists."""
        self.views_dir.mkdir(parents=True, exist_ok=True)
        return self.views_dir

    def _view_path(self, name: str) -> Path:
        """Get path to a view file."""
        # Sanitize name
        safe_name = name.replace("/", "_").replace("\\", "_")
        if not safe_name.endswith(".yaml"):
            safe_name += ".yaml"
        return self.views_dir / safe_name

    def exists(self, name: str) -> bool:
        """Check if a view exists."""
        return self._view_path(name).exists()

    def load(self, name: str) -> Optional[View]:
        """
        Load a view by name.

        Args:
            name: View name (without .yaml extension)

        Returns:
            View object or None if not found
        """
        path = self._view_path(name)
        if not path.exists():
            return None
        return load_view(str(path))

    def save(self, view: View) -> Path:
        """
        Save a view to the store.

        Args:
            view: View object to save

        Returns:
            Path to saved file
        """
        self.ensure_views_dir()
        path = self._view_path(view.name)

        # Update timestamp
        view.updated = datetime.now()
        if not view.created:
            view.created = view.updated

        save_view(view, str(path))
        return path

    def delete(self, name: str) -> bool:
        """
        Delete a view.

        Args:
            name: View name

        Returns:
            True if deleted, False if not found
        """
        path = self._view_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_views(self) -> List[str]:
        """
        List all view names.

        Returns:
            List of view names (without .yaml extension)
        """
        if not self.views_dir.exists():
            return []

        views = []
        for path in self.views_dir.glob("*.yaml"):
            views.append(path.stem)
        return sorted(views)

    def list_views_detailed(self) -> List[Dict[str, Any]]:
        """
        List views with metadata.

        Returns:
            List of dicts with view info
        """
        result = []
        for name in self.list_views():
            view = self.load(name)
            if view:
                result.append({
                    "name": view.name,
                    "description": view.description,
                    "selection_type": view.selection_type.value,
                    "item_count": len(view.items) if view.items else 0,
                    "created": view.created,
                    "updated": view.updated,
                })
        return result

    def get_view_loader(self) -> callable:
        """
        Get a view loader function for use with ViewEvaluator.

        Returns:
            Callable that loads views by name
        """
        return self.load

    def evaluate(self, name: str, db: Any) -> Optional[EvaluatedView]:
        """
        Load and evaluate a view.

        Args:
            name: View name
            db: ConversationDB instance

        Returns:
            EvaluatedView or None if view not found
        """
        view = self.load(name)
        if not view:
            return None

        evaluator = ViewEvaluator(db, self.get_view_loader())
        return evaluator.evaluate(view)

    def check_view(self, name: str, db: Any) -> Dict[str, Any]:
        """
        Check a view for issues (missing conversations, drift, etc).

        Args:
            name: View name
            db: ConversationDB instance

        Returns:
            Dict with check results
        """
        view = self.load(name)
        if not view:
            return {"error": f"View '{name}' not found"}

        evaluated = self.evaluate(name, db)
        if not evaluated:
            return {"error": f"Failed to evaluate view '{name}'"}

        return {
            "name": name,
            "total_items": len(view.items) if view.items else 0,
            "resolved_items": len(evaluated.items),
            "missing_ids": evaluated.missing_ids,
            "drift_count": evaluated.drift_count,
            "issues": len(evaluated.missing_ids) + evaluated.drift_count
        }

    def create_view(
        self,
        name: str,
        description: Optional[str] = None,
        items: Optional[List[str]] = None,
        query: Optional[Dict[str, Any]] = None,
        author: Optional[str] = None
    ) -> View:
        """
        Create a new view with common options.

        Args:
            name: View name
            description: Optional description
            items: Optional list of conversation IDs
            query: Optional query specification dict
            author: Optional author name

        Returns:
            Created View object (not yet saved)
        """
        view_items = None
        if items:
            view_items = [ViewItem(id=item_id) for item_id in items]

        view_query = None
        if query:
            view_query = ViewQuery(
                tags=query.get("tags"),
                source=query.get("source"),
                model=query.get("model"),
                starred=query.get("starred"),
                pinned=query.get("pinned"),
                archived=query.get("archived"),
                title_contains=query.get("title_contains"),
                content_contains=query.get("content_contains")
            )

        return View(
            name=name,
            description=description,
            author=author,
            created=datetime.now(),
            items=view_items,
            query=view_query
        )

    def add_to_view(
        self,
        name: str,
        conversation_id: str,
        title: Optional[str] = None,
        note: Optional[str] = None,
        db: Optional[Any] = None
    ) -> bool:
        """
        Add a conversation to an existing view.

        Args:
            name: View name
            conversation_id: Conversation ID to add
            title: Optional title override
            note: Optional note
            db: Optional database for snapshot

        Returns:
            True if added, False if view not found
        """
        view = self.load(name)
        if not view:
            return False

        # Initialize items if needed
        if view.items is None:
            view.items = []

        # Check if already in view
        for item in view.items:
            if isinstance(item, ViewItem) and item.id == conversation_id:
                return True  # Already present

        # Create snapshot if db provided and tracking enabled
        snapshot = None
        if db and view.track_changes:
            conv = db.load_conversation(conversation_id)
            if conv:
                snapshot = ContentSnapshot(
                    hash=_compute_content_hash(conv),
                    title=conv.title,
                    message_count=len(conv.message_map) if hasattr(conv, 'message_map') else 0,
                    captured_at=datetime.now()
                )

        item = ViewItem(
            id=conversation_id,
            title=title,
            note=note,
            snapshot=snapshot,
            added_at=datetime.now()
        )

        view.items.append(item)
        self.save(view)
        return True

    def remove_from_view(self, name: str, conversation_id: str) -> bool:
        """
        Remove a conversation from a view.

        Args:
            name: View name
            conversation_id: Conversation ID to remove

        Returns:
            True if removed, False if not found
        """
        view = self.load(name)
        if not view or not view.items:
            return False

        original_len = len(view.items)
        view.items = [
            item for item in view.items
            if not (isinstance(item, ViewItem) and item.id == conversation_id)
        ]

        if len(view.items) < original_len:
            self.save(view)
            return True
        return False

    def get_views_for_conversation(self, conversation_id: str) -> List[str]:
        """
        Find all views that contain a conversation.

        Args:
            conversation_id: Conversation ID to search for

        Returns:
            List of view names containing this conversation
        """
        result = []
        for name in self.list_views():
            view = self.load(name)
            if view and view.items:
                for item in view.items:
                    if isinstance(item, ViewItem) and item.id == conversation_id:
                        result.append(name)
                        break
        return result
