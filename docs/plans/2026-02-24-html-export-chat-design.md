# HTML Export: Tree-Aware Chat Continuation

## Summary

Add an embedded OpenAI-compatible chat client to the HTML exporter, allowing users to continue exported conversations by talking to a local LLM endpoint (Ollama, LM Studio, etc.) directly in the browser. Respects CTK's tree structure: users can branch off from any assistant message, creating new conversation paths that are navigable and persistent.

## Decisions

- **Always included** — no opt-in flag; chat JS is part of every HTML export
- **Tree-aware** — new messages create branches in the conversation tree, not linear appends
- **Reply from any assistant message** — each assistant message gets a reply button
- **Path context** — API receives root → replied-message path, not entire tree
- **Streaming** — SSE streaming for token-by-token response display
- **Persistent** — new branches saved to localStorage per conversation
- **Default endpoint** — `http://localhost:11434/v1` (Ollama's OpenAI-compatible API)

## Existing Infrastructure

The exported HTML already has what we need:

- **`parent_id` on every message** — `_prepare_data()` exports `msg.parent_id` (line 311)
- **All messages exported** — `conv.message_map.values()` dumps the full tree, not just one path
- **`showConversation()` renders linearly** — currently iterates `conv.messages` sorted by timestamp; this is the main thing that changes

## Tree Navigation Model

The core change: instead of rendering a flat message list, render a **path through the tree** with branch indicators.

### JS Tree Utilities

```
ConversationTree (JS class)
  - constructor(messages[])     → builds parent→children index from parent_id
  - getChildren(msgId)          → child message IDs
  - getPathToRoot(msgId)        → [root, ..., msgId] (for API context)
  - getDefaultPath()            → longest path (matches current behavior)
  - getAllPaths()                → all leaf-to-root paths (for path selector)
  - addMessage(msg)             → insert new user/assistant message into tree
```

This mirrors `ctk/core/models.py` `ConversationTree.get_all_paths()` / `get_longest_path()` / `get_children()` in JS.

### Rendering a Path

`showConversation()` changes from:

```js
// Old: linear
conv.messages.forEach(msg => { ... });
```

to:

```js
// New: render selected path, with branch indicators
const tree = new ConversationTree(conv.messages);
const path = tree.getDefaultPath();  // or user-selected path
path.forEach(msg => {
    const children = tree.getChildren(msg.id);
    const msgEl = createMessageElement(conv, msg);
    // If multiple children exist, show branch indicator: "Path 1 of 3 [< >]"
    if (children.length > 1) { addBranchIndicator(msgEl, msg, children); }
    container.appendChild(msgEl);
});
```

### Branch Indicators

When a message has multiple children (branches), a small inline navigator appears below it:

```
┌─────────────────────────────────┐
│ Branch 2 of 3    [◀] [▶]       │
└─────────────────────────────────┘
```

Clicking `[◀]`/`[▶]` switches which child branch to follow, re-rendering from that point down. The branch indicator is compact and unobtrusive.

## Chat Integration

### Reply Button

Each **assistant** message gets a `💬 Reply` button in its action bar (alongside existing `📝 Note`, `📋 Copy`). Clicking it:

1. Opens an inline input area directly below that message
2. User types and sends
3. New user message is created with `parent_id` = that assistant message's ID
4. API call fires with path context (root → that assistant message → new user message)
5. Streaming response creates a new assistant message with `parent_id` = the new user message
6. Both new messages are saved to localStorage and rendered inline
7. A branch indicator appears on the original assistant message (it now has 2+ children)

### Quick Continue

At the **bottom of the current path** (after the last message), a simple input bar appears for quick continuation — replying to the final message without needing to click a reply button. This covers the common case of "just keep chatting."

### API Context

The messages array sent to the endpoint is the **path from root to the reply point**, translated to OpenAI format:

```json
{
  "model": "llama3.2",
  "messages": [
    {"role": "user", "content": "first message"},
    {"role": "assistant", "content": "first reply"},
    {"role": "user", "content": "follow-up"},
    {"role": "assistant", "content": "the message being replied to"},
    {"role": "user", "content": "NEW: user's new message"}
  ],
  "stream": true,
  "temperature": 0.7
}
```

Only the path to the reply point is included — not sibling branches. Clean and token-efficient.

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
- `abort()` → cancels in-flight request via AbortController
- No API key (local endpoints don't need one)

## Persistence

New messages stored in localStorage per conversation as a flat list with parent_id:

```
localStorage key: `chat_branches_${conversationId}`
Value: [
  {id, role, content, parent_id, timestamp},
  ...
]
```

On page load, these are merged into the conversation's message array before building the `ConversationTree`. This means the tree navigation automatically includes user-created branches.

Separate from existing AppState keys. A "Clear branches" button in conversation header removes localStorage entries for that conversation.

## UI Summary

| Element | Location | Trigger |
|---------|----------|---------|
| Reply button (`💬 Reply`) | Each assistant message's action bar | Click opens inline input below message |
| Quick continue input | Bottom of current path | Always visible when viewing a conversation |
| Branch indicator (`Branch 2 of 3 [◀][▶]`) | Below messages with multiple children | Auto-shown when branches exist |
| Stop button | Replaces send during streaming | Click aborts fetch |
| "Clear branches" | Conversation header area | Removes localStorage branches for this conversation |
| Settings (endpoint, model, etc.) | Settings modal, new "AI Chat" section | Configure before first use |

## Error Handling

| Error | User sees |
|-------|-----------|
| Network / endpoint down | "Could not reach endpoint. Check that your server is running." |
| CORS blocked | "CORS blocked. Ollama allows all origins by default. For other servers, check CORS config." |
| Model not found | "Model 'X' not found. Check model name in Settings." |
| Stream interrupted | Partial response kept, marked incomplete. User can retry. |
| Context too long | Show endpoint's error message as-is. No client-side truncation. |
| Model not configured | Input disabled with hint: "Configure model in Settings to chat" |

## Files Modified

| File | Change |
|------|--------|
| `ctk/integrations/exporters/html.py` | `ConversationTree` JS class, `ChatClient` class, branch navigation, reply buttons, chat input CSS, settings UI |

## Non-Goals

- No API key support (add later if needed)
- No client-side context truncation
- No new CLI flags or Python API changes
- No export of localStorage branches back to CTK database
- No multi-model support per branch (single model setting for all chats)
