# Approach B — Data-Parts Architecture for Concurrent Turns (exploration)

Status: **exploration completed, reverted**. The pattern works but introduced
enough rough edges (repetitive `send_message_to_user` rendering, two-flicker
indicator transitions, status-machine bypass) that the project chose to revert
to the standard `useChat`-driven streaming pattern. This document captures
what we built, why it worked, what didn't feel clean, and the code shape so
that a future re-exploration can pick up from here without re-deriving it.

## The problem we were trying to solve

OpenPoke originally couples user-send and assistant-receive through a single
HTTP POST per turn:

```
POST /api/threads/:id/messages/stream  ──►  SSE response with text-delta,
                                              tool-input-*, etc.
```

`useChat` from `@ai-sdk/react` holds a single mutable
`this.activeResponse` slot per `Chat` instance. A second `sendMessage` while
the first is mid-stream overwrites the slot, corrupting the first turn's
lifecycle and producing `Cannot read 'state' of undefined` plus duplicate
`msg-<uuid>` keys plus visible content multiplication on every subsequent send.

Concretely: when the input was unlocked during `streaming` to allow
parallel conversation, the system broke as soon as the user typed a second
message before the first finished.

The goal: let the user type a new message while the previous turn is still
streaming (and possibly while execution agents are still running in the
background), without state corruption.

## Why `useChat`'s default flow couldn't deliver

Inside `@ai-sdk/react`:

- One `Chat` instance per `useChat` call.
- Each `sendMessage` invokes `makeRequest` which sets
  `this.activeResponse = activeResponse` (a shared mutable slot).
- The active-response object is read in the `finally` block to call
  `onFinish({ message: this.activeResponse.state.message, … })`.
- A second concurrent `makeRequest` overwrites that slot. The first
  turn's `finally` reads the wrong (or undefined) value → TypeError.

`useChat` is fundamentally one-stream-at-a-time per `Chat` instance.

## Approach B's pivot

Decouple send from receive entirely:

```
POST /api/threads/:id/messages/run    ──►  202 + { user, assistant }   (ack only)
                                            │
                                            └─ kicks off background asyncio.Task

GET  /api/threads/:id/events           ──►  long-lived SSE
                                            (data-agent-event parts for every
                                             event of every concurrent producer
                                             on this thread)
```

Client:

- `useChat` retained ONLY as a state container (`messages`, `setMessages`,
  `status`). Its `sendMessage` is never called.
- Custom `sendUserMessage(text)` does:
  1. Optimistic `setMessages([…, userMsg, asstPlaceholder])` with temp ids.
  2. `POST /messages/run` — gets back server-assigned message ids.
  3. `setMessages` swaps temp ids → server ids.
- A separate `useThreadEventStream` hook holds an open `EventSource` to
  the events endpoint. Every incoming SSE event is reduced into the
  matching assistant message's `parts` array via `payload.messageId`.

Multiple concurrent turns become: N parallel POSTs → N independent
background producers → events fan out via one shared event bus → SSE
multiplexes to the client → client routes each event to the matching
slot by `messageId`.

## Architecture diagram

```
┌────────────────────────────────────────────────────────────────────┐
│  CLIENT                                                            │
│                                                                    │
│  ChatInput.onSubmit ─► sendUserMessage(text):                      │
│    1. setMessages: push user + empty assistant placeholder         │
│    2. POST /messages/run  (ack: {userId, asstId})                  │
│    3. setMessages: replace temp ids with server ids                │
│                                                                    │
│  useChat({ transport, dataPartSchemas })                           │
│       │                                                            │
│       └── messages, setMessages, status — STATE ONLY               │
│           (never calls sendMessage internally)                     │
│                                                                    │
│  useThreadEventStream(client, threadId, setMessages):              │
│       always-open EventSource → /threads/:id/events                │
│       per event: route by payload.messageId, dispatch by type      │
│         model.text.delta  → upsert/append text part                │
│         model.reasoning.* → upsert/append reasoning part           │
│         tool.input.*      → upsert tool part by toolCallId         │
│         tool.output.*     → update tool part state + output        │
│         everything else   → append as data-agent-event part        │
│                                                                    │
│  useThreadMessages(client, threadId): one-shot history hydrate     │
│                                                                    │
└──────────────────────────────────────┬─────────────────────────────┘
                                       │ HTTP
┌──────────────────────────────────────▼─────────────────────────────┐
│  SERVER                                                            │
│                                                                    │
│  POST /api/threads/:id/messages/run  (ACK-ONLY)                    │
│    1. create_message(role='user',       turn_index = max+1)        │
│    2. create_message(role='assistant',  same turn_index, empty)    │
│    3. asyncio.create_task(run_into_event_store(...))               │
│    4. task_registry.register(asst_msg_id, task)                    │
│    5. return MessageAckResponse(user, assistant)                   │
│                                                                    │
│  runtime.run_into_event_store(thread_id, asst_msg_id, ...):        │
│    Reuses _run_streaming_interaction_loop internally.              │
│    For each yielded SSE chunk, parse and convert to a              │
│    record_event() call tagged with message_id=asst_msg_id.         │
│    On completion: update_message(content, parts)                   │
│                                                                    │
│  GET /api/threads/:id/events  (long-lived SSE)                     │
│    1. event_store.subscribe(thread_id=...)                         │
│    2. backfill: list_runs(thread_id) → list_events per run         │
│    3. live tail: drain subscription.queue                          │
│    Each emission goes out as { type:'data-agent-event', data:... } │
│                                                                    │
│  event_store (SQLite + thread-indexed subscriptions):              │
│    Every event row carries message_id; subscriptions fan out via   │
│    _thread_index in O(1).                                          │
│                                                                    │
│  threads.db.messages — incrementally updated by run_into_event_    │
│  store on completion (or with partial parts on cancel)             │
└────────────────────────────────────────────────────────────────────┘
```

## Server changes (what we implemented)

### 1. Event store: tag every event with `message_id`

Added `message_id TEXT` column on both `execution_runs` and `execution_events`
(via `_ensure_column` migrations). Extended `record_event` and `_upsert_run`
keyword args. Surfaced `messageId` on `ExecutionEvent`, `ExecutionRun`, and
`ExecutionEventPayload` TypedDicts; events inherit `message_id` from their
run row if not explicitly set.

```python
# server/services/execution/event_store.py

def record_event(
    self,
    *,
    request_id: str,
    memory_id: str,
    event_type: ExecutionEventType,
    state: ExecutionEventState | None = None,
    parent_memory_id: str | None = None,
    thread_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    text: str | None = None,
    input_data: JsonValue = None,
    output: JsonValue = None,
    error: str | None = None,
    message_id: str | None = None,
) -> None:
    # ... insert into execution_events with message_id column,
    # publish payload with messageId field;
    # falls back to run row's message_id if caller didn't supply one.
```

### 2. `run_into_event_store` on the interaction agent runtime

The core refactor. Reuses the existing `_run_streaming_interaction_loop`
generator unchanged but, instead of yielding SSE chunks to the HTTP response,
parses each chunk and re-emits it via the event store with the assistant
message id stamped on every event.

```python
# server/agents/interaction_agent/runtime.py

async def run_into_event_store(
    self,
    user_message: str,
    *,
    thread_id: str,
    assistant_message_id: str,
    turn_index: int,
) -> None:
    execution_store = get_execution_event_store()
    run_id = f"interaction-{uuid.uuid4()}"
    accumulator = _AssistantPartsAccumulator()

    execution_store._upsert_run(
        request_id=run_id,
        memory_id="interaction",
        title="Interaction",
        status="running",
        ok=None,
        thread_id=thread_id,
        message_id=assistant_message_id,
    )

    try:
        execution_store.record_event(
            request_id=run_id, memory_id="interaction",
            event_type="run.created", state="queued",
            thread_id=thread_id, message_id=assistant_message_id,
        )
        execution_store.record_event(
            request_id=run_id, memory_id="interaction",
            event_type="run.started", state="running",
            thread_id=thread_id, message_id=assistant_message_id,
        )

        # ... transcript loading ...

        async for chunk in self._run_streaming_interaction_loop(...):
            accumulator.feed_chunk(chunk)
            self._emit_chunk_as_event(
                chunk,
                run_id=run_id,
                assistant_message_id=assistant_message_id,
                thread_id=thread_id,
            )

        execution_store.record_event(
            request_id=run_id, memory_id="interaction",
            event_type="run.completed", state="completed",
            text=accumulator.text_content(),
            thread_id=thread_id, message_id=assistant_message_id,
        )
    except asyncio.CancelledError:
        execution_store.record_event(
            request_id=run_id, memory_id="interaction",
            event_type="run.failed", state="failed",
            text="cancelled by user", error="cancelled",
            thread_id=thread_id, message_id=assistant_message_id,
        )
        raise
    except Exception as exc:
        # ... record run.failed ...
    finally:
        # Finalize the assistant placeholder with accumulator state
        get_thread_repository().update_message(
            thread_id, assistant_message_id,
            content=accumulator.text_content(),
            parts=accumulator.parts,
        )
```

`_emit_chunk_as_event` parses each `data: {…}\n\n` SSE chunk and dispatches
based on chunk type:

```python
def _emit_chunk_as_event(self, sse_chunk, *, run_id, assistant_message_id, thread_id):
    # text-delta        → model.text.delta event
    # reasoning-delta   → model.reasoning.delta event
    # tool-input-start  → tool.input.started event
    # tool-input-delta  → tool.input.delta event
    # tool-input-available → tool.input.available event
    # tool-output-available → tool.output.available event
    # error             → error event
    # start / start-step / finish-step / finish / data-agent-event / data-execution-event
    #                   → ignored (lifecycle markers or duplicates of execution events
    #                     that are already in event_store via their own paths)
```

### 3. New ack endpoint

```python
# server/api/routes/threads.py

@router.post("/{threadId}/messages/run",
             response_model=MessageAckResponse,
             status_code=202)
async def run_thread_message(threadId, payload, repository):
    user_record = repository.create_message(
        threadId, role="user", content=user_content,
        parts=user_message.serializable_parts(),
    )
    assistant_record = repository.create_message(
        threadId, role="assistant", content="", parts=[],
        turn_index=user_record.turn_index,  # M-tier: same turn_index
    )

    runtime = InteractionAgentRuntime()
    loop = asyncio.get_running_loop()
    task = loop.create_task(
        runtime.run_into_event_store(
            user_message=user_content,
            thread_id=threadId,
            assistant_message_id=assistant_record.message_id,
            turn_index=user_record.turn_index,
        )
    )
    get_task_registry().register(assistant_record.message_id, task)

    return MessageAckResponse(
        user=message_resource(user_record),
        assistant=message_resource(assistant_record),
    )
```

### 4. ThreadRepository.update_message

```python
def update_message(
    self,
    thread_id: str,
    message_id: str,
    *,
    content: str | None = None,
    parts: list[dict[str, Any]] | None = None,
) -> None:
    # SQL UPDATE messages SET content=?, parts_json=? WHERE thread_id=? AND message_id=?
```

### 5. Thread SSE endpoint (already present from T0; backfill payload extended with `messageId`)

```python
def _payload_from_run_event(run, event) -> ExecutionEventPayload:
    message_id = event.get("messageId") or run.get("messageId")
    return {
        "runId": run["runId"],
        "requestId": run["requestId"],
        "memoryId": run["memoryId"],
        "threadId": run["threadId"],
        "parentMemoryId": run["parentMemoryId"],
        "parentRunId": run["parentRunId"],
        "scope": run["scope"],
        "title": run["title"],
        "messageId": message_id,   # critical for client-side routing
        "event": event,
    }
```

## Client changes

### 1. SDK: ack-endpoint method + thread-id mutex

```ts
// packages/sdk/src/client.ts

readonly threads = {
  messages: {
    run: (threadId, body) => this.#runThreadMessage(threadId, body),
    // ... existing methods kept for compat
  },
}

async #runThreadMessage(threadId, body): Promise<MessageAckResponse> {
  const response = await fetch(
    `${this.#baseUrl}/api/threads/${encodeURIComponent(threadId)}/messages/run`,
    {
      body: JSON.stringify(body),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    },
  );
  if (!response.ok) throw new Error(`run failed: HTTP ${response.status}`);
  return (await response.json()) as MessageAckResponse;
}
```

```ts
// packages/sdk/src/transport.ts

// Mutex so concurrent first-turn sends share one create-thread request.
#threadCreating: Promise<string> | null = null;

async ensureThreadId(): Promise<string> {
  if (this.#threadId) return this.#threadId;
  if (this.#threadCreating) return this.#threadCreating;
  this.#threadCreating = (async () => {
    try {
      const { data } = await this.#client.threads.create();
      this.#threadId = data.thread.threadId;
      this.#notifyThreadId(this.#threadId);
      return this.#threadId;
    } finally {
      this.#threadCreating = null;
    }
  })();
  return this.#threadCreating;
}
```

### 2. `useOpenPokeChat` hook (state container + custom sender)

```ts
// apps/web/src/features/assistant/hooks/use-openpoke-chat.ts

export function useOpenPokeChat(transport): UseOpenPokeChatResult {
  const { messages, setMessages, status } = useChat<OpenPokeChatMessage>({
    dataPartSchemas: openPokeDataPartSchemas,
    transport,  // unused but useChat requires one
  })

  const sendUserMessage = useCallback(async (text: string): Promise<void> => {
    const tempUserId = `tmp-user-${crypto.randomUUID()}`
    const tempAsstId = `tmp-asst-${crypto.randomUUID()}`

    // 1. Optimistic
    setMessages((prev) => [
      ...prev,
      { id: tempUserId, parts: [{ text, type: 'text' }], role: 'user' },
      { id: tempAsstId, parts: [], role: 'assistant' },
    ])

    // 2. Ensure threadId (creates if missing, via shared mutex)
    const threadId = await transport.ensureThreadId()

    // 3. POST ack
    const ack = await poke.threads.messages.run(threadId, {
      messages: [{ parts: [{ text, type: 'text' }], role: 'user' }],
    })

    // 4. Swap temp ids for server-assigned ids
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id === tempUserId) return { ...m, id: ack.user.messageId }
        if (m.id === tempAsstId) return { ...m, id: ack.assistant.messageId }
        return m
      }),
    )
  }, [transport, setMessages])

  return { messages, setMessages, sendUserMessage, status }
}
```

### 3. `useThreadEventStream` reducer

```ts
// apps/web/src/features/assistant/hooks/use-thread-event-stream.ts

export function mergeEventIntoMessages(prev, payload) {
  const messageId = payload.messageId ?? payload.event?.messageId ?? null
  const targetIndex = prev.findIndex(
    (m) => m.role === 'assistant' && m.id === messageId,
  )
  if (targetIndex < 0) return prev  // (with lastAssistantIndex fallback in real code)

  const t = payload.event.type
  let nextParts
  if (t === 'model.text.delta') {
    nextParts = appendTextDelta(target.parts, payload.event.text ?? '')
  } else if (t.startsWith('tool.')) {
    nextParts = upsertToolPart(target.parts, payload)
  } else {
    nextParts = [...target.parts, { type: 'data-agent-event', data: payload }]
  }

  const next = prev.slice()
  next[targetIndex] = { ...target, parts: nextParts }
  return next
}

// Hook with event-id dedup (Set in useRef) for safety against
// subscribe-then-backfill race in the server endpoint.
const appliedEventIds = useRef<Set<number>>(new Set())
const handle = (e: MessageEvent<string>) => {
  const payload = parseAgentEventFrame(e.data)
  if (!payload) return
  const eventId = payload.event.id
  if (typeof eventId === 'number') {
    if (appliedEventIds.current.has(eventId)) return
    appliedEventIds.current.add(eventId)
  }
  setMessages((prev) => mergeEventIntoMessages(prev, payload))
}
```

### 4. ChatThread wiring

```tsx
// apps/web/src/features/assistant/components/layout/chat-thread.tsx

const { messages, setMessages, sendUserMessage } = useOpenPokeChat(transport)
const [threadId, setThreadId] = useState<string | undefined>(
  () => transport.getThreadId() ?? undefined,
)
useEffect(() => transport.onThreadIdChange(setThreadId), [])

const history = useThreadMessages(poke, threadId)
// seed history once if messages is empty
useEffect(() => {
  if (history.status === 'success' && history.messages.length > 0 && messages.length === 0) {
    setMessages(history.messages)
  }
}, [threadId, history, messages.length, setMessages])

useThreadEventStream(poke, threadId, setMessages)

return (
  <MessageList messages={messages} status="ready" />
  // ChatInput is never disabled — concurrent sends always allowed.
)
```

## What worked

- **Concurrent turns are safe.** Multiple `sendUserMessage` calls in flight
  don't corrupt state because there's no shared `activeResponse`. Each turn
  is one POST + one background asyncio task + events routed by `messageId`.
  Verified with 4 simultaneous sends — all 4 streamed back independently.
- **Execution agents work unchanged.** They already publish to the event
  store; the same thread SSE delivers their events to the right assistant
  message via the `messageId` field on the parent run row.
- **Persistence is robust.** Assistant placeholder is inserted at the same
  turn_index as the user message at ack time. Producer updates it on
  completion. Reload rehydrates everything.
- **The reducer dispatch model is sound.** 12 unit-level scenarios pass
  (text accumulation, tool lifecycle, concurrent message routing, dedup).

## What didn't feel clean (the reasons for reverting)

1. **`useChat`'s status machine is bypassed.** `status` stays mostly idle
   because `useChat.sendMessage` is never called. We have to derive
   "thinking" / "streaming" / "typing" indicators ourselves from message
   parts, and the assistant indicator's normal flow doesn't apply. In
   practice this resulted in **the indicator flickering twice** (optimistic
   push, then ID swap) and not behaving like the original.

2. **Repeated `send_message_to_user` calls show as concatenated text.**
   When the interaction agent calls `send_message_to_user` more than once
   per turn (which it sometimes does across phase iterations), each
   call's text-delta events accumulate into the same text part on the
   client. Visible as "I need details... I need details... I need details..."
   triple repetition. Not an architecture bug — it's the agent being
   redundant — but the original `useChat` pattern naturally suppresses
   this because the per-turn stream wraps everything in one logical text
   part driven by the AI SDK protocol.

3. **Streamdown rendering parity is only "shape-equivalent", not behavior-equivalent.**
   The reducer produces parts in the right shape, but the AI SDK's own
   stream parser tracks more subtle state (e.g., active text part IDs,
   step boundaries) that the catalog renderer and `<Tools>` indirectly
   depend on for animations and state-transition smoothness. Replicating
   it all by hand surfaces edge cases.

4. **Two-flicker UI symptom.** Optimistic push → ack returns → ID swap is
   two renders. With the assistant indicator overlaying, this looks like
   a double flicker before content arrives. Combined with status staying
   "idle" (because useChat doesn't drive it), the perceived UX is worse
   than the original.

5. **Subscribe-then-backfill race in the events SSE.** Events fired
   between `store.subscribe()` and the backfill loop got delivered twice
   (once via queue, once via backfill DB replay). Fixable client-side
   with an event-id dedup Set, but it's a leaky abstraction. Cleaner
   would be a server-side `Last-Event-ID` cursor.

6. **Lots of moving parts.** Two endpoints to maintain (legacy stream
   path left in place during migration), three event types in flight
   (text/reasoning/tool/data-agent-event), the runtime's
   `_emit_chunk_as_event` converter as an extra layer of indirection,
   etc. The benefit (concurrent turns) didn't justify the surface area
   for this project.

## Decision: revert to the `useChat`-driven pattern

The user observed that the original `useChat({ transport })` pattern is
cleaner: status indicators work right, no flicker, no concatenated-text
artifacts. The architectural cost of supporting concurrent turns is not
worth it at this stage of the product. The right time to revisit Approach B
is when there's a concrete user-research reason to want parallel turns badly
enough to spend the engineering effort closing the polish gaps above.

## What to keep when reverting

These pieces of work are independently valuable and should stay regardless
of which chat architecture we use:

- **M (turn_index ordering).** Survives reload-with-concurrent-edits even
  in the legacy single-turn model. Already shipped.
- **T0 thread-scoped SSE.** Execution-agent events still need to surface
  outside of the per-turn SSE (e.g. for emails that arrive while the user
  is doing something else). Keep the endpoint and the indexed-subscription
  event store.
- **T1 assistant message persistence.** Reload-survival is required.
  Already shipped, integrates fine with the legacy stream path.
- **T2 cancellation tool + task registry.** Works regardless of
  architecture.
- **Indexed event-store subscriptions + bounded queue.** Pure improvement.
- **Catalog renderer pipeline.** Unaffected by architecture choice.

## What to revert

- `POST /api/threads/:id/messages/run` endpoint + `MessageAckResponse` schema.
- `runtime.run_into_event_store` + `_emit_chunk_as_event` helper.
- `ThreadRepository.update_message` (unused once we revert).
- `OpenPokeTransport.ensureThreadId` (unused; transport.sendMessages handles
  thread creation in the legacy path).
- `useOpenPokeChat` hook.
- `chat-thread.tsx`: go back to `useChat({ transport })` + `sendMessage`,
  re-enable `disabled={isStreaming}` on the input.
- The text/tool branches of the `mergeEventIntoMessages` reducer: keep the
  thread-scoped SSE merging only `data-agent-event` parts (its T0
  behavior), since text/tool come back through the per-turn `useChat`
  stream when the legacy endpoint is in use.
- `messageId` column / payload field can stay in the schema — harmless
  if unused, and useful if Approach B is revisited later.

## File-level inventory of the Approach B work

Server:

| Path | Approach B addition | Revert action |
|------|---------------------|---------------|
| `server/services/execution/event_store.py` | `message_id` column + payload field; inheritance from run row | Keep — harmless if unused, useful for future |
| `server/agents/interaction_agent/runtime.py` | `run_into_event_store` + `_emit_chunk_as_event` | Delete both methods; restore stream_execute as the sole streaming path |
| `server/api/routes/threads.py` | `POST /messages/run` route + helper | Delete the run route; restore stream_thread_message as the sole user-message endpoint |
| `server/api/schemas.py` | `MessageAckResponse` + `AgentRunEventResource.messageId` + `AgentRunResource.messageId` | Delete `MessageAckResponse`; keep the optional `messageId` fields (harmless) |
| `server/api/converters.py` | `messageId` on agent_run_resource | Keep |
| `server/db/threads.py` | `update_message` helper | Delete |

SDK:

| Path | Approach B addition | Revert action |
|------|---------------------|---------------|
| `packages/sdk/src/client.ts` | `MessageAckResponse` type + `threads.messages.run()` + `#runThreadMessage` | Delete all three |
| `packages/sdk/src/transport.ts` | `ensureThreadId()` + `#threadCreating` mutex | Delete (legacy `sendMessages` already lazily creates a thread) |
| `packages/sdk/src/streaming.ts` | `messageId` layered on `zAgentEventStreamPayload` | Keep — harmless |
| `packages/sdk/src/index.ts` | `MessageAckResponse` re-export | Delete |

Client (web):

| Path | Approach B addition | Revert action |
|------|---------------------|---------------|
| `apps/web/src/features/assistant/hooks/use-openpoke-chat.ts` | NEW | Delete |
| `apps/web/src/features/assistant/hooks/use-thread-event-stream.ts` | text-delta / reasoning / tool dispatch branches; useRef event-id dedup | Restore to the simpler T0 form that only merges `data-agent-event` parts; keep the event-id dedup Set as a guard for future races |
| `apps/web/src/features/assistant/components/layout/chat-thread.tsx` | `useOpenPokeChat` + `disabled={false}` + `status="ready"` hardcoded | Restore `useChat({ transport })` + `sendMessage` + `disabled={isStreaming}` |

## If we ever come back to this

The architecture is sound. The unsolved polish items are:

1. Per-iteration text parts (separate text part per `text-start` chunk) to
   make the agent's repetition visually obvious instead of hidden in one
   concatenated string. Server emits text_part_id in text-start; reducer
   should key by it.
2. Tighten the interaction-agent system prompt so it stops calling
   `send_message_to_user` multiple times per turn with similar content.
3. Drive the assistant indicator from a derived state machine (e.g., last
   event type + time-since-last-event) instead of `useChat.status`.
4. `Last-Event-ID` cursor support on the events SSE; eliminates client-side
   dedup as a workaround.
5. Server-side dedup in `stream_thread_events` so the wire doesn't carry
   the same event twice in the subscribe-then-backfill race window.
6. Regenerate the SDK against the OpenAPI spec so `runThreadMessage`
   becomes a typed call instead of hand-rolled fetch.

Concurrent turns are achievable. The cost is owning the parts of the AI
SDK's UI message stream protocol that `useChat` normally hides — and that
ownership has to deliver enough value to justify the maintenance.
