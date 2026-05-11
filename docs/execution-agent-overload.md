# Execution Agent Overload

## Problem

The original execution-agent routing model passed every active execution agent name into the interaction agent prompt:

```xml
<active_agents>
  <agent name="Email to Keith" />
  <agent name="DHL Docs" />
</active_agents>
```

That does not scale. Once there are many execution agents, the prompt grows with weak context and the interaction LLM has to guess which name contains the relevant history. The reuse key was also the human-readable `agent_name`, so similar tasks could create duplicate agents or route to the wrong one.

The larger issue is that execution agents were acting as both:

- runtime workers
- persistent memory containers

The first approach separates those concerns.

## Implemented Approach

Execution agents are now treated as temporary workers. Persistent context lives in memory.

```text
original:
agent_name -> execution log -> worker reuse

current:
user query -> relevant memories -> memory_id -> execution worker
```

The durable routing primitive is `memory_id`, not `agent_name`.

## Memory Model

The first implementation adds a SQLite-backed memory store at:

```text
server/data/memory.db
```

It has three core tables:

```text
memories
events
links
```

### Memories

A memory is a reusable context group. Examples:

- Gmail thread
- user task
- contact/topic
- workflow

Shape:

```json
{
  "memory_id": "mem_...",
  "kind": "gmail_thread",
  "title": "DHL shipment documentation AWB 3750993864",
  "summary": "DHL sent support documentation for shipment 3750993864.",
  "created_at": "...",
  "updated_at": "...",
  "metadata": {
    "source": "gmail"
  }
}
```

### Events

An event is one compact structured thing that happened inside a memory context.

Examples:

- `execution_request`
- `tool_call`
- `tool_result`
- `execution_response`
- `gmail_message_seen`
- `gmail_draft_created`
- `gmail_reply_sent`
- `gmail_draft_sent`

Shape:

```json
{
  "event_id": "evt_...",
  "memory_id": "mem_...",
  "idempotency_key": "gmail_message:message_id_here",
  "type": "gmail_message_seen",
  "timestamp": "2026-05-09T17:30:31Z",
  "recorded_at": "2026-05-10T13:21:00Z",
  "source": "gmail",
  "text": "DHL sent support documentation for AWB 3750993864.",
  "metadata": {
    "thread_id": "19e0dca741f6d862",
    "message_id": "...",
    "subject": "Support Documentation for AWB: 3750993864",
    "sender": "no-reply.adc@dhl.com",
    "to": "divnoorsinghnagra@gmail.com"
  }
}
```

### Links

Links attach stable identifiers to memories and events.

Examples:

```json
[
  {"kind": "gmail_thread", "value": "19e0dca741f6d862"},
  {"kind": "gmail_message", "value": "message_id_here"},
  {"kind": "email_address", "value": "no-reply.adc@dhl.com"},
  {"kind": "keyword", "value": "3750993864"}
]
```

For Gmail, the important rule is:

```text
threadId -> memory_id
messageId -> event idempotency
```

This lets all events from the same Gmail thread collapse into the same memory context, while repeated observations of the same message do not duplicate events.

## Prompt Routing

The interaction prompt no longer receives all execution agents.

It now receives ranked memories:

```xml
<relevant_memories>
  <memory id="mem_123" kind="gmail_thread" score="58" confidence="high">
    <title>DHL shipment documentation AWB 3750993864</title>
    <summary>DHL sent support documentation for shipment 3750993864.</summary>
    <links>
      <gmail_thread id="19e0dca741f6d862" />
      <email value="no-reply.adc@dhl.com" />
    </links>
    <recent_events>
      <event type="gmail_message_seen" timestamp="2026-05-09T17:30:31Z">
        DHL sent support documentation for AWB 3750993864.
      </event>
    </recent_events>
  </memory>
</relevant_memories>
```

Only the top relevant memories are passed, currently up to 8.

## Tools

The interaction tool changed from name-based routing:

```python
send_message_to_agent(agent_name, instructions)
```

To memory-based routing:

```python
send_message_to_agent(memory_id=None, task_name=None, instructions="")
```

Rules:

- pass `memory_id` to reuse an existing memory context
- pass `task_name` to create a new memory context
- do not reuse context by guessing from names

A search fallback tool was also added:

```python
search_memory(query: str, limit: int = 8)
```

The interaction agent should call this when the visible `<relevant_memories>` do not contain a fitting context but the request may refer to prior work.

## Execution Worker Context

Execution logs are now keyed by `memory_id`.

When an execution worker starts, it receives:

```text
# Memory Context
title
summary
links
recent events

# Execution History
log for memory_id
```

This lets an execution worker be rebuilt from memory and logs rather than preserved as a long-lived named agent.

## Gmail Integration

The Gmail result shape from Composio exposes useful stable identifiers:

```json
{
  "messageId": "...",
  "threadId": "19e0dca741f6d862",
  "messageTimestamp": "2026-05-09T17:30:31Z",
  "sender": "no-reply.adc@dhl.com",
  "to": "divnoorsinghnagra@gmail.com",
  "subject": "Support Documentation for AWB: 3750993864",
  "preview": {
    "body": "Dear DHL Customer..."
  }
}
```

The memory layer extracts compact metadata and intentionally does not store raw Gmail HTML or full payloads.

Stored links include:

- `gmail_thread`
- `gmail_message`
- `email_address`
- `attachment`
- extracted numeric keywords such as tracking/AWB numbers

## Ranking And Search

Ranking is currently simple lexical scoring over:

- memory title
- memory summary
- memory metadata
- event text
- event metadata
- links

Strong links, especially `gmail_thread`, receive higher weight.

This is intentionally not an embedding/vector system yet. SQLite gives us idempotency and indexed links first. Search quality can later be improved with FTS5 or embeddings without changing the routing model.

## State Reset

After implementing this first approach, old message/execution state was cleared:

- conversation log
- working memory log
- execution logs
- old roster
- memory DB contents

Kept:

- Gmail seen store
- timezone
- triggers
- connection/config data

## Key Difference From The Original Model

Original:

```text
agent = identity + memory + worker
```

Current:

```text
memory = identity/context
execution agent = temporary worker over that memory
```

This removes the core overload problem: the interaction agent no longer needs all execution-agent names in prompt context. It receives a small ranked set of memory contexts and can explicitly search the rest when needed.
