# Sub-project E-core: DB Foundations (Design)

**Date:** 2026-06-18
**Status:** Design (decisions approved in discussion; pending spec review)
**Part of:** [CTK Improvement Program](2026-06-04-improvement-program-roadmap.md), sub-project E-core
**Decisions taken with user:** hand-rolled `PRAGMA user_version` migration runner (SQLite-only); conversation metadata columns are the single source of truth, blob holds only overflow.

---

## 1. Goal and definition of done

E-core hardens CTK's SQLite/SQLAlchemy storage layer so that schema, metadata, and branch
state are recorded as structured data instead of inferred from string-matched DDL, and so the
read paths scale to a 50k-conversation archive. Every fix lands with the regression test whose
absence let the bug ship.

The four faults share one root cause: **state is inferred, not recorded.** Schema generation is
guessed by substring-matching the `conversations` CREATE TABLE text; branch state is a write-only
side table; metadata is duplicated across columns and a JSON blob with no enforced invariant.

**Definition of done:**

1. A real versioned migration runner exists (`PRAGMA user_version` + an ordered migration list),
   replacing the substring-matching `_apply_migrations`. Opening an old-schema DB upgrades it in
   place; a failed migration aborts loudly instead of being swallowed to a debug log.
2. A drift-guard test asserts a fresh `create_all` schema is column-identical to a fully-migrated
   old DB, so a future ORM column with no migration fails in CI, not in a user's first write.
3. Conversation metadata has one source of truth: the dedicated columns. The persistence blob
   carries only `custom_data` (overflow). Exporters keep the full metadata dict via a separate
   serializer, so wire formats do not change. The star/pin/archive blob-staleness bug is gone and
   covered by a round-trip test.
4. The physically-missing `idx_conv_slug` and a compound/partial index for the keyset ordering
   exist (added through the migration runner). Slug resolution uses an index seek; listing pages
   no longer do `USE TEMP B-TREE FOR ORDER BY`.
5. `list_conversations` is no longer N+1 on tags and messages: a 50-row sidebar page issues a
   bounded, small number of queries instead of ~101. The `len(list_conversations(limit=None))`
   counting anti-patterns use `count_conversations`.
6. FTS5 search no longer returns false "no results" for tokenization mismatches, escapes special
   characters for `MATCH`, and caches its availability check. The trigger-based sync, the fallback
   path, and special-character queries have regression tests.
7. `PathModel` (write-only, redundant) is retired; `has_branches` is served by a denormalized,
   indexable column maintained at save time.
8. Suite green: mypy 0, coverage at or above 59, all unit and integration tests pass.

---

## 2. Empirical grounding (probed against the real code)

All claims below were verified with line-precise evidence by a multi-reader exploration pass.

**Migrations.** `ConversationDB.__init__` runs `create_all` (database.py:186), then `_migrate_schema`
(187), then `_setup_fts5` (188). There is no version stamp anywhere (zero hits for `user_version` /
`schema_version`). `create_all` only issues `CREATE TABLE IF NOT EXISTS`, so it never alters an
existing table. `_apply_migrations` (database.py:217) reads the `conversations` CREATE TABLE text
from `sqlite_master` and does `if "slug" not in table_sql.lower()` / `if "summary" not in ...` to add
exactly two columns (database.py:233-261). `save_conversation` writes `conv_model.slug`
(database.py:687) and `conv_model.summary` (database.py:668) unconditionally, which is why those two
ALTERs exist. Migration failures are caught and logged at `debug` (database.py:241-271), so a
half-migrated DB looks healthy until a later write crashes far from the cause. `alembic>=1.13.0` is
pinned (setup.py:34, requirements.txt:2) but never imported. No test opens an old-schema DB.

**Consequence:** the next ORM column added anywhere outside `conversations.slug/summary` will pass
`_init_schema` silently and then crash the first INSERT/UPDATE on an old DB with `no such column`.
This is a blocking latent fault.

**Metadata.** `ConversationModel` has dedicated columns for title, slug, created_at, updated_at,
summary, version, format, source, model, project, starred_at, pinned_at, archived_at (db_models.py:65-89)
plus a `metadata_json` blob (db_models.py:92). `save_conversation` writes the columns (database.py:660-687)
and then re-stores most of the same fields inside the blob via `metadata.to_dict()` (database.py:690).
But `star_conversation` / `pin_conversation` / `archive_conversation` write only the columns
(database.py:1846, 1872, 1898) and never touch the blob, so the blob's starred/pinned/archived
timestamps are permanently stale. `load_conversation` overrides ten fields from the columns
(database.py:834-846), discarding the blob copies, and every list/search/filter reads columns. Only
`version`, `format`, and `custom_data` are read from the blob unchallenged. Message-level metadata is
already clean (single-sourced). The blob copies are write-only dead weight that any external SQL/MCP/REST
writer can silently desync.

**Perf.** `list_conversations` builds summaries via `ConversationSummary.from_dict(conv.to_dict())`
(database.py:1110-1113, 1136-1139); `ConversationModel.to_dict()` calls `len(self.messages)`
(db_models.py:143, pulling every message row with content just to count) and iterates `self.tags`
(db_models.py:141), both lazy with no eager loading. A 50-row page is therefore ~1 + 50 + 50 = ~101
queries. `idx_conv_slug` is declared (db_models.py:66, 121) but added via bare `ALTER` with no
`CREATE INDEX`, so it is physically absent: `EXPLAIN` of a slug lookup shows `SCAN conversations`.
The keyset and offset orderings have no supporting compound index, so every page shows
`USE TEMP B-TREE FOR ORDER BY`. `prompts.py:138-140, 195-196` do `len(list_conversations(limit=None))`
to get integers. The filter blocks are copy-pasted four times (database.py:1037-1076, 1164-1192,
1241-1272, 1424-1459). `_has_fts5()` opens a fresh connection on every search (database.py:479, 1346, 1553).

**FTS5.** Sync is maintained by six SQL triggers (INSERT/UPDATE/DELETE on both `conversations_fts`
and `messages_fts`, database.py:388-462), so the index does not go stale on normal writes (good).
Two real bugs: (a) when FTS5 succeeds but matches zero rows, search returns empty immediately without
the LIKE fallback (database.py:1355, 1566), so tokenization differences (`python` vs `pythonic`,
`C++`, `don't`) produce false "no results"; (b) `_prepare_fts_query` (database.py:495-522) does not
escape FTS5 special characters, so `C++` / `(test)` either error or match incorrectly. No tests cover
sync-after-update, sync-after-delete, the exception fallback, special characters, or the
FTS-unavailable path.

**PathModel.** Written on every save (delete-all then recompute via `get_all_paths()` then one JSON
row per root-to-leaf path, database.py:651-653, 728-742) but read only as `func.count(PathModel.id)`
for the optional `has_branches` filter (database.py:1693-1715). Its `message_ids_json` / `is_primary` /
`length` / `leaf_message_id` are never read anywhere; every real consumer calls in-memory
`get_all_paths()`. The dev DB stores ~4k path rows purely to back one COUNT.

---

## 3. Decisions taken with the user

1. **Migration mechanism: hand-rolled `PRAGMA user_version` runner.** SQLite is the only real
   target; the `postgresql://` branch is gated with a clear "migrations are SQLite-only" error rather
   than silently running SQLite-specific DDL. The dead `alembic` pin is removed from setup.py and
   requirements.txt.
2. **Metadata single source: columns authoritative.** The dedicated columns are the truth. The
   persistence blob carries only `custom_data`. Exporters keep the full dict.

Recommendations carried into the spec for confirmation at the review gate (not yet locked):

3. **PathModel: drop it; replace `has_branches` with a denormalized `is_branching` boolean column**
   maintained at save time (a single indexable bit, computed from `get_all_paths()` length > 1).
   Two-phase: stop writing/reading the table first, drop it in a later migration step.
4. **FTS5 zero-match fallback and special-char escaping are fixed** (not merely tested), because they
   are correctness bugs, not just coverage gaps.

---

## 4. Architecture and workstreams

The migration runner (W1) is the load-bearing first deliverable: the index additions (W3) and the
PathModel drop (W4) and the optional metadata blob cleanup (W2) all require schema changes that
`create_all` cannot perform, so they are expressed as migration steps and depend on W1 landing first.

### W1: Versioned migration runner (`ctk/core/migrations.py` + `database.py`)

A new module owns an ordered, append-only list of migration steps:

```python
# ctk/core/migrations.py
@dataclass(frozen=True)
class Migration:
    version: int          # target user_version after this step
    name: str
    apply: Callable[[Connection], None]   # idempotent-friendly DDL/backfill

MIGRATIONS: list[Migration] = [
    Migration(1, "baseline_slug_summary", _m1_slug_summary),
    Migration(2, "indexes_slug_keyset", _m2_indexes),
    Migration(3, "is_branching_column", _m3_is_branching),
    # ... future steps appended, never reordered or edited
]
```

`run_migrations(engine, lock)`:

- Reads `PRAGMA user_version`.
- For an existing DB at version 0 whose `conversations` table already has `slug` and `summary`,
  stamp it to the slug/summary baseline (legacy DBs created before versioning) so step 1 is a no-op.
  For a genuinely old DB missing the columns, step 1 runs the ALTER + backfill.
- Runs each pending step inside a transaction under the existing `migration_lock`
  (database.py:70-124), setting `user_version` after each step commits.
- On failure: roll back that step, log at ERROR, and raise a clear `MigrationError` that names the
  step and the underlying cause. The DB is left at the last successfully-committed version, never
  half-migrated.

`database.py:_init_schema` becomes: `create_all` (for brand-new DBs), then `run_migrations(...)`,
then `_setup_fts5`. Step 1 (`_m1_slug_summary`) is today's slug/summary ALTER + `_generate_missing_slugs`
backfill, plus `CREATE INDEX idx_conv_slug` (closing the perf gap). The `postgresql://` branch raises
`MigrationError("schema migrations are SQLite-only")` rather than running PRAGMA.

**Drift guard (test, not code):** build two DBs, one from a from-scratch `create_all`, one from an
old-schema fixture run through the migration runner, and assert their `conversations`/`messages`
column sets and indexes are identical. This is the mechanism that prevents the hand-rolled runner
from silently diverging from the ORM over time.

### W2: Metadata single source (columns authoritative)

- Add `ConversationMetadata.to_blob() -> dict` returning only `{custom_data: ...}` (and `version`/
  `format` only if a deliberate decision keeps them blob-authoritative; the recommendation is to keep
  their existing columns authoritative and drop them from the blob). Keep `to_dict()` full-fat for
  exporters and JSON/JSONL/HTML/markdown wire formats.
- `save_conversation` calls `to_blob()` at the persistence site (database.py:690) instead of
  `to_dict()`. The load override block (database.py:834-846) becomes the primary read, not an override.
- A migration step optionally strips the now-dead duplicated keys from existing `metadata_json` blobs
  (low priority; load already ignores them, so this is cosmetic for `ctk sql` inspection). Recommend
  shipping the strip as a backfill in the same step that is already touching rows, or skipping it and
  logging the stale keys as harmless.
- Regression test: `star_conversation(id)` then reload the tree and assert `metadata.starred_at` is
  set (the currently broken-but-masked path), and a column-vs-export round-trip test.

### W3: Listing/query perf

- **Indexes (migration step 2):** `idx_conv_slug`; a partial compound index matching the default
  exclude-archived listing, `CREATE INDEX idx_conv_list ON conversations(updated_at DESC, id) WHERE archived_at IS NULL`,
  plus, if offset mode keeps its `pinned_at DESC, updated_at DESC` ordering, an index leading with the
  filtered columns. (Index shape is tuned against `EXPLAIN QUERY PLAN` during implementation.)
- **Kill the list N+1:** stop routing `ConversationSummary` through `ConversationModel.to_dict()`.
  Build summaries from a query that selects the scalar columns plus a `GROUP BY` message count (the
  pattern `search_conversations` already uses, database.py:1581-1583) and `selectinload(ConversationModel.tags)`
  so tags batch-load in one extra query. Target: a 50-row page in ~2 queries.
- **Shared filter helper:** centralize the four duplicated filter blocks into one
  `_apply_conversation_filters(query, **filters)` used by list, search, and count, so they cannot drift.
- **Counting:** replace `len(list_conversations(limit=None))` in prompts.py with `count_conversations`.
- **Init-time flags:** cache `self._is_sqlite` and `self._has_fts` once in `__init__` instead of
  recomputing per query.

### W4: Retire PathModel

- Add `is_branching` (Boolean, indexed) to `ConversationModel`, set at save time from
  `len(tree.get_all_paths()) > 1`. Migration step 3 adds the column and backfills it.
- Replace the `has_branches` filter (database.py:1693-1715) with `ConversationModel.is_branching == True`.
- Stop writing `PathModel` rows in `save_conversation`. Drop the `paths` table in a later migration
  step (two-phase) once a release has shipped without writing it.

### W5: FTS5 correctness and tests

- **Zero-match fallback:** when FTS5 is available and returns zero ids, fall through to the LIKE path
  (set `fts_ids = None` and continue) instead of returning empty, so tokenization mismatches do not
  produce false "no results" (database.py:1355, 1566).
- **Escape special characters:** wrap a bare query containing FTS5 special characters
  (`* ( ) { } : + - "` and similar) in double quotes to force a phrase match, in a new
  `_escape_fts_query` used by `_prepare_fts_query`. Queries that already contain explicit FTS operators
  (AND/OR/NOT/NEAR) or quotes pass through unchanged.
- **Cache availability:** use the `self._has_fts` flag from W3 instead of opening a connection per search.
- **Tests:** sync-after-title-update, sync-after-message-delete, sync-after-conversation-delete,
  the FTS-raises -> LIKE fallback path, special-character queries (`C++`, `(test)`, `don't`), and (if
  feasible to simulate) the FTS-unavailable -> LIKE path.
- **Optional:** a `ctk db rebuild-fts` maintenance command (drop + repopulate the FTS tables) for
  corruption recovery. Low priority; include only if cheap.

---

## 5. Out of scope (deferred)

- **E-scale** (chunked top-k, persisted TF-IDF vocabulary, optional ANN index, context-window
  management, retry/backoff). E-core is correctness and the highest-impact read-path fixes only.
- PostgreSQL as a first-class backend. The migration runner is SQLite-only by decision; the PG branch
  raises a clear error.
- Streaming/generator rewrites of the exporters (the export N+1 is noted but a batched
  `load_conversations(ids)` is left to E-scale unless it falls out cheaply).

---

## 6. Testing

- **Migration runner:** old-schema fixture (no slug/summary, user_version 0) upgrades in place and a
  save round-trips; a deliberately-failing step aborts loudly and leaves user_version at the last good
  step; the drift-guard test (fresh `create_all` == migrated old).
- **Metadata:** star/pin/archive then reload reflects the flag; column-vs-export round-trip; external
  SQL write to a column is read back correctly.
- **Perf:** a query-count assertion on `list_conversations` (using a SQLAlchemy statement counter)
  proving a page is bounded, not N+1; `EXPLAIN QUERY PLAN` assertions that slug lookup and the listing
  sort use the new indexes.
- **FTS5:** the six cases in W5.
- **PathModel:** `is_branching` is correct for linear and branched trees; `has_branches` filter returns
  the same set it did before the change.

---

## 7. Release

Ships as the next minor version after merge (2.18.0), user-gated as usual. The migration runner makes
this a schema-touching release: the release notes must state that opening an existing DB performs an
in-place, locked, versioned upgrade, and that the upgrade is logged.

---

## 8. Definition-of-done checklist

- [ ] `ctk/core/migrations.py`: `Migration` type, ordered `MIGRATIONS`, `run_migrations` under the lock,
      loud failure, SQLite-only guard. `_init_schema` wired to it. `alembic` pin removed.
- [ ] Drift-guard test (fresh vs migrated schema identical) and old-schema-upgrade test.
- [ ] `to_blob()` split; save writes overflow only; load reads columns; star/pin/archive round-trip test.
- [ ] `idx_conv_slug` + keyset index via migration; slug + listing `EXPLAIN` assertions.
- [ ] List N+1 removed (selectinload tags + GROUP BY count, no `to_dict()` route); query-count test.
- [ ] `_apply_conversation_filters` helper shared by list/search/count; `count_conversations` swaps.
- [ ] FTS5 zero-match fallback + special-char escaping + cached availability; the six FTS tests.
- [ ] `is_branching` column maintained at save; `has_branches` served by it; `PathModel` writes removed.
- [ ] Suite green: mypy 0, coverage at or above 59, unit + integration pass.
