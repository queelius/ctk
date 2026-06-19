# cwd Database Discovery Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `ctk` is run with no usable database, scan the current directory for real CTK databases and offer them in an interactive picker instead of erroring out.

**Architecture:** A pure `discover_ctk_databases` helper (new module) finds directories holding a schema-valid `conversations.db`; a TTY-guarded `_offer_database_choice` picker in cli.py presents them; `_resolve_tui_db_path` calls both before its existing error returns. Non-interactive behavior is unchanged.

**Tech Stack:** Python 3.12, sqlite3 (read-only probe), pytest.

**Spec:** `docs/plans/2026-06-19-cwd-db-discovery-design.md`

## Global Constraints

- TDD: failing test first, run-to-fail, implement, pass.
- A repo write hook BLOCKS any file containing an em-dash character or the word spelled l-e-v-e-r-a-g-e (a jargon synonym of "use"). Use plain hyphens and ordinary punctuation everywhere, including docstrings and test strings.
- No bare `except:`; name exception types.
- Discovery must NOT mutate a found database (read-only probe only; never open a write connection or run migrations just to list it).
- Non-interactive safety: when `sys.stdin.isatty()` is False, the picker returns None and the caller keeps today's exact error message and exit code.
- Green gate before each commit: `python -m pytest <touched test files> -q -o addopts=""` pass; `python -m black <touched files>`; `python -m flake8 <touched files> --max-line-length=100 --ignore=E203,W503` clean on new lines; `python -m mypy ctk --ignore-missing-imports` 0 errors.

---

## Task 1: `discover_ctk_databases` (pure discovery)

**Files:**
- Create: `ctk/core/db_discovery.py`
- Test: `tests/unit/test_db_discovery.py`

**Interfaces:**
- Produces: `discover_ctk_databases(root: str, max_depth: int = 1) -> List[str]` returning sorted, de-duplicated absolute directory paths that contain a schema-valid `conversations.db`. Never raises on a bad candidate.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_db_discovery.py
import os
import sqlite3
import pytest

from ctk.core.database import ConversationDB
from ctk.core.db_discovery import discover_ctk_databases

pytestmark = pytest.mark.unit


def _make_ctk_db(dirpath):
    # ConversationDB creates conversations.db with the real schema.
    db = ConversationDB(str(dirpath))
    db.close()


def _make_non_ctk_sqlite(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    conn = sqlite3.connect(os.path.join(str(dirpath), "conversations.db"))
    conn.execute("CREATE TABLE not_ctk (id INTEGER)")
    conn.commit()
    conn.close()


def test_finds_only_valid_ctk_databases(tmp_path):
    good = tmp_path / "good"
    _make_ctk_db(good)
    bad = tmp_path / "bad"
    _make_non_ctk_sqlite(bad)
    (tmp_path / "empty").mkdir()

    found = discover_ctk_databases(str(tmp_path))
    assert os.path.abspath(str(good)) in found
    assert os.path.abspath(str(bad)) not in found
    assert len(found) == 1


def test_depth_bound(tmp_path):
    nested = tmp_path / "level1" / "deepdb"
    nested.mkdir(parents=True)
    _make_ctk_db(nested)  # two levels below tmp_path
    found = discover_ctk_databases(str(tmp_path), max_depth=1)
    assert os.path.abspath(str(nested)) not in found


def test_root_itself_counts(tmp_path):
    _make_ctk_db(tmp_path)
    found = discover_ctk_databases(str(tmp_path))
    assert os.path.abspath(str(tmp_path)) in found


def test_unreadable_candidate_is_skipped_not_raised(tmp_path):
    d = tmp_path / "garbage"
    d.mkdir()
    with open(d / "conversations.db", "wb") as fh:
        fh.write(b"this is not a sqlite file at all")
    # must not raise
    found = discover_ctk_databases(str(tmp_path))
    assert os.path.abspath(str(d)) not in found
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_db_discovery.py -q -o addopts=""`
Expected: FAIL with `ModuleNotFoundError: No module named 'ctk.core.db_discovery'`.

- [ ] **Step 3: Implement**

```python
# ctk/core/db_discovery.py
"""Discover CTK databases on disk for the no-database onboarding fallback.

A CTK database is a directory containing a conversations.db whose schema has a
conversations table. Probing is read-only and never mutates a candidate.
"""

import logging
import os
import sqlite3
from typing import List

logger = logging.getLogger(__name__)


def _is_ctk_database(db_file: str) -> bool:
    """True if db_file is a sqlite database with a conversations table."""
    try:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='conversations'"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.debug("Skipping non-CTK candidate %s: %s", db_file, exc)
        return False


def discover_ctk_databases(root: str, max_depth: int = 1) -> List[str]:
    """Return CTK database directories at or just under root (shallow).

    depth 0 is root itself; depth 1 adds its immediate subdirectories. Symlinked
    directories are not followed. Any unreadable or non-CTK candidate is skipped.
    """
    root = os.path.abspath(os.path.expanduser(root))
    dirs = [root]
    if max_depth >= 1:
        try:
            for entry in os.scandir(root):
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(entry.path)
        except OSError as exc:
            logger.debug("Cannot scan %s: %s", root, exc)
    found = []
    for d in dirs:
        db_file = os.path.join(d, "conversations.db")
        if os.path.isfile(db_file) and _is_ctk_database(db_file):
            found.append(os.path.abspath(d))
    return sorted(set(found))
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_db_discovery.py -q -o addopts=""`
Expected: PASS (4 tests).

- [ ] **Step 5: Green gate and commit**

```bash
python -m black ctk/core/db_discovery.py tests/unit/test_db_discovery.py
python -m flake8 ctk/core/db_discovery.py tests/unit/test_db_discovery.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add ctk/core/db_discovery.py tests/unit/test_db_discovery.py
git commit -m "feat(db): discover_ctk_databases (read-only shallow scan for CTK databases)"
```

---

## Task 2: `_offer_database_choice` (TTY-guarded picker)

**Files:**
- Modify: `ctk/cli.py` (add `_offer_database_choice` near `_resolve_tui_db_path`)
- Test: `tests/unit/test_db_choice.py`

**Interfaces:**
- Consumes: `discover_ctk_databases` results (a list of paths) and a default directory.
- Produces: `_offer_database_choice(candidates: List[str], default_dir: str) -> Optional[str]` returning a chosen database path, the default dir for "create new", or None (not a TTY, empty, or invalid after one reprompt).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_db_choice.py
import builtins
import pytest

from ctk.cli import _offer_database_choice

pytestmark = pytest.mark.unit


def _force_tty(monkeypatch, is_tty=True):
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: is_tty, raising=False)


def test_non_tty_returns_none(monkeypatch):
    _force_tty(monkeypatch, is_tty=False)
    assert _offer_database_choice(["/a/db"], "/home/u/.ctk") is None


def test_pick_number_returns_candidate(monkeypatch):
    _force_tty(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda *a: "1")
    assert _offer_database_choice(["/a/db", "/b/db"], "/home/u/.ctk") == "/a/db"


def test_pick_n_returns_default(monkeypatch):
    _force_tty(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda *a: "n")
    assert _offer_database_choice(["/a/db"], "/home/u/.ctk") == "/home/u/.ctk"


def test_empty_returns_none(monkeypatch):
    _force_tty(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda *a: "")
    assert _offer_database_choice(["/a/db"], "/home/u/.ctk") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_db_choice.py -q -o addopts=""`
Expected: FAIL with `ImportError: cannot import name '_offer_database_choice'`.

- [ ] **Step 3: Implement**

Add to `ctk/cli.py` (near `_resolve_tui_db_path`; ensure `os`, `sys`, and `Optional`/`List` from typing are available in the module - import locally inside the function if the module does not already import them at top):

```python
def _offer_database_choice(candidates, default_dir):
    """Interactively offer a database when none is configured.

    Returns a chosen path, the default dir for a new database, or None when
    stdin is not a TTY or the user declines. Reprompts at most once.
    """
    import os
    import sys

    if not sys.stdin.isatty():
        return None

    print("No database configured.")
    if candidates:
        print("Found these CTK databases in the current directory:")
        for i, path in enumerate(candidates, 1):
            print(f"  {i}. {path}")
    print(f"  n. Create a new database at {default_dir}")
    print("  Or type a path to a database directory.")

    for _attempt in range(2):
        try:
            choice = input("Open which database? ").strip()
        except EOFError:
            return None
        if not choice:
            return None
        if choice.lower() == "n":
            return default_dir
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(candidates):
                return candidates[idx - 1]
            print("That number is not in the list.")
            continue
        # Anything else is treated as a path.
        return os.path.expanduser(choice)
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_db_choice.py -q -o addopts=""`
Expected: PASS (4 tests).

- [ ] **Step 5: Green gate and commit**

```bash
python -m black ctk/cli.py tests/unit/test_db_choice.py
python -m flake8 ctk/cli.py tests/unit/test_db_choice.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add ctk/cli.py tests/unit/test_db_choice.py
git commit -m "feat(cli): _offer_database_choice TTY-guarded database picker"
```

---

## Task 3: Wire discovery into `_resolve_tui_db_path` + green gate + 2.19.0

**Files:**
- Modify: `ctk/cli.py` (`_resolve_tui_db_path`, lines around 1800-1839)
- Modify: `ctk/__init__.py`, `setup.py`, `CITATION.cff` (bump to 2.19.0)
- Test: `tests/unit/test_resolve_tui_db_path.py`

**Interfaces:**
- Consumes: `discover_ctk_databases`, `_offer_database_choice`.
- Behavior: when no usable database resolves, discovery + the picker are offered before the existing error returns. `--db` and a valid configured default still resolve directly with no discovery call. Non-TTY keeps today's behavior.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_resolve_tui_db_path.py
import argparse
import pytest

import ctk.cli as cli

pytestmark = pytest.mark.unit


def test_explicit_db_skips_discovery(monkeypatch, tmp_path):
    called = {"n": 0}
    monkeypatch.setattr(cli, "discover_ctk_databases", lambda *a, **k: (called.__setitem__("n", called["n"] + 1) or []))
    args = argparse.Namespace(db=str(tmp_path))
    out = cli._resolve_tui_db_path(args)
    assert out == str(tmp_path)
    assert called["n"] == 0  # discovery not called on the fast path


def test_no_db_non_tty_keeps_error(monkeypatch, capsys):
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    # No configured default
    monkeypatch.setattr(cli, "get_config", lambda: type("C", (), {"config": {}})(), raising=False)
    args = argparse.Namespace(db=None)
    out = cli._resolve_tui_db_path(args)
    assert out == 1  # unchanged non-interactive error exit


def test_no_db_tty_uses_picked_path(monkeypatch):
    import sys
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(cli, "get_config", lambda: type("C", (), {"config": {}})(), raising=False)
    monkeypatch.setattr(cli, "discover_ctk_databases", lambda *a, **k: ["/picked/db"])
    monkeypatch.setattr(cli, "_offer_database_choice", lambda cands, default: "/picked/db")
    args = argparse.Namespace(db=None)
    out = cli._resolve_tui_db_path(args)
    assert out == "/picked/db"
```

Note: the exact monkeypatch of `get_config` must match how `_resolve_tui_db_path` imports it. The function currently does `from ctk.core.config import get_config` inside the body; change it to use a module-level reference (`import` at top of cli.py or a module-level `from ctk.core.config import get_config`) so the test can monkeypatch `cli.get_config`, OR adjust the test to patch `ctk.core.config.get_config`. Pick one and keep it consistent; the implementer decides based on the real import and documents it.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_resolve_tui_db_path.py -q -o addopts=""`
Expected: FAIL (discovery is not wired in; `test_no_db_tty_uses_picked_path` returns 1 instead of the picked path).

- [ ] **Step 3: Implement**

Modify `_resolve_tui_db_path` so that at each point where it currently returns 1 for "configured default does not exist" and "no database configured", it first offers discovery + the picker. Add module-accessible references so tests can monkeypatch: `from ctk.core.db_discovery import discover_ctk_databases` and call `_offer_database_choice`. The shape:

```python
# when the configured default does not exist, or nothing is configured:
default_dir = db_path if db_path else os.path.expanduser("~/.ctk")
candidates = discover_ctk_databases(os.getcwd())
chosen = _offer_database_choice(candidates, default_dir)
if chosen:
    return chosen
# else: print the existing message and return 1 (unchanged)
```

Keep the `--db` and valid-default fast paths exactly as they are (return before any discovery call). Make sure `discover_ctk_databases` and `get_config` are referenced in a way the tests can monkeypatch on the `cli` module (module-level import, not a body-local import, for at least `discover_ctk_databases`; the implementer reconciles the test's `get_config` patching with the real import and updates the test note accordingly).

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/unit/test_resolve_tui_db_path.py tests/unit/test_db_discovery.py tests/unit/test_db_choice.py -q -o addopts=""`
Expected: PASS.

- [ ] **Step 5: Full green gate**

Run: `python -m pytest tests/unit -q` (coverage enforced); then `python -m pytest tests/integration -q -o addopts="" -m "not requires_ollama and not requires_api_key"`; then `python -m mypy ctk --ignore-missing-imports`.
Expected: all pass, coverage at or above 59, mypy 0.

- [ ] **Step 6: Bump to 2.19.0 and commit**

Set `__version__ = "2.19.0"` in `ctk/__init__.py`, `version="2.19.0"` in `setup.py`, and `version: 2.19.0` + `date-released: 2026-06-19` in `CITATION.cff`.

```bash
python -m black ctk/cli.py tests/unit/test_resolve_tui_db_path.py
python -m flake8 ctk/cli.py tests/unit/test_resolve_tui_db_path.py --max-line-length=100 --ignore=E203,W503
git add -A
git commit -m "feat(cli): offer cwd database discovery when none is configured; release 2.19.0"
```

Do NOT tag, push, or upload (release is user-gated).

---

## Self-review notes

- Spec coverage: W1 discovery -> Task 1; W2 picker -> Task 2; W3 wiring -> Task 3. Non-interactive safety is tested in Tasks 2 and 3. Read-only probe is enforced by `?mode=ro` and tested by the unreadable-candidate test.
- The Task 3 test note about monkeypatching `get_config` / `discover_ctk_databases` is a real ambiguity the implementer must resolve against the actual import style; flagged explicitly rather than guessed.
