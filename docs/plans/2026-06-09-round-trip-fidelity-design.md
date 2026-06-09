# Sub-project B: Round-Trip Fidelity (Design)

**Date:** 2026-06-09
**Status:** Design (pending spec review)
**Part of:** [CTK Improvement Program](2026-06-04-improvement-program-roadmap.md), sub-project 2 of 7
**Decisions taken with user:** reasoning is captured as a structured `ReasoningBlock` field;
JSONL idempotency comes from deterministic content-derived ids.

---

## 1. Goal and definition of done

CTK's reason to exist is faithful conversation archival. This sub-project makes import and
round-trip lossless for the things users actually export today: branch structure, tool calls,
reasoning/thinking content, and the canonical ctk format itself. Every fix lands with a
regression test, and a fidelity-matrix test locks the whole contract for later refactors.

**Definition of done (all must hold):**

1. Importing the current (June 2026) Claude export preserves the real message tree
   (regenerate/edit branches), not a flattened chain.
2. Tool calls, tool results, and thinking/reasoning blocks survive Anthropic and OpenAI
   imports as structured data; nothing is silently skipped because top-level text exists.
3. The canonical ctk JSON export re-imports via auto-detect into an equal tree (true inverse).
4. `ctk import file.zip` works for Claude and ChatGPT export archives directly.
5. Re-importing the same JSONL file is idempotent (no duplicates).
6. A fidelity-matrix test (rich fixture across ctk-JSON round-trip and DB save/load) passes
   and guards all of the above.
7. Suite stays green: mypy 0, coverage at or above 59, all unit and integration tests pass.

---

## 2. Verified findings (all empirically grounded on real exports in `dev/`)

| # | Finding | Verdict |
|---|---------|---------|
| F1 | New Claude export carries `parent_message_uuid` on every message; the importer ignores it and chains messages by iteration order. A real 70-message conversation with 4 true paths imports as 1 linear path: branches lost. | Confirmed |
| F2 | Anthropic importer takes the `if "text" in msg_data` branch whenever top-level text exists (it always does in real exports) and never reads `content` blocks: `tool_use`, `tool_result`, and `token_budget` blocks are dropped (2 of 2 tool messages in the new sample lose their tool calls). | Confirmed |
| F3 | Old-format Claude thinking is NOT lost: Anthropic bakes thinking into the top-level `text`, so it survives inline. (Corrects the original scan claim.) | Refuted |
| F4 | OpenAI `thoughts` and `reasoning_recap` parts are dropped entirely (fixture proof: reasoning text appears nowhere after import). The user's real 211 MB export contains 1,987 `thoughts` and 1,264 `reasoning_recap` parts. | Confirmed |
| F5 | The canonical ctk JSON export cannot be re-imported: auto-detect routes the envelope to the gemini importer (not JSONL as originally scanned), which raises `AttributeError`. | Confirmed, corrected |
| F6 | JSONL re-import duplicates every conversation (fresh uuid per run): double-import goes 1 to 2. Claude/OpenAI re-imports are id-stable (upsert): 5 stays 5. | Confirmed |
| F7 | Claude zip layout: `conversations.json`, `users.json`, `memories.json`, `projects/*.json` at the root. ChatGPT zips: `conversations.json` plus media directories. | Confirmed |
| F8 | `MessageContent.parts` and `.metadata` already serialize through `to_dict`/`from_dict`, so no schema work is needed for them. JSONL export is single-path by design (lossy); ctk JSON is the lossless format (full `message_map` + `root_message_ids`). | Confirmed |

---

## 3. Workstreams

### W1: Anthropic importer, tree and content rebuild

**Tree (F1).** When messages carry `parent_message_uuid`, build the tree from it:
the all-zeros sentinel (`00000000-0000-4000-8000-000000000000`) and any uuid not present in
the message set map to root (`parent_id=None`); otherwise `parent_id=parent_message_uuid`.
Messages keep their export uuids as ids (unchanged), so re-importing a new export over an old
flattened import upserts the same conversation and repairs its tree. When the field is absent
(old exports), keep the existing linear chaining. Child ordering within a branch point is
already handled by `get_children`'s timestamp sort.

**Content (F2).** Replace the either/or branch with a unified pass:

- `content.text` = top-level `text` when present and non-empty, else the joined `text` blocks
  (no double-text: top-level text already includes the text blocks' content in real exports).
- Always iterate `content` blocks when present, regardless of top-level text:
  `tool_use`/`tool_result` to `ToolCall` (existing logic), `thinking`/`redacted_thinking` to
  `ReasoningBlock`, `token_budget` to `content.metadata["token_budget"]`, unknown types to
  the existing metadata sweep.
- Attachments handling is unchanged.
- Known redundancy, accepted: old-format messages whose top-level text already embeds the
  thinking (F3) will carry it both inline and as a `ReasoningBlock`. That is duplication,
  not loss; the export's own text rendering stays verbatim, and deduplicating by substring
  matching would be exactly the stringly heuristic this project avoids.

### W2: OpenAI reasoning capture (F4)

Handle two message-level content types the importer currently returns nothing for:

- `content_type == "thoughts"`: each entry in `thoughts` (shape:
  `{"summary", "content", "chunks", "finished"}`) becomes
  `ReasoningBlock(text=entry["content"], summary=entry["summary"])`.
- `content_type == "reasoning_recap"`: becomes a `ReasoningBlock(text=content_value)`.

The existing metadata note of the part's content_type stays. No change to how the visible
assistant text is derived.

### W3: `ReasoningBlock` data model

In `ctk/core/models.py`:

```python
@dataclass
class ReasoningBlock:
    text: str = ""
    summary: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)  # provider-specific (signatures, budgets)
```

- `MessageContent.reasoning: List[ReasoningBlock]` (default empty), serialized in
  `to_dict`/`from_dict` exactly like media lists; additive and backward compatible (old DB
  rows simply load with empty reasoning).
- `MessageContent.get_reasoning_text()` helper joining block texts (summaries as headers).
- Markdown exporter: when a message has reasoning, emit a clearly marked blockquoted
  "Reasoning" section before the message body. JSON ctk format gets it automatically via
  `to_dict`. HTML exporter and TUI rendering are deferred (sub-projects D/F).

### W4: CTK importer, the canonical inverse (F5)

New `ctk/importers/ctk.py` (`CTKImporter`):

- `validate()` is high-specificity: a dict with `format == "ctk"` and a `conversations` list
  (plus a structural fallback: conversation entries carrying `root_message_ids` and a
  `messages` mapping).
- `import_data()` reconstructs each conversation via `Message.from_dict` /
  `ConversationMetadata.from_dict` into a `ConversationTree`, preserving ids, tree shape,
  media, tool calls, and reasoning.
- Auto-detect MUST route ctk envelopes here: register the importer and make detection order
  deterministic (check CTK's validate before the greedy gemini/jsonl validators, or tighten
  those validators to reject `format == "ctk"` dicts; the plan pins the mechanism after
  reading `registry.auto_detect_importer`). A regression test asserts
  `auto_detect_importer(ctk_export)` selects `ctk`.

### W5: Zip import (F7)

`ctk import <file>.zip` (and auto-detect by suffix in `cmd_import`), without full extraction:

- Read `conversations.json` (root or single top-level directory) directly from the archive
  in memory via `zipfile`; no extraction at all for media-free archives (Claude zips).
- When the archive also contains media members (ChatGPT zips), extract only those members to
  a temp directory with safe member handling (reject absolute paths and `..` traversal), set
  `source_dir` to it so image resolution keeps working, and clean it up afterward (imported
  media is copied into the DB's `media/` directory during import, so the temp copy is
  transient).
- The live database stays uncompressed by design (SQLite needs random access); with this in
  place users never need to keep unpacked exports on disk.
- Claude zips' `users.json`, `memories.json`, and `projects/` are ignored for now (noted as a
  future capability, out of scope here).

### W6: Deterministic JSONL ids (F6)

The JSONL importer derives the conversation id from a content hash instead of a random uuid:
`jsonl-<sha256 over the canonical (role, text) sequence, truncated>`. Re-importing the same
file then upserts naturally, matching provider-export behavior. Import timestamps and other
volatile fields stay out of the hash. Caveat documented in the importer docstring: rows
imported before this change keep their random ids, so one historical duplicate can remain
(cleanable via `ctk db dedupe`).

### W7: Fidelity-matrix test

One rich fixture: a branched tree (a message with multiple children) whose messages carry
text, images, audio, video, documents, tool calls (with results), reasoning blocks, and
metadata. Asserted equal (tree shape, roles, ids, text, media counts, tool calls, reasoning)
across:

1. ctk JSON export, then auto-detected re-import (W4 inverse).
2. DB `save_conversation` then `load_conversation`.

Plus per-workstream regression tests: an Anthropic new-format branched fixture (derived from
the real export's shapes), the OpenAI thoughts fixture, double-import idempotency for JSONL
and Anthropic, and a constructed zip import (including a traversal-attempt member that must
be rejected).

---

## 4. Out of scope

- TUI rendering of reasoning and tool panels for imported content (sub-project D).
- HTML exporter reasoning display and doc-site updates (sub-projects D/F).
- Importing Claude `memories.json` / `projects/` or `users.json` (future feature; noted).
- Retroactive migration of existing DB rows (old flattened Claude imports are repaired by
  simply re-importing the new export, which upserts by uuid).
- Coding-agent importer stubs honesty (rides with sub-project F).

---

## 5. Testing strategy

TDD per workstream (failing test first, from the real shapes captured in this design's
verification), the fidelity matrix as the capstone, and the usual gates: full unit suite plus
integration green, mypy 0, coverage at or above 59, black/flake8 clean on touched files.

---

## 6. Release

On completion, B ships as **2.16.0** (new data model field plus features), following the
2.15.1 release process. The release step is gated on an explicit user go-ahead.

---

## 7. Definition-of-done checklist

- [ ] Anthropic importer builds the tree from `parent_message_uuid` (sentinel-aware,
      dangling-safe, linear fallback); real branched conversation imports with all paths.
- [ ] Anthropic importer processes content blocks alongside top-level text: tool calls,
      reasoning, token_budget captured; unknown types still swept to metadata.
- [ ] OpenAI importer captures `thoughts` and `reasoning_recap` as `ReasoningBlock`s.
- [ ] `ReasoningBlock` + `MessageContent.reasoning` round-trip `to_dict`/`from_dict` and DB
      save/load; markdown exporter renders a reasoning section.
- [ ] `CTKImporter` registered; auto-detect selects it for ctk envelopes; export-then-import
      reproduces an equal tree.
- [ ] `ctk import <archive>.zip` works for Claude and ChatGPT zips with safe extraction.
- [ ] JSONL ids are content-derived; double-import test shows no duplicates.
- [ ] Fidelity-matrix test passes; all gates green (mypy 0, coverage >= 59, suite green).
