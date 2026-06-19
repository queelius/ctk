# cwd Database Discovery Fallback (Design)

**Date:** 2026-06-19
**Status:** Design (approved in discussion)
**Part of:** CTK onboarding (relates to sub-project F)

---

## 1. Goal and definition of done

When a user runs `ctk` (or `ctk tui`) with no `--db` and no usable configured database, today the
CLI prints an error and exits. This feature makes that case helpful instead of dead-ended: scan the
current directory for real CTK databases and OFFER them in a picker, with options to create a fresh
database at the configured default or enter a path.

The behavior is conservative on purpose: it OFFERS, it does not auto-load; it detects real CTK
databases, not arbitrary `.db` files; and it scans shallowly. CTK remains a global-archive tool whose
primary database is the configured default (`~/.ctk`); cwd discovery is strictly a fallback that fires
only when nothing valid is configured.

**Definition of done:**

1. `discover_ctk_databases(root)` returns the CTK databases found at or just under `root` (a CTK
   database is a directory containing a `conversations.db` whose schema has a `conversations` table).
   It is pure, shallow (depth 1), and does not raise on unreadable or non-CTK sqlite files.
2. When `_resolve_tui_db_path` cannot resolve a usable database AND stdin is a TTY, it presents a
   numbered picker of discovered databases plus "create a new database at the default" and "enter a
   path", and returns the chosen path. When stdin is not a TTY (piped, CI, tests), it keeps today's
   non-interactive error-and-exit behavior unchanged.
3. Choosing "create new" initializes a database at the configured default (or `~/.ctk`) and opens it.
4. No regression to the explicit paths: `--db` and a valid `database.default_path` still resolve
   directly with no prompt.
5. Suite green: mypy 0, coverage at or above 59, all unit + integration tests pass; the discovery and
   the resolution fallback have unit tests.

---

## 2. Current behavior (grounded)

`_resolve_tui_db_path(args, parser)` (ctk/cli.py:1800) resolves in order: `--db`, then
`database.default_path` from `~/.ctk/config.json`. It already tolerates the file-vs-directory shape
(cli.py:1819-1820: a path ending in `.db` that is a file uses its parent directory). When the
configured default does not exist it prints an error and returns 1 (cli.py:1821-1828); when nothing is
configured it prints a "No database configured" message plus help and returns 1 (cli.py:1829-1838).
`ConversationDB` treats its path as a directory and stores the SQLite file at `<dir>/conversations.db`.

The two error-return points are exactly where discovery should be offered first.

---

## 3. Design

### W1: `discover_ctk_databases(root, max_depth=1) -> list[str]`

New pure helper (in `ctk/core/db_discovery.py`, a small focused module). Walk `root` to a shallow
depth (the directory itself and its immediate subdirectories), and for each directory that contains a
`conversations.db` file, confirm it is a CTK database by opening it read-only and checking that a
`conversations` table exists (via `sqlite_master`). Return the matching directory paths, sorted, with
no duplicates. Any per-candidate error (unreadable file, locked, not sqlite, no table) is caught and
that candidate is skipped, never raised. The function never opens a write connection and never runs
migrations (it must not mutate a found database just by listing it).

### W2: `_offer_database_choice(candidates, default_dir) -> str | None`

New interactive helper (in `ctk/cli.py`, next to `_resolve_tui_db_path`). Guarded by
`sys.stdin.isatty()`: if stdin is not a TTY it returns `None` immediately (callers then keep the
existing non-interactive behavior). Otherwise it prints a numbered list of `candidates` (each shown as
its path plus a small detail such as conversation count if cheap to read), plus two trailing options:
`n` to create a new database at `default_dir`, and a free-form path entry. It reads one line via
`input()`, resolves the selection to a database path (creating nothing yet for an existing pick; for
`n` it returns `default_dir` and the caller initializes it), and returns the path, or `None` if the
user enters nothing or an invalid choice after a single reprompt. The picker does not loop forever.

### W3: Wire into `_resolve_tui_db_path`

At both error-return points, before returning 1, call discovery against the current working directory
and, if there are candidates or stdin is a TTY, call `_offer_database_choice`. If it returns a path,
use it (initializing a new database at the default when the user chose "create new"); if it returns
`None`, fall through to today's exact error message and exit code so non-interactive and decline paths
are unchanged. The `--db` and valid-default fast paths are untouched and never trigger discovery.

---

## 4. Out of scope (deferred)

- A TUI "no database" landing screen. The first version is a pre-mount CLI picker, which is simpler
  and avoids the Textual screen hazards. A polished in-TUI landing screen is a later enhancement.
- Recursive deep scanning, following symlinks, or scanning outside the current directory.
- Treating arbitrary `*.db` files as CTK databases. Only directories with a schema-valid
  `conversations.db` qualify.
- Remembering the chosen database back into the config (the user can set `database.default_path`
  themselves); auto-writing config is a separate decision.

---

## 5. Testing

- `discover_ctk_databases`: a temp tree with one valid CTK database dir, one directory holding a
  non-CTK sqlite file (no `conversations` table), and one empty directory; assert only the valid one is
  returned. A nested valid database one level down is found; two levels down is not (depth bound). An
  unreadable or non-sqlite `conversations.db` is skipped, not raised.
- `_offer_database_choice`: with stdin not a TTY, returns `None` (monkeypatch `sys.stdin.isatty`).
  With a TTY and a scripted `input`, selecting a number returns that candidate; selecting `n` returns
  the default dir; empty or invalid-after-reprompt returns `None`.
- `_resolve_tui_db_path`: with no `--db` and no configured default and stdin not a TTY, behavior is
  unchanged (prints the existing message, returns 1). With a TTY and a discoverable database, it
  returns the picked path. `--db` and a valid default still resolve with no prompt and no discovery
  call (assert discovery is not invoked on the fast paths).

---

## 6. Release

Ships as a minor feature release (2.19.0) after merge, user-gated.
