# Round-Trip Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make import and round-trip lossless for branch structure, tool calls, reasoning content, the canonical ctk format, zip archives, and repeated JSONL imports, locked by a fidelity-matrix test.

**Architecture:** A new `ReasoningBlock` value type on `MessageContent` (Task 1) is the shared substrate. The Anthropic importer gains unified content-block processing (Task 2) and true tree reconstruction from `parent_message_uuid` (Task 3); the OpenAI importer captures `thoughts`/`reasoning_recap` (Task 4). A `detection_priority` on plugins (Task 5) lets the new high-specificity `CTKImporter` (Task 6) win auto-detection over greedy validators. `cmd_import` learns zip archives without full extraction (Task 7), JSONL ids become content-derived (Task 8), markdown renders reasoning (Task 9), and a fidelity matrix locks everything (Task 10). Task 11 is the green gate.

**Tech Stack:** Python 3.10+, pytest, dataclasses, zipfile, hashlib, SQLAlchemy (unchanged), existing plugin registry.

**Companion spec:** [`2026-06-09-round-trip-fidelity-design.md`](2026-06-09-round-trip-fidelity-design.md). Verified findings F1 through F8 referenced below are defined there.

**Before you start (executor, once):**

```bash
git checkout master && git checkout -b round-trip-fidelity
git add docs/plans/2026-06-09-round-trip-fidelity-design.md docs/plans/2026-06-09-round-trip-fidelity-implementation.md
git commit -m "docs(plans): sub-project B (round-trip fidelity) spec & plan"
```

Every commit in this plan ends with the trailer line:
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

A repo hook rejects file writes containing an em-dash or the word "leverage"; use plain punctuation in everything you write.

Single-file pytest runs must pass `-o addopts=""` to skip the global coverage gate.

---

### Task 1: `ReasoningBlock` and `MessageContent.reasoning`

**Files:**
- Modify: `ctk/core/models.py` (new dataclass after `ToolCall` (ends ~line 156); fields, `get_reasoning_text`, `to_dict`, `from_dict` on `MessageContent`)
- Test: `tests/unit/test_models.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_models.py`:

```python
from ctk.core.models import ReasoningBlock


def test_reasoning_blocks_round_trip_through_dict():
    content = MessageContent(text="final answer")
    content.reasoning.append(
        ReasoningBlock(text="step one thinking", summary="Plan", extra={"budget": 4096})
    )
    content.reasoning.append(ReasoningBlock(text="step two thinking"))

    restored = MessageContent.from_dict(content.to_dict())

    assert len(restored.reasoning) == 2
    assert restored.reasoning[0].text == "step one thinking"
    assert restored.reasoning[0].summary == "Plan"
    assert restored.reasoning[0].extra == {"budget": 4096}
    assert restored.reasoning[1].summary is None
    assert restored.text == "final answer"


def test_get_reasoning_text_joins_blocks_with_summaries():
    content = MessageContent()
    content.reasoning.append(ReasoningBlock(text="alpha", summary="First"))
    content.reasoning.append(ReasoningBlock(text="beta"))
    joined = content.get_reasoning_text()
    assert "First" in joined and "alpha" in joined and "beta" in joined


def test_empty_reasoning_not_serialized():
    content = MessageContent(text="hi")
    assert "reasoning" not in content.to_dict()
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_models.py -k reasoning -v -o addopts=""`
Expected: FAIL with `ImportError: cannot import name 'ReasoningBlock'`.

- [ ] **Step 3: Implement**

In `ctk/core/models.py`, after the `ToolCall` dataclass (its `from_dict` ends ~line 156) and before `class MessageContent`, add:

```python
@dataclass
class ReasoningBlock:
    """A unit of model reasoning (thinking) attached to a message.

    Captured from provider exports (OpenAI 'thoughts' / 'reasoning_recap',
    Anthropic 'thinking' blocks). ``extra`` holds provider-specific data
    such as signatures or token budgets.
    """

    text: str = ""
    summary: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"text": self.text}
        if self.summary is not None:
            data["summary"] = self.summary
        if self.extra:
            data["extra"] = self.extra
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningBlock":
        return cls(
            text=data.get("text", ""),
            summary=data.get("summary"),
            extra=data.get("extra", {}),
        )
```

In `MessageContent`, after the `tool_calls` field (line ~166), add:

```python
    reasoning: List[ReasoningBlock] = field(default_factory=list)
```

After `has_tools` (~line 232), add:

```python
    def get_reasoning_text(self) -> str:
        """Join reasoning blocks into one readable string (summaries as headers)."""
        chunks = []
        for block in self.reasoning:
            if block.summary:
                chunks.append(f"[{block.summary}]\n{block.text}")
            else:
                chunks.append(block.text)
        return "\n\n".join(chunks)
```

In `to_dict`, after the `tool_calls` serialization (`if self.tool_calls:` block), add:

```python
        if self.reasoning:
            data["reasoning"] = [r.to_dict() for r in self.reasoning]
```

In `from_dict`, after the tool_calls loading loop, before `return content`, add:

```python
        if "reasoning" in data:
            for r_data in data["reasoning"]:
                content.reasoning.append(ReasoningBlock.from_dict(r_data))
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_models.py -v -o addopts=""`
Expected: all PASS (new tests plus all pre-existing model tests).

- [ ] **Step 5: Commit**

```bash
git add ctk/core/models.py tests/unit/test_models.py
git commit -m "feat(models): ReasoningBlock + MessageContent.reasoning with dict round-trip"
```

---

### Task 2: Anthropic importer processes content blocks alongside top-level text (F2, F3)

**Files:**
- Modify: `ctk/importers/anthropic.py` (the message loop; currently `if "text" in msg_data:` at ~line 164, `elif "content" in msg_data:` at ~line 205)
- Test: `tests/unit/test_anthropic_importer.py` (append; create it if the per-provider tests live elsewhere, then check `grep -rl AnthropicImporter tests/unit` and append to the existing file instead)

- [ ] **Step 1: Write the failing test**

Append (shapes mirror the real June 2026 export verified in the design doc):

```python
def test_tool_blocks_survive_when_top_level_text_present():
    """F2: real exports carry top-level text AND content blocks; both must import."""
    conv = {
        "uuid": "c-tools", "name": "Tools", "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
        "chat_messages": [
            {
                "uuid": "m1", "sender": "assistant", "created_at": "2026-06-09T00:00:01Z",
                "text": "I ran the tool.",
                "content": [
                    {"type": "text", "text": "I ran the tool."},
                    {"type": "tool_use", "id": "tu1", "name": "calculator",
                     "input": {"expr": "2+2"}},
                    {"type": "tool_result", "tool_use_id": "tu1", "content": "4"},
                    {"type": "token_budget", "budget": 8192},
                ],
            },
        ],
    }
    importer = AnthropicImporter()
    tree = importer.import_data([conv])[0]
    msg = tree.message_map["m1"]
    assert msg.content.text == "I ran the tool."
    assert len(msg.content.tool_calls) == 1
    assert msg.content.tool_calls[0].name == "calculator"
    assert msg.content.tool_calls[0].result == "4"
    assert msg.content.metadata.get("token_budget") == {"type": "token_budget", "budget": 8192}


def test_thinking_blocks_become_reasoning():
    conv = {
        "uuid": "c-think", "name": "Think", "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
        "chat_messages": [
            {
                "uuid": "m1", "sender": "assistant", "created_at": "2026-06-09T00:00:01Z",
                "text": "Visible answer.",
                "content": [
                    {"type": "thinking", "thinking": "hidden chain of thought"},
                    {"type": "text", "text": "Visible answer."},
                ],
            },
        ],
    }
    tree = AnthropicImporter().import_data([conv])[0]
    msg = tree.message_map["m1"]
    assert msg.content.text == "Visible answer."
    assert len(msg.content.reasoning) == 1
    assert msg.content.reasoning[0].text == "hidden chain of thought"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_anthropic_importer.py -k "tool_blocks_survive or thinking_blocks" -v -o addopts=""`
Expected: FAIL (tool_calls empty, reasoning empty: the text branch short-circuits).

- [ ] **Step 3: Implement the unified content pass**

In `ctk/importers/anthropic.py`, add one import: `ReasoningBlock` to the existing `from ctk.core.models import (...)` list.

Add a method on `AnthropicImporter` (above `import_data`):

```python
    def _process_content_blocks(self, blocks: list, content: MessageContent) -> List[str]:
        """Extract structured data from Anthropic content blocks.

        Returns the text fragments found (used as fallback message text when
        no top-level text exists). Always runs, even when top-level text is
        present, so tool calls and reasoning are never dropped (F2).
        """
        text_parts: List[str] = []
        for part in blocks:
            if isinstance(part, str):
                text_parts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            part_type = part.get("type", "")
            if part_type == "text":
                text_parts.append(part.get("text", ""))
            elif part_type == "image":
                source = part.get("source", {})
                if isinstance(source, dict):
                    if source.get("type") == "base64":
                        content.add_image(
                            data=source.get("data"),
                            mime_type=source.get("media_type", "image/png"),
                        )
                    elif "url" in source:
                        content.add_image(url=source["url"])
            elif part_type == "tool_use":
                content.tool_calls.append(
                    ToolCall(
                        id=part.get("id", ""),
                        name=part.get("name", ""),
                        arguments=part.get("input", {}),
                    )
                )
            elif part_type == "tool_result":
                tool_id = part.get("tool_use_id", "")
                for tc in content.tool_calls:
                    if tc.id == tool_id:
                        tc.result = part.get("content", "")
                        tc.status = "completed"
                        if part.get("is_error"):
                            tc.status = "failed"
                            tc.error = str(part.get("content", ""))
                        break
            elif part_type in ("thinking", "redacted_thinking"):
                content.reasoning.append(
                    ReasoningBlock(
                        text=part.get("thinking", part.get("data", "")),
                        extra={k: v for k, v in part.items()
                               if k not in ("type", "thinking")},
                    )
                )
            elif part_type == "token_budget":
                content.metadata["token_budget"] = part
            else:
                content.metadata["attachments"] = content.metadata.get("attachments", [])
                content.metadata["attachments"].append(part)
        return text_parts
```

Then restructure the message loop's content handling. Replace the entire
`if "text" in msg_data:` ... `elif "content" in msg_data:` ... block (from the line
`content = MessageContent()` through the line `content.parts = msg_data["content"]`) with:

```python
                content = MessageContent()

                # Structured pass over content blocks first (never skipped: F2).
                block_text_parts: List[str] = []
                raw_blocks = msg_data.get("content")
                if isinstance(raw_blocks, list):
                    block_text_parts = self._process_content_blocks(raw_blocks, content)
                    content.parts = raw_blocks
                elif isinstance(raw_blocks, str):
                    block_text_parts = [raw_blocks]

                # Top-level text is the export's own rendering and wins when present.
                top_text = msg_data.get("text")
                if top_text:
                    content.text = top_text
                elif block_text_parts:
                    content.text = "\n".join(block_text_parts)

                # Attachments (independent of which text source won).
                if "attachments" in msg_data:
                    for attachment in msg_data["attachments"]:
                        if isinstance(attachment, dict):
                            file_name = attachment.get("file_name", "")
                            file_type = attachment.get("file_type", "")
                            if any(
                                ext in file_name.lower()
                                for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]
                            ):
                                content.add_image(path=file_name, mime_type=file_type)
                            elif file_name:
                                content.documents.append(
                                    MediaContent(
                                        type=ContentType.DOCUMENT,
                                        path=file_name,
                                        mime_type=file_type,
                                    )
                                )
                    if msg_data["attachments"]:
                        attachment_text = "\n\nAttachments: " + ", ".join(
                            a.get("file_name", "Unknown")
                            for a in msg_data["attachments"]
                        )
                        content.text = (content.text or "") + attachment_text
```

- [ ] **Step 4: Run the importer suite to verify it passes (and no regressions)**

Run: `pytest tests/unit/test_anthropic_importer.py -v -o addopts=""`
Expected: new tests PASS; every pre-existing Anthropic test still PASSES. If a pre-existing test asserted that content blocks were ignored when text exists, that test encoded the bug: update it to the new contract and note it in the commit body.

- [ ] **Step 5: Commit**

```bash
git add ctk/importers/anthropic.py tests/unit/test_anthropic_importer.py
git commit -m "fix(anthropic): process content blocks alongside top-level text (tools, thinking, token_budget)"
```

---

### Task 3: Anthropic tree from `parent_message_uuid` (F1)

**Files:**
- Modify: `ctk/importers/anthropic.py` (the chaining lines: `parent_id = None` before the loop, `parent_id=parent_id` in the `Message(...)` call, `parent_id = msg_id` after `tree.add_message`)
- Test: `tests/unit/test_anthropic_importer.py` (append)

- [ ] **Step 1: Write the failing test**

```python
ROOT_SENTINEL = "00000000-0000-4000-8000-000000000000"


def _msg(uuid, parent_uuid, text, sender="assistant"):
    return {
        "uuid": uuid, "sender": sender, "created_at": "2026-06-09T00:00:01Z",
        "text": text, "content": [{"type": "text", "text": text}],
        "parent_message_uuid": parent_uuid,
    }


def test_parent_message_uuid_builds_real_tree():
    """F1: a message with several children must import as branches, not a chain."""
    conv = {
        "uuid": "c-branch", "name": "Branchy", "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
        "chat_messages": [
            _msg("u1", ROOT_SENTINEL, "question", sender="human"),
            _msg("a1", "u1", "answer v1"),
            _msg("a2", "u1", "answer v2"),
            _msg("a3", "u1", "answer v3"),
        ],
    }
    tree = AnthropicImporter().import_data([conv])[0]
    assert tree.root_message_ids == ["u1"]
    assert tree.message_map["a1"].parent_id == "u1"
    assert tree.message_map["a2"].parent_id == "u1"
    assert tree.message_map["a3"].parent_id == "u1"
    assert len(tree.get_all_paths()) == 3


def test_dangling_parent_uuid_treated_as_root():
    conv = {
        "uuid": "c-dangle", "name": "Dangle", "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
        "chat_messages": [_msg("m1", "not-in-this-export", "orphan")],
    }
    tree = AnthropicImporter().import_data([conv])[0]
    assert tree.message_map["m1"].parent_id is None


def test_old_format_without_parent_uuid_stays_linear():
    conv = {
        "uuid": "c-old", "name": "Old", "created_at": "2026-06-09T00:00:00Z",
        "updated_at": "2026-06-09T00:00:00Z",
        "chat_messages": [
            {"uuid": "m1", "sender": "human", "text": "hi",
             "created_at": "2026-06-09T00:00:01Z"},
            {"uuid": "m2", "sender": "assistant", "text": "hello",
             "created_at": "2026-06-09T00:00:02Z"},
        ],
    }
    tree = AnthropicImporter().import_data([conv])[0]
    assert tree.message_map["m2"].parent_id == "m1"
    assert len(tree.get_all_paths()) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_anthropic_importer.py -k "parent_message_uuid or dangling or stays_linear" -v -o addopts=""`
Expected: `test_parent_message_uuid_builds_real_tree` FAILS (1 path, chained parents); the linear test may pass already.

- [ ] **Step 3: Implement**

In `ctk/importers/anthropic.py`, add a module-level constant near the top (after imports):

```python
# Anthropic's parent uuid for root messages in the 2026+ export format.
ROOT_PARENT_SENTINEL = "00000000-0000-4000-8000-000000000000"
```

In `import_data`, replace the single line `parent_id = None` (just before the message loop) with:

```python
            # Tree reconstruction (F1): the 2026+ export carries
            # parent_message_uuid on every message; honor it. Older exports
            # lack it; fall back to linear chaining by iteration order.
            known_ids = {
                (m.get("uuid") or m.get("id", f"msg_{i}"))
                for i, m in enumerate(messages)
            }
            linear_parent_id: Optional[str] = None
```

Inside the loop, immediately after `msg_id` is derived, add:

```python
                if "parent_message_uuid" in msg_data:
                    parent_uuid = msg_data.get("parent_message_uuid")
                    if (
                        not parent_uuid
                        or parent_uuid == ROOT_PARENT_SENTINEL
                        or parent_uuid not in known_ids
                    ):
                        parent_id = None
                    else:
                        parent_id = parent_uuid
                else:
                    parent_id = linear_parent_id
```

Replace the post-add line `parent_id = msg_id` with:

```python
                linear_parent_id = msg_id
```

(The `Message(..., parent_id=parent_id, ...)` call is unchanged.)

- [ ] **Step 4: Run the full importer suite**

Run: `pytest tests/unit/test_anthropic_importer.py -v -o addopts=""`
Expected: all PASS.

- [ ] **Step 5: Smoke against the real export, then commit**

```bash
python - <<'PY'
import json
from ctk.importers.anthropic import AnthropicImporter
trees = AnthropicImporter().import_data(json.load(open("dev/anthropic-6-9-2026/conversations.json")))
big = max(trees, key=lambda t: len(t.message_map))
print(len(big.message_map), "msgs,", len(big.get_all_paths()), "paths (expect 4)")
PY
git add ctk/importers/anthropic.py tests/unit/test_anthropic_importer.py
git commit -m "fix(anthropic): build the message tree from parent_message_uuid (branches preserved)"
```

Expected smoke output: `70 msgs, 4 paths (expect 4)`.

---

### Task 4: OpenAI `thoughts` / `reasoning_recap` capture (F4)

**Files:**
- Modify: `ctk/importers/openai.py` (the content-dict processing at ~lines 352-381, where `content.type = content_data.get("content_type", "text")` is set)
- Test: `tests/unit/test_openai_importer.py` (append; confirm filename via `grep -rl OpenAIImporter tests/unit`)

- [ ] **Step 1: Write the failing test**

```python
def _mapping_conv(content_dict):
    return {
        "title": "Thoughts test", "create_time": 1, "update_time": 2,
        "mapping": {
            "root": {"id": "root", "message": None, "parent": None, "children": ["n1"]},
            "n1": {"id": "n1", "parent": "root", "children": [],
                   "message": {"id": "n1", "author": {"role": "assistant"},
                               "create_time": 2, "content": content_dict,
                               "status": "finished_successfully", "metadata": {}}},
        },
        "current_node": "n1",
    }


def test_thoughts_parts_become_reasoning_blocks():
    conv = _mapping_conv({
        "content_type": "thoughts",
        "thoughts": [
            {"summary": "Plan", "content": "SECRET-REASONING-XYZ",
             "chunks": [], "finished": True},
            {"summary": "Check", "content": "more thinking",
             "chunks": [], "finished": True},
        ],
    })
    tree = OpenAIImporter().import_data([conv])[0]
    msg = next(m for m in tree.message_map.values() if m.content.reasoning)
    assert len(msg.content.reasoning) == 2
    assert msg.content.reasoning[0].summary == "Plan"
    assert "SECRET-REASONING-XYZ" in msg.content.get_reasoning_text()


def test_reasoning_recap_becomes_reasoning_block():
    conv = _mapping_conv({"content_type": "reasoning_recap",
                          "content": "Recapped the reasoning."})
    tree = OpenAIImporter().import_data([conv])[0]
    msg = next(m for m in tree.message_map.values() if m.content.reasoning)
    assert msg.content.reasoning[0].text == "Recapped the reasoning."
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_openai_importer.py -k "thoughts_parts or reasoning_recap" -v -o addopts=""`
Expected: FAIL with `StopIteration` (no message has reasoning).

- [ ] **Step 3: Implement**

In `ctk/importers/openai.py`, add `ReasoningBlock` to the models import. Then in the
content-dict branch, immediately after `content.type = content_data.get("content_type", "text")`
and before `parts = content_data.get("parts", [])`, add:

```python
                    # Reasoning content has no 'parts'; capture it structurally (F4).
                    if content_data.get("content_type") == "thoughts":
                        for thought in content_data.get("thoughts", []):
                            if isinstance(thought, dict):
                                content.reasoning.append(
                                    ReasoningBlock(
                                        text=thought.get("content", ""),
                                        summary=thought.get("summary"),
                                    )
                                )
                    elif content_data.get("content_type") == "reasoning_recap":
                        recap = content_data.get("content", "")
                        if recap:
                            content.reasoning.append(ReasoningBlock(text=recap))
```

(The existing `parts` loop then no-ops for these messages, leaving visible text empty,
matching how ChatGPT renders thoughts separately from the reply.)

- [ ] **Step 4: Run the OpenAI importer suite**

Run: `pytest tests/unit/test_openai_importer.py -v -o addopts=""`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ctk/importers/openai.py tests/unit/test_openai_importer.py
git commit -m "feat(openai): capture thoughts/reasoning_recap as ReasoningBlocks (stop dropping reasoning)"
```

---

### Task 5: `detection_priority` for deterministic auto-detect (F5 mechanism)

**Files:**
- Modify: `ctk/core/plugin.py` (`BasePlugin` class attrs ~line 282; `auto_detect_importer` at ~line 517)
- Test: `tests/unit/test_plugin_priority.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_plugin_priority.py`:

```python
from ctk.core.plugin import ImporterPlugin, PluginRegistry


class _GreedyImporter(ImporterPlugin):
    name = "greedy-test"
    detection_priority = 0

    def validate(self, data):
        return True

    def import_data(self, data, **kwargs):
        return []


class _SpecificImporter(ImporterPlugin):
    name = "specific-test"
    detection_priority = 100

    def validate(self, data):
        return isinstance(data, dict) and data.get("format") == "specific"

    def import_data(self, data, **kwargs):
        return []


def test_auto_detect_prefers_higher_priority():
    reg = PluginRegistry()
    # Bypass discovery; inject in worst-case insertion order (greedy first).
    reg._discovered = True  # noqa: SLF001 (test-only; skip filesystem discovery)
    reg.importers = {"greedy-test": _GreedyImporter(), "specific-test": _SpecificImporter()}
    chosen = reg.auto_detect_importer({"format": "specific"})
    assert chosen.name == "specific-test"
```

Note: if `PluginRegistry` has no `_discovered` attribute, read `discover_plugins` and set
whatever flag it uses to skip re-discovery (or monkeypatch `reg.discover_plugins = lambda *a, **k: None`);
adjust the test accordingly and keep the assertion identical.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_plugin_priority.py -v -o addopts=""`
Expected: FAIL (greedy importer wins because iteration is insertion-ordered).

- [ ] **Step 3: Implement**

In `ctk/core/plugin.py`, add to `BasePlugin`'s class attributes (with `name`, `description`,
`version`, `supported_formats`):

```python
    # Higher wins in auto-detection. Specific-format importers should outrank
    # greedy validators (e.g. the ctk envelope importer outranks gemini/jsonl).
    detection_priority: int = 0
```

Replace the loop body of `auto_detect_importer`:

```python
        ordered = sorted(
            self.importers.items(),
            key=lambda kv: (-getattr(kv[1], "detection_priority", 0), kv[0]),
        )
        for name, importer in ordered:
            if importer.detect_format(data):
                return importer

        return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_plugin_priority.py tests/unit/test_plugin*.py -v -o addopts=""`
Expected: PASS, including any pre-existing plugin tests.

- [ ] **Step 5: Commit**

```bash
git add ctk/core/plugin.py tests/unit/test_plugin_priority.py
git commit -m "feat(plugin): detection_priority ordering for deterministic auto-detect"
```

---

### Task 6: `CTKImporter`, the canonical inverse (F5)

**Files:**
- Create: `ctk/importers/ctk.py`
- Modify: `ctk/importers/__init__.py` (import + `__all__`)
- Test: `tests/unit/test_ctk_importer.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ctk_importer.py`:

```python
import json

from ctk.core.models import (ConversationTree, Message, MessageContent,
                             MessageRole, ReasoningBlock)
from ctk.core.plugin import registry


def _rich_tree():
    tree = ConversationTree(id="rt-1", title="RT Title")
    tree.metadata.source = "test"
    tree.add_message(Message(id="u1", role=MessageRole.USER,
                             content=MessageContent(text="Q"), parent_id=None))
    a1 = MessageContent(text="A-v1")
    a1.reasoning.append(ReasoningBlock(text="thinking", summary="Plan"))
    a1.add_tool_call(name="calc", arguments={"x": 1}, tool_id="t1")
    tree.add_message(Message(id="a1", role=MessageRole.ASSISTANT, content=a1,
                             parent_id="u1"))
    tree.add_message(Message(id="a2", role=MessageRole.ASSISTANT,
                             content=MessageContent(text="A-v2"), parent_id="u1"))
    return tree


def _export_ctk(tree) -> str:
    registry.discover_plugins()
    return registry.get_exporter("json").export_conversations([tree])


def test_auto_detect_routes_ctk_envelope_to_ctk_importer():
    parsed = json.loads(_export_ctk(_rich_tree()))
    registry.discover_plugins()
    importer = registry.auto_detect_importer(parsed)
    assert importer is not None and importer.name == "ctk"


def test_ctk_export_reimports_to_equal_tree():
    original = _rich_tree()
    parsed = json.loads(_export_ctk(original))
    importer = registry.get_importer("ctk")
    restored = importer.import_data(parsed)[0]

    assert restored.id == original.id
    assert restored.title == original.title
    assert set(restored.message_map) == set(original.message_map)
    assert restored.root_message_ids == original.root_message_ids
    for mid, orig in original.message_map.items():
        got = restored.message_map[mid]
        assert got.parent_id == orig.parent_id
        assert got.role == orig.role
        assert got.content.text == orig.content.text
    a1 = restored.message_map["a1"].content
    assert len(a1.reasoning) == 1 and a1.reasoning[0].summary == "Plan"
    assert len(a1.tool_calls) == 1 and a1.tool_calls[0].name == "calc"
    assert len(restored.get_all_paths()) == 2


def test_ctk_importer_accepts_string_input():
    raw = _export_ctk(_rich_tree())
    importer = registry.get_importer("ctk")
    assert importer.validate(raw)
    assert len(importer.import_data(raw)) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_ctk_importer.py -v -o addopts=""`
Expected: FAIL (`get_importer("ctk")` returns None; auto-detect picks gemini).

- [ ] **Step 3: Implement**

Create `ctk/importers/ctk.py`:

```python
"""Importer for CTK's own canonical JSON export (the inverse of the json
exporter's 'ctk' format_style). Preserves ids, tree structure, media, tool
calls, and reasoning exactly."""

import json
import uuid
from typing import Any, List

from ctk.core.models import (ConversationMetadata, ConversationTree, Message)
from ctk.core.plugin import ImporterPlugin


class CTKImporter(ImporterPlugin):
    """Import conversations from CTK's native JSON export."""

    name = "ctk"
    description = "Import CTK's own canonical JSON export (lossless inverse)"
    version = "1.0.0"
    supported_formats = ["ctk"]
    # Must outrank greedy validators (gemini/jsonl both claim dicts with a
    # 'conversations' key); see F5 in the round-trip-fidelity design doc.
    detection_priority = 100

    def validate(self, data: Any) -> bool:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                return False
        if not isinstance(data, dict):
            return False
        conversations = data.get("conversations")
        if not isinstance(conversations, list):
            return False
        if data.get("format") == "ctk":
            return True
        # Structural fallback: ctk conversations carry a message map plus
        # root_message_ids, which no other supported export format does.
        if conversations and isinstance(conversations[0], dict):
            first = conversations[0]
            return isinstance(first.get("messages"), dict) and "root_message_ids" in first
        return False

    def import_data(self, data: Any, **kwargs) -> List[ConversationTree]:
        if isinstance(data, str):
            data = json.loads(data)

        conversations: List[ConversationTree] = []
        for conv_data in data.get("conversations", []):
            metadata = (
                ConversationMetadata.from_dict(conv_data["metadata"])
                if isinstance(conv_data.get("metadata"), dict)
                else ConversationMetadata()
            )
            tree = ConversationTree(
                id=conv_data.get("id", str(uuid.uuid4())),
                title=conv_data.get("title"),
                metadata=metadata,
            )
            # Faithful inverse: populate the map and roots directly rather
            # than via add_message, which would overwrite metadata.updated_at
            # and re-derive roots (see CLAUDE.md gotchas).
            for msg_id, msg_dict in conv_data.get("messages", {}).items():
                tree.message_map[msg_id] = Message.from_dict(msg_dict)
            tree.root_message_ids = list(conv_data.get("root_message_ids", []))
            conversations.append(tree)

        return conversations
```

In `ctk/importers/__init__.py`, add `from ctk.importers.ctk import CTKImporter` to the
imports (alphabetical position) and `"CTKImporter"` to `__all__`.

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_ctk_importer.py tests/unit/test_plugin_priority.py -v -o addopts=""`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add ctk/importers/ctk.py ctk/importers/__init__.py tests/unit/test_ctk_importer.py
git commit -m "feat(import): CTKImporter, a lossless inverse for the canonical ctk JSON export"
```

---

### Task 7: Zip import without full extraction (F7)

**Files:**
- Modify: `ctk/cli.py` (new helper `_read_zip_export` above `cmd_import`; zip branch inside `cmd_import` where the input file is read, anchor: `# Read input file`)
- Test: `tests/unit/test_zip_import.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_zip_import.py`:

```python
import json
import zipfile
from pathlib import Path

from ctk.cli import _read_zip_export

CLAUDE_CONVS = [{
    "uuid": "z1", "name": "Zipped", "created_at": "2026-06-09T00:00:00Z",
    "updated_at": "2026-06-09T00:00:00Z",
    "chat_messages": [{"uuid": "m1", "sender": "human", "text": "hi",
                       "created_at": "2026-06-09T00:00:01Z"}],
}]


def _make_zip(path: Path, members: dict) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, payload in members.items():
            zf.writestr(name, payload)
    return path


def test_claude_zip_reads_json_in_memory_no_media_dir(tmp_path):
    zp = _make_zip(tmp_path / "claude.zip", {
        "conversations.json": json.dumps(CLAUDE_CONVS),
        "users.json": "[]", "memories.json": "{}",
    })
    data, media_dir = _read_zip_export(zp)
    assert json.loads(data)[0]["uuid"] == "z1"
    assert media_dir is None  # nothing extracted for media-free archives


def test_chatgpt_style_zip_extracts_only_media(tmp_path):
    zp = _make_zip(tmp_path / "oai.zip", {
        "conversations.json": json.dumps([{"title": "t", "mapping": {}}]),
        "dalle-generations/img.webp": b"\x00fakebytes".decode("latin1"),
    })
    data, media_dir = _read_zip_export(zp)
    assert "mapping" in data
    assert media_dir is not None
    assert (Path(media_dir) / "dalle-generations" / "img.webp").exists()
    assert not (Path(media_dir) / "conversations.json").exists()


def test_zip_traversal_members_are_skipped(tmp_path):
    zp = _make_zip(tmp_path / "evil.zip", {
        "conversations.json": json.dumps(CLAUDE_CONVS),
        "../evil.bin": "x", "/abs/evil.bin": "x",
    })
    data, media_dir = _read_zip_export(zp)
    assert json.loads(data)[0]["uuid"] == "z1"
    if media_dir is not None:
        extracted = [str(p) for p in Path(media_dir).rglob("*")]
        assert not any("evil" in p for p in extracted)
    assert not (tmp_path / "evil.bin").exists()


def test_zip_in_single_top_level_directory(tmp_path):
    zp = _make_zip(tmp_path / "nested.zip", {
        "export-2026/conversations.json": json.dumps(CLAUDE_CONVS),
    })
    data, _ = _read_zip_export(zp)
    assert json.loads(data)[0]["uuid"] == "z1"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_zip_import.py -v -o addopts=""`
Expected: FAIL with `ImportError: cannot import name '_read_zip_export'`.

- [ ] **Step 3: Implement the helper**

In `ctk/cli.py`, above `def cmd_import`, add:

```python
def _read_zip_export(zip_path) -> "tuple[str, Optional[str]]":
    """Read a provider export archive without fully extracting it.

    Returns ``(json_text, media_dir)``: the contents of the archive's
    conversations.json (root or single top-level directory), and a temp
    directory holding extracted media members when the archive contains any
    (ChatGPT zips), else None. The caller owns cleanup of media_dir.
    Traversal-unsafe members (absolute paths or '..') are skipped.
    """
    import shutil
    import tempfile
    import zipfile
    from pathlib import Path, PurePosixPath

    def _is_safe(name: str) -> bool:
        p = PurePosixPath(name)
        return not p.is_absolute() and ".." not in p.parts

    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if _is_safe(n) and not n.endswith("/")]
        json_members = [n for n in names if PurePosixPath(n).name == "conversations.json"]
        if not json_members:
            raise ValueError(
                f"Archive {zip_path} does not contain a conversations.json"
            )
        # Prefer the shallowest match (root, else single top-level directory).
        member = min(json_members, key=lambda n: len(PurePosixPath(n).parts))
        root_prefix = str(PurePosixPath(member).parent)
        data = zf.read(member).decode("utf-8")

        media_members = [
            n for n in names
            if not n.lower().endswith(".json")
        ]
        media_dir = None
        if media_members:
            media_dir = tempfile.mkdtemp(prefix="ctk-zip-")
            base = Path(media_dir).resolve()
            for n in media_members:
                rel = PurePosixPath(n)
                if root_prefix not in (".", ""):
                    try:
                        rel = rel.relative_to(root_prefix)
                    except ValueError:
                        pass
                target = (base / Path(*rel.parts)).resolve()
                if base not in target.parents and target != base:
                    continue  # belt and suspenders against traversal
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(n) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        return data, media_dir
```

- [ ] **Step 4: Wire `cmd_import`**

In `cmd_import`, change the input-reading section. Before the `if input_path.is_dir():`
line add `zip_media_dir = None`, and turn the chain into:

```python
        zip_media_dir = None
        if input_path.suffix.lower() == ".zip":
            try:
                data, zip_media_dir = _read_zip_export(input_path)
            except (ValueError, OSError) as e:
                _err(f"Error: Cannot read archive: {e}")
                return 1
        elif input_path.is_dir():
            ...existing directory handling unchanged...
        else:
            # Read input file
            with open(input_path, "r") as f:
                data = f.read()
```

In the OpenAI `source_dir` block (anchor: `if is_openai_format:`), add a zip case first:

```python
        if is_openai_format:
            if zip_media_dir:
                import_kwargs["source_dir"] = zip_media_dir
            elif input_path.is_dir():
                import_kwargs["source_dir"] = str(input_path)
            else:
                import_kwargs["source_dir"] = str(input_path.parent)
```

Wrap the import-and-save remainder of the function so the temp dir is always cleaned:
immediately before the `conversations = importer.import_data(data, **import_kwargs)` line,
open a `try:` block, and at the end of the function body (before the final `return 0`
path completes) add:

```python
        finally:
            if zip_media_dir:
                import shutil
                shutil.rmtree(zip_media_dir, ignore_errors=True)
```

(Indent the enclosed code one level; keep all existing logic unchanged.)

- [ ] **Step 5: Run unit tests plus an end-to-end zip import**

```bash
pytest tests/unit/test_zip_import.py -v -o addopts=""
rm -rf /tmp/b-zip-db && python -m ctk.cli import dev/anthropic-6-9-2026.zip --format anthropic --db /tmp/b-zip-db
```
Expected: tests PASS; CLI prints `Imported 5 conversation(s)`.

- [ ] **Step 6: Commit**

```bash
git add ctk/cli.py tests/unit/test_zip_import.py
git commit -m "feat(import): zip archives import directly (in-memory JSON, media-only extraction, traversal-safe)"
```

---

### Task 8: Deterministic JSONL ids (F6)

**Files:**
- Modify: `ctk/importers/jsonl.py` (conversation id at ~line 228, message id at ~line 272)
- Test: `tests/unit/test_jsonl_importer.py` (append; confirm filename via `grep -rl JSONLImporter tests/unit`)

- [ ] **Step 1: Write the failing test**

```python
def test_reimporting_same_jsonl_yields_same_ids():
    raw = '{"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]}\n'
    importer = JSONLImporter()
    first = importer.import_data(raw)
    second = importer.import_data(raw)
    assert first[0].id == second[0].id
    assert sorted(first[0].message_map) == sorted(second[0].message_map)


def test_different_content_yields_different_ids():
    importer = JSONLImporter()
    a = importer.import_data('{"messages": [{"role": "user", "content": "aaa"}]}\n')
    b = importer.import_data('{"messages": [{"role": "user", "content": "bbb"}]}\n')
    assert a[0].id != b[0].id


def test_explicit_id_still_wins():
    raw = '{"id": "mine", "messages": [{"role": "user", "content": "hi"}]}\n'
    assert JSONLImporter().import_data(raw)[0].id == "mine"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_jsonl_importer.py -k "same_ids or different_content or explicit_id" -v -o addopts=""`
Expected: the first test FAILS (uuid suffix differs per run).

- [ ] **Step 3: Implement**

In `ctk/importers/jsonl.py`, add `import hashlib` to the imports. Add a module-level helper:

```python
def _content_fingerprint(messages_data: list) -> str:
    """Deterministic id fragment from the (role, content) sequence.

    Identical content yields an identical conversation id, so re-importing
    the same file upserts instead of duplicating (design doc F6). Volatile
    fields (timestamps, import counters) stay out of the hash.
    """
    hasher = hashlib.sha256()
    for msg in messages_data:
        role = str(msg.get("role", ""))
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, sort_keys=True, default=str)
        hasher.update(role.encode("utf-8"))
        hasher.update(b"\x1f")
        hasher.update(content.encode("utf-8"))
        hasher.update(b"\x1e")
    return hasher.hexdigest()[:16]
```

Replace the conversation-id line:

```python
            conv_id = conv_metadata.get(
                "id", f"jsonl_{_content_fingerprint(messages_data)}"
            )
```

Replace the message-id line (`msg_id = f"msg_{msg_idx}_{uuid.uuid4().hex[:8]}"`):

```python
                # Deterministic and globally unique (message PK is global):
                # scoped by the content-derived conversation id.
                msg_id = f"{conv_id}_msg_{msg_idx}"
```

- [ ] **Step 4: Run the JSONL suite and a DB-level idempotency check**

```bash
pytest tests/unit/test_jsonl_importer.py -v -o addopts=""
python - <<'PY'
from ctk.core.database import ConversationDB
from ctk.importers.jsonl import JSONLImporter
raw = '{"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]}\n'
db = ConversationDB(":memory:")
for _ in (1, 2):
    for t in JSONLImporter().import_data(raw):
        db.save_conversation(t)
print("conversations after double import:", len(db.list_conversations(limit=100)), "(expect 1)")
db.close()
PY
```
Expected: tests PASS; script prints `1`.

- [ ] **Step 5: Commit**

```bash
git add ctk/importers/jsonl.py tests/unit/test_jsonl_importer.py
git commit -m "feat(jsonl): content-derived deterministic ids (idempotent re-import)"
```

---

### Task 9: Markdown exporter renders reasoning

**Files:**
- Modify: `ctk/exporters/markdown.py` (`_write_conversation_path`, after the role header block ~line 279)
- Test: `tests/unit/test_markdown_reasoning.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_markdown_reasoning.py`:

```python
from ctk.core.models import (ConversationTree, Message, MessageContent,
                             MessageRole, ReasoningBlock)
from ctk.core.plugin import registry


def test_markdown_export_includes_reasoning_section():
    tree = ConversationTree(id="md-1", title="MD")
    content = MessageContent(text="The answer is 4.")
    content.reasoning.append(ReasoningBlock(text="2+2 must be 4", summary="Arithmetic"))
    tree.add_message(Message(id="m1", role=MessageRole.ASSISTANT, content=content,
                             parent_id=None))
    registry.discover_plugins()
    out = registry.get_exporter("markdown").export_conversations([tree])
    assert "Reasoning" in out
    assert "2+2 must be 4" in out
    assert out.index("2+2 must be 4") < out.index("The answer is 4.")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_markdown_reasoning.py -v -o addopts=""`
Expected: FAIL (`"Reasoning" in out` is False).

- [ ] **Step 3: Implement**

In `ctk/exporters/markdown.py` `_write_conversation_path`, after the role-header
`output.write("\n\n")` and before the `# Message content` block, add:

```python
            # Reasoning (clearly marked, quoted, before the visible reply)
            if msg.content and msg.content.reasoning:
                output.write("> **Reasoning**\n")
                for line in msg.content.get_reasoning_text().splitlines():
                    output.write(f"> {line}\n")
                output.write("\n")
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_markdown_reasoning.py -v -o addopts=""`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ctk/exporters/markdown.py tests/unit/test_markdown_reasoning.py
git commit -m "feat(markdown): render reasoning blocks as a quoted section"
```

---

### Task 10: Fidelity-matrix capstone test (W7)

**Files:**
- Test: `tests/unit/test_fidelity_matrix.py` (create)

- [ ] **Step 1: Write the test (it should pass if Tasks 1 to 9 are correct; any failure is a real bug to fix before proceeding)**

Create `tests/unit/test_fidelity_matrix.py`:

```python
"""The round-trip fidelity contract: one rich fixture must survive
(1) ctk JSON export then auto-detected re-import, and
(2) DB save then load,
with tree shape, roles, text, media, tool calls, and reasoning intact."""

import json

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (ContentType, ConversationTree, MediaContent,
                             Message, MessageContent, MessageRole,
                             ReasoningBlock)
from ctk.core.plugin import registry


def _rich_fixture() -> ConversationTree:
    tree = ConversationTree(id="fid-1", title="Fidelity fixture")
    tree.metadata.source = "test"
    tree.metadata.tags = ["fidelity"]

    u1 = MessageContent(text="Question with media")
    u1.add_image(path="pic.png", mime_type="image/png")
    u1.audio.append(MediaContent(type=ContentType.AUDIO, path="clip.mp3"))
    u1.video.append(MediaContent(type=ContentType.VIDEO, path="movie.mp4"))
    u1.documents.append(MediaContent(type=ContentType.DOCUMENT, path="doc.pdf",
                                     mime_type="application/pdf"))
    tree.add_message(Message(id="u1", role=MessageRole.USER, content=u1,
                             parent_id=None))

    a1 = MessageContent(text="Answer v1")
    a1.reasoning.append(ReasoningBlock(text="thinking hard", summary="Plan",
                                       extra={"budget": 1024}))
    tc = a1.add_tool_call(name="search", arguments={"q": "x"}, tool_id="t1")
    tc.result = "found it"
    tc.status = "completed"
    tree.add_message(Message(id="a1", role=MessageRole.ASSISTANT, content=a1,
                             parent_id="u1", metadata={"k": "v"}))

    tree.add_message(Message(id="a2", role=MessageRole.ASSISTANT,
                             content=MessageContent(text="Answer v2"),
                             parent_id="u1"))
    return tree


def _assert_equal_trees(got: ConversationTree, want: ConversationTree):
    assert got.id == want.id
    assert got.title == want.title
    assert set(got.message_map) == set(want.message_map)
    assert got.root_message_ids == want.root_message_ids
    assert len(got.get_all_paths()) == len(want.get_all_paths())
    for mid, w in want.message_map.items():
        g = got.message_map[mid]
        assert g.parent_id == w.parent_id, mid
        assert g.role == w.role, mid
        assert g.content.text == w.content.text, mid
        assert len(g.content.images) == len(w.content.images), mid
        assert len(g.content.audio) == len(w.content.audio), mid
        assert len(g.content.video) == len(w.content.video), mid
        assert len(g.content.documents) == len(w.content.documents), mid
        assert len(g.content.tool_calls) == len(w.content.tool_calls), mid
        for gt, wt in zip(g.content.tool_calls, w.content.tool_calls):
            assert (gt.id, gt.name, gt.result) == (wt.id, wt.name, wt.result)
        assert len(g.content.reasoning) == len(w.content.reasoning), mid
        for gr, wr in zip(g.content.reasoning, w.content.reasoning):
            assert (gr.text, gr.summary, gr.extra) == (wr.text, wr.summary, wr.extra)


def test_ctk_export_then_autodetect_reimport_is_lossless():
    original = _rich_fixture()
    registry.discover_plugins()
    raw = registry.get_exporter("json").export_conversations([original])
    parsed = json.loads(raw)
    importer = registry.auto_detect_importer(parsed)
    assert importer is not None and importer.name == "ctk"
    _assert_equal_trees(importer.import_data(parsed)[0], original)


def test_db_save_then_load_is_lossless():
    original = _rich_fixture()
    db = ConversationDB(":memory:")
    db.save_conversation(original)
    loaded = db.load_conversation("fid-1")
    assert loaded is not None
    _assert_equal_trees(loaded, original)
    db.close()
```

- [ ] **Step 2: Run it**

Run: `pytest tests/unit/test_fidelity_matrix.py -v -o addopts=""`
Expected: PASS. If either leg fails, the failure is a genuine fidelity bug surfaced by the
matrix; fix it in the responsible module (with the matrix as the regression test) before
moving on. Do not weaken the assertions.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_fidelity_matrix.py
git commit -m "test: fidelity matrix locks ctk-export/reimport and DB save/load losslessness"
```

---

### Task 11: Green gate

**Files:** none (verification; small fixes only if gates fail)

- [ ] **Step 1: Lint and types on touched files**

```bash
black ctk/core/models.py ctk/core/plugin.py ctk/importers/anthropic.py \
  ctk/importers/openai.py ctk/importers/jsonl.py ctk/importers/ctk.py \
  ctk/importers/__init__.py ctk/exporters/markdown.py ctk/cli.py tests/unit/test_*.py
flake8 ctk/core/models.py ctk/core/plugin.py ctk/importers/anthropic.py \
  ctk/importers/openai.py ctk/importers/jsonl.py ctk/importers/ctk.py \
  ctk/exporters/markdown.py ctk/cli.py --max-line-length=100 --ignore=E203,W503
mypy ctk --ignore-missing-imports
```
Expected: black makes no further changes (or commit its reformat), flake8 reports 0 for these
files, mypy reports `Success: no issues found`.

- [ ] **Step 2: Full suite with the coverage gate**

Run: `python -m pytest tests/unit && python -m pytest tests/integration -o addopts=""`
Expected: all unit tests pass with coverage at or above 59; all integration tests pass.

- [ ] **Step 3: Real-data smoke (both formats, plus the zip)**

```bash
rm -rf /tmp/b-final && python -m ctk.cli import dev/anthropic-6-9-2026.zip --format anthropic --db /tmp/b-final
python - <<'PY'
from ctk.core.database import ConversationDB
db = ConversationDB("/tmp/b-final")
paths = sum(len(db.load_conversation(s.id).get_all_paths()) for s in db.list_conversations(limit=100) if db.load_conversation(s.id))
print("total paths:", paths, "(expect 6: 4 branched + 2 linear)")
db.close()
PY
```

- [ ] **Step 4: Commit anything the gates changed, with a summary message**

```bash
git add -u && git commit -m "chore: round-trip fidelity green gate (lint, types, suite, real-data smoke)" --allow-empty
```

---

## Self-review notes (for the executor)

- Tasks 2 and 3 both edit `ctk/importers/anthropic.py`; run them strictly in order.
- If any pre-existing test pinned the old lossy behavior (linear chaining, dropped blocks,
  random jsonl ids), update that test to the new contract and say so in the commit body;
  the design doc is the authority.
- Anchors are given as code snippets, not bare line numbers, because Task 2 shifts lines for
  Task 3; match on the quoted code.
- The fidelity matrix (Task 10) must not be weakened to pass; it is the contract.
