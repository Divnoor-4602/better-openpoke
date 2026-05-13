# Backend Streaming And Execution Contract

This document defines the backend contract for chat streaming, execution
visibility, and execution-run continuation.

It intentionally avoids presentation-layer implementation details. The only
external assumption is that stream consumers understand AI SDK UI Message Stream
chunk names.

## Principles

```text
Interaction agent owns user-facing chat text.
Execution agents own structured process events and raw task results.
Execution runs are durable and resumable by request_id.
Execution workers are disposable.
Memory records are the durable routing context.
```

The backend emits AI SDK UI Message Stream wire-format chunks directly from
FastAPI. The backend does not use the Vercel AI SDK runtime.

Only `text-*` chunks are chat text. Tool calls and execution progress are
structured visibility data.

## Endpoints

### POST /api/chat/stream

Handles one immediate interaction-agent turn.

Responsibilities:

```text
read latest user text from UI messages
record user message
run interaction agent
stream direct interaction-agent tool visibility
stream direct interaction-agent text if produced
submit execution runs if needed
emit initial execution events for submitted runs
finish without waiting for execution completion
```

Headers:

```text
x-vercel-ai-ui-message-stream: v1
cache-control: no-cache
content-type: text/event-stream
```

Typical chunks:

```text
start
start-step
tool-input-start
tool-input-delta
tool-input-available
tool-output-available
data-execution-event
text-start
text-delta
text-end
finish-step
finish
[DONE]
```

The chat stream must not convert execution-agent `agent-response` events into
chat text. Execution-run continuation owns that.

### GET /api/execution/runs

Returns recent durable execution runs.

Each run includes:

```text
requestId
memoryId
parentMemoryId
title
status
ok
createdAt
updatedAt
parts
```

`parts` are stored execution events in ascending event-id order.

### GET /api/execution/agents

Compatibility endpoint for older execution-log consumers.

When durable execution runs exist, it returns:

```text
{
  "runs": [...],
  "agents": [...]
}
```

The `agents` shape is derived from runs and should be treated as compatibility
data. New backend behavior should use runs/events.

### GET /api/execution/runs/{requestId}/stream?afterId=...

Continues one execution run.

Responsibilities:

```text
load run by requestId
emit start
replay stored events with id > afterId
subscribe to live events for requestId
emit data-execution-event for every execution event
compose agent-response through the interaction agent
emit composed text as text-* chunks
finish when terminal status is reached
```

If the run is not found, the stream emits an error chunk, `finish`, and `[DONE]`.

## Execution Events

Execution events are stored in SQLite:

```text
server/data/execution_events.db
```

Tables:

```text
execution_runs
execution_events
```

Event payloads are emitted as:

```json
{
  "type": "data-execution-event",
  "data": {
    "requestId": "req_...",
    "memoryId": "mem_...",
    "parentMemoryId": null,
    "title": "Draft email to Alice",
    "event": {
      "id": 123,
      "type": "status",
      "state": "queued",
      "toolCallId": null,
      "toolName": null,
      "text": "Draft an email...",
      "input": null,
      "output": null,
      "error": null,
      "createdAt": "2026-05-11T15:30:00-0700"
    }
  }
}
```

Supported event types:

```text
status
tool-call
tool-result
agent-response
```

Supported states:

```text
queued
running
completed
failed
input-available
output-available
output-error
```

Semantics:

```text
status / queued
  The interaction agent accepted and submitted execution work.

status / running
  The execution worker started.

tool-call / input-available
  The worker is about to execute or has requested a tool call.

tool-result / output-available
  Tool execution completed successfully.

tool-result / output-error
  Tool execution failed.

agent-response / output-available
  Raw execution-agent final response. This is process data, not chat copy.

status / completed
  Run completed successfully.

status / failed
  Run completed unsuccessfully.
```

`event.id` is the durable resume cursor. Consumers resume with:

```text
afterId=<last seen event id>
```

## Interaction-Agent Text Ownership

Direct user-facing text can come from two backend paths.

### Immediate interaction text

The interaction agent may answer directly with no execution work. The chat stream
emits normal `text-*` chunks.

### Tool-owned user messages

Some interaction tools return `user_message`. Examples:

```text
Gmail disconnected preflight
draft preview produced by send_draft
direct send_message_to_user reply
```

When `user_message` is present, the chat stream emits exactly one visible
`text-*` response and ends the interaction turn. It does not ask the model to
paraphrase the same tool result.

## Execution-Agent Result Composition

Execution-agent final responses are not directly shown as chat.

Flow:

```text
execution agent completes
  -> record agent-response event
  -> execution stream sees agent-response
  -> InteractionAgentRuntime.handle_agent_message(...)
  -> emit composed text-* chunks
```

This gives the interaction agent final control over wording, deduplication, draft
presentation, and user-facing follow-up questions.

## Active Runs And Duplicate Prevention

Every interaction-agent prompt includes:

```xml
<active_execution_runs>
  ...
</active_execution_runs>
```

This section lists queued/running execution runs with request id, memory id,
title, status, and latest compact event text.

The interaction agent is instructed not to submit work that is already queued or
running.

The tool layer also enforces this with a duplicate guard. A new execution request
returns:

```json
{ "status": "already_in_progress", "request_id": "..." }
```

instead of creating a new run when an active run matches by:

```text
memory_id
task title
submitted instructions
```

## Gmail Preflight

Gmail-dependent interaction tools check Gmail connection before creating an
execution run.

If Gmail is disconnected:

```text
no execution run is created
one user-facing text response is emitted
```

## Current Limits

Current backend limits:

- Live event subscriptions are in-process only.
- SQLite replay is durable, but live pub/sub is not multi-instance.
- There is no explicit cancellation endpoint yet.
- Duplicate detection is heuristic and should be tightened with stronger task
  identity over time.
- Stream protocol needs broader contract tests beyond event-store unit tests.
