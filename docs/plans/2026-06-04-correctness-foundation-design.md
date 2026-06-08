# Sub-project A: Correctness Foundation and Green CI (Design)

**Date:** 2026-06-04
**Status:** Design (approved scope and approach; pending spec review)
**Part of:** [CTK Improvement Program](2026-06-04-improvement-program-roadmap.md), sub-project 1 of 7
**Approach chosen:** *Fix-all CI*. Clear all mypy errors and cross the coverage gate as part of the
foundation, not just relax the gates.

---

## 1. Goal and success criteria

Make CTK correct on its primary paths and restore a green, honest CI signal, so the later growth
sub-projects (B through F) can refactor with a working safety net.

**Definition of done (all must hold):**

1. The in-TUI LLM tool path no longer silently fails. Every builtin tool that resolves a conversation
   id works against a real DB, with regression tests.
2. Conversation reload is lossless for all media types (audio, video, documents), with a round-trip
   regression test.
3. Agent-type detection is structure-driven, not substring-driven; the 5 environment-specific test
   failures pass on any tmpdir.
4. The REST surface runs against a real `ConversationDB` (no `AttributeError`), its Flask dependency
   is declared, and at least one test exercises it without mocks.
5. `mypy ctk --ignore-missing-imports` reports 0 errors.
6. The coverage gate passes: measured coverage is at or above `--cov-fail-under` (currently 59) on the
   suite CI runs, and the gate value is honest (not lowered below what the suite actually achieves).
7. All CI jobs are green: test, lint, and integration. No `continue-on-error` masking.
8. The folded-in correctness wins (broken headline example, missing deps, CSV quoting, stderr
   routing, `--version`, CLI-staleness guard) are landed.

---

## 2. Background: what verification confirmed

Every item below was confirmed against the real code with line-precise evidence (two workflow passes:
a 7-reader scan, then a 6-cluster verification). Key nuances that shape the design:

- The `_resolve_conversation_id` bug is a **silent failure, not a crash**. The broad
  `except Exception` at `cli.py:1540` swallows the `NameError` into a returned string like
  `"Error executing star_conversation: name '_resolve_conversation_id' is not defined"`. The tools
  appear to "work" (no traceback) but never act.
- The 5 failing filesystem tests are **environment-specific**: they fail here because the tmpdir is
  `/tmp/claude-1000` (contains the substring "claude"). They likely pass on GitHub runners. The
  underlying substring-match bug is real regardless and must be fixed structurally.
- Coverage is **54% unit-only / 57.4% full-suite** against a **59** gate. The gap is roughly 5 points
  (about 550 statements), closable by testing the live 0%-coverage modules plus the untested
  `execute_ask_tool` and REST methods.
- `mypy` reports **226 errors in 38 files**. Only 23 are genuine bugs (17 `name-defined`, 6
  `valid-type`); the other ~203 are type-annotation noise concentrated in a few large files.

---

## 3. Workstream 1: Correctness bug fixes

### 1.1 `_resolve_conversation_id` undefined (in-TUI LLM tool dispatcher)

**Problem.** `ctk/cli.py` `execute_ask_tool` calls `_resolve_conversation_id(db, conv_id)` at 15
sites; the function is defined nowhere. The `NameError` is swallowed at `cli.py:1540` into an error
string, so every LLM-driven star/unstar/pin/unpin/archive/unarchive/rename/delete/tag/remove_tag/
export/duplicate/show_tree/list_paths/auto_tag silently fails.

**Call sites (all `ctk/cli.py`):** 1001, 1013, 1025, 1037, 1049, 1061, 1076, 1118, 1133, 1152, 1195,
1256, 1321, 1460, 1524.

**Contract reconciliation (important).** 13 sites check `if conv_id.startswith("Error:"): return conv_id`.
Two sites (1460 `list_conversation_paths`, 1524 `auto_tag_conversation`) check `if not conv_id`
(expect `None`). The existing `db.resolve_conversation()` (`database.py:876-940`) returns
`Optional[str]`, which natively satisfies only the 2 `None`-expecting sites.

**Fix.** Add a thin module-level wrapper in `ctk/cli.py` above `execute_ask_tool` (before line 737)
that adapts the existing DB resolver to the string-sentinel contract the 13 sites use:

```python
def _resolve_conversation_id(db, conv_id):
    """Resolve a partial id/slug to a full conversation id, or return an 'Error:' sentinel."""
    full = db.resolve_conversation(conv_id)  # ctk/core/database.py:876
    if full is None:
        return f"Error: No conversation found matching '{conv_id}'"
    return full
```

Then update the 2 `None`-expecting sites (1460, 1524) to the `.startswith("Error:")` check for
uniformity (or call `db.resolve_conversation(...)` directly there). Reuses the existing resolver
rather than adding a 16th prefix scan, consistent with the "one source of truth" principle.

**Tests (new).** `tests/unit/` parametrized test over the 15 affected tool names against an in-memory
`ConversationDB`: (a) a valid prefix resolves and the op succeeds; (b) an unknown id returns the
`Error:`-prefixed message (not a swallowed `NameError`). `grep execute_ask_tool tests/` is currently
empty, so this is net-new coverage of a 1557-statement file at 18%.

### 1.2 `MessageContent.from_dict` drops audio/video/documents

**Problem.** `ctk/core/models.py` `to_dict` (232-255) serializes images, audio, video, documents,
tool_calls. `from_dict` (257-282) reconstructs only images (268-275) and tool_calls (278-280). Audio,
video, and documents are dropped on every round-trip, and therefore on every DB reload
(`database.py:696` save, `database.py:851` load). The Anthropic importer deliberately creates
`ContentType.DOCUMENT` objects for PDFs (`anthropic.py:188-195`); those vanish on reload. Empirically
confirmed: 1 image survives, 1 audio + 1 video + 1 document all become 0 after `from_dict(to_dict(x))`.

**Fix.** In `from_dict`, after the images loop, add three loops mirroring it, appending `MediaContent`
with the correct `ContentType` (`AUDIO`, `VIDEO`, `DOCUMENT`) to `content.audio`, `content.video`,
`content.documents` respectively. The enum values already exist (`models.py:56-66`); the field names
are at `models.py:163-166`.

**Test (new).** Lift the verification repro into `tests/unit/test_models.py`: build a `MessageContent`
with one of each media type plus tool_calls, assert all survive `from_dict(to_dict(x))`. (This is a
down-payment on sub-project B's full fidelity matrix; B will generalize it.)

### 1.3 Substring agent detection (`filesystem_coding` importer)

**Problem.** `ctk/importers/filesystem_coding.py:73-96` `_detect_agent_type` does
`path_str = str(path).lower()` then substring-matches "claude"/"cursor"/"copilot"/"codeium" against
the entire absolute path, so any path under `/tmp/claude-1000` returns `claude_code`, short-circuiting
the marker-file checks below. This violates the "no substring-matching of structured data" principle
and causes 5 environment-specific test failures.

**Structural sentinels (verified):**

| Agent | Dir-name leaf sentinel | Marker file sentinel(s) |
|-------|------------------------|-------------------------|
| copilot | `.vscode` | `copilot.db`, `copilot_conversations.json` |
| cursor | `.cursor` | `cursor.db`, `conversations.db` |
| claude_code | `.claude` | (none; name-only) |
| codeium | `.codeium` | (none; name-only) |
| generic | (fallback) | `chat_history.json`, `sessions.json` |

**Fix.** Rewrite `_detect_agent_type` to match on `path.name` (the leaf, case-insensitive) against the
dir-name sentinels and `(path / marker).exists()` against marker files, returning `None` otherwise.
Drive it from a per-agent `{names, markers}` structure (not a substring ladder). Note: `claude_code`
and `codeium` have only dir-name sentinels, so the fix cannot rely on marker files alone (that would
regress `test_detect_codeium_from_codeium_path`). The four stub parsers
(`_import_claude_code`, `_import_codeium`, `_parse_cursor_conversation`, `_parse_generic_conversation`)
stay unchanged: their tests assert `[]`/`None`, and real parsers are out of scope (agentic territory).

**Tests.** The 5 existing failing tests become the regression guard; they pass on any tmpdir once
detection is structural.

### 1.4 REST surface uses non-existent DB attributes

**Problem.** `ctk/interfaces/rest/api.py` calls `db.session`, `db.ConversationModel`, and
`db._model_to_tree` in three methods; none exist on `ConversationDB`. `GET /api/conversations`,
`POST /api/export`, and `PATCH /api/conversations/<id>` raise `AttributeError` against a real DB. The
29 REST tests pass only because they inject a bare `MagicMock` db (auto-creating those attributes) and
a `sys.modules["flask_cors"] = MagicMock()` shim. `flask` and `flask_cors` are imported at module top
but declared in neither `setup.py` nor `requirements.txt`.

**Fix (route through the public API):**

- `list_conversations` (api.py:580-624): use `db.list_conversations(limit, offset, source, project,
  model, tags)` returning `List[ConversationSummary]`; build payload from `summary.to_dict()`. Replace
  the dynamic `getattr(ConversationModel, sort_by)` with the method's fixed ordering.
- `export_conversations` (api.py:480-526): iterate `db.list_conversations(...)` then
  `db.load_conversation(id)` per item to get a `ConversationTree`.
- `update_conversation` (api.py:667-702): use `db.update_conversation_metadata(id, title=...,
  project=...)` (already used by `rename_conversation` at api.py:799).
- Packaging: add a `rest` extra to `setup.py` `extras_require`: `"rest": ["flask>=2.0",
  "flask-cors>=4.0"]`. Defer the `flask`/`flask_cors` imports into method bodies (or guard at module
  top) with a friendly `ImportError` pointing at `pip install conversation-tk[rest]`. Add `flask-cors`
  to the `dev` extra so CI exercises the real import path.

**Tests.** Add at least one REST test backed by a real on-disk `ConversationDB` (not a mock) that hits
the three rewritten endpoints and asserts they call the public DB methods. Keeping the mock-only tests
is fine for routing/status assertions, but the real-DB test is what prevents this class of bug.

---

## 4. Workstream 2: Green CI (fix-all)

### 2.1 mypy: 0 errors (from 226)

**Genuine bugs (fix first):**

- `name-defined` (17): 15 are the `_resolve_conversation_id` sites (resolved by 1.1). The other 2 are
  `PaginatedResult` forward-refs at `database.py:975` and `:1431` (imported lazily in the body at
  `:1005`/`:1460`). Add a `if TYPE_CHECKING:` import of `PaginatedResult` (and `ConversationSummary`)
  in `database.py` so the string annotations resolve. This is a type-hint gap, not a runtime bug.
- `valid-type` (6): `callable` (the builtin) used as an annotation. Replace with `typing.Callable` in
  `db_operations.py:67` and the five `HANDLERS: Dict[str, callable]` declarations
  (`mcp/handlers/sql.py:111`, `search.py:148`, `metadata.py:62`, `analysis.py:330`,
  `conversation.py:274`). Add `from typing import Callable` where missing.

**Bulk noise (~203, clear systematically).** Concentrated by file: `database.py` 63, `html.py` 32,
`models.py` 31, `cli.py` 26, `json.py` 24, `db_helpers.py` 22, `conversation_index.py` 20,
`mcp_client.py` 11, `plugin.py` 10, `db_operations.py` 9, `rest/api.py` 8. Dominant codes: `assignment`
79, `arg-type` 42, `index` 18, `attr-defined` 18, `return-value` 12, `union-attr` 8, `var-annotated`
7. Approach, in priority order:

1. Fix with real annotations / narrowing where the error reveals a genuine type confusion (e.g.
   `set[str]` getting `.extend`, `Sequence[str]` getting `.append`, `Optional`-typed args declared as
   `str`). These are latent correctness signals.
2. Add precise type annotations where mypy lacks information (`var-annotated`, many `assignment`).
3. Use targeted `# type: ignore[code]` with a one-line justification ONLY where the type system
   genuinely cannot express the intent (last resort, not the default). Blanket file-level ignores are
   not acceptable.

This is the single heaviest part of sub-project A. `database.py`, `html.py`, and `models.py` together
hold 126 of the 226 errors and should be tackled file-by-file.

**Note:** `mcp_client.py` (11 mypy errors, 0% coverage) is dead code that sub-project C will either
wire up or delete. Spend minimal effort here in A: fix its mypy errors cheaply or, if C is likely to
delete it, coordinate so we do not annotate code we are about to remove. Default: fix the 11 errors
(cheap) and leave the wiring decision to C.

### 2.2 Coverage: at or above the gate (from 54% unit / 57.4% full)

Target the live 0%-coverage and near-0% modules with new unit tests (biggest, cleanest wins first):

| Module | Stmts | Cover | Notes |
|--------|-------|-------|-------|
| `ctk/core/prompts.py` | 69 | 0% | pure; easy |
| `ctk/core/network_tools.py` | 68 | 0% | queries `SimilarityModel`; testable with fixtures |
| `ctk/core/conversation_display.py` | 57 | 0% | formatting helper |
| `ctk/core/tools.py` | 9 | 0% | trivial |
| `ctk/embeddings/tfidf.py` | 85 | 34% | raise coverage |
| `ctk/core/db_operations.py` | 406 | 12% | merge/dedupe/diff; high absolute miss (356) |
| `ctk/cli.py` (execute_ask_tool) | 1557 | 18% | the 1.1 tests add a big chunk |

`ctk/core/tree.py` (291 stmts, 0%) needs an investigation step: determine whether it is live or dead
(recent commit `c70b58c` pruned a "leftover module"). If dead, delete it (removes 291 uncovered
statements from the denominator, a clean coverage gain and a clarity gain). If live, testing it is a
large coverage win. Do NOT target `mcp_client.py` (210 stmts, 0%) for coverage in A; it is theme-C
dead code.

The combination of the `execute_ask_tool` tests (1.1), the REST real-DB test (1.4), the media
round-trip test (1.2), and tests for the 0% live modules above comfortably exceeds the ~550-statement
gap to 59%. The gate value itself stays at 59 (honest, since we are actually crossing it), not lowered.

### 2.3 Stale CI smoke step and stale integration tests

- `.github/workflows/test.yml:99-107` runs removed subcommands `plugins`, `list`, `stats`. Replace
  with current commands: `query --db test.db`, `db info test.db` (or `db stats`). The valid top-level
  set is: `import, export, auto-tag, tui, query, sql, db, net, llm, config`.
- `tests/integration/test_cli.py`: `test_plugins_command` (221-228) asserts a removed subcommand
  returns 0. Delete or rewrite. `test_cli_no_command` (93-99) asserts bare `ctk` returns 1, but bare
  `ctk` now opens the TUI (can hang without a TTY). Rewrite to assert TUI-launch behavior, or
  skip/short-circuit when no TTY.

### 2.4 Duplicate top-level test files

`pytest.ini testpaths=tests` collects both `tests/` and `tests/unit/`, so duplicates run twice and
`make test-unit` silently skips the top-level ones.

- Delete `tests/test_database_comprehensive.py` and `tests/test_models_comprehensive.py` (the
  `tests/unit/` counterparts have more tests and are canonical).
- Move `tests/test_db_operations.py` and `tests/test_db_operations_comprehensive.py` into
  `tests/unit/` (no counterpart exists; do not delete).

### 2.5 pytest-timeout (guard against hangs)

`pytest-timeout` 2.4.0 is installed and active but undeclared. Add `pytest-timeout>=2.0.0` to
`requirements-dev.txt` and `setup.py` `extras_require['dev']`, and add `timeout = 60` (with
`timeout_method = thread`) to `pytest.ini`. This converts a hanging TUI/no-TTY test into a fast,
actionable failure instead of a 6-hour CI stall.

---

## 5. Workstream 3: Folded-in correctness wins (F-quick)

These are cheap and fix genuine output/doc correctness bugs, so they ride with the foundation.

### 3.1 Broken headline fluent-API example

`README.md:398` and `docs/index.md:398` both show
`CTK("chats").search("python").filter(source="ChatGPT").limit(10).get()`. `SearchBuilder` has no
`.filter` (its filters are `in_source`/`with_model`/`in_project`/`with_tags`); `.filter` exists only
on `ConversationLoader`. Replace `.filter(source="ChatGPT")` with `.in_source("ChatGPT")` in both
files. (The project `CLAUDE.md` example does not use `.filter`, so it is already correct.)

### 3.2 `requirements.txt` missing TUI deps

`requirements.txt` omits `textual`, `textual-image`, `openai` (which the bare `ctk` TUI imports);
`setup.py` `install_requires` has all three. Principled fix: make `requirements.txt` and
`setup.py install_requires` a single source of truth (have `setup.py` read `requirements.txt`, or drop
`requirements.txt` in favor of the editable install). Minimum fix: append the three missing lines.

### 3.3 Hand-rolled CSV (no quoting/escaping)

`ctk/core/db_helpers.py:229-237` and `:250-258` (query `--format csv`) and `ctk/cli.py:2410-2413`
(`_display_sql_results`, sql `--format csv`) build CSV by comma-joining raw values. Titles with
commas/quotes/newlines corrupt rows, and a title starting with `=,+,-,@` is a formula-injection vector.
Replace all three with `csv.writer(sys.stdout)`. The two `db_helpers` branches are identical and should
share one helper.

### 3.4 stderr routing, `--version`, `prog`

- 70 `print(f"Error...")` calls in `cli.py` go to stdout, interleaving diagnostics with data and
  breaking `ctk query --format json | jq`. Route diagnostics to stderr (a small `_err()` helper, or
  `file=sys.stderr`). Reserve stdout for payload.
- Add `prog="ctk"` and a `--version` action to the `ArgumentParser` at `cli.py:2437`:
  `parser.add_argument("--version", action="version", version=f"%(prog)s {ctk.__version__}")`.

### 3.5 CLI-staleness guard (structural)

There is no test asserting the documented subcommands exist. To prevent the doc-rot class of bug
(sub-project F will regenerate the docs; this guard keeps them honest), refactor `cli.py main()` so
parser construction is a standalone `build_parser()` function, then add a test asserting the
subparsers' `choices` keyset equals the documented command set
`{import, export, query, sql, db, net, auto-tag, llm, config, tui}`. This makes the CLI table in
`CLAUDE.md`/`README` a checkable invariant (derive from structure, do not hand-maintain).

---

## 6. Out of scope for A (deferred)

- Real Cursor/Claude-Code/Codeium parsers (agentic territory; the stubs stay stubs).
- The fuller round-trip fidelity work: ctk-format re-import inverse, reasoning capture, `.zip` import,
  idempotent re-import, the full fidelity matrix (sub-project B). A lands only the `from_dict` media
  fix and a single round-trip test as a down-payment.
- Wiring or deleting `mcp_client.py`, unifying the tool surfaces, fixing `execute_sql` params binding
  (sub-project C).
- Versioned migrations, FTS5 tests, metadata single-source (sub-project E-core).

---

## 7. Testing strategy

- Every bug fix lands with a regression test in `tests/unit/` (or `tests/integration/` where
  appropriate).
- New coverage targets are chosen to both fix real gaps and cross the gate honestly; coverage is a
  by-product of meaningful tests, not the goal itself.
- The full suite must pass with `mypy` clean and coverage at or above 59 before A is considered done.
- Run order for verification: `make lint` (flake8 + mypy), `make test` (full suite + coverage),
  confirm CI workflow files reference only current commands.

---

## 8. Risks and notes

- **mypy fix-all is the largest single effort in A** (~203 noise errors across `database.py` 63,
  `html.py` 32, `models.py` 31, `cli.py` 26, `json.py` 24). Budget accordingly. Resist blanket
  ignores; each one is a small admission of defeat against the "derive from structure" value.
- **The 5 filesystem test failures are environment-specific** and may already pass on GitHub runners.
  The fix is still correct and makes local `make test` green regardless of tmpdir.
- **Coverage numbers differ by suite** (54% unit-only vs 57.4% full). Confirm which suite the CI test
  job measures and target that one; the gate is enforced via `pytest.ini addopts` uniformly.
- **`tree.py` live-vs-dead** must be resolved before counting it as a coverage lever; deleting dead
  code is preferable to testing it.

---

## 9. Definition of done (checklist)

- [ ] `_resolve_conversation_id` helper added; 2 `None`-contract sites reconciled; parametrized
      `execute_ask_tool` test passes for all 15 tools.
- [ ] `from_dict` reconstructs audio/video/documents; round-trip media test passes.
- [ ] `_detect_agent_type` is structure-driven; 5 filesystem tests pass on any tmpdir.
- [ ] REST `list`/`export`/`update` route through the public DB API; `rest` extra added; deferred
      imports with friendly error; one real-DB REST test passes.
- [ ] `mypy ctk --ignore-missing-imports` reports 0 errors.
- [ ] Coverage at or above 59 on the CI-measured suite; gate value unchanged at 59.
- [ ] CI smoke step uses current subcommands; stale integration tests rewritten; duplicate top-level
      test files removed/moved; `pytest-timeout` declared and `timeout = 60` set.
- [ ] Headline example fixed in README + docs/index; `requirements.txt` reconciled with `setup.py`;
      CSV via `csv.writer`; diagnostics to stderr; `--version` and `prog="ctk"` added.
- [ ] `build_parser()` extracted; CLI-staleness guard test asserts the documented command set.
- [ ] All CI jobs (test, lint, integration) green with no `continue-on-error` masking.
