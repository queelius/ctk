# CTK Feature Roadmap Design

**Date**: 2026-02-14
**Status**: Approved

## Goals

1. **Performance**: Future-proof DB queries for 100k+ conversations
2. **Exports**: Add CSV format, harden existing 6 exporters
3. **Imports**: Harden existing 6 importers, plan new provider support
4. **REST API**: Batch ops, embedding/similarity endpoints, cursor pagination
5. **Continue plan phases**: 4 (constants), 6 (nesting), 7 (docs), 5 (light TUI refactor), 8 (integration tests)

## Constraints

- TDD-guided: write failing tests first, then implement
- Interleaved sprints: alternate quality phases and new features
- Phase 5 (TUI split): light refactor only, not full modularization
- New importers: plan/research only, don't build without real export samples

## Sprint Plan

### Sprint 1: Quick Foundations
- **Phase 4**: Create `ctk/core/constants.py`, replace hardcoded timeouts/limits
- **Phase 6**: Extract multimodal content parsing helpers in OpenAI importer
- **Phase 7**: Update CLAUDE.md and MEMORY.md with all patterns learned

### Sprint 2: Export Hardening + CSV
- **Harden exporters**: Edge case tests for all 6 formats (JSONL, JSON, Markdown, HTML, Hugo, ECHO)
- **CSV exporter**: New `ctk/integrations/exporters/csv.py`
  - Columns: id, title, source, model, created_at, updated_at, message_count, tags, starred, pinned, archived
  - Option for message-level rows (one row per message with conv_id, role, content, timestamp)
  - Path selection for branching conversations
  - TSV variant via delimiter option

### Sprint 3: Import Hardening + Planning
- **Harden importers**: Test with malformed data, missing fields, encoding issues
- **Fixture data**: Create test fixtures for each provider format
- **Research**: Document export formats for DeepSeek, Mistral, Perplexity, xAI/Grok
- **Import validation**: Improve error messages for format detection failures

### Sprint 4: Performance
- **Cursor pagination**: Keyset pagination (WHERE id > last_seen ORDER BY id LIMIT n)
  - Add to ConversationDB query methods
  - Backward-compatible: offset/limit still works
- **Streaming results**: Generator-based query results for large exports
- **Combined count+data**: Use SQL window functions or separate optimized count path
- **Memory**: Lazy loading of message content for list operations

### Sprint 5: REST API Enhancements
- **Batch operations**: POST /api/batch with action + list of IDs
  - Actions: star, unstar, pin, unpin, archive, unarchive, delete, tag, untag
- **Embedding endpoints**: GET /api/conversations/<id>/similar, POST /api/search/semantic
- **Cursor pagination**: cursor parameter in list/search endpoints
  - Response includes next_cursor field

### Sprint 6: TUI Light Refactor
- Extract command dispatch logic from main class
- Extract LLM streaming/chat logic into separate module
- Keep main ChatTUI class as orchestrator
- Target: reduce tui.py from 6,254 lines to ~3,000

### Sprint 7: Integration & Verification
- Fix 9 known-failing integration tests (old CLI command names)
- End-to-end import/export round-trip tests
- Coverage validation above 59% threshold
- Performance benchmarks for large databases

## Architecture Decisions

### CSV Exporter
- Implement as ExporterPlugin subclass
- Two modes: conversation-level (summary rows) and message-level (content rows)
- Use Python csv module (not pandas) to avoid dependency
- Sanitize content for CSV safety (strip newlines, escape quotes)

### Cursor Pagination
- Keyset pagination using (created_at, id) composite cursor
- Base64-encode cursor for opaque API tokens
- Fallback to offset/limit for backward compatibility
- Apply to both DB layer and REST API

### Batch Operations
- Single endpoint with action discriminator
- Atomic: all-or-nothing per batch
- Return per-item results for partial failure visibility
- Rate limit: max 100 items per batch

### Import Hardening
- Add `validate_strict()` method to ImporterPlugin base
- Test each importer with: empty data, missing fields, wrong types, huge messages
- Improve error reporting: which field failed, expected vs actual

## Testing Strategy

All work follows TDD:
1. Write test file with failing tests
2. Implement to make tests pass
3. Refactor with safety net
4. Coverage check after each sprint
