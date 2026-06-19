# E-core DB Foundations + C Hotfixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace inferred DB state (substring-matched schema, dual-written metadata, write-only path table) with structured, single-sourced state plus the missing indexes and N+1 fixes, and ship C's two zero-dependency tool hotfixes alongside.

**Architecture:** A new `PRAGMA user_version` migration runner (`ctk/core/migrations.py`) becomes the only place schema changes happen; it is the prerequisite for the index additions and the `is_branching` column. Conversation metadata columns become the single source of truth (the blob keeps only `custom_data`). The list read path stops being N+1. C's hotfixes (defensive `_format_message`, provider-derived tool routing) are independent and land first.

**Tech Stack:** Python 3.12, SQLAlchemy (SQLite), pytest, mypy, black, flake8.

**Specs:** `docs/plans/2026-06-18-db-foundations-design.md` (E-core), `docs/plans/2026-06-18-unified-tool-surface-design.md` (C, workstream W0 only here).

## Global Constraints

- Green gate before each commit: `python -m pytest <touched test files> -q -o addopts=""` pass; `python -m mypy ctk --ignore-missing-imports` reports 0 errors; `python -m black <touched files>` then `python -m flake8 <touched files> --max-line-length=100 --ignore=E203,W503` clean.
- The repo has a write hook that BLOCKS any file containing an em-dash character or the word "leverage". Use plain hyphens and ordinary punctuation in every file, including docstrings and test strings.
- Import shared values from `ctk/core/constants.py`; do not hardcode timeouts/limits.
- Never use a bare `except:`; always name the exception type. `except Exception:` only in cleanup/finally with logging.
- `ConversationDB(":memory:")` and `ConversationDB("postgresql://...")` both set `self.db_dir = None`; only `:memory:` is SQLite. Detect SQLite with `engine.dialect.name == "sqlite"`, never with `db_dir`.
- `ConversationModel.updated_at` has `onupdate=func.now()`; the ORM overwrites explicit values. Use raw SQL when a test must force a timestamp.
- Run the full suite once at the end of each task group: `python -m pytest tests/unit -q -o addopts=""`.

---

## Task 1: C-W0a -- type-safe `_format_message`

**Files:**
- Modify: `ctk/llm/openai.py` (`_format_message`, around line 350-359)
- Test: `tests/unit/test_llm_openai.py` (add tests; create if absent)

**Interfaces:**
- Consumes: `OpenAIProvider._format_message(self, msg: Message) -> Dict[str, Any]`; `ctk.llm.base.Message(role, content, metadata)`; `OpenAIProvider._build_payload(...)` which maps `_format_message` over messages and is consumed by the openai SDK (must be JSON-serializable).
- Produces: nothing new; behavior change only (non-string content no longer crashes JSON serialization).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_llm_openai.py
import json
import pytest
from ctk.llm.base import Message, MessageRole
from ctk.llm.openai import OpenAIProvider

pytestmark = pytest.mark.unit


def _provider():
    # No network call happens during construction or _format_message.
    return OpenAIProvider(model="test-model", base_url="http://localhost:0/v1", api_key="x")


class _ContentObj:
    def get_text(self):
        return "hello from object"


def test_format_message_coerces_get_text_content():
    p = _provider()
    out = p._format_message(Message(role=MessageRole.USER, content=_ContentObj()))
    assert out["content"] == "hello from object"
    json.dumps(out)  # must be serializable


def test_format_message_coerces_non_string_content():
    p = _provider()
    out = p._format_message(Message(role=MessageRole.USER, content=12345))
    assert out["content"] == "12345"
    json.dumps(out)


def test_format_message_passes_plain_string():
    p = _provider()
    out = p._format_message(Message(role=MessageRole.ASSISTANT, content="plain"))
    assert out["content"] == "plain"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/test_llm_openai.py -k format_message -q -o addopts=""`
Expected: `test_format_message_coerces_get_text_content` and `_coerces_non_string_content` FAIL (the `_ContentObj` / int is passed through; the assert or `json.dumps` raises). Confirm the constructor signature in step 3 matches the real `OpenAIProvider.__init__`; if the kwargs differ, adapt `_provider()` to the real signature (read `ctk/llm/openai.py` `__init__`).

- [ ] **Step 3: Implement the coercion**

Replace the body of `_format_message` so content is normalized:

```python
def _format_message(self, msg: Message) -> Dict[str, Any]:
    content = msg.content
    if hasattr(content, "get_text"):
        content = content.get_text()
    elif content is None:
        content = ""
    elif not isinstance(content, str):
        content = str(content)
    formatted: Dict[str, Any] = {
        "role": msg.role.value,
        "content": content,
    }
    if msg.metadata and "tool_call_id" in msg.metadata:
        formatted["tool_call_id"] = msg.metadata["tool_call_id"]
    return formatted
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_llm_openai.py -k format_message -q -o addopts=""`
Expected: PASS (3 tests).

- [ ] **Step 5: Green gate and commit**

```bash
python -m black ctk/llm/openai.py tests/unit/test_llm_openai.py
python -m flake8 ctk/llm/openai.py tests/unit/test_llm_openai.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add ctk/llm/openai.py tests/unit/test_llm_openai.py
git commit -m "fix(llm): _format_message coerces non-string content to a JSON-serializable string"
```

---

## Task 2: C-W0b -- provider-derived tool routing

**Files:**
- Modify: `ctk/core/tools_registry.py` (add `provider_for_tool`)
- Modify: `ctk/tui/app.py` (`_execute_tool` around line 675; delete `_NETWORK_TOOL_NAMES` at line 673)
- Test: `tests/unit/test_tools_registry.py` (add; create if absent)

**Interfaces:**
- Consumes: `tools_registry._PROVIDERS: List[ToolProvider]` where `ToolProvider` has `.name` and `.tools` (list of dicts each with a `"name"` key); `ctk.core.network_tools` registers the `ctk.network` provider at import time.
- Produces: `tools_registry.provider_for_tool(name: str) -> Optional[str]` returning the owning provider name or `None`. `CTKApp._execute_tool` routes on it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_tools_registry.py
import pytest
import ctk.core.network_tools  # noqa: F401  -- import registers the ctk.network provider
from ctk.core.tools_registry import provider_for_tool

pytestmark = pytest.mark.unit


def test_builtin_tool_resolves_to_builtin_provider():
    assert provider_for_tool("search_conversations") == "ctk.builtin"


def test_network_tool_resolves_to_network_provider():
    assert provider_for_tool("find_similar_conversations") == "ctk.network"
    assert provider_for_tool("list_neighbors") == "ctk.network"


def test_unknown_tool_resolves_to_none():
    assert provider_for_tool("does_not_exist") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_tools_registry.py -q -o addopts=""`
Expected: FAIL with `ImportError: cannot import name 'provider_for_tool'`.

- [ ] **Step 3: Implement `provider_for_tool`**

Add to `ctk/core/tools_registry.py` (near `all_tools`), and ensure `Optional` is imported from `typing`:

```python
def provider_for_tool(name: str) -> Optional[str]:
    """Return the name of the provider that owns ``name``, or None.

    Routing derives from provider ownership rather than a hardcoded
    name set, so adding a tool to a provider needs no edit elsewhere.
    """
    for provider in _PROVIDERS:
        for tool in provider.tools:
            if tool.get("name") == name:
                return provider.name
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/unit/test_tools_registry.py -q -o addopts=""`
Expected: PASS (3 tests).

- [ ] **Step 5: Rewire `_execute_tool` and delete the frozenset**

In `ctk/tui/app.py`, delete the `_NETWORK_TOOL_NAMES = frozenset({...})` class attribute (line ~673) and change the routing in `_execute_tool` to derive from the provider. Ensure `ctk.core.network_tools` is imported during app startup so `ctk.network` is registered before routing (check `_register_builtin_providers`; if it does not already import `ctk.core.network_tools`, add the import there).

```python
def _execute_tool(self, name: str, args: Dict[str, Any]) -> str:
    """Run a CTK tool, returning its result as a string.

    Routes by the tool's owning provider (from the registry) rather
    than a hardcoded name set, so a new provider needs no edit here.
    """
    from ctk.core.tools_registry import provider_for_tool

    if provider_for_tool(name) == "ctk.network":
        from ctk.core.network_tools import execute_network_tool

        return execute_network_tool(self.db, name, args)

    from ctk.cli import execute_ask_tool

    # use_rich would print to stdout, which the TUI swallows.
    return execute_ask_tool(self.db, name, args, use_rich=False)
```

- [ ] **Step 6: Add a Pilot routing test**

Append to `tests/unit/test_tui_chat_dispatch.py` (it already exercises the worker path) a test that a network tool routes to the network executor without any hardcoded set. Use a fake `execute_network_tool` via monkeypatch:

```python
def test_execute_tool_routes_network_by_provider(monkeypatch, tmp_path):
    import ctk.core.network_tools as nt
    from ctk.core.database import ConversationDB
    from ctk.tui.app import CTKApp

    called = {}

    def fake_exec(db, name, args):
        called["name"] = name
        return "ok"

    monkeypatch.setattr(nt, "execute_network_tool", fake_exec)
    db = ConversationDB(str(tmp_path / "db"))
    try:
        app = CTKApp(db=db, provider=None, enable_tools=True)
        assert app._execute_tool("find_similar_conversations", {"conversation_id": "x"}) == "ok"
        assert called["name"] == "find_similar_conversations"
        assert not hasattr(CTKApp, "_NETWORK_TOOL_NAMES")
    finally:
        db.close()
```

This test is synchronous and does not need a running app (it calls `_execute_tool` directly); keep it out of the `pytest.mark.asyncio` set if the file marks the module asyncio (mark it with `@pytest.mark.unit` only, or define it as a plain function the asyncio plugin ignores).

- [ ] **Step 7: Run, green gate, commit**

```bash
python -m pytest tests/unit/test_tools_registry.py tests/unit/test_tui_chat_dispatch.py -q -o addopts=""
python -m black ctk/core/tools_registry.py ctk/tui/app.py tests/unit/test_tools_registry.py tests/unit/test_tui_chat_dispatch.py
python -m flake8 ctk/core/tools_registry.py ctk/tui/app.py tests/unit/test_tools_registry.py tests/unit/test_tui_chat_dispatch.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add -A && git commit -m "refactor(tools): derive TUI tool routing from provider ownership; drop hardcoded _NETWORK_TOOL_NAMES"
```

---

## Task 3: E-core W1 -- versioned migration runner

**Files:**
- Create: `ctk/core/migrations.py`
- Modify: `ctk/core/database.py` (`_migrate_schema` around line 191; replace the `_apply_migrations` body around line 217 with a call into the runner; keep `_generate_missing_slugs`)
- Test: covered in Task 4

**Interfaces:**
- Produces: `ctk.core.migrations.MigrationError`; `ctk.core.migrations.Migration(version: int, name: str, apply: Callable[[Connection], None])`; `ctk.core.migrations.MIGRATIONS: list[Migration]`; `ctk.core.migrations.run_migrations(engine, generate_slugs: Optional[Callable[[], None]] = None) -> None`.
- Consumes: SQLAlchemy `engine`; the existing `migration_lock` contextmanager and `MIGRATION_LOCK_TIMEOUT`.

- [ ] **Step 1: Create the migrations module**

```python
# ctk/core/migrations.py
"""Versioned, SQLite-only schema migrations using PRAGMA user_version.

Each Migration carries a target version and an idempotent apply() that runs
under its own transaction; user_version advances only when a step commits.
Adding a schema change means appending a Migration, never editing an old one.
"""

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    """Raised when a schema migration step fails; aborts loudly."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[Connection], None]


def _columns(conn: Connection, table: str) -> set:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _m1_slug_summary_index(conn: Connection) -> None:
    cols = _columns(conn, "conversations")
    if "slug" not in cols:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN slug VARCHAR"))
    if "summary" not in cols:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN summary TEXT"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_conv_slug ON conversations(slug)"))


def _m2_keyset_list_index(conn: Connection) -> None:
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_conv_list "
            "ON conversations(updated_at DESC, id) WHERE archived_at IS NULL"
        )
    )


MIGRATIONS: List[Migration] = [
    Migration(1, "slug_summary_index", _m1_slug_summary_index),
    Migration(2, "keyset_list_index", _m2_keyset_list_index),
]


def run_migrations(engine: Engine, generate_slugs: Optional[Callable[[], None]] = None) -> None:
    """Apply pending migrations to a SQLite engine. No-op (warn) on other dialects."""
    if engine.dialect.name != "sqlite":
        logger.warning(
            "Schema migrations are SQLite-only; skipping on %s", engine.dialect.name
        )
        return

    with engine.connect() as conn:
        current = conn.execute(text("PRAGMA user_version")).scalar() or 0

    ran_any = False
    for migration in MIGRATIONS:
        if migration.version <= current:
            continue
        try:
            with engine.begin() as conn:
                migration.apply(conn)
                conn.execute(text(f"PRAGMA user_version = {migration.version}"))
        except Exception as exc:
            raise MigrationError(
                f"migration {migration.version} ({migration.name}) failed: {exc}"
            ) from exc
        logger.info("Applied migration %s (%s)", migration.version, migration.name)
        ran_any = True

    if ran_any and generate_slugs is not None:
        generate_slugs()
```

Note: `PRAGMA user_version = N` cannot be parameter-bound; the value comes only from the trusted `MIGRATIONS` list (ints), so the f-string is safe here.

- [ ] **Step 2: Wire the runner into `database.py`**

In `ctk/core/database.py`, change `_migrate_schema` to call the runner instead of the old `_apply_migrations`. Keep the file-lock wrapper for directory-backed SQLite and the direct call for in-memory. Replace the entire old `_apply_migrations` body (the substring-matching block) with a thin delegator, and keep `_generate_missing_slugs` unchanged:

```python
def _migrate_schema(self):
    """Apply versioned schema migrations under a file lock for directory DBs."""
    if self.db_dir is None:
        self._run_migrations()
        return
    lock_path = self.db_dir / ".migration.lock"
    try:
        with migration_lock(lock_path, timeout=MIGRATION_LOCK_TIMEOUT):
            self._run_migrations()
    except TimeoutError:
        logger.warning("Migration lock timeout - another process may be migrating")
        self._run_migrations()

def _run_migrations(self):
    from ctk.core.migrations import run_migrations

    run_migrations(self.engine, generate_slugs=self._generate_missing_slugs)
```

Delete the old `_apply_migrations` method body (the slug/summary substring block at lines 217-271). Do NOT swallow `MigrationError`: let it propagate out of `__init__` so a failed upgrade is loud.

- [ ] **Step 3: Verify nothing regressed yet**

Run: `python -m pytest tests/unit/test_database.py -q -o addopts=""`
Expected: PASS (fresh DBs still initialize; `create_all` makes the columns, migrations are idempotent). If `idx_conv_slug` already exists from `create_all`, `CREATE INDEX IF NOT EXISTS` is a no-op. Fix any failures before continuing.

- [ ] **Step 4: Green gate (tests added in Task 4); commit**

```bash
python -m black ctk/core/migrations.py ctk/core/database.py
python -m flake8 ctk/core/migrations.py ctk/core/database.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add ctk/core/migrations.py ctk/core/database.py
git commit -m "feat(db): versioned PRAGMA user_version migration runner replacing substring-matched DDL"
```

---

## Task 4: E-core W1 -- migration tests + drop dead alembic pin

**Files:**
- Test: `tests/unit/test_migrations.py` (create)
- Modify: `setup.py` (remove the `alembic>=1.13.0` line), `requirements.txt` (remove the `alembic>=1.13.0` line)

**Interfaces:**
- Consumes: `ConversationDB`, `ctk.core.migrations.MIGRATIONS`, `ConversationModel.__table__.columns`.

The drift guard builds a DB from a STATIC legacy DDL (so it does not auto-gain future ORM columns) and asserts the migrated schema equals the ORM's declared columns. If a future ORM column is added without a migration, this test fails in CI.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_migrations.py
import sqlite3
import pytest
from sqlalchemy import text

from ctk.core.database import ConversationDB
from ctk.core.db_models import ConversationModel
from ctk.core.migrations import MIGRATIONS

pytestmark = pytest.mark.unit

# The conversations columns that existed before versioning (no slug/summary,
# no is_branching). Kept STATIC on purpose so the drift guard fails when a
# future ORM column has no migration. Update ONLY when adding a baseline col.
LEGACY_CONVERSATIONS_DDL = """
CREATE TABLE conversations (
    id VARCHAR PRIMARY KEY,
    title VARCHAR,
    created_at DATETIME,
    updated_at DATETIME,
    version VARCHAR,
    format VARCHAR,
    source VARCHAR,
    model VARCHAR,
    project VARCHAR,
    starred_at DATETIME,
    pinned_at DATETIME,
    archived_at DATETIME,
    metadata_json JSON
)
"""


def _make_legacy_db(dirpath):
    """Create a pre-versioning conversations.db at user_version 0."""
    dbfile = dirpath / "conversations.db"
    conn = sqlite3.connect(str(dbfile))
    conn.executescript(LEGACY_CONVERSATIONS_DDL)
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()
    return dbfile


def _conv_columns(db):
    with db.engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(conversations)")).fetchall()
    return {row[1] for row in rows}


def test_opening_legacy_db_upgrades_in_place(tmp_path):
    _make_legacy_db(tmp_path)
    db = ConversationDB(str(tmp_path))
    try:
        cols = _conv_columns(db)
        assert "slug" in cols and "summary" in cols
        with db.engine.connect() as conn:
            uv = conn.execute(text("PRAGMA user_version")).scalar()
            idx = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_conv_slug'")
            ).fetchone()
        assert uv == MIGRATIONS[-1].version
        assert idx is not None
    finally:
        db.close()


def test_drift_guard_migrated_schema_matches_orm(tmp_path):
    _make_legacy_db(tmp_path)
    db = ConversationDB(str(tmp_path))
    try:
        migrated = _conv_columns(db)
        declared = {c.name for c in ConversationModel.__table__.columns}
        missing = declared - migrated
        assert not missing, (
            f"ORM columns with no migration path from legacy schema: {missing}. "
            "Add a Migration step in ctk/core/migrations.py for each."
        )
    finally:
        db.close()


def test_legacy_db_save_round_trips_after_upgrade(tmp_path):
    import uuid
    from datetime import datetime
    from ctk.core.models import (
        ConversationMetadata, ConversationTree, Message, MessageContent, MessageRole,
    )
    _make_legacy_db(tmp_path)
    db = ConversationDB(str(tmp_path))
    try:
        tree = ConversationTree(
            id=str(uuid.uuid4()),
            title="after upgrade",
            metadata=ConversationMetadata(created_at=datetime.now(), updated_at=datetime.now()),
        )
        tree.add_message(
            Message(id=str(uuid.uuid4()), role=MessageRole.USER,
                    content=MessageContent(text="hi"), timestamp=datetime.now())
        )
        db.save_conversation(tree)
        loaded = db.load_conversation(tree.id)
        assert loaded is not None and loaded.title == "after upgrade"
    finally:
        db.close()
```

- [ ] **Step 2: Run to verify the upgrade tests pass and the drift guard passes now**

Run: `python -m pytest tests/unit/test_migrations.py -q -o addopts=""`
Expected: all PASS. (The drift guard passes today because every ORM column is reachable: slug/summary via migration 1, the rest present in the legacy DDL.) If `test_drift_guard...` fails, the legacy DDL is missing a baseline column that the ORM has but no migration adds; either add the column to a migration or, if it is a true baseline column, to `LEGACY_CONVERSATIONS_DDL` -- decide which per the column's history.

- [ ] **Step 3: Add a failed-migration-aborts-loudly test**

```python
def test_failed_migration_raises_and_does_not_advance_version(tmp_path, monkeypatch):
    import ctk.core.migrations as m
    _make_legacy_db(tmp_path)

    def boom(conn):
        raise RuntimeError("simulated DDL failure")

    bad = m.Migration(version=999, name="boom", apply=boom)
    monkeypatch.setattr(m, "MIGRATIONS", m.MIGRATIONS + [bad])
    with pytest.raises(m.MigrationError):
        ConversationDB(str(tmp_path))
    # version stayed at the last good migration, not 999
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "conversations.db"))
    uv = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert uv < 999
```

Run: `python -m pytest tests/unit/test_migrations.py -q -o addopts=""` -> PASS.

- [ ] **Step 4: Drop the dead alembic dependency**

Remove the `alembic>=1.13.0` line from `setup.py` (install_requires, around line 34) and from `requirements.txt` (around line 2). Grep to confirm nothing imports it: `grep -rn "alembic" ctk/ tests/` returns nothing.

- [ ] **Step 5: Green gate and commit**

```bash
python -m pytest tests/unit/test_migrations.py tests/unit/test_database.py -q -o addopts=""
python -m black tests/unit/test_migrations.py
python -m flake8 tests/unit/test_migrations.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add tests/unit/test_migrations.py setup.py requirements.txt
git commit -m "test(db): legacy-DB upgrade + drift-guard + loud-failure migration tests; drop unused alembic pin"
```

---

## Task 5: E-core W3a -- listing N+1 removal + shared filter helper + counting swap

**Files:**
- Modify: `ctk/core/database.py` (`list_conversations`, the duplicated filter blocks, `_has_fts5` caching, `__init__`)
- Modify: `ctk/core/prompts.py` (lines ~138-140, 195-196: `len(list_conversations(limit=None))` -> `count_conversations`)
- Test: `tests/unit/test_database_perf.py` (create)

**Interfaces:**
- Consumes: `ConversationDB.list_conversations`, `.search_conversations`, `.count_conversations`; `ConversationModel`, `MessageModel`, `TagModel`; `ConversationSummary`.
- Produces: `ConversationDB._apply_conversation_filters(query, **filters)` (a private helper shared by list/search/count); `self._is_sqlite: bool` and `self._has_fts: bool` cached at init.

- [ ] **Step 1: Write the failing query-count test**

```python
# tests/unit/test_database_perf.py
import uuid
from datetime import datetime
import pytest
from sqlalchemy import event

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata, ConversationTree, Message, MessageContent, MessageRole,
)

pytestmark = pytest.mark.unit


def _seed(db, n, msgs_per=3):
    for i in range(n):
        tree = ConversationTree(
            id=str(uuid.uuid4()), title=f"conv {i}",
            metadata=ConversationMetadata(created_at=datetime.now(), updated_at=datetime.now()),
        )
        parent = None
        for j in range(msgs_per):
            m = Message(id=str(uuid.uuid4()),
                        role=MessageRole.USER if j % 2 == 0 else MessageRole.ASSISTANT,
                        content=MessageContent(text=f"m{j}"), parent_id=parent,
                        timestamp=datetime.now())
            tree.add_message(m)
            parent = m.id
        db.save_conversation(tree)


def test_list_conversations_is_not_n_plus_1(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        _seed(db, 20, msgs_per=4)
        counter = {"n": 0}

        @event.listens_for(db.engine, "before_cursor_execute")
        def _count(conn, cursor, statement, params, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                counter["n"] += 1

        results = db.list_conversations(limit=20)
        assert len(results) == 20
        # Bounded, not ~1 + 20 + 20. Allow a small constant for the page +
        # one batched tag load + the message-count aggregate.
        assert counter["n"] <= 6, f"list_conversations issued {counter['n']} SELECTs (N+1)"
    finally:
        db.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_database_perf.py -q -o addopts=""`
Expected: FAIL (the SELECT count is ~41, far above 6) because `ConversationModel.to_dict()` lazy-loads `self.messages` and `self.tags` per row.

- [ ] **Step 3: Implement the fix**

Read `list_conversations` and `search_conversations` first. Then:

1. Add a private `_apply_conversation_filters(self, query, *, starred=None, pinned=None, archived=None, source=None, project=None, model=None, tags=None)` that applies the WHERE clauses currently duplicated across the four blocks, and call it from list/search/count so the logic lives once.
2. In `list_conversations`, stop building summaries via `ConversationModel.to_dict()`. Instead select the scalar columns plus a message count using an outer-joined `func.count(MessageModel.id)` grouped by conversation id (mirror the approach already in `search_conversations` around line 1581-1583), and `selectinload(ConversationModel.tags)` so tags load in one extra batched query. Build `ConversationSummary` from those values directly. Keep the return type and field names identical so callers are unaffected.
3. Cache dialect/FTS once: in `__init__` after `_init_schema()`, set `self._is_sqlite = self.engine.dialect.name == "sqlite"` and `self._has_fts = self._compute_has_fts5()` (rename the current `_has_fts5` body to `_compute_has_fts5`; make `_has_fts5()` return the cached `self._has_fts`). Replace `'sqlite' in str(self.engine.url)` checks with `self._is_sqlite`.

Keep all existing behavior (ordering, pagination, filters) identical; only the query shape changes.

- [ ] **Step 4: Run the perf test and the existing DB tests**

Run: `python -m pytest tests/unit/test_database_perf.py tests/unit/test_database.py -q -o addopts=""`
Expected: PASS. The perf test now sees a bounded SELECT count; existing list/search behavior tests still pass. If a list test checks `message_count` or `tags`, confirm the new query populates them identically.

- [ ] **Step 5: Swap the counting anti-pattern in prompts.py**

In `ctk/core/prompts.py`, replace each `len(db.list_conversations(..., limit=None))` used purely to get an integer with `db.count_conversations(...)` passing the same filters. Run `python -m pytest tests/unit -k prompt -q -o addopts=""` (or the prompts test if one exists) to confirm.

- [ ] **Step 6: Green gate and commit**

```bash
python -m pytest tests/unit/test_database_perf.py tests/unit/test_database.py -q -o addopts=""
python -m black ctk/core/database.py ctk/core/prompts.py tests/unit/test_database_perf.py
python -m flake8 ctk/core/database.py ctk/core/prompts.py tests/unit/test_database_perf.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add -A && git commit -m "perf(db): bounded list_conversations (no N+1), shared filter helper, cached dialect/FTS flags"
```

---

## Task 6: E-core W3a -- keyset index migration + EXPLAIN assertions

**Files:**
- Modify: `ctk/core/migrations.py` (migration 2 already adds `idx_conv_list`; confirm shape against EXPLAIN)
- Test: `tests/unit/test_migrations.py` (add EXPLAIN assertions)

**Interfaces:**
- Consumes: the `idx_conv_slug` and `idx_conv_list` indexes from migrations 1 and 2.

- [ ] **Step 1: Write the failing EXPLAIN test**

```python
# add to tests/unit/test_migrations.py
def test_indexes_serve_slug_and_listing(tmp_path):
    from ctk.core.database import ConversationDB
    db = ConversationDB(str(tmp_path))
    try:
        with db.engine.connect() as conn:
            slug_plan = conn.execute(
                text("EXPLAIN QUERY PLAN SELECT id FROM conversations WHERE slug = 'x'")
            ).fetchall()
            slug_text = " ".join(str(r) for r in slug_plan)
            assert "idx_conv_slug" in slug_text, slug_text

            list_plan = conn.execute(
                text(
                    "EXPLAIN QUERY PLAN SELECT id FROM conversations "
                    "WHERE archived_at IS NULL ORDER BY updated_at DESC, id LIMIT 51"
                )
            ).fetchall()
            list_text = " ".join(str(r) for r in list_plan)
            assert "idx_conv_list" in list_text, list_text
            assert "USE TEMP B-TREE" not in list_text.upper(), list_text
    finally:
        db.close()
```

- [ ] **Step 2: Run to verify**

Run: `python -m pytest tests/unit/test_migrations.py -k indexes_serve -q -o addopts=""`
Expected: PASS if migration 2's index shape matches the listing query. If `USE TEMP B-TREE` still appears or `idx_conv_list` is not chosen, adjust the index definition in `_m2_keyset_list_index` (column order must lead with the equality/filter column and match the ORDER BY direction) until EXPLAIN uses it. Re-run until green. This is the one task where the implementation (index shape) is tuned to the EXPLAIN output.

- [ ] **Step 3: Green gate and commit**

```bash
python -m pytest tests/unit/test_migrations.py -q -o addopts=""
python -m black ctk/core/migrations.py tests/unit/test_migrations.py
python -m flake8 ctk/core/migrations.py tests/unit/test_migrations.py --max-line-length=100 --ignore=E203,W503
git add -A && git commit -m "perf(db): keyset listing index via migration; EXPLAIN-verified slug + listing plans"
```

---

## Task 7: E-core W2 -- metadata single source (columns authoritative)

**Files:**
- Modify: `ctk/core/models.py` (`ConversationMetadata`: add `to_blob`)
- Modify: `ctk/core/database.py` (`save_conversation` around line 690: write `to_blob()` not `to_dict()`)
- Test: `tests/unit/test_metadata_single_source.py` (create)

**Interfaces:**
- Consumes: `ConversationMetadata.to_dict()` (full, for exporters, unchanged); `ConversationModel` columns; `star_conversation`, `load_conversation`.
- Produces: `ConversationMetadata.to_blob() -> dict` returning only overflow (`custom_data`), used at the persistence site.

- [ ] **Step 1: Write the failing test (the masked star/pin/archive bug)**

```python
# tests/unit/test_metadata_single_source.py
import uuid
from datetime import datetime
import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata, ConversationTree, Message, MessageContent, MessageRole,
)

pytestmark = pytest.mark.unit


def _save_one(db):
    tree = ConversationTree(
        id=str(uuid.uuid4()), title="m",
        metadata=ConversationMetadata(created_at=datetime.now(), updated_at=datetime.now()),
    )
    tree.add_message(Message(id=str(uuid.uuid4()), role=MessageRole.USER,
                             content=MessageContent(text="x"), timestamp=datetime.now()))
    db.save_conversation(tree)
    return tree.id


def test_star_then_reload_reflects_flag(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        cid = _save_one(db)
        db.star_conversation(cid)
        loaded = db.load_conversation(cid)
        assert loaded.metadata.starred_at is not None
    finally:
        db.close()


def test_to_blob_holds_only_overflow():
    md = ConversationMetadata(
        created_at=datetime.now(), updated_at=datetime.now(),
        source="openai", model="gpt-4", custom_data={"k": "v"},
    )
    blob = md.to_blob()
    assert blob.get("custom_data") == {"k": "v"}
    # column-backed fields are NOT duplicated into the persistence blob
    assert "source" not in blob and "model" not in blob and "starred_at" not in blob


def test_to_dict_still_full_for_exporters():
    md = ConversationMetadata(
        created_at=datetime.now(), updated_at=datetime.now(), source="openai", model="gpt-4",
    )
    full = md.to_dict()
    assert full.get("source") == "openai" and full.get("model") == "gpt-4"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_metadata_single_source.py -q -o addopts=""`
Expected: `test_to_blob_holds_only_overflow` FAILS with `AttributeError: to_blob` (method does not exist yet). `test_star_then_reload_reflects_flag` already passes today (load overrides from the column), so it is a guard against regression, not the red test here.

- [ ] **Step 3: Implement `to_blob` and use it at the save site**

Add to `ConversationMetadata` (read `to_dict` first to match field names):

```python
def to_blob(self) -> Dict[str, Any]:
    """The persistence overflow store: only fields with no dedicated column.

    Column-backed fields (source, model, project, slug, summary, timestamps,
    starred/pinned/archived, version, format, tags) are the single source of
    truth and are NOT duplicated here. to_dict() stays full for export.
    """
    blob: Dict[str, Any] = {}
    if self.custom_data:
        blob["custom_data"] = self.custom_data
    return blob
```

In `database.py:save_conversation`, change the blob assignment (around line 690) from `conv_model.metadata_json = conversation.metadata.to_dict()` to `conv_model.metadata_json = conversation.metadata.to_blob()`.

Confirm `load_conversation` still reads `custom_data` from the blob and every other field from the columns (it already overrides those from columns at lines 834-846; that override block is now the primary read and needs no change). If `version`/`format` were being read only from the blob, ensure their columns are written and read instead (they already have columns at db_models.py:76-77; if `load` does not override them from columns, add that so they are not lost when the blob no longer carries them).

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_metadata_single_source.py tests/unit/test_database.py -q -o addopts=""`
Expected: PASS. Watch for any exporter test that reads `metadata.to_dict()`; those must still pass because `to_dict` is unchanged.

- [ ] **Step 5: Green gate and commit**

```bash
python -m black ctk/core/models.py ctk/core/database.py tests/unit/test_metadata_single_source.py
python -m flake8 ctk/core/models.py ctk/core/database.py tests/unit/test_metadata_single_source.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add -A && git commit -m "refactor(db): conversation metadata columns are the single source; blob holds only custom_data overflow"
```

---

## Task 8: E-core W5 -- FTS5 zero-match fallback + special-char escaping + tests

**Files:**
- Modify: `ctk/core/database.py` (`_prepare_fts_query` around line 495; the FTS zero-match returns around lines 1355 and 1566; use cached `self._has_fts`)
- Test: `tests/unit/test_fts_search.py` (create)

**Interfaces:**
- Consumes: `search_conversations`, `iter_search_results`, the FTS5 path and LIKE fallback; `_prepare_fts_query`.
- Produces: `_escape_fts_query` (or an extension of `_prepare_fts_query`) that quotes special-character queries; zero-match falls through to LIKE.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_fts_search.py
import uuid
from datetime import datetime
import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata, ConversationTree, Message, MessageContent, MessageRole,
)

pytestmark = pytest.mark.unit


def _save(db, title, body):
    tree = ConversationTree(
        id=str(uuid.uuid4()), title=title,
        metadata=ConversationMetadata(created_at=datetime.now(), updated_at=datetime.now()),
    )
    tree.add_message(Message(id=str(uuid.uuid4()), role=MessageRole.USER,
                             content=MessageContent(text=body), timestamp=datetime.now()))
    db.save_conversation(tree)
    return tree.id


def test_special_char_query_does_not_crash_and_finds_match(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        _save(db, "code chat", "I love C++ and C# programming")
        results = db.search_conversations(query="C++")
        assert any("code chat" == r.title for r in results)
    finally:
        db.close()


def test_search_after_title_update_reflects_new_title(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        cid = _save(db, "old title", "body text")
        db.update_conversation_metadata(cid, title="renamed marker")
        results = db.search_conversations(query="renamed")
        assert any(r.id == cid for r in results)
    finally:
        db.close()


def test_search_after_delete_drops_from_results(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        cid = _save(db, "deletable unique-token-zzz", "body")
        db.delete_conversation(cid)
        results = db.search_conversations(query="unique-token-zzz")
        assert all(r.id != cid for r in results)
    finally:
        db.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_fts_search.py -q -o addopts=""`
Expected: `test_special_char_query...` FAILS (the `C++` query either raises an FTS5 syntax error or returns empty). The title-update and delete tests should pass (triggers handle sync) and serve as guards. If the special-char test errors rather than returns empty, that confirms the missing escaping.

- [ ] **Step 3: Implement escaping and zero-match fallback**

In `_prepare_fts_query` (read it first), add escaping: if the query is not already using explicit FTS operators (AND/OR/NOT/NEAR) or quotes, and it contains any FTS5 special character (`*`, `(`, `)`, `:`, `+`, `-`, `"`, `{`, `}`, `^`), wrap the whole query in double quotes to force a phrase match:

```python
_FTS_SPECIAL = set('*():+-"{}^')

def _escape_fts_query(self, query_text: str) -> str:
    if not query_text:
        return query_text
    upper = query_text.upper()
    if any(op in upper for op in (" AND ", " OR ", " NOT ", " NEAR")):
        return query_text
    if '"' in query_text:
        return query_text
    if any(ch in self._FTS_SPECIAL for ch in query_text):
        escaped = query_text.replace('"', '""')
        return f'"{escaped}"'
    return query_text
```

Call `_escape_fts_query` inside `_prepare_fts_query` (or before building the MATCH). In `search_conversations` and `iter_search_results`, change the FTS zero-match early return: when FTS5 is available and returns zero ids, set `fts_ids = None` and fall through to the LIKE path instead of returning empty, so tokenization mismatches do not produce false "no results". Replace `_has_fts5()` call sites with the cached `self._has_fts` (from Task 5).

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_fts_search.py tests/unit/test_database.py -q -o addopts=""`
Expected: PASS. If a pre-existing search test asserted that a no-FTS-match query returns empty, update it to reflect the new fall-through semantics (the LIKE path may now return substring matches).

- [ ] **Step 5: Green gate and commit**

```bash
python -m black ctk/core/database.py tests/unit/test_fts_search.py
python -m flake8 ctk/core/database.py tests/unit/test_fts_search.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add -A && git commit -m "fix(db): FTS5 special-char escaping + zero-match LIKE fallback; FTS sync/search tests"
```

---

## Task 9: E-core W4 -- retire PathModel for a denormalized `is_branching` column

**Files:**
- Modify: `ctk/core/db_models.py` (add `is_branching` column to `ConversationModel`; remove `PathModel` writes coupling)
- Modify: `ctk/core/migrations.py` (append migration 3 adding `is_branching` + its index)
- Modify: `ctk/core/database.py` (`save_conversation`: set `is_branching`, stop writing `PathModel`; `has_branches` filter uses the column)
- Test: `tests/unit/test_is_branching.py` (create); the drift guard from Task 4 now requires migration 3

**Interfaces:**
- Consumes: `ConversationTree.get_all_paths()`; the `has_branches` filter in `list_conversations`/`search_conversations`.
- Produces: `ConversationModel.is_branching: bool` maintained at save; migration 3 `is_branching_column`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_is_branching.py
import uuid
from datetime import datetime
import pytest
from sqlalchemy import text

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationMetadata, ConversationTree, Message, MessageContent, MessageRole,
)

pytestmark = pytest.mark.unit


def _linear(db):
    tree = ConversationTree(id=str(uuid.uuid4()), title="linear",
        metadata=ConversationMetadata(created_at=datetime.now(), updated_at=datetime.now()))
    p = None
    for j in range(3):
        m = Message(id=str(uuid.uuid4()), role=MessageRole.USER,
                    content=MessageContent(text=f"m{j}"), parent_id=p, timestamp=datetime.now())
        tree.add_message(m); p = m.id
    db.save_conversation(tree); return tree.id


def _branched(db):
    tree = ConversationTree(id=str(uuid.uuid4()), title="branched",
        metadata=ConversationMetadata(created_at=datetime.now(), updated_at=datetime.now()))
    root = Message(id=str(uuid.uuid4()), role=MessageRole.USER,
                   content=MessageContent(text="root"), timestamp=datetime.now())
    tree.add_message(root)
    for j in range(2):  # two children of root -> branch
        tree.add_message(Message(id=str(uuid.uuid4()), role=MessageRole.ASSISTANT,
            content=MessageContent(text=f"b{j}"), parent_id=root.id, timestamp=datetime.now()))
    db.save_conversation(tree); return tree.id


def test_is_branching_column_set_correctly(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        lin = _linear(db); br = _branched(db)
        with db.engine.connect() as conn:
            def flag(cid):
                return conn.execute(
                    text("SELECT is_branching FROM conversations WHERE id = :i"), {"i": cid}
                ).scalar()
            assert not flag(lin)
            assert flag(br)
    finally:
        db.close()


def test_has_branches_filter_uses_column(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        _linear(db); br = _branched(db)
        results = db.list_conversations(has_branches=True)
        ids = {r.id for r in results}
        assert br in ids
        assert all(r.id == br for r in results)
    finally:
        db.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/unit/test_is_branching.py -q -o addopts=""`
Expected: FAIL (`no such column: is_branching`, or the `has_branches` filter still routes through `PathModel`). Also run `python -m pytest tests/unit/test_migrations.py -k drift -q -o addopts=""` and expect the drift guard to FAIL once you add the ORM column in step 3 without migration 3 -- that is the guard doing its job; add migration 3 in the same step.

- [ ] **Step 3: Implement**

1. `db_models.py`: add `is_branching = Column(Boolean, default=False, index=True)` to `ConversationModel`. (Import `Boolean` if needed.)
2. `migrations.py`: append `Migration(3, "is_branching_column", _m3_is_branching)` with:

```python
def _m3_is_branching(conn: Connection) -> None:
    cols = _columns(conn, "conversations")
    if "is_branching" not in cols:
        conn.execute(text("ALTER TABLE conversations ADD COLUMN is_branching BOOLEAN DEFAULT 0"))
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS idx_conv_is_branching ON conversations(is_branching)")
    )
```

3. `database.py:save_conversation`: set `conv_model.is_branching = len(conversation.get_all_paths()) > 1` and remove the `PathModel` delete+reinsert block (the per-save path recompute). Change the `has_branches` filter in `_apply_conversation_filters`/list/search to `ConversationModel.is_branching.is_(True)` instead of the `func.count(PathModel.id)` subquery.
4. Leave the `paths` table defined for now (two-phase): stop writing it, drop it in a later release. Add a one-line code comment noting the table is deprecated and unwritten as of this version.

- [ ] **Step 4: Run to verify pass (including the drift guard)**

Run: `python -m pytest tests/unit/test_is_branching.py tests/unit/test_migrations.py tests/unit/test_database.py -q -o addopts=""`
Expected: PASS, including `test_drift_guard_migrated_schema_matches_orm` (now green because migration 3 adds the column the ORM declares).

- [ ] **Step 5: Green gate and commit**

```bash
python -m black ctk/core/db_models.py ctk/core/migrations.py ctk/core/database.py tests/unit/test_is_branching.py
python -m flake8 ctk/core/db_models.py ctk/core/migrations.py ctk/core/database.py tests/unit/test_is_branching.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add -A && git commit -m "perf(db): retire write-only PathModel for a denormalized is_branching column (migration 3)"
```

---

## Task 10: Full-suite green gate + release prep

**Files:**
- Modify: `ctk/__init__.py`, `setup.py`, `CITATION.cff` (version bump to 2.18.0)
- Modify: `CLAUDE.md` (note the migration runner; correct the stale MCP "7 tools" line if touched)

- [ ] **Step 1: Full suite**

Run: `python -m pytest tests/unit -q` (with the configured addopts, so coverage is enforced).
Expected: all pass; coverage at or above 59. Then `python -m pytest tests/integration -q -o addopts="" -m "not requires_ollama and not requires_api_key"`.

- [ ] **Step 2: mypy across the tree**

Run: `python -m mypy ctk --ignore-missing-imports`
Expected: 0 errors.

- [ ] **Step 3: Version bump**

Set `__version__ = "2.18.0"` in `ctk/__init__.py`, `version="2.18.0"` in `setup.py`, and `version: 2.18.0` + today's `date-released` in `CITATION.cff`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "release: 2.18.0 (E-core DB foundations: versioned migrations, single-source metadata, index + N+1 fixes, FTS5 correctness, PathModel retired; C hotfixes)"
```

Do NOT tag, push, or upload here. Release is user-gated (the maintainer runs the publish steps after testing).

---

## Self-review notes

- **Spec coverage:** W1 migrations -> Tasks 3,4,6,9 (the runner plus its three migrations and tests). W2 metadata -> Task 7. W3 perf -> Tasks 5 (N+1, filter helper, counting, cached flags) and 6 (indexes). W4 PathModel -> Task 9. W5 FTS5 -> Task 8. C-W0 -> Tasks 1,2. The optional `ctk db rebuild-fts` command is intentionally omitted (low priority; add later if needed).
- **Sequencing:** Task 3 (runner) precedes every schema-changing task (6, 9) because `create_all` cannot alter existing tables. Task 5 builds `_apply_conversation_filters`, which Task 9 edits for the `has_branches` filter; keep that ordering.
- **Drift guard interplay:** Task 4 writes the drift guard; Task 9 adds an ORM column and must keep it green by adding migration 3. This cross-task tension is intentional and is the guard's purpose.
- **Deviation from spec flagged for review:** the runner SKIPS with a warning on non-SQLite dialects rather than raising, to avoid making the postgresql open path unusable; the spec's wording said "raise". Confirm this softening at review, or change `run_migrations` to raise `MigrationError` on non-sqlite.
