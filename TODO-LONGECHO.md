# ctk — longecho Integration TODO

This document outlines features needed in ctk to support the [longecho](../longecho) personal archive ecosystem.

---

## Design Insight: Raw Conversations ARE the Persona

Per the [design interview](../longecho/spec/INTERVIEW-INSIGHTS.md), explicit persona extraction is **optional for MVP**. The raw conversations themselves are sufficient — future LLMs can work with them directly via RAG.

This dramatically simplifies the critical path:
1. **Export conversations** (JSON tree + readable markdown)
2. Trust future systems to handle persona inference

Everything else is enhancement.

---

## Priority: CRITICAL

### 1. Export to Durable Format

**THE MVP.** Get conversations out of ctk into durable, self-describing format.

**Command:**
```bash
ctk export longecho --db ~/chats.db --output ~/export/
```

**Output structure:**
```
export/
├── README.txt                    # What this is, how to read it
├── conversations/
│   ├── conv-uuid-1/
│   │   ├── README.txt            # Auto-generated: title, date, summary
│   │   ├── conversation.json     # Full tree structure
│   │   ├── conversation.md       # Human-readable (latest path)
│   │   └── metadata.json         # Provider, model, dates, stats
│   └── conv-uuid-2/
│       └── ...
├── index.json                    # List of all conversations
└── chats.db                      # Original SQLite (if reasonable size)
```

**conversation.json format:**
```json
{
  "id": "conv-uuid",
  "title": "Conversation about X",
  "created": "2024-01-15T10:30:00Z",
  "modified": "2024-01-16T14:00:00Z",
  "provider": "anthropic",
  "model": "claude-3",
  "tree": {
    "role": "user",
    "content": "...",
    "children": [
      {
        "role": "assistant",
        "content": "...",
        "children": [...]
      }
    ]
  }
}
```

**Key decisions:**
- JSON is primary (preserves full tree)
- Markdown is secondary (human-readable, latest path only)
- Include SQLite database if not too large
- Your messages are persona; assistant responses are context

**Priority:** CRITICAL — This is the entire MVP

---

## Priority: HIGH (Enhancement)

### 2. Embeddings for All Messages

Generate vector embeddings for semantic search across conversations.

**Command:**
```bash
ctk embeddings generate --db ~/chats.db
ctk embeddings status --db ~/chats.db
```

**Implementation:**
- Use sentence-transformers (all-MiniLM-L6-v2 or similar)
- Store in database (blob column) or separate FAISS index
- Incremental updates (only embed new messages)

**Priority:** HIGH — Enables semantic search and RAG for ghost mode

---

### 3. Cross-Reference Detection

Detect when conversations reference external entities.

**Detect:**
- Book mentions → link to ebk
- URL mentions → link to btk
- Project mentions → link to repoindex
- People mentions → extract for relationship graph

**Command:**
```bash
ctk crossref detect --db ~/chats.db
ctk crossref show conv-id
```

**Priority:** HIGH — Enables longecho synthesis

---

### 6. Voice Analysis

Deeper analysis of communication patterns for persona calibration.

**Analyze:**
- How you explain concepts
- How you ask questions
- How you express disagreement
- How you show enthusiasm
- How you handle being wrong

**Output:** Detailed voice profile for ghost calibration

**Priority:** HIGH — Improves ghost quality

---

## Priority: MEDIUM

### 7. Conversation Summarization

Generate summaries for conversations.

**Command:**
```bash
ctk summarize conv-id --db ~/chats.db
ctk summarize --all --db ~/chats.db
```

**Priority:** MEDIUM — Useful for browsing and longecho

---

### 8. Topic Clustering

Automatically cluster conversations by topic.

**Command:**
```bash
ctk topics --db ~/chats.db
ctk topics show topic-id
```

**Priority:** MEDIUM — Better organization

---

### 9. Timeline View

Chronological view of conversation activity.

**Command:**
```bash
ctk timeline --db ~/chats.db
ctk timeline 2024 --db ~/chats.db
```

**Priority:** MEDIUM — Useful for longecho synthesis

---

### 10. Export to Note Apps

Export significant conversations as notes for Logseq/Obsidian.

**Command:**
```bash
ctk export logseq --db ~/chats.db --output ~/logseq-graph/pages/
ctk export obsidian --db ~/chats.db --output ~/obsidian-vault/
```

**What to export:**
- Starred conversations
- Conversations with insights
- Technical explanations
- Decision discussions

**Priority:** MEDIUM — Bootstrap notes from conversations

---

## Priority: LOWER

### 11. Fine-tuning Data Export

Export in formats suitable for LLM fine-tuning.

**Command:**
```bash
ctk export finetune --db ~/chats.db --format alpaca
ctk export finetune --db ~/chats.db --format sharegpt
```

**Priority:** LOWER — Advanced use case

---

### 12. Relationship Extraction

Extract mentions of people and relationships.

**Command:**
```bash
ctk people --db ~/chats.db
ctk people "John" --db ~/chats.db
```

**Priority:** LOWER — Useful but complex

---

## Implementation Order

Suggested order based on dependencies and impact:

1. **Embeddings** — Foundation for everything semantic
2. **Persona extraction** — Core of the ghost
3. **Ghost mode** — The killer feature
4. **Unified export** — longecho integration
5. **Cross-reference detection** — Synthesis support
6. **Voice analysis** — Ghost improvement
7. (Rest as time permits)

---

## Technical Notes

### Embedding Storage

Options:
1. **SQLite blob column** — Simple, portable, slower for large scale
2. **Separate FAISS index** — Fast, but another file to manage
3. **SQLite + FAISS** — Store in SQLite, load into FAISS at runtime

Recommendation: Start with SQLite blob, add FAISS index file for search.

### LLM Integration

For ghost mode and summarization:
- Use existing ctk LLM integration
- Support Ollama (local) and API providers
- Persona extraction can be done with any capable model
- Ghost mode should use best available model

### Privacy

Persona and ghost features expose personal patterns. Consider:
- Clear documentation of what's extracted
- Option to exclude sensitive conversations
- Redaction support in exports

---

## Related Documents

- [longecho spec](../longecho/spec/LONGECHO.md) — Full ecosystem specification
- [Unified artifact schema](../longecho/spec/LONGECHO.md#unified-artifact-schema) — Export format
