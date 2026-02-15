# CTK Code Quality & Feature Plan

## Completed Phases

### Phase 1: Input Validation & Security (P0) - DONE
- Created `ctk/core/input_validation.py` with validation utilities
- Added validation to `cmd_import`, `cmd_export`, `cmd_show` in CLI
- Changed JSONL exporter sanitize default from `False` to `True`
- MCP server confirmed async-only (no thread safety issue)
- Implemented `allow_partial` (UUID format enforcement) and `allow_relative` (absolute path requirement)

### Phase 2: Fix Bare Except Clauses (P0) - DONE
- Replaced 30 bare `except:` clauses with specific exceptions across 15 files
- Categories: LLM providers, importers, taggers, TUI
- Exception patterns: RequestException for network, ValueError for parsing, Exception for cleanup
- Fixed regression in OpenAI `is_available()` test (mock needed specific exception type)

### Phase 3: Extract Code Duplication (P1) - DONE
- Created `ctk/core/utils.py` with `parse_timestamp()` and `try_parse_json()`
- Refactored 4 importers (openai, gemini, anthropic, filesystem_coding)
- Eliminated ~77 lines of duplicate timestamp parsing code
- Removed dead `_try_parse_json()` from `ImporterPlugin` base class

### Phase 4: Centralize Magic Numbers (P2) - DONE
- Created `ctk/core/constants.py` with 18 constants (timeouts, limits, display)
- Replaced hardcoded values in 7 files: 5 LLM providers, database.py, mcp_server.py
- 18 tests in `tests/unit/test_constants.py`

### Phase 6: Reduce Nesting in OpenAI Importer (P3) - DONE
- Extracted 4 helper methods: `_process_part`, `_process_asset_pointer`, `_process_image_url`, `_process_tool_calls`
- Reduced nesting from 7 levels to 2-3 levels
- 35 tests in `tests/unit/test_openai_importer.py` (TDD: tests written first)

### Phase 7: Update Documentation (P3) - DONE
- Updated CLAUDE.md with exception handling, constants, and utilities patterns
- Updated MEMORY.md and PLAN.md

### Hugo Export Enhancement - DONE
- Added `--hugo-organize` CLI option (none, tags, source, date)
- Added `_get_target_dir()` method to HugoExporter
- Added empty directory name fallback for special-char tags/sources

### Code Review & Testing - DONE
- 10 code review findings addressed (dead loop, type annotations, unused imports, etc.)
- Created `tests/unit/test_input_validation.py` (83 tests, 98% coverage)
- Created `tests/unit/test_utils.py` (29 tests)
- Created `tests/unit/test_hugo_exporter.py` (45 tests, 74% coverage)
- Total: 1349 unit tests pass (up from 782), 1 pre-existing failure

---

## Remaining Phases

### Phase 5: Split TUI Module (P2) - LIGHT REFACTOR
- Extract command dispatch and heaviest sections from 6,254-line `tui.py`
- Light refactor only, not full modularization
- Deferred to Sprint 6

### Phase 8: Integration Testing & Verification (P1)
- Fix 9 known-failing integration tests (old CLI command names)
- End-to-end import/export round-trip tests
- Coverage validation

---

## Feature Roadmap (Approved 2026-02-14)

See `docs/plans/2026-02-14-feature-roadmap-design.md` for full design.

### Sprint 2: Export Hardening + CSV
- Harden existing 6 exporters (edge cases, error handling, test coverage)
- Add CSV exporter (conversation-level + message-level modes)

### Sprint 3: Import Hardening + Planning
- Harden existing 6 importers (malformed data, missing fields, encoding)
- Research/plan importers for DeepSeek, Mistral, Perplexity, xAI/Grok

### Sprint 4: Performance
- Cursor-based pagination (keyset pagination)
- Streaming results for large exports
- Query optimization (combined count+data)

### Sprint 5: REST API Enhancements
- Batch operations (star/pin/archive/delete multiple)
- Embedding/similarity endpoints
- Cursor pagination in API

### Sprint 6: TUI Light Refactor
- Extract command dispatch from main ChatTUI class
- Extract LLM streaming/chat into separate module

### Sprint 7: Integration & Verification
- Fix 9 known-failing integration tests
- End-to-end round-trip tests
- Coverage push above 59%

---

## Known Issues
- Integration tests use old CLI command names (known-failing)
- Coverage threshold at 59% but actual is ~37% for unit-only
- Plugin security validation needs improvement
- Performance optimization for large databases (>100k conversations)
