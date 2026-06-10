# TUI Chat Client (Streaming, Thinking, Cancel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream text, reasoning, and tool calls live through the tool-enabled chat path, render thinking as a collapsible block, show elapsed progress, make Escape cancel the turn, and put errors in the transcript.

**Architecture:** A new `StreamEvent` iterator (`LLMProvider.stream_turn`) unifies streaming with tools at the provider layer (index-keyed tool_call delta accumulation handles both OpenAI-fragmented and ollama single-shot shapes). The TUI worker consumes events and posts per-delta messages; UI handlers manage a lazy live bubble, a collapsible `ThinkingBlock`, an elapsed indicator, and cancellation/error rendering. Persistence reuses sub-project B's `ReasoningBlock`.

**Tech Stack:** Python 3.10+, Textual (workers, custom messages), openai SDK streaming, pytest (+ pilot tests), dataclasses.

**Companion spec:** [`2026-06-10-tui-chat-client-design.md`](2026-06-10-tui-chat-client-design.md) (W1-W4, DoD).

**Before you start (executor, once):**

```bash
git checkout master && git checkout -b tui-chat-client
git add docs/plans/2026-06-10-tui-chat-client-design.md docs/plans/2026-06-10-tui-chat-client-implementation.md
git commit -m "docs(plans): sub-project D (TUI chat client) spec & plan"
```

Every commit ends with the trailer line: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
A repo hook rejects file writes containing an em-dash or the word "leverage". Single-file pytest runs need `-o addopts=""`.
CLAUDE.md gotchas that bind here: no leading underscore on Textual `Message` subclasses (handler-name derivation); never define `_render`/`_bindings` on widgets.

---

### Task 1: `StreamEvent` and `OpenAIProvider.stream_turn`

**Files:**
- Modify: `ctk/llm/base.py` (add `StreamEvent` after `ChatResponse`; add `stream_turn` default on `LLMProvider`)
- Modify: `ctk/llm/openai.py` (implement `stream_turn`)
- Test: `tests/unit/test_llm_openai.py` (append; reuse its `SimpleNamespace` helpers and `mock_openai` fixture)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_llm_openai.py`:

```python
# ---------------------------------------------------------------------------
# stream_turn() (unified streaming with tools)
# ---------------------------------------------------------------------------


def _chunk(content=None, reasoning=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(content=content, reasoning=reasoning, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tc_frag(index, id=None, name=None, arguments=None):
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=id, function=fn)


class TestOpenAIProviderStreamTurn:
    def _events(self, mock_openai, chunks, tools=None):
        mock_openai.chat.completions.create.return_value = iter(chunks)
        provider = OpenAIProvider({"api_key": "k"})
        return list(
            provider.stream_turn(
                [Message(role=MessageRole.USER, content="hi")], tools=tools
            )
        )

    def test_text_and_reasoning_deltas_become_events(self, mock_openai):
        events = self._events(
            mock_openai,
            [
                _chunk(reasoning="thin"),
                _chunk(reasoning="king"),
                _chunk(content="Hel"),
                _chunk(content="lo"),
                _chunk(finish_reason="stop"),
            ],
        )
        kinds = [(e.kind, e.text) for e in events[:-1]]
        assert kinds == [
            ("reasoning", "thin"),
            ("reasoning", "king"),
            ("text", "Hel"),
            ("text", "lo"),
        ]
        assert events[-1].kind == "done"
        assert events[-1].finish_reason == "stop"

    def test_fragmented_tool_call_arguments_are_assembled(self, mock_openai):
        # Real OpenAI fragments the argument string across deltas, same index.
        events = self._events(
            mock_openai,
            [
                _chunk(tool_calls=[_tc_frag(0, id="tc-1", name="search", arguments="")]),
                _chunk(tool_calls=[_tc_frag(0, arguments='{"q": "')]),
                _chunk(tool_calls=[_tc_frag(0, arguments='x"}')]),
                _chunk(finish_reason="tool_calls"),
            ],
            tools=[{"name": "search", "description": "d", "input_schema": {}}],
        )
        tool_events = [e for e in events if e.kind == "tool_calls"]
        assert len(tool_events) == 1
        assert tool_events[0].tool_calls == [
            {"id": "tc-1", "name": "search", "arguments": {"q": "x"}}
        ]
        assert events[-1].kind == "done"
        assert events[-1].finish_reason == "tool_calls"

    def test_single_shot_tool_call_delta_works(self, mock_openai):
        # ollama delivers one complete delta (verified against the real server).
        events = self._events(
            mock_openai,
            [
                _chunk(reasoning="hmm"),
                _chunk(
                    tool_calls=[
                        _tc_frag(0, id="call_1", name="get_weather",
                                 arguments='{"city":"Paris"}')
                    ]
                ),
                _chunk(finish_reason="tool_calls"),
            ],
            tools=[{"name": "get_weather", "description": "d", "input_schema": {}}],
        )
        tool_events = [e for e in events if e.kind == "tool_calls"]
        assert tool_events[0].tool_calls == [
            {"id": "call_1", "name": "get_weather", "arguments": {"city": "Paris"}}
        ]

    def test_bad_tool_json_degrades_to_empty_dict(self, mock_openai):
        events = self._events(
            mock_openai,
            [
                _chunk(tool_calls=[_tc_frag(0, id="t", name="x", arguments="not json")]),
                _chunk(finish_reason="tool_calls"),
            ],
            tools=[{"name": "x", "description": "d", "input_schema": {}}],
        )
        tool_events = [e for e in events if e.kind == "tool_calls"]
        assert tool_events[0].tool_calls == [{"id": "t", "name": "x", "arguments": {}}]

    def test_base_provider_default_raises(self):
        from ctk.llm.base import LLMProvider

        class Bare(LLMProvider):
            def chat(self, messages, **kw):  # pragma: no cover
                raise NotImplementedError

            def stream_chat(self, messages, **kw):  # pragma: no cover
                raise NotImplementedError

            def get_models(self):  # pragma: no cover
                return []

            def validate_config(self):  # pragma: no cover
                return True

        with pytest.raises(NotImplementedError):
            list(Bare({}).stream_turn([]))
```

NOTE: `Bare` must implement whatever abstract methods `LLMProvider` declares; read the ABC and adjust the stub list (keep the assertion identical). If `validate_config` is not abstract, drop it.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_llm_openai.py -k stream_turn -v -o addopts=""`
Expected: FAIL/ERROR (`stream_turn` does not exist).

- [ ] **Step 3: Implement `StreamEvent` + base default**

In `ctk/llm/base.py`, after the `ChatResponse` dataclass, add:

```python
@dataclass
class StreamEvent:
    """One event from a unified streaming turn (``LLMProvider.stream_turn``).

    kind: "text" | "reasoning" | "tool_calls" | "done".
    ``text`` carries the delta for text/reasoning kinds. ``tool_calls`` is the
    fully assembled list (id/name/arguments) emitted once, before "done", when
    the model requested tools. ``finish_reason`` is set on "done".
    """

    kind: str
    text: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: Optional[str] = None
```

On `LLMProvider` (near `stream_chat`), add:

```python
    def stream_turn(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator["StreamEvent"]:
        """Stream a full turn (text, reasoning, and tool calls) as events.

        Default raises so concrete providers opt in explicitly.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement stream_turn"
        )
```

(Ensure `Iterator` is imported in base.py; add to the typing import if missing.)

- [ ] **Step 4: Implement `OpenAIProvider.stream_turn`**

In `ctk/llm/openai.py`, after `stream_chat`, add:

```python
    def stream_turn(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[StreamEvent]:
        """Stream one turn as StreamEvents, tools included.

        Accumulates tool_call deltas keyed by index: real OpenAI fragments the
        argument string across chunks; ollama sends one complete delta. Both
        reduce to string concatenation per index.
        """
        payload = self._build_payload(
            messages, temperature, max_tokens, stream=True, tools=tools, **kwargs
        )
        try:
            stream = self._client.chat.completions.create(**payload)
            pending: Dict[int, Dict[str, Any]] = {}
            finish_reason: Optional[str] = None
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                piece = getattr(delta, "content", None)
                if piece:
                    yield StreamEvent(kind="text", text=piece)
                thought = getattr(delta, "reasoning", None)
                if thought:
                    yield StreamEvent(kind="reasoning", text=thought)
                for frag in getattr(delta, "tool_calls", None) or []:
                    idx = getattr(frag, "index", 0) or 0
                    slot = pending.setdefault(
                        idx, {"id": None, "name": None, "arguments": ""}
                    )
                    if getattr(frag, "id", None):
                        slot["id"] = frag.id
                    fn = getattr(frag, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            slot["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["arguments"] += fn.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
            if pending:
                assembled = []
                for idx in sorted(pending):
                    slot = pending[idx]
                    try:
                        arguments = json.loads(slot["arguments"] or "{}")
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "Tool-call arguments were not valid JSON: %s", exc
                        )
                        arguments = {}
                    assembled.append(
                        {
                            "id": slot["id"] or "",
                            "name": slot["name"] or "",
                            "arguments": arguments,
                        }
                    )
                yield StreamEvent(kind="tool_calls", tool_calls=assembled)
            yield StreamEvent(kind="done", finish_reason=finish_reason)
        except Exception as exc:
            raise self._translate_exception(exc) from exc
```

Notes: add `StreamEvent` to the `ctk.llm.base` import list in openai.py. `_build_payload` already handles `tools` (it formats them and only sets `tool_choice` when `stream=False`, which is correct here).

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/unit/test_llm_openai.py -v -o addopts=""`
Expected: all PASS (new stream_turn tests + all 23 existing).

- [ ] **Step 6: Gates + commit**

```bash
black ctk/llm/base.py ctk/llm/openai.py tests/unit/test_llm_openai.py
flake8 ctk/llm/base.py ctk/llm/openai.py tests/unit/test_llm_openai.py --max-line-length=100 --ignore=E203,W503
mypy ctk/llm/base.py ctk/llm/openai.py --ignore-missing-imports
git add ctk/llm/base.py ctk/llm/openai.py tests/unit/test_llm_openai.py
git commit -m "feat(llm): StreamEvent + stream_turn (unified streaming with tools, both delta shapes)"
```

(The pre-existing `F401 dataclasses.field` in base.py is master debt; only new warnings count.)

---

### Task 2: `stream_chat` becomes an adapter over `stream_turn`

**Files:**
- Modify: `ctk/llm/openai.py` (`stream_chat` body)
- Test: `tests/unit/test_llm_openai.py` (existing stream tests must keep passing; add one adapter test)

- [ ] **Step 1: Add the adapter test**

```python
    def test_stream_chat_is_thin_adapter_over_stream_turn(self, mock_openai):
        mock_openai.chat.completions.create.return_value = iter(
            [
                _chunk(reasoning="th"),
                _chunk(content="Hi"),
                _chunk(finish_reason="stop"),
            ]
        )
        provider = OpenAIProvider({"api_key": "k"})
        chunks = list(
            provider.stream_chat([Message(role=MessageRole.USER, content="hi")])
        )
        assert chunks == ["th", "Hi"]
```

(Place it in `TestOpenAIProviderStreamChat`.)

- [ ] **Step 2: Replace `stream_chat`'s body**

```python
    def stream_chat(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        # Thin adapter over stream_turn: text plus reasoning fallback, so
        # thinking models are never silently blank (2.16.2 behavior).
        for event in self.stream_turn(
            messages, temperature=temperature, max_tokens=max_tokens, **kwargs
        ):
            if event.kind in ("text", "reasoning") and event.text:
                yield event.text
```

- [ ] **Step 3: Run the provider suite**

Run: `pytest tests/unit/test_llm_openai.py -q -o addopts=""`
Expected: all PASS (including `test_yields_chunks` and `test_stream_yields_reasoning_when_no_content`).

- [ ] **Step 4: Commit**

```bash
git add ctk/llm/openai.py tests/unit/test_llm_openai.py
git commit -m "refactor(llm): stream_chat adapts over stream_turn (one streaming code path)"
```

---

### Task 3: `ThinkingBlock` widget and styles

**Files:**
- Modify: `ctk/tui/main_pane.py` (new widget after `BranchIndicator`)
- Modify: `ctk/tui/styles.tcss` (new classes)
- Test: `tests/unit/test_tui_streaming.py` (create; widget-level tests first)

- [ ] **Step 1: Write the failing widget tests**

Create `tests/unit/test_tui_streaming.py`:

```python
"""Pilot tests for the streaming chat turn: thinking block, live bubbles,
elapsed indicator, cancellation, and in-stream errors."""

from __future__ import annotations

import pytest

from ctk.tui.main_pane import ThinkingBlock

pytestmark = [pytest.mark.unit]


class TestThinkingBlock:
    def test_appends_and_reports_text(self):
        block = ThinkingBlock()
        block.append_reasoning("step one ")
        block.append_reasoning("step two")
        assert block.reasoning_text == "step one step two"
        assert not block.folded

    def test_fold_and_toggle(self):
        block = ThinkingBlock()
        block.append_reasoning("hmm")
        block.fold()
        assert block.folded
        block.action_toggle()
        assert not block.folded
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_tui_streaming.py -v -o addopts=""`
Expected: ImportError (no `ThinkingBlock`).

- [ ] **Step 3: Implement the widget**

In `ctk/tui/main_pane.py`, after `BranchIndicator`, add (note: never name widget members `_render`/`_bindings`, per CLAUDE.md):

```python
class ThinkingBlock(Static):
    """Collapsible chain-of-thought for one assistant turn.

    Streams reasoning deltas live while expanded; ``fold()`` collapses it to a
    one-line summary once the answer (or a tool call) begins. Focus + Enter
    toggles. Reasoning-only turns are left expanded by the app, because the
    reasoning is the de facto reply.
    """

    can_focus = True

    BINDINGS = [Binding("enter", "toggle", "thinking", show=False)]

    def __init__(self) -> None:
        super().__init__("", classes="message-thinking")
        self._reasoning_text = ""
        self._elapsed_s: float = 0.0
        self._started = time.monotonic()
        self._folded = False

    @property
    def reasoning_text(self) -> str:
        return self._reasoning_text

    @property
    def folded(self) -> bool:
        return self._folded

    def append_reasoning(self, text: str) -> None:
        self._reasoning_text += text
        if not self._folded:
            self._refresh_view()

    def fold(self) -> None:
        self._elapsed_s = time.monotonic() - self._started
        self._folded = True
        self._refresh_view()

    def action_toggle(self) -> None:
        self._folded = not self._folded
        self._refresh_view()

    def _refresh_view(self) -> None:
        if self._folded:
            self.update(
                Text(f"thought for {self._elapsed_s:.1f}s  (Enter to expand)",
                     style="dim italic")
            )
        else:
            self.update(Text(self._reasoning_text, style="dim"))
```

Add imports to main_pane.py if missing: `import time` and `from textual.binding import Binding` (check existing imports first; `Text` is already imported).

- [ ] **Step 4: Add styles**

Append to `ctk/tui/styles.tcss` (mirror the look of `.message-tool` / `.message-system` blocks; read them and match the property style):

```css
.message-thinking {
    color: $text-muted;
    margin: 0 2 0 4;
    padding: 0 1;
    border-left: solid $secondary;
}

.message-thinking:focus {
    border-left: thick $accent;
}

.message-error {
    color: $error;
    margin: 0 2 0 4;
    padding: 0 1;
    border-left: thick $error;
}

.turn-indicator {
    color: $text-muted;
    margin: 0 2 0 4;
    text-style: italic;
}
```

- [ ] **Step 5: Run widget tests + existing TUI suite**

```bash
pytest tests/unit/test_tui_streaming.py -v -o addopts=""
pytest tests/unit/test_textual_tui.py -q -o addopts=""
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add ctk/tui/main_pane.py ctk/tui/styles.tcss tests/unit/test_tui_streaming.py
git commit -m "feat(tui): collapsible ThinkingBlock widget + thinking/error/indicator styles"
```

---

### Task 4: Streaming tool worker and UI handlers

This is the core task. It rewrites `_chat_worker_with_tools` to consume `stream_turn`, adds the `ReasoningToken`/`TurnStarted` messages, extends `ChatAssistantText` and `ChatDone`, makes the live bubble lazy, folds thinking, and persists `ReasoningBlock`s.

**Files:**
- Modify: `ctk/tui/app.py`
- Test: `tests/unit/test_tui_streaming.py` (append pilot tests)

- [ ] **Step 1: Write the failing pilot tests**

Append to `tests/unit/test_tui_streaming.py`:

```python
import asyncio

from ctk.core.database import ConversationDB
from ctk.core.models import MessageRole
from ctk.llm.base import Message as LLMMessage
from ctk.llm.base import MessageRole as LLMMessageRole
from ctk.llm.base import StreamEvent
from ctk.tui.app import CTKApp


class ScriptedProvider:
    """stream_turn yields scripted event turns; each call pops the next turn."""

    model = "scripted"
    base_url = "http://fake.local"

    def __init__(self, turns):
        self._turns = list(turns)

    def is_available(self):
        return True

    def supports_tool_calling(self):
        return True

    def stream_turn(self, messages, tools=None, **kwargs):
        for event in self._turns.pop(0):
            yield event

    def format_tool_result_message(self, name, result, tool_call_id=None):
        return LLMMessage(role=LLMMessageRole.USER, content=str(result))


async def _drive_turn(app, pilot, text="ping", max_steps=200):
    user_msg = app._append_user_message(text)
    app._turn_active = True
    app.main.set_streaming(True)
    app._active_worker = app._chat_worker_with_tools(user_msg.id)
    for _ in range(max_steps):
        await pilot.pause(0.05)
        if not app._turn_active:
            break


def _assistant_messages(app):
    return [
        m
        for m in app._current_tree.message_map.values()
        if m.role == MessageRole.ASSISTANT
    ]


@pytest.mark.asyncio
async def test_text_streams_and_persists(tmp_path):
    provider = ScriptedProvider(
        [[StreamEvent(kind="text", text="Hel"),
          StreamEvent(kind="text", text="lo"),
          StreamEvent(kind="done", finish_reason="stop")]]
    )
    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            msgs = _assistant_messages(app)
            assert [m.content.text for m in msgs] == ["Hello"]
            assert app._turn_active is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_reasoning_streams_folds_on_text_and_persists(tmp_path):
    provider = ScriptedProvider(
        [[StreamEvent(kind="reasoning", text="thinking..."),
          StreamEvent(kind="text", text="Answer"),
          StreamEvent(kind="done", finish_reason="stop")]]
    )
    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            from ctk.tui.main_pane import ThinkingBlock

            blocks = list(app.query(ThinkingBlock))
            assert len(blocks) == 1
            assert blocks[0].folded  # folded when the answer began
            msg = _assistant_messages(app)[0]
            assert msg.content.text == "Answer"
            assert len(msg.content.reasoning) == 1
            assert msg.content.reasoning[0].text == "thinking..."
    finally:
        db.close()


@pytest.mark.asyncio
async def test_reasoning_only_turn_stays_expanded_and_is_the_reply(tmp_path):
    provider = ScriptedProvider(
        [[StreamEvent(kind="reasoning", text="only thoughts"),
          StreamEvent(kind="done", finish_reason="stop")]]
    )
    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            from ctk.tui.main_pane import ThinkingBlock

            blocks = list(app.query(ThinkingBlock))
            assert len(blocks) == 1
            assert not blocks[0].folded  # the reasoning IS the reply
            msg = _assistant_messages(app)[0]
            assert msg.content.text == "only thoughts"  # never-blank fallback
            assert msg.content.reasoning[0].text == "only thoughts"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_tool_loop_streams_two_turns(tmp_path, monkeypatch):
    provider = ScriptedProvider(
        [
            [StreamEvent(kind="reasoning", text="need a tool"),
             StreamEvent(kind="tool_calls",
                         tool_calls=[{"id": "t1", "name": "list_tags",
                                      "arguments": {}}]),
             StreamEvent(kind="done", finish_reason="tool_calls")],
            [StreamEvent(kind="text", text="Done!"),
             StreamEvent(kind="done", finish_reason="stop")],
        ]
    )
    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=provider, enable_tools=True)
    monkeypatch.setattr(app, "_execute_tool", lambda name, args: "tool-ok")
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            texts = [m.content.text for m in _assistant_messages(app)]
            assert "Done!" in texts
            assert app._turn_active is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_error_renders_in_transcript(tmp_path):
    class ExplodingProvider(ScriptedProvider):
        def stream_turn(self, messages, tools=None, **kwargs):
            raise RuntimeError("endpoint exploded")
            yield  # pragma: no cover

    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=ExplodingProvider([]), enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            await _drive_turn(app, pilot)
            assert app._turn_active is False
            error_nodes = list(app.query(".message-error"))
            assert error_nodes, "provider error must render in the transcript"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_escape_cancels_inflight_turn(tmp_path):
    class SlowProvider(ScriptedProvider):
        def stream_turn(self, messages, tools=None, **kwargs):
            import time as _t

            for i in range(200):
                _t.sleep(0.02)
                yield StreamEvent(kind="reasoning", text=f"step{i} ")
            yield StreamEvent(kind="done", finish_reason="stop")

    db = ConversationDB(str(tmp_path / "db"))
    app = CTKApp(db=db, provider=SlowProvider([]), enable_tools=True)
    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            user_msg = app._append_user_message("ping")
            app._turn_active = True
            app.main.set_streaming(True)
            app._active_worker = app._chat_worker_with_tools(user_msg.id)
            await pilot.pause(0.3)  # let some reasoning stream
            app.action_cancel_turn_or_dismiss()
            for _ in range(100):
                await pilot.pause(0.05)
                if not app._turn_active:
                    break
            assert app._turn_active is False
            cancelled_nodes = [
                n for n in app.query(Static) if "cancelled" in str(n.renderable)
            ]
            assert cancelled_nodes, "a (cancelled) marker must be appended"
    finally:
        db.close()
```

Add `from textual.widgets import Static` to the test imports.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_tui_streaming.py -v -o addopts="" 2>&1 | tail -15`
Expected: the new pilot tests FAIL (no `_active_worker`, no `action_cancel_turn_or_dismiss`, worker is non-streaming).

- [ ] **Step 3: Message classes and state (app.py)**

After the existing `ChatDone` class, add (NO leading underscores):

```python
class ReasoningToken(TextualMessage):
    """One streamed reasoning (thinking) delta in the tool path."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class TurnStarted(TextualMessage):
    """A model turn began (first turn or re-entry after tool execution)."""

    def __init__(self, turn_index: int) -> None:
        super().__init__()
        self.turn_index = turn_index
```

Extend `ChatAssistantText.__init__` to carry reasoning (keep positional back-compat):

```python
    def __init__(self, text: str, final: bool, reasoning: str = "") -> None:
        super().__init__()
        self.text = text
        self.final = final
        self.reasoning = reasoning
```

Extend `ChatDone.__init__`:

```python
    def __init__(self, error: Optional[str] = None, cancelled: bool = False) -> None:
        super().__init__()
        self.error = error
        self.cancelled = cancelled
```

In `CTKApp.__init__`, alongside `self._turn_active`, add:

```python
        self._active_worker: Optional[Any] = None
        self._thinking_block: Optional[ThinkingBlock] = None
        self._turn_indicator: Optional[Static] = None
        self._turn_indicator_timer: Optional[Any] = None
        self._turn_started_at: float = 0.0
```

Imports: add `ThinkingBlock` to the `from ctk.tui.main_pane import ...` line, `ReasoningBlock` to the `from ctk.core.models import (...)` block, and `import time` if absent.

- [ ] **Step 4: Rewrite the worker**

Replace the entire body of `_chat_worker_with_tools` (keep the decorator and docstring spirit):

```python
    @work(thread=True, exclusive=True)
    def _chat_worker_with_tools(self, parent_msg_id: str) -> None:
        """Stream a tool-enabled chat turn (text, reasoning, tools live).

        Consumes ``provider.stream_turn`` events, posting one UI message per
        delta. Tool calls execute here in the worker thread; the loop then
        re-enters streaming for the next turn. Cancellation is polled between
        events (a blocked network read defers it to the next chunk).
        """
        from textual.worker import get_current_worker

        from ctk.core.tools import get_ask_tools  # lazy: tests don't need it

        worker = get_current_worker()

        def _cancelled() -> bool:
            return worker is not None and worker.is_cancelled

        try:
            assert self.provider is not None
            history = self._llm_history_for(self._current_tree)
            tools = get_ask_tools(include_pass_through=False)

            for turn in range(self._MAX_TOOL_TURNS):
                self.post_message(TurnStarted(turn))
                turn_text = ""
                turn_reasoning = ""
                tool_calls: List[Dict[str, Any]] = []

                for event in self.provider.stream_turn(history, tools=tools):
                    if _cancelled():
                        self.post_message(
                            ChatAssistantText(
                                turn_text, final=True, reasoning=turn_reasoning
                            )
                        )
                        self.post_message(ChatDone(cancelled=True))
                        return
                    if event.kind == "text":
                        turn_text += event.text
                        self.post_message(StreamToken(event.text))
                    elif event.kind == "reasoning":
                        turn_reasoning += event.text
                        self.post_message(ReasoningToken(event.text))
                    elif event.kind == "tool_calls":
                        tool_calls = event.tool_calls or []

                if turn_text or turn_reasoning:
                    self.post_message(
                        ChatAssistantText(
                            turn_text,
                            final=not tool_calls,
                            reasoning=turn_reasoning,
                        )
                    )
                    if turn_text:
                        history.append(
                            LLMMessage(
                                role=LLMMessageRole.ASSISTANT, content=turn_text
                            )
                        )

                if not tool_calls:
                    self.post_message(ChatDone())
                    return

                for tc in tool_calls:
                    if _cancelled():
                        self.post_message(ChatDone(cancelled=True))
                        return
                    name = tc["name"]
                    args = tc.get("arguments") or {}
                    self.post_message(
                        ChatToolCall(name=name, args=args, status="started")
                    )
                    try:
                        result = self._execute_tool(name, args)
                        self.post_message(
                            ChatToolCall(
                                name=name, args=args, status="ok", result=result
                            )
                        )
                    except Exception as exc:
                        self.post_message(
                            ChatToolCall(
                                name=name,
                                args=args,
                                status="error",
                                result=str(exc),
                            )
                        )
                        result = f"Tool error: {exc}"
                    history.append(
                        self.provider.format_tool_result_message(
                            name, result, tool_call_id=tc.get("id")
                        )
                    )

            self.post_message(
                ChatDone(
                    error=(
                        f"Tool loop exceeded {self._MAX_TOOL_TURNS} turns; "
                        "stopping. The model may be stuck calling tools."
                    )
                )
            )
        except Exception as exc:  # pragma: no cover
            self.post_message(ChatDone(error=str(exc)))
```

- [ ] **Step 5: UI handlers (app.py)**

In `on_chat_input_submitted`, capture the worker handle (both paths):

```python
        if self.enable_tools:
            self._active_worker = self._chat_worker_with_tools(user_msg.id)
        else:
            self._start_streaming_bubble(user_msg.id)
            self._active_worker = self._stream_worker(
                self._llm_history_for(self._current_tree)
            )
```

Add the turn-indicator helpers and new handlers (place near the other chat handlers):

```python
    def on_turn_started(self, event: TurnStarted) -> None:
        self._show_turn_indicator()

    def _show_turn_indicator(self) -> None:
        if self.main is None or self._turn_indicator is not None:
            return
        self._turn_started_at = time.monotonic()
        self._turn_indicator = Static(
            Text("thinking… (0s)"), classes="turn-indicator"
        )
        self.main.messages.mount(self._turn_indicator)
        self.main.messages.scroll_end(animate=False)
        self._turn_indicator_timer = self.set_interval(
            1.0, self._tick_turn_indicator
        )

    def _tick_turn_indicator(self) -> None:
        if self._turn_indicator is None:
            return
        elapsed = int(time.monotonic() - self._turn_started_at)
        self._turn_indicator.update(Text(f"thinking… ({elapsed}s)"))

    def _clear_turn_indicator(self) -> None:
        if self._turn_indicator_timer is not None:
            self._turn_indicator_timer.stop()
            self._turn_indicator_timer = None
        if self._turn_indicator is not None:
            self._turn_indicator.remove()
            self._turn_indicator = None

    def on_reasoning_token(self, event: ReasoningToken) -> None:
        if self.main is None:
            return
        self._clear_turn_indicator()
        if self._thinking_block is None:
            self._thinking_block = ThinkingBlock()
            self.main.messages.mount(self._thinking_block)
        self._thinking_block.append_reasoning(event.text)
        self.main.messages.scroll_end(animate=False)

    def _fold_thinking(self) -> None:
        if self._thinking_block is not None and not self._thinking_block.folded:
            self._thinking_block.fold()

    def _ensure_live_bubble(self) -> None:
        """Lazy visual bubble for streamed text in the tool path.

        Unlike _start_streaming_bubble (the no-tools path), this mounts a
        purely visual bubble: the tree Message is created at turn end by
        on_chat_assistant_text, with reasoning attached.
        """
        assert self.main is not None
        bubble_msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.ASSISTANT,
            content=MessageContent(text=""),
            parent_id=None,
            timestamp=datetime.now(),
        )
        self._streaming_buffer = ""
        bubble = MessageBubble(bubble_msg)
        self._streaming_bubble = bubble
        self.main.messages.mount(
            Static(Text("bot", style="bold green"), classes="message-role")
        )
        self.main.messages.mount(bubble)
        self.main.messages.scroll_end(animate=False)
```

Modify `on_stream_token` so the tool path lazily creates its bubble (the no-tools path pre-creates one, so behavior there is unchanged):

```python
    def on_stream_token(self, event: StreamToken) -> None:
        self._clear_turn_indicator()
        self._fold_thinking()
        if self._streaming_bubble is None:
            if not self._turn_active or self.main is None:
                return
            self._ensure_live_bubble()
        self._streaming_buffer += event.text
        self._update_streaming_bubble(self._streaming_buffer)
```

Replace `on_chat_assistant_text` (it now finalizes instead of mounting a duplicate bubble):

```python
    def on_chat_assistant_text(self, event: ChatAssistantText) -> None:
        """Finalize one turn: persist text + reasoning into the tree.

        The visual bubble already exists (streamed live); reasoning-only
        turns have no bubble and keep their expanded ThinkingBlock as the
        visible reply.
        """
        if self.main is None or self._current_tree is None:
            return
        parent_id = None
        path = self._current_tree.get_longest_path()
        if path:
            parent_id = path[-1].id
        content = MessageContent(text=event.text or event.reasoning or "")
        if event.reasoning:
            content.reasoning.append(ReasoningBlock(text=event.reasoning))
        assistant_msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.ASSISTANT,
            content=content,
            parent_id=parent_id,
            timestamp=datetime.now(),
        )
        self._current_tree.add_message(assistant_msg)
        # Reset per-turn live widgets so the next turn creates fresh ones.
        self._streaming_bubble = None
        self._streaming_buffer = ""
        self._thinking_block = None
```

In `on_chat_tool_call`, add two lines at the top (before building the panel text):

```python
        self._clear_turn_indicator()
        self._fold_thinking()
```

Replace `on_chat_done`:

```python
    def on_chat_done(self, event: ChatDone) -> None:
        self._clear_turn_indicator()
        if self.main is not None:
            if event.cancelled:
                self.main.messages.mount(
                    Static(Text("(cancelled)", style="dim italic"),
                           classes="message-system")
                )
            if event.error:
                self.main.messages.mount(
                    Static(Text(f"error: {event.error}"), classes="message-error")
                )
                self.main.messages.scroll_end(animate=False)
            self.main.set_streaming(False)
        self._turn_active = False
        self._active_worker = None
        self._streaming_bubble = None
        self._streaming_buffer = ""
        self._thinking_block = None
        if event.error:
            self.notify(event.error, severity="error")
        if self._current_tree is not None:
            self._safe_save(self._current_tree)
        if self.sidebar is not None:
            self.sidebar.refresh_list()
        self._refresh_status()
```

- [ ] **Step 6: Escape arbitration**

Change the binding (line ~178): `Binding("escape", "cancel_turn_or_dismiss", "cancel", show=False)`. Add the action next to `action_dismiss_search`:

```python
    def action_cancel_turn_or_dismiss(self) -> None:
        """Escape: cancel an in-flight turn, else dismiss the search overlay."""
        if self._turn_active and self._active_worker is not None:
            self._active_worker.cancel()
            return
        self.action_dismiss_search()
```

- [ ] **Step 7: Run the pilot tests + full TUI suites**

```bash
pytest tests/unit/test_tui_streaming.py -v -o addopts="" 2>&1 | tail -15
pytest tests/unit/test_textual_tui.py tests/unit/test_tui_chat_dispatch.py -q -o addopts="" 2>&1 | tail -3
```
Expected: all PASS. The dispatch-guard test automatically validates `ReasoningToken` -> `on_reasoning_token` and `TurnStarted` -> `on_turn_started`. If `test_tui_chat_dispatch.py`'s behavioral test fails because its `_FakeProvider` lacks `stream_turn`, give that fake a `stream_turn` yielding `[StreamEvent(kind="text", text="PONG-REPLY"), StreamEvent(kind="done", finish_reason="stop")]` (the contract moved with the worker; note it in the commit body).

- [ ] **Step 8: Gates + commit**

```bash
black ctk/tui/app.py tests/unit/test_tui_streaming.py tests/unit/test_tui_chat_dispatch.py
flake8 ctk/tui/app.py tests/unit/test_tui_streaming.py --max-line-length=100 --ignore=E203,W503
mypy ctk/tui/app.py --ignore-missing-imports
git add ctk/tui/app.py tests/unit/test_tui_streaming.py tests/unit/test_tui_chat_dispatch.py
git commit -m "feat(tui): streaming tool turns (live text+reasoning, fold-on-answer, elapsed, Escape-cancel, in-stream errors)"
```

---

### Task 5: Full-suite gate and real-model smoke

**Files:** none (verification; small fixes only)

- [ ] **Step 1: Full gated suite + integration**

```bash
python -m pytest tests/unit 2>&1 | tail -3
python -m pytest tests/integration -o addopts="" 2>&1 | tail -2
mypy ctk --ignore-missing-imports
```
Expected: all pass, coverage at or above 59, mypy 0.

- [ ] **Step 2: Real-model smoke (requires the user's ollama at 192.168.0.204)**

```bash
timeout 180 python3 - <<'PY'
import asyncio, tempfile
from ctk.core.database import ConversationDB
from ctk.tui.app import CTKApp
from ctk.llm.factory import build_provider
from ctk.core.models import MessageRole
from ctk.tui.main_pane import ThinkingBlock

async def main():
    db = ConversationDB(tempfile.mkdtemp())
    app = CTKApp(db=db, provider=build_provider(), enable_tools=True)
    async with app.run_test() as pilot:
        await pilot.pause()
        um = app._append_user_message("hi, who are you in one sentence?")
        app._turn_active = True; app.main.set_streaming(True)
        app._active_worker = app._chat_worker_with_tools(um.id)
        waited = 0.0
        while app._turn_active and waited < 150:
            await pilot.pause(0.3); waited += 0.3
        blocks = list(app.query(ThinkingBlock))
        msgs = [m for m in app._current_tree.message_map.values()
                if m.role == MessageRole.ASSISTANT]
        print("turn cleared:", not app._turn_active, f"after {waited:.0f}s")
        print("thinking blocks:", len(blocks),
              "| folded:", [b.folded for b in blocks])
        print("assistant text head:", repr((msgs[0].content.text or "")[:80]) if msgs else None)
        print("reasoning persisted:", bool(msgs and msgs[0].content.reasoning))
    db.close()

asyncio.run(main())
PY
```
Expected: turn cleared True; at least one ThinkingBlock; assistant text non-empty; reasoning persisted True. (Fold state depends on whether the model emitted separate content; reasoning-only turns legitimately stay expanded.)

- [ ] **Step 3: Commit anything the gates changed**

```bash
git add -u && git commit --allow-empty -m "chore: tui chat client green gate (suite, mypy, real-model streaming smoke)"
```

---

## Self-review notes (for the executor)

- Task 4 is large; its steps are ordered so the file stays importable after each step. Run
  the dispatch-guard test (`test_tui_chat_dispatch.py`) after adding the new message classes
  to catch handler-name drift immediately.
- The no-tools path (`_stream_worker` / `on_stream_done`) is intentionally untouched except
  that `on_stream_token` gained the lazy-bubble branch (guarded so the no-tools flow, which
  pre-creates its bubble and tree message, behaves exactly as before).
- Cancellation is polled between events: a stream blocked waiting for the first chunk will
  not cancel until that chunk arrives. This is a documented limitation (spec W2), not a bug
  to fix here.
- Do not weaken the pilot assertions; they are the coverage this path never had.
