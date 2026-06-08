# CTK Improvement Program: Roadmap

**Date:** 2026-06-04
**Status:** Approved (sequencing and trajectory); sub-project specs to follow
**Trajectory decision:** *Reinvest and grow*. CTK is treated as an actively-developed flagship, not a maintenance-mode project heading to archival.

---

## Why this document exists

A multi-agent scan of the whole codebase (7 subsystem readers plus synthesis, then a 6-cluster
verification pass confirming every load-bearing claim with line-precise evidence) surfaced six
coherent improvement themes. The user chose to pursue all of them, in an appropriate order.
That is a program, not a single project, so each theme becomes its own sub-project with its own
`design` and `implementation` doc pair (matching the existing `docs/plans/` convention).

This document records the decomposition and the sequence, and the dependency reasoning
behind that sequence. It does not contain the detailed designs. Those live in the per-sub-project
specs listed below.

### A note that must be retired

`docs/plans/2026-03-03-mcp-consolidation-design.md` contains the line *"CTK is in maintenance mode
heading toward archival (memex is the successor)."* The trajectory decision above supersedes that.
When sub-project F (docs) runs, that note must be updated or removed so the project's stated
direction is internally consistent.

---

## The six sub-projects

| ID | Name | Core intent | Effort |
|----|------|-------------|--------|
| **A** | Correctness foundation and green CI | Kill shipped silent-failures, make every CI gate green and honest | Medium |
| **B** | Round-trip fidelity | Fix silent data loss in the one job CTK exists to do | Medium |
| **C** | Unify the tool surface | One `ToolProvider` registry feeding TUI, MCP server, and external MCP servers | High |
| **D** | TUI as a real chat client | Interruptibility, edit/regenerate, streaming-with-tools, responsiveness | Medium to High |
| **E** | DB foundations and scale | Versioned migrations, FTS5 tests, single-source metadata, perf/scale | High |
| **F** | Trustworthy docs and onboarding | Regenerate the stale doc site, fix examples, add a staleness guard | Low to Medium |
| **G** | Repo-wide lint sweep (black + flake8) | Bring the whole repo to a green lint job: black-format every file and flake8-clean the remaining pre-existing issues | Low (mechanical) |

Sub-project G was discovered during sub-project A's execution: the CI lint job runs
`black --check`, `flake8`, and `mypy`, and on `master` it was already red on both black
(76 files needing reformat) and flake8 (432 issues), a pre-existing debt the original plan
did not scope. Sub-project A black-formatted and flake8-cleaned only the files it touched
(so it adds no debt and reaches mypy 0); G is the standalone, mostly-mechanical follow-up that
brings the remaining files to green so the lint job passes repo-wide. G is independent and can
run any time after A.

Two themes are split so foundational parts run early and scale/regeneration parts run late:

- **E-core** (versioned migrations, FTS5 tests, metadata single-source, N+1/PathModel perf) runs
  before the big feature refactors. **E-scale** (chunked top-k, persisted TF-IDF vocab, optional ANN
  index, context-window management, retry/backoff) runs after features land.
- **F-quick** (broken headline example, missing `requirements.txt` deps, CSV quoting, stderr,
  `--version`, a CLI-staleness guard) is folded into **A** as cheap correctness wins. **F-full**
  (mkdocs regeneration, CHANGELOG, examples rewrite) runs last, against the final surface.

---

## The sequence (and why)

```
1. A . Correctness foundation and green CI    (launchpad: nothing else is safe to refactor on red CI)
2. B . Round-trip fidelity                    (core value prop; its fidelity-matrix test guards later work)
3. E-core . DB foundations                    (storage correctness before schema-touching feature work)
4. C . Unify the tool surface                 (marquee architectural bet, now on solid ground)
5. D . TUI as a real chat client              (highest user-visible payoff; benefits from C and E-core)
6. E-scale . Search/similarity scaling        (scale once correctness and features are in)
7. F-full . Docs/onboarding regeneration      (last, so docs describe the final surface)
```

**Dependency rationale**

- **A first** because every other sub-project is a refactor, and a green CI signal is the safety net
  that makes refactoring safe. A also fixes the `execute_ask_tool` silent-failure that undermines the
  LLM tool path C will later rebuild. A is the band-aid, C is the cure.
- **B second** because fidelity is CTK's reason to exist, and the fidelity-matrix test B introduces
  becomes a regression guard for every subsequent refactor (C, D, and E all touch save/load paths).
- **E-core third** because versioned migrations and the metadata single-source must exist before
  any feature refactor changes the schema. Doing it after would mean retrofitting migrations.
- **C fourth**, the highest-impact architectural change (collapse the parallel tool surfaces),
  deliberately placed after the foundation is sound and the fidelity guard exists.
- **D fifth** because the richest TUI affordances benefit from C's unified tools and E-core's perf.
- **E-scale sixth**, since scale work is only worth doing once the data model and features are stable.
- **F-full last**, because regenerating docs before C, D, and E reshape the surface just means doing
  it twice.

---

## Per-sub-project specs

Each sub-project gets a `design` doc (and later an `implementation` doc) under `docs/plans/`:

| ID | Design doc |
|----|------------|
| A | `2026-06-04-correctness-foundation-design.md` (written) |
| B | `YYYY-MM-DD-round-trip-fidelity-design.md` (TBD) |
| E-core | `YYYY-MM-DD-db-foundations-design.md` (TBD) |
| C | `YYYY-MM-DD-unified-tool-surface-design.md` (TBD) |
| D | `YYYY-MM-DD-tui-chat-client-design.md` (TBD) |
| E-scale | `YYYY-MM-DD-search-scaling-design.md` (TBD) |
| F-full | `YYYY-MM-DD-docs-regeneration-design.md` (TBD) |
| G | (mechanical; no design doc needed: run `make format` repo-wide, then a flake8 sweep) |

Each sub-project runs its own brainstorm, spec, writing-plans, implement, and review cycle. We are
currently at sub-project A.

---

## Cross-cutting principles (apply to every sub-project)

These come from the project's stated working style (`CLAUDE.md`) and recur across the findings:

1. **Derive behavior from structure.** No substring-matching of structured data, no parallel lookup
   tables, no stringly-typed interfaces. Several findings (agent-detector substring match,
   stringly-typed `_toggle_flag`, hand-maintained parallel tool surfaces, doc tables maintained by
   hand) violate this principle. Fixes should remove the violation, not paper over it.
2. **One source of truth.** Where the same fact lives in two places (metadata columns vs JSON blob,
   `requirements.txt` vs `setup.py`, TUI tools vs MCP tools, doc CLI table vs argparse registry),
   collapse to one and derive the rest.
3. **Tests before trust.** Every bug fixed in this program lands with a regression test, and every
   gate (coverage, mypy, build) must end green and honest. A permanently-red required check trains
   everyone to ignore CI, which is how this debt accumulated.
4. **Verify before asserting.** The findings driving this program were adversarially verified against
   the real code with line-precise evidence. The same discipline applies to claiming any fix works.
