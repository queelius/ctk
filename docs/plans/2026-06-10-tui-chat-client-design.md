# Sub-project D: TUI as a Real Chat Client (Design)

**Date:** 2026-06-10
**Status:** Design (approved in discussion; pending spec review)
**Part of:** [CTK Improvement Program](2026-06-04-improvement-program-roadmap.md), sub-project D
**Decisions taken with user:** full streaming-with-tools (not the lighter progress-only
variant); collapsible thinking rendering (auto-fold once the answer begins).

---

## 1. Goal and definition of done

Make a chat turn feel alive and controllable. Today the tool-enabled path (the default) is a
blocking `provider.chat()` loop with no progress indicator, no cancel, toast-only errors, and
raw chain-of-thought dumped as the reply text. Three shipped hotfixes (2.16.1 dispatch,
2.16.2 reasoning fallback) each exposed the next rough edge; this sub-project fixes the turn
experience as a whole.

**Definition of done:**

1. With tools enabled, assistant text AND reasoning stream token-by-token into the UI; tool
   calls execute mid-stream and the loop re-enters streaming for the next turn.
2. Reasoning renders as a collapsible block: streams live while the model thinks, auto-folds
   to a one-line `thought for Ns` summary once the first answer token arrives, toggles open
   on focus + Enter. When a turn produces ONLY reasoning (empty content), the block stays
   expanded because it is the de facto reply.
3. A live elapsed indicator (`thinking… (Ns)`) shows before the first token and between tool
   turns; it never sits next to already-streaming content.
4. Escape cancels an in-flight turn: the stream closes, partial content is kept with a dim
   `(cancelled)` marker, turn state resets, and the input unlocks. When no turn is active,
   Escape keeps its existing dismiss-search behavior.
5. Provider and tool errors render as a distinct message in the transcript (not only a
   transient toast).
6. The assistant message persisted to the DB carries reasoning as `ReasoningBlock`s (the
   structured field shipped in 2.16.0), so saved conversations keep their thinking and the
   markdown exporter renders it.
7. Suite green: mypy 0, coverage at or above 59, all unit + integration tests pass; the new
   streaming worker and widgets have pilot coverage (the old worker had none, which is how
   2.16.1's bug shipped).

---

## 2. Empirical grounding (probed against the user's real stack)

Probed ollama's OpenAI-compatible endpoint (gemma4:12b) with `stream=True` and tools:

- `delta.reasoning` streams live: 98 reasoning deltas for one turn.
- `delta.tool_calls` arrives in-stream and `finish_reason == "tool_calls"`. ollama delivers
  the tool call as ONE complete delta (full id, name, complete JSON argument string), while
  real OpenAI fragments the argument string across many deltas keyed by `index`.
  The accumulator therefore handles both shapes; a single complete fragment is the
  degenerate case of index-keyed accumulation.
- `delta.content` was 0 for this model/turn: the thinking block is the only live feedback
  until an answer or tool call appears, which is why it must stream.

---

## 3. Architecture

### W1: Unified streaming interface (`ctk/llm/`)

New event type and provider method (additive; existing `chat()` is untouched because the
CLI and auto-tag depend on its blocking semantics):

```python
@dataclass
class StreamEvent:
    kind: str                # "text" | "reasoning" | "tool_calls" | "done"
    text: str = ""           # delta payload for text/reasoning
    tool_calls: Optional[List[Dict[str, Any]]] = None  # assembled, on "tool_calls"
    finish_reason: Optional[str] = None                # on "done"

def stream_turn(self, messages, *, tools=None, temperature=0.7,
                max_tokens=None, **kwargs) -> Iterator[StreamEvent]
```

`OpenAIProvider.stream_turn` opens one streaming completion (passing `tools` through the
existing payload builder) and per chunk:

- `delta.content` yields `StreamEvent(kind="text", text=...)`.
- `delta.reasoning` yields `StreamEvent(kind="reasoning", text=...)`.
- `delta.tool_calls` accumulates fragments into an index-keyed dict
  (`id`, `name`, argument-string concatenation); at stream end, if any were seen, yield one
  `StreamEvent(kind="tool_calls", tool_calls=[...])` with arguments JSON-parsed (the same
  bad-JSON-degrades-to-empty-dict policy `chat()` already uses).
- Finally yield `StreamEvent(kind="done", finish_reason=...)`.

`stream_chat()` becomes a thin adapter over `stream_turn` (yield only text-kind events'
text), so there is one streaming code path. Errors translate through the existing
`_translate_exception` taxonomy.

### W2: Streaming tool worker (`ctk/tui/app.py`)

`_chat_worker_with_tools` is rewritten to consume `stream_turn`:

- For each turn (bounded by the existing `_MAX_TOOL_TURNS`): iterate events, posting
  `StreamToken`-style messages for text and a new `ReasoningToken` message for reasoning;
  on `tool_calls`, post the existing `ChatToolCall` started/ok/error messages, execute via
  the existing `_execute_tool`, append tool-result messages to history, and re-enter
  `stream_turn`.
- The worker checks Textual's `get_current_worker().is_cancelled` between events and exits
  promptly when cancelled (closing the SDK stream by letting the generator be garbage
  collected after `break`; the underlying httpx response closes with it).
- Turn-boundary bookkeeping (which bubble is live, when to fold thinking) lives in the UI
  handlers, driven by the event messages; the worker stays UI-free.
- Message classes follow the no-leading-underscore rule (CLAUDE.md gotcha from 2.16.1);
  the structural dispatch-guard test automatically covers any new message class.

### W3: Widgets and controls (`ctk/tui/main_pane.py`, `ctk/tui/app.py`)

- **ThinkingBlock widget:** collapsible container streaming reasoning deltas live while
  expanded. Auto-folds to `thought for Ns` when the first text token of the same turn
  arrives; focusable, Enter toggles. If the turn ends with no text and no tool calls, it
  stays expanded (reasoning-only reply). Per-turn instance in the message stream.
- **Elapsed indicator:** a one-line `thinking… (Ns)` Static shown when a turn starts and
  between tool turns, updated by a timer, removed when the first event of the next phase
  renders.
- **Escape arbitration:** the existing `escape` binding routes by state: if
  `_turn_active`, cancel the worker (then the worker-cancelled path appends the dim
  `(cancelled)` marker and resets state); elif the search overlay is open, dismiss it
  (current behavior); else no-op.
- **In-stream errors:** a `message-error` styled Static mounted into the transcript for
  provider/tool failures (the toast may stay as a secondary cue).

### W4: Persistence

On turn completion (or cancel), the assistant `Message` stored into the tree carries:
`content.text` = streamed text (or the streamed reasoning when the turn was reasoning-only,
preserving 2.16.2's never-blank behavior), and `content.reasoning` = the turn's reasoning as
a single `ReasoningBlock` whenever any reasoning streamed. DB round-trip and markdown
rendering then come free from sub-project B's work.

---

## 4. Out of scope (deferred to later passes)

- Message affordances: copy, edit-and-resend, regenerate.
- Sidebar debounce and incremental search; `q`-binding scoping.
- Context-window management and retry/backoff (E-scale).
- Rendering reasoning in the HTML exporter (F).

---

## 5. Testing

- **Provider unit tests** (`tests/unit/test_llm_openai.py` pattern): mocked streams
  interleaving content, reasoning, and tool_call deltas; assert event sequence, both
  tool_call shapes (fragmented arguments and single complete delta), bad-JSON degradation,
  and that `stream_chat` still yields plain text.
- **Pilot tests** (new `tests/unit/test_tui_streaming.py`): fake provider with scripted
  `stream_turn` events; assert live text mounts, thinking folds on first answer token,
  reasoning-only turns stay expanded, Escape mid-turn cancels (turn state resets, marker
  appended), error events render in-stream, and the dispatch-guard still passes.
- **Real-data smoke** before release: the year-ago query against gemma4:12b shows streaming
  thinking, a folded block, and a visible final answer.

---

## 6. Release

Ships as **2.17.0** after merge, user-gated as usual.

---

## 7. Definition-of-done checklist

- [ ] `StreamEvent` + `LLMProvider.stream_turn` + `OpenAIProvider` implementation (both
      tool_call delta shapes); `stream_chat` adapts over it.
- [ ] Worker consumes events, executes tools mid-stream, re-enters streaming, honors
      cancellation between events.
- [ ] ThinkingBlock: streams live, auto-folds on first answer token, Enter toggles,
      reasoning-only stays expanded.
- [ ] Elapsed indicator before first token and between tool turns.
- [ ] Escape cancels an active turn (keeps partial output, `(cancelled)` marker, state
      reset); falls through to dismiss-search when idle.
- [ ] Errors render in the transcript.
- [ ] Persisted assistant messages carry `ReasoningBlock`s; DB round-trip verified.
- [ ] Provider + pilot tests green; mypy 0; coverage at or above 59; real-model smoke.
