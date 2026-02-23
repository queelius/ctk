# Semantic Search: MCP Server Redesign + TUI Integration

**Date**: 2026-02-23
**Status**: Approved
**Scope**: Wire existing similarity engine into MCP server and TUI, add unit tests

## Context

CTK has a working semantic search engine (`ctk/core/similarity.py`) with two embedding providers (TF-IDF, Ollama), similarity computation (4 metrics), graph building, and community detection. However, it's only accessible via the Python API and `ctk net` CLI commands. The MCP server, TUI shell, and REST API don't expose it.

This sprint wires the existing engine into MCP and TUI, redesigns the MCP server architecture for maintainability, and adds comprehensive unit tests for the similarity module (currently untested).

**Deferred**: Vector index optimization (sqlite-vec/hnswlib for O(log n) queries), REST API integration.

## Part 1: MCP Server Redesign

### Architecture

Split the monolithic `mcp_server.py` (891 lines) into modular handlers in `ctk/interfaces/mcp/`:

```
ctk/mcp_server.py                    → thin entry point (preserved for backward compat)
ctk/interfaces/mcp/
├── __init__.py
├── server.py                         → Server class, tool registration, main()
├── validation.py                     → Shared validation helpers (extracted)
├── handlers/
│   ├── __init__.py
│   ├── search.py                     → search_conversations, list_conversations
│   ├── conversation.py               → get_conversation, star, pin, archive, title
│   ├── analysis.py                   → find_similar, semantic_search, get_network_summary, get_clusters
│   └── metadata.py                   → get_statistics, get_tags
```

`ctk/mcp_server.py` becomes a thin entry point that imports from `ctk/interfaces/mcp/server.py`.

### New MCP Tools (analysis.py)

| Tool | Description | Key Inputs |
|------|-------------|------------|
| `find_similar` | Find conversations similar to a given one | `id`, `top_k=10`, `threshold=0.3`, `provider="tfidf"` |
| `semantic_search` | Search by meaning (embed query text, find similar) | `query`, `top_k=10`, `provider="tfidf"` |
| `get_network_summary` | Graph stats: density, clusters, central nodes | `threshold=0.3` |
| `get_clusters` | Community detection with conversation titles | `algorithm="label_propagation"` |

### Existing Tools (kept, descriptions improved)

`search_conversations`, `list_conversations`, `get_conversation`, `get_statistics`, `star_conversation`, `pin_conversation`, `archive_conversation`, `set_title`, `get_tags`

### Migration

- `python -m ctk.mcp_server` still works (entry point preserved)
- No breaking changes to existing tool names or schemas
- Existing MCP configs keep working

## Part 2: TUI Shell Commands

### New Command Module: `ctk/core/commands/semantic.py`

Registered via `create_semantic_commands(db, navigator, tui_instance)`, same pattern as all other command modules.

| Command | Usage | Description |
|---------|-------|-------------|
| `semantic search "query"` | Text → embed → find similar | Semantic search by meaning |
| `semantic similar <id>` | Find similar to a conversation | Uses cached embeddings |
| `semantic similar .` | Similar to current conversation | VFS context-aware |
| `index build` | Generate embeddings | `--provider tfidf`, `--limit 100` |
| `index status` | Show embedding coverage | Count, provider, dimensions |
| `index clear` | Remove cached embeddings | `--provider tfidf` |

### Behavior

- `semantic search` and `semantic similar` auto-trigger `index build` if no embeddings exist (with confirmation)
- Results as table: rank, similarity score, ID prefix, title
- Pipe-compatible: `semantic similar abc123 | head 5`
- Default provider: `tfidf` (offline, no external deps beyond scikit-learn)

## Part 3: Unit Tests

### New Test Files

| File | Tests | Approach |
|------|-------|----------|
| `test_similarity.py` | `ConversationEmbedder`, `SimilarityComputer`, `ConversationGraphBuilder` | Mock `EmbeddingProvider` with deterministic vectors |
| `test_embedding_base.py` | `EmbeddingProvider` base, `aggregate_embeddings()` | All 6 aggregation strategies with known vectors |
| `test_mcp_analysis.py` | New MCP analysis handler tools | Mock database |
| `test_semantic_commands.py` | TUI `semantic` and `index` commands | Mock db/navigator, verify CommandResult |

### Testing Strategy

- `MockEmbeddingProvider` returns deterministic vectors (hash-based) for reproducibility
- Edge cases: empty conversations, single-message, tool-only messages
- Caching: verify embeddings saved/loaded from DB
- Graph: known vectors → known similarity matrix → expected edges
- Estimated ~80-100 new tests across 4 files
