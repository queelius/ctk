# HTML Export: Inline Chat Continuation

## Summary

Add an embedded OpenAI-compatible chat client to the HTML exporter, allowing users to continue exported conversations by talking to a local LLM endpoint (Ollama, LM Studio, etc.) directly in the browser.

## Decisions

- **Always included** — no opt-in flag; chat JS is part of every HTML export
- **Inline continuation** — new messages render below original messages with same styling
- **Full context** — entire conversation history sent with each request
- **Streaming** — SSE streaming for token-by-token response display
- **Persistent** — new messages saved to localStorage per conversation
- **Default endpoint** — `http://localhost:11434/v1` (Ollama's OpenAI-compatible API)

## Settings

Stored in existing `preferences.chat` localStorage key:

| Field | Type | Default | Required |
|-------|------|---------|----------|
| `endpoint` | string | `http://localhost:11434/v1` | yes |
| `model` | string | `""` (blank) | yes (before first chat) |
| `temperature` | number | `0.7` | no |
| `systemPrompt` | string | `""` | no |

Settings UI: new "AI Chat" section in existing preferences panel with text inputs for endpoint/model, number input for temperature, textarea for system prompt.

## Chat Client

`ChatClient` JS class:

- `sendMessage(messages[])` → async generator of SSE tokens
- `POST {endpoint}/chat/completions` with `{model, messages, stream: true, temperature}`
- Parses OpenAI-compatible SSE: `data: {"choices":[{"delta":{"content":"..."}}]}`
- No API key (local endpoints don't need one)

Message array built from: embedded `CONVERSATIONS` data (longest path) + localStorage continuation messages + new user message.

## UI

- Fixed-bottom input bar when viewing a conversation (auto-expanding textarea + Send button)
- "Stop" button during streaming (aborts fetch)
- Disabled with hint when model not configured
- Visual separator ("Continued") between original and new messages
- "Clear continuation" button to discard localStorage messages for a conversation
- New messages use identical rendering pipeline (Markdown/KaTeX/syntax highlighting)

## Persistence

```
localStorage key: `chat_${conversationId}`
Value: [{role, content, timestamp}, ...]
```

Separate from existing AppState keys. Loaded on page open and appended to message list.

## Error Handling

| Error | User sees |
|-------|-----------|
| Network / endpoint down | "Could not reach endpoint. Check that your server is running." |
| CORS blocked | "CORS blocked. Ollama allows all origins by default. For other servers, check CORS config." |
| Model not found | "Model 'X' not found. Check model name in Settings." |
| Stream interrupted | Partial response kept, marked incomplete. User can retry. |
| Context too long | Show endpoint's error message as-is. No client-side truncation. |

## Files Modified

| File | Change |
|------|--------|
| `ctk/integrations/exporters/html.py` | Add `ChatClient` class in `_get_javascript()`, chat input CSS in `_get_css()`, settings UI in preferences panel, chat input bar in conversation view |

## Non-Goals

- No API key support (add later if needed)
- No client-side context truncation
- No new CLI flags or Python API changes
- No branching/forking of conversations in the HTML (linear continuation only)
