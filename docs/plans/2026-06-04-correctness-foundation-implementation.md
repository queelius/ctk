# Correctness Foundation and Green CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CTK correct on its primary paths and restore a green, honest CI signal (all tests pass, coverage at or above the 59 gate, mypy reports 0 errors), so sub-projects B through F can refactor on a working safety net.

**Architecture:** A sequence of small, test-first fixes. Phase 1 fixes shipped silent-failures (the LLM tool dispatcher, media round-trip loss, substring agent detection, the REST surface). Phase 2 repairs CI hygiene. Phase 3 lands cheap correctness wins folded in from the docs theme. Phase 4 clears mypy. Phase 5 closes the coverage gap. Phase 6 confirms an all-green gate.

**Tech Stack:** Python 3.10+, pytest (+ pytest-cov, pytest-timeout), mypy, flake8, SQLAlchemy, argparse, Textual. Package name `conversation-tk`.

**Companion spec:** [`2026-06-04-correctness-foundation-design.md`](2026-06-04-correctness-foundation-design.md). Part of the [improvement program roadmap](2026-06-04-improvement-program-roadmap.md).

**Before you start:** This plan is executed on a feature branch, not `master`. Create it first:

```bash
git checkout -b correctness-foundation
```

---

## Phase 1: Correctness bug fixes

### Task 1: Define `_resolve_conversation_id` and reconcile its two callers

**Context.** `ctk/cli.py` `execute_ask_tool` calls `_resolve_conversation_id(db, conv_id)` at 15 sites, but the function is defined nowhere. The `NameError` is swallowed by the broad `except Exception` at the end of `execute_ask_tool`, so every LLM-driven star/pin/delete/tag/export/auto-tag returns a confusing error string instead of acting. 13 call sites expect an `Error:`-prefixed string on failure; 2 sites (`list_conversation_paths` line 1460, `auto_tag_conversation` line 1524) currently expect `None` (`if not conv_id`). The existing resolver `ConversationDB.resolve_conversation(id_or_slug) -> Optional[str]` (`ctk/core/database.py:876`) returns `None` on miss/ambiguous.

**Files:**
- Modify: `ctk/cli.py` (add helper above `execute_ask_tool` at line 737; edit lines 1460-1462 and 1524-1526)
- Test: `tests/unit/test_execute_ask_tool.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_execute_ask_tool.py`:

```python
import pytest

from ctk.cli import execute_ask_tool
from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole,
)


def _make_conversation(db, conv_id, title="Test conversation"):
    tree = ConversationTree(id=conv_id, title=title)
    tree.add_message(
        Message(
            id="m1",
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
            parent_id=None,
        )
    )
    db.save_conversation(tree)
    return tree


@pytest.fixture
def db():
    database = ConversationDB(":memory:")
    yield database
    database.close()


# Tools that take a conversation_id and resolve it via _resolve_conversation_id.
RESOLVING_TOOLS = [
    "star_conversation", "unstar_conversation",
    "pin_conversation", "unpin_conversation",
    "archive_conversation", "unarchive_conversation",
    "delete_conversation",
    "list_conversation_paths",
    "auto_tag_conversation",
]


@pytest.mark.parametrize("tool_name", RESOLVING_TOOLS)
def test_resolving_tool_with_valid_prefix_does_not_namerror(db, tool_name):
    conv_id = "abcdef01-0000-0000-0000-000000000000"
    _make_conversation(db, conv_id)
    result = execute_ask_tool(db, tool_name, {"conversation_id": conv_id[:8]})
    # The bug returned: "Error executing <tool>: name '_resolve_conversation_id' ..."
    assert "_resolve_conversation_id" not in result
    assert "is not defined" not in result


@pytest.mark.parametrize("tool_name", RESOLVING_TOOLS)
def test_resolving_tool_with_unknown_id_reports_not_found(db, tool_name):
    result = execute_ask_tool(db, tool_name, {"conversation_id": "zzzzzzzz"})
    lowered = result.lower()
    assert "not found" in lowered or result.startswith("Error:")
    assert "_resolve_conversation_id" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_execute_ask_tool.py -v -o addopts=""`
Expected: FAIL. Results contain `"name '_resolve_conversation_id' is not defined"`.

- [ ] **Step 3: Add the helper**

In `ctk/cli.py`, immediately above `def execute_ask_tool(` (line 737), add:

```python
def _resolve_conversation_id(db, conv_id):
    """Resolve a partial id or slug to a full conversation id.

    Returns the full id on success, or an ``Error:``-prefixed string on
    miss/ambiguity (the sentinel contract the ask-tool branches check with
    ``conv_id.startswith("Error:")``). Reuses ``ConversationDB.resolve_conversation``
    rather than re-implementing a prefix scan.
    """
    full = db.resolve_conversation(conv_id)
    if full is None:
        return f"Error: No conversation found matching '{conv_id}'"
    return full
```

- [ ] **Step 4: Reconcile the two None-expecting call sites**

In `ctk/cli.py`, change `list_conversation_paths` (currently lines 1460-1462):

```python
            conv_id = _resolve_conversation_id(db, conv_id_arg)
            if conv_id.startswith("Error:"):
                return f"Conversation not found: {conv_id_arg}"
```

And `auto_tag_conversation` (currently lines 1524-1526):

```python
            conv_id = _resolve_conversation_id(db, conv_id_arg)
            if conv_id.startswith("Error:"):
                return f"Conversation not found: {conv_id_arg}"
```

(The 13 other call sites already use `if conv_id.startswith("Error:"): return conv_id`, so they need no change.)

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_execute_ask_tool.py -v -o addopts=""`
Expected: PASS (18 parametrized cases).

- [ ] **Step 6: Commit**

```bash
git add ctk/cli.py tests/unit/test_execute_ask_tool.py
git commit -m "fix(cli): define _resolve_conversation_id; ask-tool branches no longer silently fail"
```

---

### Task 2: Reconstruct audio/video/documents in `MessageContent.from_dict`

**Context.** `ctk/core/models.py` `to_dict` (lines 232-255) serializes images, audio, video, documents, tool_calls; `from_dict` (lines 257-282) reconstructs only images and tool_calls. Audio/video/documents are dropped on every DB reload (`database.py:696` save, `:851` load). The Anthropic importer creates `ContentType.DOCUMENT` objects for PDFs that vanish on reload.

**Files:**
- Modify: `ctk/core/models.py` (`MessageContent.from_dict`, lines 257-282)
- Test: `tests/unit/test_models.py` (add a test; create the file if absent)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_models.py` (create if it does not exist, with the imports):

```python
from ctk.core.models import ContentType, MediaContent, MessageContent


def test_from_dict_round_trips_all_media_types():
    content = MessageContent(text="see attached")
    content.images.append(MediaContent(type=ContentType.IMAGE, path="pic.png"))
    content.audio.append(MediaContent(type=ContentType.AUDIO, path="clip.mp3"))
    content.video.append(MediaContent(type=ContentType.VIDEO, path="movie.mp4"))
    content.documents.append(
        MediaContent(type=ContentType.DOCUMENT, path="report.pdf",
                     mime_type="application/pdf")
    )

    restored = MessageContent.from_dict(content.to_dict())

    assert len(restored.images) == 1
    assert len(restored.audio) == 1
    assert len(restored.video) == 1
    assert len(restored.documents) == 1
    assert restored.documents[0].path == "report.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py::test_from_dict_round_trips_all_media_types -v -o addopts=""`
Expected: FAIL. `restored.audio`, `restored.video`, `restored.documents` are length 0.

- [ ] **Step 3: Add the three loops**

In `ctk/core/models.py` `from_dict`, immediately after the existing `images` loop (ends line 275) and before the `tool_calls` loop (line 277), add:

```python
        if "audio" in data:
            for a_data in data["audio"]:
                content.audio.append(
                    MediaContent(
                        type=ContentType.AUDIO,
                        **{k: v for k, v in a_data.items() if k != "type"},
                    )
                )

        if "video" in data:
            for v_data in data["video"]:
                content.video.append(
                    MediaContent(
                        type=ContentType.VIDEO,
                        **{k: v for k, v in v_data.items() if k != "type"},
                    )
                )

        if "documents" in data:
            for d_data in data["documents"]:
                content.documents.append(
                    MediaContent(
                        type=ContentType.DOCUMENT,
                        **{k: v for k, v in d_data.items() if k != "type"},
                    )
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py::test_from_dict_round_trips_all_media_types -v -o addopts=""`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ctk/core/models.py tests/unit/test_models.py
git commit -m "fix(models): from_dict reconstructs audio/video/documents (stop silent media loss on reload)"
```

---

### Task 3: Make agent-type detection structural, not substring-based

**Context.** `ctk/importers/filesystem_coding.py:73-96` `_detect_agent_type` does `str(path).lower()` and substring-matches agent names against the whole path, so any path under `/tmp/claude-1000` returns `claude_code`. This breaks 5 tests in this environment and violates the "no substring-matching of structured data" principle. `claude_code` and `codeium` have only dir-name sentinels (no marker file), so the fix must match `path.name`, not marker files alone.

**Files:**
- Modify: `ctk/importers/filesystem_coding.py` (`_detect_agent_type`, lines 73-96; add a module-level sentinel table)
- Test: `tests/unit/test_filesystem_coding_importer.py` (existing 5 failures become the guard)

- [ ] **Step 1: Run the existing tests to confirm the 5 failures**

Run: `pytest tests/unit/test_filesystem_coding_importer.py -v -o addopts=""`
Expected: `5 failed, 84 passed`. Failures: `test_validate_empty_directory_no_agent`, `test_detect_codeium_from_codeium_path`, `test_detect_generic_from_chat_history_json`, `test_detect_generic_from_sessions_json`, `test_detect_unknown_path_returns_none`.

- [ ] **Step 2: Replace `_detect_agent_type` with structural detection**

In `ctk/importers/filesystem_coding.py`, add a module-level table near the top of the module (after imports):

```python
# Detection is derived from structure: the final directory name and the
# presence of sentinel marker files. Never a substring of the full path
# (which would misclassify any path that merely contains an agent name,
# e.g. a tmpdir at /tmp/claude-1000).
_AGENT_SENTINELS = {
    # agent_type: (dir_name_leaves, marker_files)
    "copilot": ({".vscode"}, {"copilot.db", "copilot_conversations.json"}),
    "cursor": ({".cursor"}, {"cursor.db", "conversations.db"}),
    "claude_code": ({".claude"}, set()),
    "codeium": ({".codeium"}, set()),
}
_GENERIC_MARKER_FILES = {"chat_history.json", "sessions.json"}
```

Then replace the body of `_detect_agent_type` (lines 73-96) with:

```python
    def _detect_agent_type(self, path: Path) -> Optional[str]:
        """Detect which coding agent a directory belongs to, by structure.

        Keyed on the final directory name and sentinel marker files, never on
        a substring of the absolute path.
        """
        leaf = path.name.lower()

        # 1. Final-directory-name match (authoritative for claude_code and
        #    codeium, which have no marker file).
        for agent, (names, _markers) in _AGENT_SENTINELS.items():
            if leaf in names:
                return agent

        # 2. Marker-file match (for dirs not named after the agent).
        for agent, (_names, markers) in _AGENT_SENTINELS.items():
            if any((path / marker).exists() for marker in markers):
                return agent

        # 3. Generic fallback by marker file.
        if any((path / marker).exists() for marker in _GENERIC_MARKER_FILES):
            return "generic"

        return None
```

- [ ] **Step 3: Run the full file to verify all pass**

Run: `pytest tests/unit/test_filesystem_coding_importer.py -v -o addopts=""`
Expected: `89 passed` (the 5 failures pass; the 84 keep passing). If any previously-passing test relied on substring matching of a non-leaf path component, that test was asserting the bad behavior; update it to use a dir-name leaf or marker file.

- [ ] **Step 4: Commit**

```bash
git add ctk/importers/filesystem_coding.py
git commit -m "fix(importers): structural agent detection (dir name + marker files), not path substring"
```

---

### Task 4: Route the REST surface through the public DB API and gate Flask behind an extra

**Context.** `ctk/interfaces/rest/api.py` `list_conversations` (580-624), `export_conversations` (480-526), and `update_conversation` (667-702) call `db.session`, `db.ConversationModel`, and `db._model_to_tree`, none of which exist on `ConversationDB`. They `AttributeError` against a real DB; tests pass only because they inject a `MagicMock` db and a `sys.modules["flask_cors"]` shim. `flask`/`flask_cors` are imported at module top but undeclared in packaging. The correct public methods are `db.list_conversations(...)` (returns `List[ConversationSummary]`, each with `.to_dict()`), `db.load_conversation(id)` (returns `ConversationTree`), and `db.update_conversation_metadata(id, ...)` (already used by `rename_conversation` at api.py:799).

**Files:**
- Modify: `ctk/interfaces/rest/api.py` (imports lines 9-10; `__init__` line 29-30; the three methods)
- Modify: `setup.py` (`extras_require`)
- Test: `tests/unit/test_rest_api_realdb.py` (create)

- [ ] **Step 1: Write the failing real-DB test**

Create `tests/unit/test_rest_api_realdb.py`:

```python
import pytest

pytest.importorskip("flask_cors")  # only runs where the rest extra is installed

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole,
)
from ctk.interfaces.rest.api import RestInterface


@pytest.fixture
def db_dir(tmp_path):
    db = ConversationDB(str(tmp_path / "db"))
    tree = ConversationTree(id="conv-1", title="Hello world")
    tree.metadata.source = "openai"
    tree.add_message(
        Message(id="m1", role=MessageRole.USER,
                content=MessageContent(text="hi"), parent_id=None)
    )
    db.save_conversation(tree)
    db.close()
    return str(tmp_path / "db")


def test_list_conversations_uses_public_api(db_dir):
    iface = RestInterface(db_path=db_dir)
    resp = iface.list_conversations(limit=10, offset=0)
    # Must not raise AttributeError on db.session / db.ConversationModel.
    assert resp.status.value == "success" or resp.status == "success"
    titles = [c["title"] for c in resp.data["conversations"]]
    assert "Hello world" in titles


def test_update_conversation_uses_public_api(db_dir):
    iface = RestInterface(db_path=db_dir)
    resp = iface.update_conversation("conv-1", {"title": "Renamed"})
    assert "updated" in (resp.message or "").lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_rest_api_realdb.py -v -o addopts=""`
Expected: FAIL with `AttributeError` referencing `session` / `ConversationModel` (or SKIP if `flask_cors` is not installed locally; install it with `pip install flask-cors` to run the test, or rely on CI where the dev extra provides it).

- [ ] **Step 3: Gate the Flask imports**

In `ctk/interfaces/rest/api.py`, replace the top imports (lines 9-10):

```python
try:
    from flask import Flask, Response, jsonify, request
    from flask_cors import CORS
    _FLASK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the rest extra in CI
    _FLASK_AVAILABLE = False
```

In `__init__` (before line 29 `self.app = Flask(__name__)`), add the friendly guard:

```python
        if not _FLASK_AVAILABLE:
            raise ImportError(
                "The REST interface requires Flask. Install it with: "
                "pip install conversation-tk[rest]"
            )
```

- [ ] **Step 4: Fix `export_conversations` (replace the else-branch at lines 499-508)**

```python
                    else:
                        filters = filters or {}
                        for summary in db.list_conversations(
                            limit=None,
                            source=filters.get("source"),
                            project=filters.get("project"),
                            model=filters.get("model"),
                            tags=filters.get("tags"),
                        ):
                            conv = db.load_conversation(summary.id)
                            if conv:
                                conversations.append(conv)
```

- [ ] **Step 5: Fix `list_conversations` (replace lines 593-613 inside `with self.db as db:`)**

```python
                with self.db as db:
                    filters = filters or {}
                    all_summaries = db.list_conversations(
                        limit=None,
                        source=filters.get("source"),
                        project=filters.get("project"),
                        model=filters.get("model"),
                        tags=filters.get("tags"),
                    )
                    total = len(all_summaries)
                    page = (
                        all_summaries[offset:offset + limit]
                        if limit else all_summaries[offset:]
                    )
                    conversations = [s.to_dict() for s in page]
```

(`db.list_conversations` orders pinned-then-recent internally; the previous dynamic `sort_by` is dropped. Note this in the method docstring.)

- [ ] **Step 6: Fix `update_conversation` (replace lines 675-696 inside `with self.db as db:`)**

```python
            with self.db as db:
                existing = db.load_conversation(conversation_id)
                if not existing:
                    return InterfaceResponse.error(
                        f"Conversation {conversation_id} not found"
                    )

                meta_updates = {}
                if "title" in updates:
                    meta_updates["title"] = updates["title"]
                if "project" in updates:
                    meta_updates["project"] = updates["project"]
                if meta_updates:
                    db.update_conversation_metadata(conversation_id, **meta_updates)
```

Confirm `update_conversation_metadata`'s keyword arguments at `ctk/core/database.py` (it is already called by `rename_conversation`); adjust the kwarg names if they differ.

- [ ] **Step 7: Add the `rest` extra and put flask-cors in `dev`**

In `setup.py` `extras_require`, add a `rest` extra and ensure the `dev` extra includes flask so CI exercises the real import path:

```python
    extras_require={
        "dev": [
            # ... existing dev deps ...
            "pytest-timeout>=2.0.0",
            "flask>=2.0",
            "flask-cors>=4.0",
        ],
        "rest": [
            "flask>=2.0",
            "flask-cors>=4.0",
        ],
    },
```

(If the `dev` list already exists, append the three lines rather than redefining it. `pytest-timeout` is added here and also in Task 5.)

- [ ] **Step 8: Run the real-DB test and the existing REST tests**

Run:
```bash
pip install flask-cors  # if not already present locally
pytest tests/unit/test_rest_api_realdb.py tests/unit/test_rest_api.py -v -o addopts=""
```
Expected: real-DB tests PASS; the 29 existing REST tests still PASS.

- [ ] **Step 9: Commit**

```bash
git add ctk/interfaces/rest/api.py setup.py tests/unit/test_rest_api_realdb.py
git commit -m "fix(rest): route list/export/update through public DB API; add rest extra + friendly flask guard"
```

---

## Phase 2: CI hygiene

### Task 5: Declare pytest-timeout and set a per-test timeout

**Files:**
- Modify: `requirements-dev.txt`, `pytest.ini`
- (setup.py `dev` extra already updated in Task 4 Step 7)

- [ ] **Step 1: Add the dependency**

Append to `requirements-dev.txt`:

```
pytest-timeout>=2.0.0
```

- [ ] **Step 2: Add the timeout to pytest.ini**

In `pytest.ini` under `[pytest]`, add:

```ini
timeout = 60
timeout_method = thread
```

- [ ] **Step 3: Verify the plugin is active and tests still run**

Run: `pytest tests/unit/test_models.py -v` (expected: PASS, and `pytest --help | grep timeout` shows the option).

- [ ] **Step 4: Commit**

```bash
git add requirements-dev.txt pytest.ini
git commit -m "test: declare pytest-timeout and set timeout=60 to guard against TUI/no-TTY hangs"
```

---

### Task 6: Update the stale CI smoke step and stale integration tests

**Context.** `.github/workflows/test.yml:99-107` runs removed subcommands (`plugins`, `list`, `stats`). `tests/integration/test_cli.py` has `test_plugins_command` (221-228, asserts a removed subcommand) and `test_cli_no_command` (93-99, asserts bare `ctk` returns 1, but bare `ctk` now opens the TUI). Valid commands: `import, export, auto-tag, tui, query, sql, db, net, llm, config`.

**Files:**
- Modify: `.github/workflows/test.yml` (lines ~99-107)
- Modify: `tests/integration/test_cli.py`

- [ ] **Step 1: Update the workflow smoke step**

In `.github/workflows/test.yml`, replace the removed-command lines with current ones, for example:

```yaml
          python -m ctk.cli --help
          python -m ctk.cli query --db test.db || true
          python -m ctk.cli db info test.db || true
```

(Keep whatever DB-setup precedes them; the point is to invoke only commands that exist.)

- [ ] **Step 2: Rewrite the stale integration tests**

In `tests/integration/test_cli.py`, replace `test_plugins_command` (lines 221-228) and `test_cli_no_command` (lines 93-99):

```python
def test_query_command_runs(self):
    """`ctk query` exits cleanly against an empty db."""
    with patch("sys.argv", ["ctk", "query", "--db", self.db_path]):
        from ctk.cli import main
        assert main() == 0


def test_no_command_attempts_tui(self, monkeypatch):
    """Bare `ctk` routes to the TUI rather than returning an error code."""
    called = {}

    def fake_run_tui(*args, **kwargs):
        called["tui"] = True
        return 0

    # Patch the TUI launch path so the test does not need a TTY.
    monkeypatch.setattr("ctk.cli.run_tui", fake_run_tui, raising=False)
    with patch("sys.argv", ["ctk"]):
        from ctk.cli import main
        main()
    assert called.get("tui") is True
```

Confirm the TUI entry-point name in `ctk/cli.py` (search for where bare `ctk` dispatches to the TUI) and patch that exact symbol. If it is not `run_tui`, adjust the `monkeypatch.setattr` target.

- [ ] **Step 3: Run the integration tests**

Run: `pytest tests/integration/test_cli.py -v` (expected: PASS, no hang thanks to Task 5's timeout).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/test.yml tests/integration/test_cli.py
git commit -m "test(ci): replace removed subcommands (plugins/list/stats) in smoke step and integration tests"
```

---

### Task 7: De-duplicate the top-level test files

**Context.** `pytest.ini testpaths=tests` collects both `tests/` and `tests/unit/`. `tests/test_database_comprehensive.py` and `tests/test_models_comprehensive.py` duplicate the (larger) `tests/unit/` versions. `tests/test_db_operations.py` and `tests/test_db_operations_comprehensive.py` have no `tests/unit/` counterpart.

**Files:**
- Delete: `tests/test_database_comprehensive.py`, `tests/test_models_comprehensive.py`
- Move: `tests/test_db_operations.py`, `tests/test_db_operations_comprehensive.py` into `tests/unit/`

- [ ] **Step 1: Delete the duplicates and move the originals**

```bash
git rm tests/test_database_comprehensive.py tests/test_models_comprehensive.py
git mv tests/test_db_operations.py tests/unit/test_db_operations.py
git mv tests/test_db_operations_comprehensive.py tests/unit/test_db_operations_comprehensive.py
```

- [ ] **Step 2: Verify collection has no duplicate-name clash and the moved tests run**

Run: `pytest tests/unit/test_db_operations.py tests/unit/test_db_operations_comprehensive.py -v -o addopts=""`
Expected: PASS. Then `pytest --collect-only -q | grep -c test_database_comprehensive` should show only the `tests/unit/` copy.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: remove duplicate top-level comprehensive tests; move db_operations tests under tests/unit"
```

---

## Phase 3: Folded-in correctness wins (F-quick)

### Task 8: Fix the broken headline fluent-API example

**Context.** `README.md:398` and `docs/index.md:398` show `.filter(source="ChatGPT")` on a `SearchBuilder`, which has no `.filter` (its method is `.in_source`). The example raises `AttributeError`.

**Files:**
- Modify: `README.md` (line 398), `docs/index.md` (line 398)

- [ ] **Step 1: Replace `.filter(...)` with `.in_source(...)` in both files**

Change `.filter(source="ChatGPT")` to `.in_source("ChatGPT")` at `README.md:398` and `docs/index.md:398`.

- [ ] **Step 2: Verify the corrected example runs**

Run:
```bash
python -c "from ctk.api import CTK; print(hasattr(type(CTK(':memory:').search('x')), 'in_source'))"
```
Expected: `True`.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/index.md
git commit -m "docs: fix headline fluent-API example (.filter -> .in_source on SearchBuilder)"
```

---

### Task 9: Reconcile `requirements.txt` with `setup.py`

**Context.** `requirements.txt` omits `textual`, `textual-image`, `openai` (which the bare `ctk` TUI imports); `setup.py install_requires` has all three. Make one the source of truth.

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append the three missing runtime deps**

Add to `requirements.txt`:

```
textual>=0.50.0
textual-image>=0.6.0
openai>=1.40.0
```

(Keeping a flat `requirements.txt` that mirrors `install_requires` is the minimum fix. A follow-up may collapse the two by having `setup.py` read `requirements.txt`, but that is optional and out of scope for this task.)

- [ ] **Step 2: Verify a requirements-only install would import the TUI**

Run: `python -c "import textual, textual_image, openai; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "build: add textual/textual-image/openai to requirements.txt (bare ctk TUI needs them)"
```

---

### Task 10: Emit CSV with the stdlib `csv` module

**Context.** CSV is hand-built by comma-joining raw values in `ctk/core/db_helpers.py:230-237` and `:251-258` (query `--format csv`) and `ctk/cli.py:2411-2413` (`_display_sql_results`). Titles with commas/quotes/newlines corrupt rows; a title starting with `=,+,-,@` is a formula-injection vector.

**Files:**
- Modify: `ctk/core/db_helpers.py` (two CSV branches), `ctk/cli.py` (`_display_sql_results`)
- Test: `tests/unit/test_csv_output.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_csv_output.py`:

```python
import csv
import io

from ctk.cli import _display_sql_results


def test_sql_csv_quotes_commas_and_newlines(capsys):
    rows = [("conv-1", "Hello, world\nsecond line")]
    keys = ["id", "title"]
    _display_sql_results(console=None, rows=rows, keys=keys,
                         format_type="csv", limit=0)
    out = capsys.readouterr().out
    parsed = list(csv.reader(io.StringIO(out)))
    # Header + exactly one data row; the comma/newline title stays one field.
    assert parsed[0] == ["id", "title"]
    assert parsed[1] == ["conv-1", "Hello, world\nsecond line"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_csv_output.py -v -o addopts=""`
Expected: FAIL. The raw join splits the comma/newline title across fields/rows.

- [ ] **Step 3: Rewrite `_display_sql_results` CSV branch**

In `ctk/cli.py`, replace the CSV branch (lines 2410-2413):

```python
    elif format_type == "csv":
        import csv
        import sys
        writer = csv.writer(sys.stdout)
        writer.writerow([str(k) for k in keys])
        for row in rows:
            writer.writerow(["" if v is None else str(v) for v in row])
```

- [ ] **Step 4: Rewrite both CSV branches in `db_helpers.py`**

In `ctk/core/db_helpers.py`, add a shared helper near the top of the module (after imports):

```python
def _write_conversation_csv(items):
    """Write conversation summaries as RFC-4180 CSV to stdout."""
    import csv
    import sys
    writer = csv.writer(sys.stdout)
    writer.writerow(["ID", "Title", "Messages", "Source", "Model", "Created", "Updated"])
    for conv in items:
        d = conv.to_dict() if hasattr(conv, "to_dict") else conv
        writer.writerow([
            d["id"],
            d.get("title", "Untitled"),
            d.get("message_count", 0),
            d.get("source", ""),
            d.get("model", ""),
            d.get("created_at", ""),
            d.get("updated_at", ""),
        ])
```

Replace the paginated CSV branch (lines 229-237) with `_write_conversation_csv(items)` and the non-paginated CSV branch (lines 250-258) with `_write_conversation_csv(results)`.

- [ ] **Step 5: Run the test and a query-CSV smoke check**

Run: `pytest tests/unit/test_csv_output.py -v -o addopts=""`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ctk/cli.py ctk/core/db_helpers.py tests/unit/test_csv_output.py
git commit -m "fix(output): emit CSV via stdlib csv.writer (correct quoting; closes formula-injection)"
```

---

### Task 11: Route diagnostics to stderr and add `--version` / `prog="ctk"`

**Context.** 70 `print(f"Error...")` calls in `cli.py` write to stdout, interleaving diagnostics with data and breaking `ctk query --format json | jq`. There is no `--version`, and `prog` is unset so usage shows `cli.py`.

**Files:**
- Modify: `ctk/cli.py` (add `_err` helper; the `ArgumentParser` at line 2437; route error prints)
- Test: `tests/unit/test_cli_diagnostics.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cli_diagnostics.py`:

```python
import subprocess
import sys

import ctk


def test_version_flag_prints_version():
    out = subprocess.run(
        [sys.executable, "-m", "ctk.cli", "--version"],
        capture_output=True, text=True,
    )
    assert ctk.__version__ in (out.stdout + out.stderr)
    assert out.returncode == 0


def test_usage_uses_ctk_prog():
    out = subprocess.run(
        [sys.executable, "-m", "ctk.cli", "--help"],
        capture_output=True, text=True,
    )
    assert "usage: ctk" in out.stdout
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_cli_diagnostics.py -v -o addopts=""`
Expected: FAIL. `--version` prints usage (no version); usage shows `cli.py`.

- [ ] **Step 3: Add `prog` and `--version` to the parser**

In `ctk/cli.py`, change the `ArgumentParser(...)` at line 2437 to pass `prog="ctk"`, and add a version action right after it:

```python
    parser = argparse.ArgumentParser(
        prog="ctk",
        description=(
            "Conversation Toolkit. Run with no subcommand to open the TUI; "
            "use a subcommand for bulk / scripted operations."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {ctk.__version__}",
    )
```

Ensure `import ctk` (or `from ctk import __version__`) is available at the top of `cli.py`.

- [ ] **Step 4: Add an `_err` helper and route the highest-traffic error prints to stderr**

Near the top of `ctk/cli.py`, add:

```python
def _err(message):
    """Print a diagnostic to stderr so stdout stays clean for piped data."""
    import sys
    print(message, file=sys.stderr)
```

Convert the `print(f"Error: ...")` diagnostics to `_err(f"Error: ...")`. Prioritize the data-emitting commands first (`cmd_query`, `_display_sql_results`, the export/import handlers) so that `ctk query --format json | jq` is clean; the remaining conversion can proceed file-region by file-region. Do not change `print(...)` calls that emit actual result payload.

- [ ] **Step 5: Run the test**

Run: `pytest tests/unit/test_cli_diagnostics.py -v -o addopts=""`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ctk/cli.py tests/unit/test_cli_diagnostics.py
git commit -m "feat(cli): add --version and prog=ctk; route diagnostics to stderr for clean pipes"
```

---

### Task 12: Extract `build_parser()` and add a CLI-staleness guard test

**Context.** No test asserts the documented subcommands exist, which is how the doc site drifted. Extracting parser construction into a function makes the command set a checkable invariant (derive from structure).

**Files:**
- Modify: `ctk/cli.py` (extract `build_parser()` from `main()`)
- Test: `tests/unit/test_cli_parser.py` (create)

- [ ] **Step 1: Extract `build_parser()`**

In `ctk/cli.py`, move all parser construction currently inline in `main()` (from `parser = argparse.ArgumentParser(...)` at line 2437 through the end of subparser registration, including the `db`/`net`/`llm`/`config` `add_*` calls) into a new module-level function:

```python
def build_parser():
    """Construct and return the top-level argparse parser.

    Exposed as a standalone function so the documented command set is a
    testable invariant (see tests/unit/test_cli_parser.py).
    """
    parser = argparse.ArgumentParser(prog="ctk", description=(...))
    # ... all existing argument and subparser setup, unchanged ...
    return parser
```

Then in `main()`, replace the inline construction with `parser = build_parser()`. Keep behavior identical.

- [ ] **Step 2: Write the staleness-guard test**

Create `tests/unit/test_cli_parser.py`:

```python
import argparse

from ctk.cli import build_parser

EXPECTED_COMMANDS = {
    "import", "export", "query", "sql", "db",
    "net", "auto-tag", "llm", "config", "tui",
}


def test_documented_subcommands_exist():
    parser = build_parser()
    subparser_actions = [
        a for a in parser._actions
        if isinstance(a, argparse._SubParsersAction)
    ]
    assert subparser_actions, "no subparsers registered"
    registered = set(subparser_actions[0].choices.keys())
    assert EXPECTED_COMMANDS <= registered, (
        f"missing: {EXPECTED_COMMANDS - registered}; "
        f"unexpected: {registered - EXPECTED_COMMANDS}"
    )
```

- [ ] **Step 3: Run the test**

Run: `pytest tests/unit/test_cli_parser.py -v -o addopts=""`
Expected: PASS. (If FAIL, the command set drifted; reconcile docs and parser.)

- [ ] **Step 4: Commit**

```bash
git add ctk/cli.py tests/unit/test_cli_parser.py
git commit -m "refactor(cli): extract build_parser(); add staleness guard asserting documented command set"
```

---

## Phase 4: mypy to zero

### Task 13: Fix the genuine mypy bugs

**Context.** Of 226 mypy errors, the genuine bugs are: 2 `name-defined` forward-refs (`PaginatedResult` at `database.py:975`/`:1431`) and 6 `valid-type` (`callable` builtin used as an annotation). The 15 `_resolve_conversation_id` `name-defined` errors were fixed in Task 1.

**Files:**
- Modify: `ctk/core/database.py`, `ctk/core/db_operations.py`, `ctk/interfaces/mcp/handlers/{sql,search,metadata,analysis,conversation}.py`

- [ ] **Step 1: Confirm the current genuine-bug count**

Run: `mypy ctk --ignore-missing-imports 2>&1 | grep -E "name-defined|valid-type"`
Expected: the `PaginatedResult` lines and 6 `callable` lines (the 15 `_resolve_conversation_id` lines are already gone after Task 1).

- [ ] **Step 2: Add a TYPE_CHECKING import for the forward refs**

In `ctk/core/database.py`, ensure these exist near the top:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import PaginatedResult, ConversationSummary
```

(If `ConversationSummary` is already imported at module top, do not duplicate it; the goal is that the string annotations `'PaginatedResult'` and `'ConversationSummary'` resolve for mypy.)

- [ ] **Step 3: Replace `callable` with `typing.Callable`**

In each of these, change the annotation and add `from typing import Callable` if missing:
- `ctk/core/db_operations.py:67`: `progress_callback: Optional[Callable] = None`
- `ctk/interfaces/mcp/handlers/sql.py:111`: `HANDLERS: Dict[str, Callable] = {`
- `ctk/interfaces/mcp/handlers/search.py:148`: `HANDLERS: Dict[str, Callable] = {`
- `ctk/interfaces/mcp/handlers/metadata.py:62`: `HANDLERS: Dict[str, Callable] = {`
- `ctk/interfaces/mcp/handlers/analysis.py:330`: `HANDLERS: Dict[str, Callable] = {`
- `ctk/interfaces/mcp/handlers/conversation.py:274`: `HANDLERS: Dict[str, Callable] = {`

- [ ] **Step 4: Verify the genuine-bug categories are clear**

Run: `mypy ctk --ignore-missing-imports 2>&1 | grep -E "name-defined|valid-type" | wc -l`
Expected: `0`.

- [ ] **Step 5: Commit**

```bash
git add ctk/core/database.py ctk/core/db_operations.py ctk/interfaces/mcp/handlers/
git commit -m "fix(types): resolve PaginatedResult forward-refs and callable->Callable annotations"
```

---

### Task 14: Clear the remaining mypy errors, file by file

**Context.** After Tasks 1 and 13, roughly 203 annotation errors remain, concentrated in `database.py` (63), `html.py` (32), `models.py` (31), `cli.py` (26), `json.py` (24), `db_helpers.py` (22), `conversation_index.py` (20), then a long tail. The rule: fix with a real annotation or a narrowing, not a blanket ignore. A targeted `# type: ignore[code]` is acceptable only per-line with a one-line justification where the type system genuinely cannot express the intent.

This task is iterative. Do one file per commit, in descending error-count order. For each file:

- [ ] **Step A: List the file's errors**

Run (example for `database.py`): `mypy ctk/core/database.py --ignore-missing-imports`

- [ ] **Step B: Apply the right fix per category**

Concrete patterns (from the real errors found):

- `attr-defined` such as `set[str]` has no `.extend` (`conversation_index.py:284,293`) or `Sequence[str]` has no `.append` (`json.py:109`): the declared container type is wrong for the usage. Fix the annotation to the type actually used (e.g. `List[str]`), or use the correct method (`set.add`/`set.update`).
- `assignment` such as assigning `Optional[...]` into a `str`-typed target (`models.py:196-198`, `sanitizer.py:181`): widen the annotation to `Optional[str]` or guard with a default so the value is never `None` at assignment.
- `arg-type` such as passing `str | None` where `str` is expected (`db_operations.py:121`) or `str` where `Path` is expected (`plugin.py:397`): narrow with an explicit check (`assert x is not None`) or convert (`Path(x)`).
- `var-annotated`: add the missing annotation (e.g. `results: List[ConversationSummary] = []`).
- `return-value` / `union-attr`: narrow the union before use, or correct the declared return type.

- [ ] **Step C: Re-run mypy on the file until clean**

Run: `mypy ctk/core/database.py --ignore-missing-imports`
Expected: `Success: no issues found` for that file.

- [ ] **Step D: Run that file's tests, then commit**

```bash
pytest tests/unit -k "database" -q -o addopts=""
git add ctk/core/database.py
git commit -m "types(database): annotate to mypy-clean"
```

Repeat A through D for each file in order: `database.py`, `html.py`, `models.py`, `cli.py`, `json.py`, `db_helpers.py`, `conversation_index.py`, then the tail (`mcp_client.py`, `plugin.py`, `db_operations.py`, `rest/api.py`, `sidebar.py`, `base.py`, `analysis.py`, `copilot.py`, and any others mypy still reports). For `mcp_client.py` (theme-C dead code), fix its errors cheaply; do not invest in deep annotation there.

- [ ] **Final step: Confirm zero errors across the package**

Run: `mypy ctk --ignore-missing-imports`
Expected: `Success: no issues found in 82 source files` (count may shift slightly if `tree.py` is removed in Task 15).

```bash
git commit --allow-empty -m "types: ctk is mypy-clean (0 errors)"
```

---

## Phase 5: Close the coverage gap

### Task 15: Resolve `ctk/core/tree.py` (live or dead)

**Context.** `tree.py` is 291 statements at 0% coverage. Commit `c70b58c` pruned a "leftover module"; this one may be dead. If dead, deleting it removes 291 uncovered statements (raising the coverage percentage and removing confusion). If live, it is a large coverage opportunity.

**Files:**
- Possibly delete: `ctk/core/tree.py`
- Or test: `tests/unit/test_tree.py` (create) if live

- [ ] **Step 1: Determine whether anything imports it**

Run:
```bash
grep -rn "from ctk.core.tree\|import tree\|core\.tree" ctk/ tests/ examples/ | grep -v "ctk/core/tree.py:"
grep -rn "tree" ctk/core/__init__.py
```

- [ ] **Step 2a: If there are no importers and it is not re-exported, delete it**

```bash
git rm ctk/core/tree.py
pytest tests/unit -q -o addopts="" -p no:cacheprovider
```
Expected: full suite still passes (nothing depended on it).

```bash
git commit -m "chore: remove dead ctk/core/tree.py (no importers; superseded by models.ConversationTree)"
```

- [ ] **Step 2b: If it is imported, write tests covering its public functions**

Create `tests/unit/test_tree.py` exercising each public function/class in `tree.py` (read the module, write one focused test per public callable, asserting documented behavior). Then:

```bash
pytest tests/unit/test_tree.py -v -o addopts=""
git add tests/unit/test_tree.py
git commit -m "test: cover ctk/core/tree.py"
```

---

### Task 16: Add tests for the 0%-coverage live modules until coverage clears 59

**Context.** Live modules at 0% or near-0%: `prompts.py` (69, 0%), `network_tools.py` (68, 0%), `conversation_display.py` (57, 0%), `tools.py` (9, 0%), `tfidf.py` (85, 34%), `db_operations.py` (406, 12%). Combined with the new tests from Tasks 1, 2, 4, 10, 11, 12, this comfortably clears the ~550-statement gap to 59. Do NOT write coverage tests for `mcp_client.py` (theme-C dead code).

**Files:**
- Create: `tests/unit/test_prompts.py`, `tests/unit/test_network_tools.py`, `tests/unit/test_conversation_display.py`, `tests/unit/test_tools.py` (and extend `test_db_operations*.py` / a tfidf test as needed)

- [ ] **Step 1: Measure the current coverage after Phases 1 to 4**

Run: `pytest tests/unit --cov=ctk --cov-report=term-missing -q -o addopts="" -p no:cacheprovider`
Note the TOTAL percentage and which modules still show large `Miss` counts.

- [ ] **Step 2: Write a focused test module per 0% target**

For each module, read it and write tests that exercise its public surface against real inputs. Example for `ctk/core/prompts.py`:

```python
from ctk.core.prompts import get_ctk_system_prompt


def test_system_prompt_is_nonempty_and_mentions_tools():
    prompt = get_ctk_system_prompt()
    assert isinstance(prompt, str) and len(prompt) > 0
```

Example for `ctk/core/network_tools.py` (uses the persisted `SimilarityModel`):

```python
from ctk.core.database import ConversationDB
from ctk.core import network_tools


def test_list_neighbors_on_empty_graph_returns_empty():
    db = ConversationDB(":memory:")
    result = network_tools.execute_network_tool(
        "list_neighbors", {"conversation_id": "nope"}, db
    )
    assert "neighbor" in result.lower() or "no " in result.lower()
    db.close()
```

(Read each module's actual function names and signatures before writing; mirror the patterns in existing `tests/unit/` tests for fixtures and DB setup.)

- [ ] **Step 3: Re-measure until TOTAL is at or above 59**

Run: `pytest tests/unit --cov=ctk --cov-report=term-missing -q -o addopts="" -p no:cacheprovider 2>&1 | tail -5`
Expected: TOTAL at or above 59%. If still short, add tests for the next-largest `Miss` module (`db_operations.py`, `cli_db.py`, `cli.py` paths exercised via `execute_ask_tool`).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/
git commit -m "test: cover prompts/network_tools/conversation_display/tools; cross the 59 coverage gate"
```

---

## Phase 6: Final green gate

### Task 17: Confirm an all-green, honest CI gate

**Files:** none (verification only)

- [ ] **Step 1: Lint clean (flake8 + mypy)**

Run: `make lint`
Expected: flake8 passes; `mypy ctk --ignore-missing-imports` reports `Success: no issues found`.

- [ ] **Step 2: Full suite green with coverage at or above the gate**

Run: `make test`
Expected: all tests pass; coverage report shows TOTAL at or above 59% and the run does not fail on `--cov-fail-under=59`.

- [ ] **Step 3: Confirm CI workflow references only current commands**

Run: `grep -nE "ctk\.cli (plugins|list|stats)\b" .github/workflows/*.yml`
Expected: no matches.

- [ ] **Step 4: Confirm no `continue-on-error` masking on required jobs**

Run: `grep -n "continue-on-error" .github/workflows/*.yml`
Expected: none on the test/lint/integration jobs (release-workflow hardening is a separate sub-project; only confirm the CI gates here are honest).

- [ ] **Step 5: Final commit / ready for PR**

```bash
git commit --allow-empty -m "chore: correctness foundation complete; CI green (tests, mypy 0, coverage >= 59)"
```

---

## Self-review notes (for the executor)

- Every fix lands with a regression test that fails before and passes after. Do not skip the
  "verify it fails" step; a test that never failed proves nothing.
- The mypy fix-all (Task 14) is the largest effort. Resist blanket file-level ignores. Each
  per-line `# type: ignore[code]` must carry a one-line justification.
- Coverage is a by-product of meaningful tests (Tasks 1, 2, 4, 10-12, 16), not the goal. If you are
  tempted to test trivial getters purely for the number, prefer testing `db_operations.py` or the
  `execute_ask_tool` branches, which are both under-tested and behaviorally important.
- After all tasks, the Definition of Done checklist in the design doc (§9) should be fully checkable.
