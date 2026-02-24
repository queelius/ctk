# HTML Export: Tree-Aware Chat — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add tree navigation and an embedded OpenAI-compatible chat client to the HTML exporter, allowing users to branch off from any assistant message and chat with a local LLM.

**Architecture:** All changes are in `ctk/integrations/exporters/html.py`. The existing `_get_javascript()` method gets a new `ConversationTree` class for tree traversal, `ChatClient` for API calls, and UI components for branch navigation, reply buttons, and chat input. `showConversation()` switches from linear rendering to path-based rendering. Settings stored in existing `state.preferences.chat` localStorage key.

**Tech Stack:** Vanilla JS (no frameworks), SSE streaming, OpenAI-compatible `/v1/chat/completions` API, localStorage persistence.

**Design doc:** `docs/plans/2026-02-24-html-export-chat-design.md`

---

### Task 1: ConversationTree JS Class

**Files:**
- Modify: `ctk/integrations/exporters/html.py:2153-2160` (add class after AppState in `_get_javascript()`)
- Test: `tests/unit/test_html_chat.py` (new file)

**Step 1: Write the failing test**

Create `tests/unit/test_html_chat.py`:

```python
"""Tests for HTML export chat/tree features."""
import pytest
import json
import re
from ctk.integrations.exporters.html import HTMLExporter


class TestConversationTreeJS:
    """Test that ConversationTree JS class is included and correct."""

    def test_javascript_contains_conversation_tree_class(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "class ConversationTree" in js

    def test_conversation_tree_has_required_methods(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        for method in [
            "getChildren",
            "getPathToRoot",
            "getDefaultPath",
            "addMessage",
        ]:
            assert method in js, f"Missing method: {method}"

    def test_conversation_tree_builds_parent_index(self):
        """Verify constructor builds childrenMap from parent_id."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "childrenMap" in js
        assert "parent_id" in js
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_html_chat.py -v`
Expected: FAIL — `class ConversationTree` not found in JS output.

**Step 3: Write minimal implementation**

In `html.py`, inside `_get_javascript()`, add the `ConversationTree` class **after the `AppState` class** (after line ~2460, before `function renderConversationList`). Find the line `function renderConversationList()` and insert before it:

```javascript
// ==================== Conversation Tree ====================
class ConversationTree {
    constructor(messages) {
        this.messages = new Map();
        this.childrenMap = new Map();
        this.roots = [];

        messages.forEach(msg => {
            this.messages.set(msg.id, msg);
            if (!this.childrenMap.has(msg.id)) {
                this.childrenMap.set(msg.id, []);
            }
        });

        messages.forEach(msg => {
            if (msg.parent_id && this.messages.has(msg.parent_id)) {
                this.childrenMap.get(msg.parent_id).push(msg.id);
            } else if (!msg.parent_id) {
                this.roots.push(msg.id);
            }
        });
    }

    getChildren(msgId) {
        return this.childrenMap.get(msgId) || [];
    }

    getPathToRoot(msgId) {
        const path = [];
        let current = msgId;
        while (current) {
            const msg = this.messages.get(current);
            if (!msg) break;
            path.unshift(msg);
            current = msg.parent_id;
        }
        return path;
    }

    getDefaultPath() {
        // Follow first child at each level (longest/deepest path)
        if (this.roots.length === 0) return [];
        const path = [];
        let currentId = this.roots[0];
        while (currentId) {
            const msg = this.messages.get(currentId);
            if (!msg) break;
            path.push(msg);
            const children = this.getChildren(currentId);
            currentId = children.length > 0 ? children[0] : null;
        }
        return path;
    }

    addMessage(msg) {
        this.messages.set(msg.id, msg);
        if (!this.childrenMap.has(msg.id)) {
            this.childrenMap.set(msg.id, []);
        }
        if (msg.parent_id && this.childrenMap.has(msg.parent_id)) {
            this.childrenMap.get(msg.parent_id).push(msg.id);
        } else if (!msg.parent_id) {
            this.roots.push(msg.id);
        }
    }
}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_html_chat.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_html_chat.py ctk/integrations/exporters/html.py
git commit -m "feat(html): add ConversationTree JS class for tree navigation"
```

---

### Task 2: Path-Based Rendering in showConversation

**Files:**
- Modify: `ctk/integrations/exporters/html.py:2849-2946` (`showConversation` function)
- Modify: `ctk/integrations/exporters/html.py:2949-3054` (`createMessageElement` — add msg.id as data attribute)
- Test: `tests/unit/test_html_chat.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_html_chat.py`:

```python
class TestPathBasedRendering:
    """Test that showConversation uses tree-based path rendering."""

    def test_show_conversation_builds_tree(self):
        """showConversation should instantiate ConversationTree."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        # Should create a tree from merged messages
        assert "new ConversationTree(" in js
        assert "getDefaultPath" in js

    def test_show_conversation_has_branch_indicator(self):
        """Messages with multiple children should show branch navigation."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "branch-indicator" in js

    def test_message_element_has_data_id(self):
        """Each message div should have data-msg-id for tree navigation."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "data-msg-id" in js

    def test_switch_branch_function_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "function switchBranch" in js or "switchBranch" in js

    def test_merge_local_branches_on_load(self):
        """localStorage branches should be merged before tree construction."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "chat_branches_" in js
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_html_chat.py::TestPathBasedRendering -v`
Expected: FAIL

**Step 3: Write implementation**

Replace the message rendering loop in `showConversation()` (lines 2942-2946). The current code is:

```javascript
    // Messages
    conv.messages.forEach(msg => {
        const messageDiv = createMessageElement(conv, msg);
        container.appendChild(messageDiv);
    });
}
```

Replace with:

```javascript
    // Merge localStorage branches into message list
    const localKey = 'chat_branches_' + conv.id;
    const localBranches = JSON.parse(localStorage.getItem(localKey) || '[]');
    const allMessages = [...conv.messages, ...localBranches];

    // Build tree and render selected path
    const tree = new ConversationTree(allMessages);
    state.currentTree = tree;
    state.currentPath = tree.getDefaultPath();

    state.currentPath.forEach(msg => {
        const messageDiv = createMessageElement(conv, msg);
        const children = tree.getChildren(msg.id);
        if (children.length > 1) {
            const indicator = createBranchIndicator(msg, children, tree, conv);
            messageDiv.appendChild(indicator);
        }
        container.appendChild(messageDiv);
    });

    // Quick continue input at bottom
    const continueInput = createQuickContinueInput(conv, tree);
    container.appendChild(continueInput);
}
```

Add `data-msg-id` to `createMessageElement` — in the function body after `div.className = ...`:

```javascript
    div.dataset.msgId = msg.id;
```

Add helper functions after `showConversation`:

```javascript
function createBranchIndicator(parentMsg, childIds, tree, conv) {
    const currentChild = state.currentPath.find(m =>
        childIds.includes(m.id)
    );
    const currentIndex = currentChild ? childIds.indexOf(currentChild.id) : 0;

    const indicator = document.createElement('div');
    indicator.className = 'branch-indicator';

    const label = document.createElement('span');
    label.className = 'branch-label';
    label.textContent = 'Branch ' + (currentIndex + 1) + ' of ' + childIds.length;

    const prevBtn = document.createElement('button');
    prevBtn.className = 'branch-nav-btn';
    prevBtn.textContent = '\u25C0';
    prevBtn.disabled = currentIndex === 0;
    prevBtn.addEventListener('click', () => {
        switchBranch(parentMsg.id, childIds[currentIndex - 1], tree, conv);
    });

    const nextBtn = document.createElement('button');
    nextBtn.className = 'branch-nav-btn';
    nextBtn.textContent = '\u25B6';
    nextBtn.disabled = currentIndex === childIds.length - 1;
    nextBtn.addEventListener('click', () => {
        switchBranch(parentMsg.id, childIds[currentIndex + 1], tree, conv);
    });

    indicator.appendChild(prevBtn);
    indicator.appendChild(label);
    indicator.appendChild(nextBtn);
    return indicator;
}

function switchBranch(parentMsgId, newChildId, tree, conv) {
    // Build new path: root->parent, then follow newChildId down
    const pathToParent = tree.getPathToRoot(parentMsgId);
    let path = [...pathToParent];
    let currentId = newChildId;
    while (currentId) {
        const msg = tree.messages.get(currentId);
        if (!msg) break;
        path.push(msg);
        const children = tree.getChildren(currentId);
        currentId = children.length > 0 ? children[0] : null;
    }
    state.currentPath = path;
    showConversation(conv);
}

function clearLocalBranches(convId) {
    localStorage.removeItem('chat_branches_' + convId);
    if (state.currentConv && state.currentConv.id === convId) {
        showConversation(state.currentConv);
    }
}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_html_chat.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add ctk/integrations/exporters/html.py tests/unit/test_html_chat.py
git commit -m "feat(html): path-based rendering with branch navigation"
```

---

### Task 3: CSS for Branch Indicators, Chat Input, and Chat Messages

**Files:**
- Modify: `ctk/integrations/exporters/html.py:720-2151` (inside `_get_css()`)
- Test: `tests/unit/test_html_chat.py`

**Step 1: Write the failing test**

```python
class TestChatCSS:
    """Test that CSS includes styles for chat components."""

    def test_css_has_branch_indicator_styles(self):
        exporter = HTMLExporter()
        css = exporter._get_css()
        assert ".branch-indicator" in css

    def test_css_has_chat_input_styles(self):
        exporter = HTMLExporter()
        css = exporter._get_css()
        assert ".chat-input-area" in css

    def test_css_has_chat_message_styles(self):
        exporter = HTMLExporter()
        css = exporter._get_css()
        assert ".chat-message" in css

    def test_css_has_streaming_indicator(self):
        exporter = HTMLExporter()
        css = exporter._get_css()
        assert ".streaming" in css
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_html_chat.py::TestChatCSS -v`
Expected: FAIL

**Step 3: Write implementation**

Add CSS at the end of `_get_css()`, just before the closing `"""`:

```css
/* ==================== Branch Navigation ==================== */
.branch-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.75rem;
    margin-top: 0.25rem;
    font-size: 0.8rem;
    color: var(--text-secondary);
    background: var(--bg-secondary);
    border-radius: 0.25rem;
    width: fit-content;
}

.branch-nav-btn {
    background: none;
    border: 1px solid var(--border-color);
    border-radius: 0.25rem;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0.1rem 0.4rem;
    font-size: 0.75rem;
}

.branch-nav-btn:hover:not(:disabled) {
    background: var(--accent);
    color: white;
}

.branch-nav-btn:disabled {
    opacity: 0.3;
    cursor: default;
}

.branch-label {
    min-width: 6rem;
    text-align: center;
}

/* ==================== Chat Input ==================== */
.chat-input-area {
    display: flex;
    gap: 0.5rem;
    padding: 0.75rem;
    margin-top: 0.5rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 0.5rem;
}

.chat-input-area textarea {
    flex: 1;
    padding: 0.5rem;
    border: 1px solid var(--border-color);
    border-radius: 0.25rem;
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.9rem;
    resize: vertical;
    min-height: 2.5rem;
    max-height: 8rem;
}

.chat-input-area textarea:focus {
    outline: none;
    border-color: var(--accent);
}

.chat-send-btn, .chat-stop-btn {
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-size: 0.9rem;
    white-space: nowrap;
}

.chat-send-btn {
    background: var(--accent);
    color: white;
}

.chat-send-btn:hover {
    opacity: 0.9;
}

.chat-send-btn:disabled {
    opacity: 0.5;
    cursor: default;
}

.chat-stop-btn {
    background: #e74c3c;
    color: white;
}

.chat-stop-btn:hover {
    opacity: 0.9;
}

.chat-config-hint {
    padding: 0.75rem;
    margin-top: 0.5rem;
    background: var(--bg-secondary);
    border: 1px dashed var(--border-color);
    border-radius: 0.5rem;
    color: var(--text-secondary);
    font-size: 0.85rem;
    text-align: center;
}

/* ==================== Chat Messages ==================== */
.chat-message {
    border-left: 3px solid var(--accent);
    opacity: 0.95;
}

.chat-message .message-role::after {
    content: ' (local)';
    font-size: 0.75rem;
    opacity: 0.6;
}

.chat-continuation-separator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0;
    color: var(--text-secondary);
    font-size: 0.8rem;
}

.chat-continuation-separator::before,
.chat-continuation-separator::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border-color);
}

.streaming .message-content::after {
    content: '\u2588';
    animation: blink 0.7s infinite;
}

@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
}

.chat-error {
    padding: 0.5rem 0.75rem;
    margin-top: 0.25rem;
    background: rgba(231, 76, 60, 0.1);
    border: 1px solid rgba(231, 76, 60, 0.3);
    border-radius: 0.25rem;
    color: #e74c3c;
    font-size: 0.85rem;
}

.inline-reply-area {
    margin: 0.5rem 0;
}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_html_chat.py::TestChatCSS -v`
Expected: PASS

**Step 5: Commit**

```bash
git add ctk/integrations/exporters/html.py tests/unit/test_html_chat.py
git commit -m "feat(html): add CSS for branch indicators, chat input, and chat messages"
```

---

### Task 4: ChatClient JS Class

**Files:**
- Modify: `ctk/integrations/exporters/html.py` (inside `_get_javascript()`, after ConversationTree)
- Test: `tests/unit/test_html_chat.py`

**Step 1: Write the failing test**

```python
class TestChatClientJS:
    """Test that ChatClient JS class is included."""

    def test_chat_client_class_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "class ChatClient" in js

    def test_chat_client_has_send_method(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "sendMessage" in js

    def test_chat_client_has_abort(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "AbortController" in js

    def test_chat_client_uses_streaming(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "stream" in js
        assert "chat/completions" in js

    def test_chat_client_reads_settings_from_preferences(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "preferences.chat" in js
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_html_chat.py::TestChatClientJS -v`
Expected: FAIL

**Step 3: Write implementation**

Add after ConversationTree class in `_get_javascript()`:

```javascript
// ==================== Chat Client ====================
class ChatClient {
    constructor() {
        this.controller = null;
    }

    getSettings() {
        const chat = state.preferences.chat || {};
        return {
            endpoint: chat.endpoint || 'http://localhost:11434/v1',
            model: chat.model || '',
            temperature: chat.temperature !== undefined ? chat.temperature : 0.7,
            systemPrompt: chat.systemPrompt || ''
        };
    }

    async *sendMessage(messages) {
        const settings = this.getSettings();
        if (!settings.model) {
            throw new Error('MODEL_NOT_CONFIGURED');
        }

        this.controller = new AbortController();

        const apiMessages = [];
        if (settings.systemPrompt) {
            apiMessages.push({ role: 'system', content: settings.systemPrompt });
        }
        messages.forEach(m => {
            apiMessages.push({ role: m.role, content: m.content });
        });

        const url = settings.endpoint.replace(/\\/+$/, '') + '/chat/completions';
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: settings.model,
                messages: apiMessages,
                stream: true,
                temperature: settings.temperature
            }),
            signal: this.controller.signal
        });

        if (!response.ok) {
            const text = await response.text().catch(() => '');
            if (response.status === 404 && text.includes('model')) {
                throw new Error('MODEL_NOT_FOUND:' + settings.model);
            }
            throw new Error('API_ERROR:' + response.status + ' ' + text);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || !trimmed.startsWith('data: ')) continue;
                    const data = trimmed.slice(6);
                    if (data === '[DONE]') return;
                    try {
                        const parsed = JSON.parse(data);
                        const content = parsed.choices?.[0]?.delta?.content;
                        if (content) yield content;
                    } catch (e) {
                        // Skip malformed SSE chunks
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    }

    abort() {
        if (this.controller) {
            this.controller.abort();
            this.controller = null;
        }
    }
}

const chatClient = new ChatClient();
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_html_chat.py::TestChatClientJS -v`
Expected: PASS

**Step 5: Commit**

```bash
git add ctk/integrations/exporters/html.py tests/unit/test_html_chat.py
git commit -m "feat(html): add ChatClient JS class with SSE streaming"
```

---

### Task 5: Settings UI for AI Chat

**Files:**
- Modify: `ctk/integrations/exporters/html.py:606-624` (settings modal HTML)
- Modify: `ctk/integrations/exporters/html.py:2430-2438` (settings event wiring)
- Test: `tests/unit/test_html_chat.py`

**Step 1: Write the failing test**

```python
class TestChatSettings:
    """Test that AI Chat settings are in the settings modal."""

    def test_settings_modal_has_chat_section(self):
        exporter = HTMLExporter()
        html = exporter._generate_html([])
        assert "AI Chat" in html

    def test_settings_has_endpoint_input(self):
        exporter = HTMLExporter()
        html = exporter._generate_html([])
        assert "chatEndpoint" in html

    def test_settings_has_model_input(self):
        exporter = HTMLExporter()
        html = exporter._generate_html([])
        assert "chatModel" in html

    def test_settings_has_temperature_input(self):
        exporter = HTMLExporter()
        html = exporter._generate_html([])
        assert "chatTemperature" in html

    def test_settings_has_system_prompt_input(self):
        exporter = HTMLExporter()
        html = exporter._generate_html([])
        assert "chatSystemPrompt" in html

    def test_default_endpoint_value(self):
        exporter = HTMLExporter()
        html = exporter._generate_html([])
        assert "localhost:11434" in html
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_html_chat.py::TestChatSettings -v`
Expected: FAIL

**Step 3: Write implementation**

In the settings modal HTML (line ~618, before `<h3>Data Management</h3>`), add:

```html
                    <h3>AI Chat</h3>
                    <p class="help-text">Configure a local LLM endpoint (Ollama, LM Studio, etc.) to continue conversations in the browser.</p>
                    <label>Endpoint: <input type="text" id="chatEndpoint" placeholder="http://localhost:11434/v1" style="width: 100%;"></label>
                    <label>Model: <input type="text" id="chatModel" placeholder="e.g. llama3.2, mistral" style="width: 100%;"></label>
                    <label>Temperature: <input type="number" id="chatTemperature" min="0" max="2" step="0.1" value="0.7" style="width: 4rem;"></label>
                    <label>System Prompt: <textarea id="chatSystemPrompt" rows="3" style="width: 100%; font-family: inherit;" placeholder="Optional system prompt for all chats"></textarea></label>
```

In the settings event wiring section (after the fontSizeSlider listener, line ~2438), add JS to load/save chat settings:

```javascript
    // AI Chat settings
    const chatFields = ['chatEndpoint', 'chatModel', 'chatTemperature', 'chatSystemPrompt'];
    const chatSettings = state.preferences.chat || {};
    const chatEndpointEl = document.getElementById('chatEndpoint');
    const chatModelEl = document.getElementById('chatModel');
    const chatTempEl = document.getElementById('chatTemperature');
    const chatPromptEl = document.getElementById('chatSystemPrompt');

    if (chatEndpointEl) chatEndpointEl.value = chatSettings.endpoint || 'http://localhost:11434/v1';
    if (chatModelEl) chatModelEl.value = chatSettings.model || '';
    if (chatTempEl) chatTempEl.value = chatSettings.temperature !== undefined ? chatSettings.temperature : 0.7;
    if (chatPromptEl) chatPromptEl.value = chatSettings.systemPrompt || '';

    chatFields.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => {
                if (!state.preferences.chat) state.preferences.chat = {};
                state.preferences.chat.endpoint = chatEndpointEl.value;
                state.preferences.chat.model = chatModelEl.value;
                state.preferences.chat.temperature = parseFloat(chatTempEl.value) || 0.7;
                state.preferences.chat.systemPrompt = chatPromptEl.value;
                state.save('preferences');
            });
        }
    });
```

Also add to `applyPreferences()` function (around line 2646) to restore chat settings on page load:

```javascript
    // Restore chat settings
    if (state.preferences.chat) {
        const cs = state.preferences.chat;
        const ep = document.getElementById('chatEndpoint');
        const mo = document.getElementById('chatModel');
        const te = document.getElementById('chatTemperature');
        const sp = document.getElementById('chatSystemPrompt');
        if (ep) ep.value = cs.endpoint || 'http://localhost:11434/v1';
        if (mo) mo.value = cs.model || '';
        if (te) te.value = cs.temperature !== undefined ? cs.temperature : 0.7;
        if (sp) sp.value = cs.systemPrompt || '';
    }
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_html_chat.py::TestChatSettings -v`
Expected: PASS

**Step 5: Commit**

```bash
git add ctk/integrations/exporters/html.py tests/unit/test_html_chat.py
git commit -m "feat(html): add AI Chat settings section to preferences"
```

---

### Task 6: Chat Input Components (Reply Button, Quick Continue, Send Logic)

**Files:**
- Modify: `ctk/integrations/exporters/html.py:2949-2967` (add Reply button to `createMessageElement`)
- Modify: `ctk/integrations/exporters/html.py` (add `createQuickContinueInput`, `sendChatMessage`, `createInlineReplyInput` functions)
- Test: `tests/unit/test_html_chat.py`

**Step 1: Write the failing tests**

```python
class TestChatInputComponents:
    """Test chat input UI components."""

    def test_assistant_messages_have_reply_button(self):
        """Reply button should be added to assistant message action bars."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "Reply" in js

    def test_quick_continue_input_function_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "createQuickContinueInput" in js

    def test_send_chat_message_function_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "sendChatMessage" in js

    def test_inline_reply_input_function_exists(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "createInlineReplyInput" in js

    def test_chat_message_persistence(self):
        """New chat messages should be saved to localStorage."""
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "chat_branches_" in js
        assert "localStorage.setItem" in js

    def test_error_handling_for_network(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "Could not reach" in js or "CORS" in js or "MODEL_NOT_CONFIGURED" in js

    def test_stop_button_aborts_stream(self):
        exporter = HTMLExporter()
        js = exporter._get_javascript()
        assert "chatClient.abort" in js
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_html_chat.py::TestChatInputComponents -v`
Expected: FAIL

**Step 3: Write implementation**

**6a. Add Reply button to `createMessageElement`.**

In `createMessageElement` (line ~2963), the existing action buttons are set via a template. Add a Reply button for assistant messages. After the existing action buttons block (where `actions` div content is set), add:

```javascript
    if (msg.role === 'assistant') {
        const replyBtn = document.createElement('button');
        replyBtn.className = 'message-action';
        replyBtn.textContent = '\uD83D\uDCAC Reply';
        replyBtn.addEventListener('click', () => {
            // Remove any existing inline reply areas
            document.querySelectorAll('.inline-reply-area').forEach(el => el.remove());
            const replyArea = createInlineReplyInput(conv, msg, div);
            div.after(replyArea);
        });
        actions.appendChild(replyBtn);
    }
```

**6b. Add `createInlineReplyInput` function** (after the branch navigation functions):

```javascript
function createInlineReplyInput(conv, parentMsg, parentDiv) {
    const wrapper = document.createElement('div');
    wrapper.className = 'inline-reply-area';

    const area = document.createElement('div');
    area.className = 'chat-input-area';

    const textarea = document.createElement('textarea');
    textarea.placeholder = 'Reply to this message...';
    textarea.rows = 2;
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage(conv, parentMsg.id, textarea.value.trim(), wrapper);
        }
    });

    const sendBtn = document.createElement('button');
    sendBtn.className = 'chat-send-btn';
    sendBtn.textContent = 'Send';
    sendBtn.addEventListener('click', () => {
        sendChatMessage(conv, parentMsg.id, textarea.value.trim(), wrapper);
    });

    area.appendChild(textarea);
    area.appendChild(sendBtn);
    wrapper.appendChild(area);

    setTimeout(() => textarea.focus(), 50);
    return wrapper;
}
```

**6c. Add `createQuickContinueInput` function:**

```javascript
function createQuickContinueInput(conv, tree) {
    const chat = state.preferences.chat || {};
    if (!chat.model) {
        const hint = document.createElement('div');
        hint.className = 'chat-config-hint';
        hint.textContent = 'Configure a model in Settings > AI Chat to continue this conversation.';
        return hint;
    }

    const lastMsg = state.currentPath[state.currentPath.length - 1];
    if (!lastMsg) {
        return document.createElement('div');
    }

    const sep = document.createElement('div');
    sep.className = 'chat-continuation-separator';
    sep.textContent = 'Continue conversation';

    const area = document.createElement('div');
    area.className = 'chat-input-area';

    const textarea = document.createElement('textarea');
    textarea.placeholder = 'Type a message...';
    textarea.rows = 2;
    textarea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage(conv, lastMsg.id, textarea.value.trim(), area);
        }
    });

    const sendBtn = document.createElement('button');
    sendBtn.className = 'chat-send-btn';
    sendBtn.textContent = 'Send';
    sendBtn.addEventListener('click', () => {
        sendChatMessage(conv, lastMsg.id, textarea.value.trim(), area);
    });

    area.appendChild(textarea);
    area.appendChild(sendBtn);

    const wrapper = document.createElement('div');
    wrapper.appendChild(sep);
    wrapper.appendChild(area);
    return wrapper;
}
```

**6d. Add `sendChatMessage` function:**

```javascript
async function sendChatMessage(conv, parentMsgId, text, inputContainer) {
    if (!text) return;

    const tree = state.currentTree;
    if (!tree) return;

    // Create user message
    const userMsg = {
        id: 'chat_' + Date.now() + '_user',
        role: 'user',
        content: text,
        parent_id: parentMsgId,
        timestamp: new Date().toISOString(),
        is_chat: true
    };
    tree.addMessage(userMsg);
    saveChatBranch(conv.id, userMsg);

    // Build context path: root -> parentMsg -> new user message
    const contextPath = tree.getPathToRoot(parentMsgId);
    contextPath.push(userMsg);

    // Create placeholder assistant message
    const assistantMsg = {
        id: 'chat_' + Date.now() + '_assistant',
        role: 'assistant',
        content: '',
        parent_id: userMsg.id,
        timestamp: new Date().toISOString(),
        is_chat: true
    };
    tree.addMessage(assistantMsg);

    // Update current path and re-render
    state.currentPath = tree.getPathToRoot(assistantMsg.id);
    showConversation(conv);

    // Find the assistant message element and start streaming
    const msgEl = document.querySelector('[data-msg-id="' + assistantMsg.id + '"]');
    if (msgEl) msgEl.classList.add('streaming');

    // Replace send button with stop button in the quick continue area
    const stopBtn = document.createElement('button');
    stopBtn.className = 'chat-stop-btn';
    stopBtn.textContent = 'Stop';
    stopBtn.addEventListener('click', () => chatClient.abort());

    try {
        let fullContent = '';
        const contentEl = msgEl ? msgEl.querySelector('.message-content') : null;

        for await (const token of chatClient.sendMessage(contextPath)) {
            fullContent += token;
            if (contentEl) contentEl.textContent = fullContent;
        }

        assistantMsg.content = fullContent;
        saveChatBranch(conv.id, assistantMsg);
    } catch (err) {
        if (msgEl) msgEl.classList.remove('streaming');

        const errorDiv = document.createElement('div');
        errorDiv.className = 'chat-error';

        if (err.name === 'AbortError') {
            // User cancelled — keep partial response
            if (assistantMsg.content) {
                saveChatBranch(conv.id, assistantMsg);
            }
            return;
        } else if (err.message === 'MODEL_NOT_CONFIGURED') {
            errorDiv.textContent = 'Configure a model in Settings > AI Chat to chat.';
        } else if (err.message.startsWith('MODEL_NOT_FOUND:')) {
            const model = err.message.split(':')[1];
            errorDiv.textContent = "Model '" + model + "' not found. Check model name in Settings.";
        } else if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
            errorDiv.textContent = 'Could not reach endpoint. Check that your server is running.';
        } else {
            errorDiv.textContent = err.message;
        }

        if (msgEl) msgEl.appendChild(errorDiv);
        return;
    } finally {
        if (msgEl) msgEl.classList.remove('streaming');
    }

    // Re-render to show final state with branch indicators
    state.currentPath = tree.getPathToRoot(assistantMsg.id);
    showConversation(conv);
}

function saveChatBranch(convId, msg) {
    const key = 'chat_branches_' + convId;
    const branches = JSON.parse(localStorage.getItem(key) || '[]');
    const existingIdx = branches.findIndex(m => m.id === msg.id);
    if (existingIdx >= 0) {
        branches[existingIdx] = msg;
    } else {
        branches.push(msg);
    }
    localStorage.setItem(key, JSON.stringify(branches));
}
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_html_chat.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add ctk/integrations/exporters/html.py tests/unit/test_html_chat.py
git commit -m "feat(html): add reply button, quick continue, and send logic"
```

---

### Task 7: Integration Test with Full Export

**Files:**
- Test: `tests/unit/test_html_chat.py`

**Step 1: Write integration-level tests**

```python
class TestHTMLExportIntegration:
    """Integration tests verifying the full HTML export includes chat features."""

    def test_full_export_contains_all_chat_components(self):
        """A full HTML export should contain all chat-related components."""
        exporter = HTMLExporter()
        html = exporter._generate_html([])
        # JS classes
        assert "class ConversationTree" in html
        assert "class ChatClient" in html
        # CSS
        assert ".branch-indicator" in html
        assert ".chat-input-area" in html
        # Settings
        assert "chatEndpoint" in html
        assert "chatModel" in html
        # Functions
        assert "sendChatMessage" in html
        assert "createQuickContinueInput" in html

    def test_export_with_conversations_includes_parent_id(self, sample_conversation):
        """Exported data should include parent_id on messages."""
        from ctk.integrations.exporters.html import HTMLExporter
        exporter = HTMLExporter()
        data = exporter._prepare_data([sample_conversation])
        for conv in data:
            for msg in conv.get("messages", []):
                assert "parent_id" in msg or "id" in msg

    def test_export_with_branching_conversation(self, branching_conversation):
        """Branching conversations should export all messages."""
        from ctk.integrations.exporters.html import HTMLExporter
        exporter = HTMLExporter()
        html = exporter._generate_html([branching_conversation])
        assert "class ConversationTree" in html
```

Note: `sample_conversation` and `branching_conversation` fixtures are available in `tests/conftest.py`.

**Step 2: Run tests**

Run: `pytest tests/unit/test_html_chat.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/unit/test_html_chat.py
git commit -m "test(html): add integration tests for chat export features"
```

---

### Task 8: Manual Smoke Test

**No code changes.** Verify the feature works end-to-end:

**Step 1: Export a real conversation to HTML**

```bash
# Pick a conversation with messages
ctk conv export <conv-id> --format html -o /tmp/test-chat.html
```

**Step 2: Open in browser and verify**

1. Open `/tmp/test-chat.html` in a browser
2. Click a conversation in the sidebar
3. Verify messages render (path-based, not broken)
4. Check Settings > AI Chat section exists with endpoint, model, temperature, system prompt fields
5. If you have Ollama running: set model name, send a message via quick continue input
6. Verify streaming response appears with blinking cursor
7. If no Ollama: verify "Configure model" hint appears at conversation bottom
8. If conversation has branches: verify branch indicators appear with navigation buttons

**Step 3: Final commit with any fixes**

```bash
# If any fixes were needed:
git add ctk/integrations/exporters/html.py tests/unit/test_html_chat.py
git commit -m "fix(html): smoke test fixes for chat export"
```

---

## Verification (all tasks)

```bash
# Run full test suite
python -m pytest tests/unit/ -x -q --ignore=tests/unit/test_taggers.py

# Run only new tests
python -m pytest tests/unit/test_html_chat.py -v

# Lint changed files
python -m flake8 ctk/integrations/exporters/html.py --max-line-length=100

# Quick smoke test
python -c "from ctk.integrations.exporters.html import HTMLExporter; e = HTMLExporter(); js = e._get_javascript(); assert 'ConversationTree' in js and 'ChatClient' in js; print('OK')"
```
