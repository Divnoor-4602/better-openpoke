# Execution Agent Overload

## Status

The old execution-agent overload problem is removed from the active request path.

OpenPoke no longer passes the full roster of execution agents into the interaction
agent prompt. Execution agents are now disposable workers. Durable task identity,
context, and reuse live in the memory system.

The current prompt path is:

```text
latest user message
  -> active execution run lookup
  -> memory search
  -> top relevant memory contexts + active execution runs
  -> interaction agent prompt
  -> send_message_to_agent(memory_id=...)
  -> disposable execution worker
```

The old path was:

```text
latest user message
  -> full execution-agent roster in prompt
  -> interaction agent chooses an agent by name
  -> persistent named execution agent
```

That old path created a relevance and context-window failure mode once the system
had many agents such as `Email to Alice`, `Q3 Budget Analysis`, or
`Tokyo Restaurant Search`. The active architecture avoids that by never asking the
interaction agent to inspect every worker.

## Why The Old Roster Model Failed

The previous design blurred two separate responsibilities:

```text
execution agent = runtime worker
execution agent = persistent memory container
```

As agent count grew, every request risked carrying too much low-signal context:

```xml
<active_agents>
  <agent name="Email to Alice" />
  <agent name="Q3 Budget Analysis" />
  <agent name="Tokyo Restaurant Search" />
  ...
</active_agents>
```

This had three practical problems:

- Prompt cost grew with total historical agents, not with the current request.
- Similar agent names competed with each other and produced routing mistakes.
- Agent identity was based on a human-readable name rather than stable external
  handles, memory links, or event history.

## Current Architecture

The current design separates durable context from execution:

```text
memory = durable identity and context
event = one compact thing that happened
link = stable external handle
execution worker = temporary runtime over one memory
```

Execution workers are created as needed and receive a memory context. They are not
the long-term source of truth.

The durable routing key is `memory_id`, not an agent name.

Execution run state is keyed by `request_id`. A memory can have many execution
runs over time, but only queued/running runs are considered active.

## Memory Store

The local source of truth is SQLite:

```text
server/data/memory.db
```

SQLite is used for local durability, idempotency, exact-link lookup, lexical
fallback, and the indexing outbox. It remains the local development/runtime
database in this architecture. It is not a full multi-tenant production database.

The core tables are:

```text
memories
events
links
memory_index_queue
```

### Memories

A memory is a reusable context group.

Examples:

- Gmail thread
- user task
- research topic
- recurring workflow

Important fields:

```text
memory_id
kind
title
summary
metadata_json
created_at
updated_at
```

The interaction agent routes to existing work by passing a `memory_id` to
`send_message_to_agent`.

### Events

An event is one compact fact or action attached to a memory.

Examples:

- `gmail_message_seen`
- `execution_request`
- `tool_call`
- `tool_result`
- `execution_response`
- `gmail_draft_created`

Events are intentionally compact. They should store the information needed for
continuation and search, not raw connector payloads or full Gmail HTML.

Important fields:

```text
event_id
memory_id
idempotency_key
type
timestamp
recorded_at
source
text
metadata_json
```

### Links

Links attach stable handles to memories and events.

Examples:

```text
gmail_thread: 19e0dca741f6d862
gmail_message: 18fd...
gmail_draft: r-...
email_address: alice@example.com
keyword: 3750993864
```

Exact links are the primary way the system avoids duplicate context. For Gmail,
the important mapping is:

```text
threadId -> memory_id
messageId -> event idempotency
```

That means repeated work on the same Gmail thread should land in the same memory,
while repeated observations of the same message should not duplicate events.

## Prompt Routing

The interaction prompt is assembled in
`server/agents/interaction_agent/agent.py`.

It includes:

- conversation history
- `<active_execution_runs>`
- `<relevant_memories>`
- latest user or agent message

It does not include the full execution-agent roster.

The memory section is bounded:

```text
get_memory_store().search(query, limit=8, context="prompt_context")
```

Only the top relevant memory contexts are injected. If the visible memories are
not enough, the interaction agent has a search tool:

```text
search_memory(query, limit)
```

The routing tool is:

```text
send_message_to_agent(memory_id=None, task_name=None, instructions="")
```

Usage rules:

- Use `memory_id` when an existing memory fits.
- Use `task_name` only when creating a new memory context.
- Do not route by a remembered execution-agent name.
- Before creating work, inspect `<active_execution_runs>`. If the same work is
  already queued or running, do not submit it again.

The tool layer also has a duplicate guard. Even if the model attempts to submit
overlapping work, the backend returns `already_in_progress` instead of creating a
new execution run when it finds an active run with the same memory, task title,
or submitted instructions.

## Backend Streaming And Execution Contract

OpenPoke now has two separate streaming responsibilities:

```text
POST /api/chat/stream
  -> immediate interaction-agent turn
  -> submit execution work if needed
  -> expose request_id / memory_id / title
  -> end without waiting for worker completion

GET /api/execution/runs/{requestId}/stream?afterId=...
  -> durable execution-run continuation
  -> replay stored events after afterId
  -> subscribe to live events for that run
  -> compose final user-facing text through InteractionAgentRuntime
```

The backend manually emits Vercel AI SDK UI Message Stream chunks. It does not
depend on the Vercel AI SDK server runtime.

Chat stream chunks may include:

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

Execution stream chunks may include:

```text
start
data-execution-event
text-start
text-delta
text-end
finish
[DONE]
```

The rule is:

```text
Only `text-*` chunks are user-facing chat text.
Execution/tool/process state is structured data.
Raw execution-agent responses are not direct chat copy.
```

When a direct interaction tool returns `user_message`, the chat stream emits
exactly one visible `text-*` response and ends that interaction turn. This is how
preflight errors and draft previews become visible without asking the model to
paraphrase tool payloads.

When execution work is submitted, the chat stream emits tool visibility and any
initial `data-execution-event` records, then closes. It does not wait for the
execution worker's final result.

## Execution Event Store

Execution visibility is stored in SQLite:

```text
server/data/execution_events.db
```

Core tables:

```text
execution_runs
execution_events
```

Run fields include:

```text
request_id
memory_id
parent_memory_id
title
status
ok
created_at
updated_at
```

Event fields include:

```text
id
request_id
memory_id
parent_memory_id
type
state
tool_call_id
tool_name
text
input_json
output_json
error
created_at
```

Every `data-execution-event.data` payload has this shape:

```ts
type ExecutionEventPayload = {
  requestId: string
  memoryId: string
  parentMemoryId?: string | null
  title: string
  event: {
    id: number
    type: "status" | "tool-call" | "tool-result" | "agent-response"
    state?:
      | "queued"
      | "running"
      | "completed"
      | "failed"
      | "input-available"
      | "output-available"
      | "output-error"
    toolCallId?: string | null
    toolName?: string | null
    text?: string | null
    input?: unknown
    output?: unknown
    error?: string | null
    createdAt: string
  }
}
```

Standard event meanings:

```text
status queued      -> execution request accepted
status running     -> worker started
tool-call          -> worker tool input available
tool-result        -> worker tool output or error available
agent-response     -> raw worker final response for interaction-agent composition
status completed   -> run terminal success
status failed      -> run terminal failure
```

The `event.id` is the replay cursor. Execution streams accept `afterId` and emit
only events with `id > afterId`.

## Execution Result Composition

Execution agents are treated like subagents:

```text
execution agent does work
  -> emits structured progress events
  -> returns raw final response
  -> interaction agent composes user-facing response
```

When an execution stream sees an `agent-response` event, it calls:

```text
InteractionAgentRuntime.handle_agent_message(...)
```

The result from the interaction agent is emitted as `text-*` chunks on the
execution stream. This keeps user-facing prose owned by the interaction agent,
while the execution agent's raw output remains process data.

Completed historical runs are replayable as logs. They should not automatically
create old chat messages unless a stream consumer deliberately subscribes to that
run and receives composed text.

## Search Capabilities

Memory search has three layers.

### 1. Indexed Exact-Link Lookup

Exact identifiers are extracted from the query:

- emails
- memory ids
- long ids such as Gmail thread/message/draft ids

`exact_link_candidates()` now filters in SQL against `links(kind, value)` instead
of scanning every link row in Python. This is the fast path for requests like:

```text
"find the thread thread-99990000"
"continue with ops@example.com"
"what happened with draft-87654321"
```

### 2. Pinecone Hybrid Search

When Pinecone is configured, the system performs hybrid search:

```text
query
  -> dense embedding
  -> sparse embedding
  -> Pinecone index query
  -> candidate merge
  -> Pinecone rerank
  -> batched SQLite hydration
```

Indexed documents include both memory records and event records. Pinecone stores
search metadata and the vector id:

```text
memory:{memory_id}
event:{event_id}
```

The SQLite memory database remains the source of truth. Pinecone is a retrieval
index, not authoritative storage.

The rerank step uses Pinecone's standalone reranker. Conceptually, this is a
cross-encoder style scoring pass over the query and candidate document:

```text
score(q, d) = w^T Transformer([CLS] q [SEP] d [SEP])_CLS + b
```

Unlike embedding search, the reranker reads the query and document together, so
it is more precise but also more expensive. That is why it runs after the initial
candidate retrieval and only over a bounded candidate set.

### 3. Bounded SQLite Lexical Fallback

If Pinecone is disabled or unavailable, search falls back to lexical scoring over:

- memory title
- memory summary
- memory metadata
- event text
- event metadata
- links

The fallback is bounded to recent records so an outage does not degrade into an
unbounded full-table scan.

Current bounds:

```text
recent memories: 1000
recent events: 5000
recent links: 5000
```

This is still a fallback, not the final production search plan. A future
production database should use FTS or indexed search primitives for this path.

## Result Hydration

Search candidates are converted into prompt/tool results by hydrating memories
from SQLite.

This is now batched:

```text
candidate memory ids -> get_memories([...]) -> ranked results
```

The previous N+1 pattern called `get_memory()` once per candidate. The current
path loads candidate memories in a small fixed number of SQLite queries, then
preserves the matched event first for `search_memory` results.

## SQLite Outbox For Indexing

The `memory_index_queue` table is the durable local outbox for Pinecone indexing.

Rows are written in the same SQLite transaction as memory/event/link writes.
This keeps local state and indexing intent consistent.

Important fields:

```text
id
idempotency_key
entity_type
entity_id
operation
version
status
attempts
available_at
max_attempts
last_error
created_at
updated_at
```

Supported operations:

```text
upsert
delete
```

Supported statuses:

```text
pending
processing
failed
dead
done
```

The outbox is idempotent for active rows:

```text
operation:entity_type:entity_id
```

Repeated writes update an active queue row instead of creating unlimited
duplicates.

## Background Worker

`MemoryIndexWorker` runs outside request handling.

Startup path:

```text
server/app.py
  -> get_memory_index_worker()
  -> MemoryIndexWorker.start()
```

Loop behavior:

```text
sleep MEMORY_INDEX_POLL_INTERVAL_SECONDS
claim due rows from SQLite
if no rows: return without creating a Pinecone client
serialize records
embed in batches
upsert/delete Pinecone vectors
mark rows done or failed/dead
```

The worker now checks SQLite before creating a Pinecone Index client. This avoids
idle logs such as repeated Pinecone client creation every poll.

Configuration:

```text
MEMORY_INDEX_WORKERS=2
MEMORY_INDEX_BATCH_SIZE=50
MEMORY_INDEX_MAX_ATTEMPTS=5
MEMORY_INDEX_POLL_INTERVAL_SECONDS=2
```

## Retry, Backoff, And Dead Lettering

Failed queue rows do not retry forever.

Rows use exponential backoff:

```text
30s, 60s, 120s, 240s, 480s
```

After `max_attempts`, the row is marked:

```text
dead
```

Dead rows are not claimed by workers. Queue health is visible through:

```text
GET /api/meta/memory-index
```

The response includes:

```text
pending
processing
failed
dead
done
oldest_active_age_seconds
recent_failures
```

## Pinecone Deletes

Delete operations remove stale vectors:

```text
memory:{memory_id}
event:{event_id}
```

This matters because SQLite deletes alone are not enough. Without Pinecone
deletes, stale vectors could still be retrieved and then fail hydration or point
to deleted context.

## Logging And Privacy

Production logs should not contain raw user memory/event text by default.

Default behavior:

```text
MEMORY_DEBUG_LOG_CONTENT=0
```

Logs include:

- ids
- counts
- scores
- confidence
- reasons
- timings
- fallback path
- queue health

They do not include event text snippets by default.

Local debugging can opt in:

```text
MEMORY_DEBUG_LOG_CONTENT=1
```

## Current Guarantees

The current architecture addresses the specific execution-agent overload issue:

- The full execution-agent roster is not injected into every prompt.
- Existing contexts are discovered by memory search, not by agent-name listing.
- Prompt memory context is bounded.
- Execution workers are disposable.
- Durable context lives in SQLite memory records, events, and links.
- Pinecone is used as a retrieval index with SQLite as source of truth.
- Indexing is asynchronous through a durable SQLite outbox.

## Remaining Production Gaps

This architecture is better than roster injection, but it is not the final
100x/multi-tenant architecture.

These are known future problems, not immediate blockers for a local or
single-user deployment. They become important when OpenPoke has multiple users,
multiple app instances, high write volume, or strict latency/SLO requirements.

### Tenant Isolation

Problem:

```text
memories, events, links, and queue rows are not scoped by user_id or org_id
```

Why it matters:

- Cross-user memory leaks are possible in a shared deployment.
- Exact-link and Pinecone search can return another user's context.
- Per-user export, deletion, and retention are hard to implement correctly.
- `events.idempotency_key` is globally unique, so two users with the same
  connector/action id could collide.

Potential fix:

- Add `user_id` and optionally `org_id` to `memories`, `events`, `links`, and
  `memory_index_queue`.
- Scope all reads/writes/searches by tenant.
- Include tenant metadata in Pinecone records and filter every query by tenant,
  or use tenant-specific Pinecone namespaces.
- Make idempotency unique per tenant, for example
  `(user_id, idempotency_key)`.

Priority:

```text
Required before real multi-user production.
```

### SQLite Source Of Truth

Problem:

```text
SQLite is still the source-of-truth database
```

Why it matters:

- One local `memory.db` is single-node state.
- Multiple app instances would either diverge or need unsafe shared filesystem
  access.
- Concurrent writes, queue polling, indexing updates, and searches can contend.
- Production failures may surface as `database is locked`, slow writes, or
  inconsistent state across instances.

Potential fix:

- Keep SQLite for local/dev.
- Move production memory tables to Postgres.
- Use normal relational constraints for idempotency, links, and queue leases.
- Add migrations instead of ad hoc schema initialization for production.

Priority:

```text
Future blocker for multi-instance or high-write production.
Not urgent for single-user/local use.
```

### SQLite Polling Queue

Problem:

```text
memory_index_queue is a SQLite-polled outbox
```

Current state:

- Queue rows are durable.
- Workers claim due rows.
- Retries use `available_at`.
- Failures back off and eventually move to `dead`.
- Idle polls check SQLite before creating a Pinecone client.

Why it still matters:

- SQLite polling is not a distributed job system.
- Multi-instance coordination remains limited.
- Backpressure and worker autoscaling are primitive.
- A busy write workload can contend with queue workers.

Potential fix:

- For a Postgres deployment, use a Postgres job table with leases:
  `FOR UPDATE SKIP LOCKED`, `available_at`, `attempts`, and `dead` status.
- Or move indexing jobs to a durable queue such as SQS, Redis Streams, Celery,
  Sidekiq, or a managed task queue.
- Keep the outbox pattern: write memory data and indexing intent atomically,
  then have workers drain jobs asynchronously.

Priority:

```text
Acceptable locally. Replace before multi-instance production ingestion.
```

### Pinecone Per-Request Latency

Problem:

```text
search can call dense embed, sparse embed, Pinecone query, and rerank per request
```

Why it matters:

- User latency depends on multiple external calls.
- Slow Pinecone inference or rerank can stall chat.
- Cost and rate-limit pressure grow with traffic.
- If Pinecone degrades, the system needs fast fallback instead of slow failure.

Potential fix:

- Add explicit timeouts around dense embed, sparse embed, index query, rerank,
  upsert, and delete calls.
- Add a small circuit breaker:
  - open after repeated Pinecone failures/timeouts
  - skip Pinecone briefly while open
  - use bounded SQLite lexical fallback
  - half-open after a cooldown to test recovery
- Cache short-lived query embeddings or search results for repeated prompts when
  safe.
- Reduce rerank input size based on query type and exact-link confidence.
- Track fallback rate and latency metrics.

Priority:

```text
Good near-term hardening. Smaller than a database migration and protects UX.
```

### Search Fallback Quality

Problem:

```text
bounded lexical fallback is not a true indexed search path
```

Current state:

- The fallback no longer scans unbounded tables.
- It searches recent memories, events, and links with caps.

Why it still matters:

- If Pinecone is down, older but relevant memories can be missed.
- Python scoring does not use a real inverted index.
- The fallback can still become expensive as caps rise.

Potential fix:

- Add SQLite FTS5 for local/dev.
- In production Postgres, use `tsvector`/GIN indexes or a dedicated search
  service.
- Keep exact-link lookup as a separate high-confidence path.

Priority:

```text
Future improvement. Not urgent unless Pinecone fallback quality is poor.
```

### Hydration Query Shape

Problem:

```text
search hydration still loads nested memory details per hydrated memory
```

Current state:

- Candidate memory ids are batched through `get_memories()`.
- This removes the worst N+1 pattern from ranked candidates.
- Each `MemoryRecord` still loads links and recent events, and each event can
  load its links.

Why it matters:

- With the current prompt limit of 8, this is acceptable.
- With larger limits, heavy traffic, or a remote database, nested hydration can
  become noticeable.

Potential fix:

- Add a dedicated batched hydration query for search results:
  - load all memory rows in one query
  - load all links for those memories in one query
  - load recent events with a window function
  - load event links in one query
- Return the same `MemoryRecord` shape from pre-grouped rows.
- Keep matched-event-first behavior for `search_memory`.

Priority:

```text
Partially solved. Optimize later based on profiling.
```

### Retention And Compaction

Problem:

```text
events grow forever
```

Why it matters:

- Storage, backups, migrations, and search/index maintenance get slower over
  time.
- Old low-value events compete with more useful recent context.

Potential fix:

- Add retention policies by event type and connector.
- Summarize old event ranges into memory summaries.
- Archive or delete low-value raw events after compaction.
- Preserve externally important handles in `links`.

Priority:

```text
Future scale work. Needed before long-running high-volume production.
```

### Observability And SLOs

Problem:

```text
logs exist, but metrics and alerting are still incomplete
```

Needed metrics:

- search latency
- dense embed latency
- sparse embed latency
- Pinecone query latency
- rerank latency
- fallback rate
- queue depth
- oldest active queue age
- indexing success/failure count
- dead-letter count
- hydration latency
- search miss rate or duplicate-memory creation rate

Potential fix:

- Export counters and histograms to the production metrics stack.
- Alert on high queue age, rising dead rows, Pinecone failure rate, and fallback
  rate spikes.
- Log ids and counts by default, not user content.

Priority:

```text
Needed for production operations. Logs are enough only during early development.
```

## Future Direction

The next production step is not to resurrect an execution-agent roster. The next
step is to harden memory as the routing layer:

- Add tenant/user scoping to memories, events, links, queue rows, and Pinecone
  namespace or metadata filters.
- Move the source-of-truth database from SQLite to Postgres for production.
- Add FTS or indexed lexical fallback.
- Move queue processing to a production job system with leases and backpressure.
- Add Pinecone timeouts, circuit breaking, and graceful fallback controls.
- Add fully batched hydration if profiling shows query overhead.
- Add retention and compaction for old events.
- Add metrics for fallback rate, search latency, rerank latency, queue lag,
  indexing failures, hydration latency, and dead-letter count.

The central rule should remain:

```text
Memory is durable. Execution workers are disposable.
```
