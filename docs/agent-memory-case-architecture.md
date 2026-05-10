# Agent Memory, Case-Based Execution, and Ranked Context Architecture

This document captures the target architecture for OpenPoke's agent system as it evolves from persistent execution-agent logs toward durable cases, ranked memory, connector-driven freshness, and disposable execution workers.

## 1. Core Problem

The current system has an interaction agent that can create execution agents in parallel for different tasks.

Example:

```text
User: Send an email to Alice about the proposal.
Interaction agent creates:
  - Gmail execution agent
```

Today, an execution agent is persistent mostly by name and log file:

```text
server/data/execution_agents/roster.json
server/data/execution_agents/<agent-slug>.log
```

The execution log contains entries like:

```xml
<agent_request>Send an email to Alice about the proposal</agent_request>
<agent_action>Calling gmail_create_draft with: ...</agent_action>
<tool_response>gmail_create_draft: ...</tool_response>
<agent_response>Draft created...</agent_response>
```

This makes the execution agent both:

```text
1. The executor
2. The memory container
```

That works at small scale, but it breaks down as the system creates many execution agents. Passing all worker names, contexts, and histories into the interaction-agent prompt creates context bloat and makes routing depend on fragile agent names.

The architecture should shift from:

```text
agent name = memory identity
worker log = continuation state
interaction agent = chooses worker by name
```

to:

```text
case/entity = memory identity
case log = continuation state
memory ranker = chooses relevant context
execution worker = disposable runtime
```

Best principle:

```text
The execution worker is disposable.
The case, action log, external handle, and memory record are durable.
```

## 2. Current System Summary

Current OpenPoke has two main agent layers:

```text
User
  |
  v
InteractionAgentRuntime
  |
  | send_message_to_agent(agent_name, instructions)
  v
ExecutionBatchManager
  |
  | async execution jobs
  v
ExecutionAgentRuntime(agent_name)
```

The interaction agent:

- owns user-facing conversation flow
- records user messages and replies in the conversation log
- sees active execution agent names in its prompt
- can send work to execution agents with `send_message_to_agent`
- can receive execution results through `handle_agent_message`

The execution agent:

- is created fresh for each execution request
- loads prior memory by reading its agent-specific log file
- runs LLM/tool loops
- records actions, tool responses, and final responses
- returns a final result to the batch manager

Current batching is fan-out/fan-in:

```text
Agent A starts
Agent B starts
Agent C starts

Agent B finishes first
  -> result stored in batch
  -> no user-facing result yet

Agent A finishes
  -> result stored in batch

Agent C finishes
  -> pending becomes 0
  -> combined batch result sent to interaction agent
```

The batch manager emits one combined result after every pending execution in the active batch finishes. It does not stream partial worker results to the user.

Important caveat: current batching is based on one active batch state, not a strict user-turn ID. If a second user message starts new execution work while a first batch is still open, the new work can join the active batch.

## 3. Target High-Level Architecture

```text
User Message
  |
  v
InteractionAgentRuntime
  |
  v
Intent + Entity Extraction
  |
  v
CaseResolver
  |
  v
ContextCandidateRetriever
  |-- Working memory summary
  |-- Recent conversation tail
  |-- Active cases from DB
  |-- Relevant memories from Supermemory
  |-- Current external state via connectors when needed
  |
  v
ContextRanker
  |
  v
ContextPacker
  |
  v
Interaction Agent Prompt
  |
  v
Decision:
  |-- Answer from memory/state
  |-- Refresh via connector
  |-- Spin up execution worker for action
```

The interaction agent should receive a compact ranked context pack, not a full list of workers.

## 4. Main Design Principle

Old model:

```text
Worker owns memory.
Worker owns action logs.
Worker identity matters.
Interaction agent finds old worker.
```

New model:

```text
Case owns memory.
Case owns action history.
External object owns freshness.
Worker is temporary.
Interaction agent finds case/entity.
```

The interaction agent should think in terms of:

```text
case
entity
source
status
external handle
memory event
```

not:

```text
agent name
old worker identity
full worker prompt
```

## 5. Durable Concepts

### 5.1 Case

A case is the durable unit of work.

Examples:

```text
Email Alice about proposal
Check Vercel invoice email
Follow up with Sarah
Update Linear issue
Sync Notion launch doc
```

A case represents a user task or external workflow that may continue over time.

```ts
type Case = {
  id: string

  source: "gmail" | "linear" | "notion" | "calendar" | "slack" | "generic"

  entityType:
    | "gmail_thread"
    | "gmail_draft"
    | "linear_issue"
    | "notion_page"
    | "calendar_event"
    | "generic_task"

  entityId?: string

  title: string
  summary: string

  status:
    | "new"
    | "active"
    | "waiting_user"
    | "waiting_external"
    | "resolved"
    | "deactivated"
    | "reopened"

  primaryAgentId?: string
  lastWorkerRunId?: string

  createdAt: string
  updatedAt: string
  lastCheckedAt?: string

  metadata: Record<string, unknown>
}
```

For Gmail, `entityId` should usually become the Gmail `threadId`. Gmail's `threads` resource groups replies with the original message into one conversation and can retrieve all messages in that conversation in order. This makes `gmailThreadId` the correct durable freshness handle for email workflows.

Reference: https://developers.google.com/workspace/gmail/api/guides/threads

### 5.2 CaseEntity

Cases should be searchable by people, emails, subjects, source objects, and user wording.

```ts
type CaseEntity = {
  caseId: string

  entityType:
    | "person"
    | "email"
    | "gmail_thread"
    | "gmail_message"
    | "gmail_draft"
    | "linear_issue"
    | "notion_page"
    | "topic"
    | "project"

  entityValue: string
  normalizedValue: string
}
```

Example:

```text
case_email_alice_123 | person       | Alice             | alice
case_email_alice_123 | email        | alice@example.com | alice@example.com
case_email_alice_123 | gmail_thread | thread_abc        | thread_abc
case_email_alice_123 | topic        | proposal          | proposal
```

### 5.3 CaseEvent

A case event records meaningful state changes and actions.

```ts
type CaseEvent = {
  id: string
  caseId: string

  type:
    | "created"
    | "worker_started"
    | "tool_called"
    | "draft_created"
    | "email_sent"
    | "email_received"
    | "status_changed"
    | "worker_completed"
    | "worker_failed"
    | "resolved"
    | "reopened"

  source: "gmail" | "linear" | "notion" | "calendar" | "slack" | "generic"

  agentId?: string
  workerRunId?: string
  toolName?: string

  entityType?: string
  entityId?: string

  summary: string
  rawLogRef?: string

  createdAt: string
  metadata?: Record<string, unknown>
}
```

### 5.4 WorkerRun

A worker run is one execution instance. The same conceptual worker type can run many times across many cases. The runtime is disposable.

```ts
type WorkerRun = {
  id: string
  caseId: string

  workerType:
    | "gmail_reply_worker"
    | "gmail_search_worker"
    | "linear_issue_worker"
    | "notion_page_worker"
    | "generic_execution_worker"

  agentId?: string

  status: "running" | "succeeded" | "failed" | "cancelled"

  startedAt: string
  completedAt?: string

  rawLogRef: string
  summary?: string
}
```

### 5.5 AgentProfile

Agent profiles are reusable skill templates, not task-specific memory containers.

Good permanent profiles:

```text
gmail_reply_worker_profile
gmail_search_worker_profile
linear_issue_worker_profile
notion_page_worker_profile
```

Bad permanent profiles:

```text
send-email-to-alice-about-proposal-worker
find-vercel-email-from-last-week-worker
```

Those should be cases, not permanent workers.

```ts
type AgentProfile = {
  id: string
  workerType: string

  purpose: string
  tools: string[]
  instructions: string

  reusableSkillSummary: string

  createdAt: string
  updatedAt: string
}
```

## 6. Memory Layers

The system should have four memory layers.

### 6.1 Raw Audit Logs

Complete append-only logs.

Examples:

```text
server/data/conversation/poke_conversation.log
server/data/cases/case_email_alice_123/action_log.jsonl
server/data/cases/case_email_alice_123/runs/run_001.log
```

Used for:

```text
debugging
audit
exact replay
tool trace inspection
failure recovery
```

Do not inject raw logs into prompts by default.

### 6.2 Working Memory

Current interaction memory.

Existing architecture:

```text
poke_working_memory.log
  - one conversation_summary
  - recent unsummarized entries
```

This should stay.

Working memory answers:

```text
What has the current conversation been about?
What is the recent context?
What commitments/preferences are active?
```

It should remain:

```text
conversation_summary + recent tail
```

### 6.3 Retrieval Memory / Supermemory

Supermemory should be used as the searchable context layer.

It stores:

```text
case summaries
agent events
tool result summaries
workflow patterns
user preferences
conversation summary chunks
cross-source event memories
```

Supermemory supports hybrid search over memories and document chunks, metadata filtering, recency-oriented ranking inputs, and reranking. This makes it a good fit for retrieving relevant memory without stuffing all history into the interaction prompt.

Reference: https://supermemory.ai/docs/search

Supermemory should not be the source of truth for current status. It is a recall layer.

### 6.4 State DB

The source of truth for current state.

Stores:

```text
active cases
case status
worker run status
external object IDs
last checked timestamps
last known message IDs
resolved/deactivated state
```

If Supermemory says a case is waiting, but DB says it is resolved, DB wins.

## 7. Supermemory Usage

Supermemory should store summaries and searchable event memories, not full raw logs.

### 7.1 Memory Types

```ts
type MemoryType =
  | "conversation_summary_block"
  | "case_summary"
  | "agent_event"
  | "tool_result_summary"
  | "case_status_update"
  | "workflow_pattern"
  | "user_preference"
  | "final_outcome"
```

### 7.2 Memory Record Shape

```ts
type MemoryRecord = {
  content: string

  metadata: {
    memoryType: MemoryType

    userId: string
    caseId?: string
    agentId?: string
    workerRunId?: string
    batchId?: string

    source?: "gmail" | "linear" | "notion" | "calendar" | "slack" | "generic"

    entityType?: string
    entityId?: string

    status?: string

    toolName?: string
    rawLogRef?: string

    occurredAt?: string
    createdAt: string
    updatedAt?: string

    supersedesMemoryId?: string
    supersededBy?: string

    importance?: number
  }
}
```

### 7.3 Example: Gmail Case Summary Memory

```json
{
  "content": "The user asked to send an email to Alice about the proposal. The Gmail worker sent the email and linked it to Gmail thread thread_abc. The case is waiting for Alice to respond.",
  "metadata": {
    "memoryType": "case_summary",
    "userId": "user_123",
    "caseId": "case_email_alice_123",
    "source": "gmail",
    "entityType": "gmail_thread",
    "entityId": "thread_abc",
    "status": "waiting_external",
    "agentId": "agent_gmail_reply_profile",
    "workerRunId": "run_001",
    "rawLogRef": "server/data/cases/case_email_alice_123/runs/run_001.log",
    "createdAt": "2026-05-10T00:00:00Z"
  }
}
```

### 7.4 Example: Agent Event Memory

```json
{
  "content": "Gmail worker run_001 sent an email to Alice about the proposal and stored Gmail thread thread_abc for future response checks.",
  "metadata": {
    "memoryType": "agent_event",
    "userId": "user_123",
    "caseId": "case_email_alice_123",
    "source": "gmail",
    "entityType": "gmail_thread",
    "entityId": "thread_abc",
    "toolName": "gmail.send",
    "status": "waiting_external",
    "workerRunId": "run_001",
    "createdAt": "2026-05-10T00:00:00Z"
  }
}
```

### 7.5 Supermemory Graph Semantics

Supermemory's public model describes memory relationships as a graph of facts built on other facts, not primarily as classic entity-relation-entity triples.

The public relation types are:

```text
updates
extends
derives
```

Use them conceptually as:

```text
updates:
  New memory supersedes older memory.

extends:
  New memory adds detail without invalidating the older memory.

derives:
  New memory is inferred from one or more previous memories.
```

For OpenPoke, prefer append-only correction events by default. Do not erase old memories simply because state changed.

Example:

```json
{
  "content": "Alice replied to the Gmail thread. The previous waiting_external state is now stale. The case is waiting for user review.",
  "metadata": {
    "memoryType": "case_status_update",
    "caseId": "case_email_alice_123",
    "source": "gmail",
    "entityType": "gmail_thread",
    "entityId": "thread_abc",
    "previousStatus": "waiting_external",
    "newStatus": "waiting_user",
    "supersedesMemoryId": "mem_old_456"
  }
}
```

## 8. Conversation Summarization Integration

Current summarization behavior:

```text
conversation_summary_threshold = 100
conversation_summary_tail_size = 10
```

After around 110 unsummarized entries:

```text
summarize entries 0..99
keep entries 100..109 raw
```

This should remain, but summarization should also write searchable memory.

Improved flow:

```text
Before:
  entries 0..109 raw

Summarization:
  summarize entries 0..99
  keep entries 100..109 raw

New additional step:
  write conversation_summary_block to Supermemory
  optionally write smaller semantic chunks/events to Supermemory

After:
  working memory = summary + recent raw tail
  retrieval memory = searchable chunks/events for old messages
  raw log = complete source of truth
```

Pseudo-code:

```python
def summarize_if_needed():
    block = unsummarized_entries[:100]
    tail = unsummarized_entries[100:]

    summary = update_conversation_summary(block)

    working_memory.save(
        conversation_summary=summary,
        recent_tail=tail,
    )

    supermemory.add(
        content=summary,
        metadata={
            "memoryType": "conversation_summary_block",
            "source": "interaction_agent",
            "startEntryId": block[0].id,
            "endEntryId": block[-1].id,
            "rawLogRef": "server/data/conversation/poke_conversation.log",
        }
    )
```

This turns the architecture from:

```text
summary-only recall
```

into:

```text
summary + retrieval-based recall
```

## 9. Execution Worker Flow

### 9.1 Action Request

Example:

```text
User: Send an email to Alice about the proposal.
```

Flow:

```text
Interaction agent
  |
  v
extract intent/entities
  |
  v
create Case
  |
  v
spin up Gmail worker
  |
  v
worker receives hydration context
  |
  v
worker sends/drafts email
  |
  v
worker writes complete raw log
  |
  v
case state updates
  |
  v
case event is recorded
  |
  v
Supermemory gets searchable event/summary
  |
  v
worker shuts down
```

The worker should not need to remain active.

### 9.2 Worker Hydration Context

A fresh worker should receive:

```xml
<case_state>
  caseId: case_email_alice_123
  source: gmail
  status: waiting_external
  recipient: Alice
  gmailThreadId: thread_abc
</case_state>

<case_summary>
  User asked to send an email to Alice about the proposal.
  Email was sent last week.
</case_summary>

<relevant_action_summaries>
  run_001: Gmail worker sent email and linked thread_abc.
</relevant_action_summaries>

<fresh_external_state>
  Gmail thread currently contains...
</fresh_external_state>

<user_preferences>
  User prefers concise, friendly email replies.
</user_preferences>
```

Only load full raw logs if exact details are required.

## 10. Freshness Model

Freshness should be connector-driven, not agent-driven.

For Gmail, the source of truth is Gmail.

To check whether Alice responded:

```text
resolve case
  |
  v
get gmailThreadId
  |
  v
call Gmail thread retrieval
  |
  v
compare latest messages to lastKnownMessageId / lastCheckedAt
  |
  v
update case state
  |
  v
write Supermemory status event if changed
  |
  v
answer user
```

Do not wake the old execution worker just to check freshness.

The Gmail API supports push notifications for mailbox changes. Gmail sends a notification with a `historyId`, and the app then uses the history API to fetch mailbox deltas. This is the right background sync mechanism for keeping Gmail cases fresh.

Reference: https://developers.google.com/workspace/gmail/api/guides/push

Freshness flow:

```text
User: Did Alice respond?
  |
  v
Interaction agent extracts:
  person = Alice
  source = gmail
  intent = response/status check
  |
  v
CaseResolver finds:
  case_email_alice_123
  gmailThreadId = thread_abc
  |
  v
GmailConnector refetches thread
  |
  v
CaseManager updates status
  |
  v
MemoryReconciler writes update to Supermemory if changed
  |
  v
Interaction agent answers
```

## 11. Background Gmail Worker

The current OpenPoke Gmail watcher polls recent inbox messages, skips seen message IDs, classifies importance, and dispatches important summaries to the interaction agent. It is not yet a durable Gmail case synchronizer.

The future Gmail background worker should have access to Supermemory, but only through a constrained memory reconciler.

Its main job:

```text
sync Gmail reality into local case state
```

Not:

```text
act as the source of truth
freely rewrite memory history
decide all agent lifecycle from memory
```

Recommended split:

```text
GmailSyncWorker
  - reads Gmail deltas / historyId / recent changes
  - updates local GmailCase DB
  - emits meaningful domain events

ImportantEmailWatcher
  - decides what should proactively interrupt the user

MemoryEventWriter
  - writes important case/event memories to Supermemory
```

Background Gmail flow:

```text
Gmail push / polling
  |
  v
GmailSyncWorker
  |
  v
fetch history delta / changed thread
  |
  v
normalize to IntegrationEvent
  |
  v
CaseManager updates local DB
  |
  v
MemoryReconciler writes new memory event
  |
  v
AgentRuntimeManager optionally wakes worker
```

Allowed memory actions:

```text
write new event memories
mark old memories superseded
retrieve related context when DB lookup is insufficient
```

Avoid:

```text
deleting old memories for normal stale state
treating Supermemory as current truth
rewriting history aggressively
```

Use append-only correction memories by default.

## 12. Context Ranking System

The interaction agent should not receive all memories. It should receive a ranked context pack.

### 12.1 Candidate Retrieval

Candidate sources:

```text
active cases from DB
pending user actions from DB
relevant memories from Supermemory
recent case events
relevant workflow patterns
relevant user preferences
```

Supermemory should be used for semantic/hybrid retrieval and metadata filtering. Hybrid retrieval is useful because it combines semantic matching with exact keyword/entity matching.

### 12.2 Ranking Formula

Use semantic relevance as the backbone, but not the only signal.

```python
final_score =
    0.35 * semantic_score
  + 0.20 * lifecycle_score
  + 0.15 * entity_match_score
  + 0.10 * recency_score
  + 0.10 * importance_score
  + 0.05 * source_tool_match_score
  + 0.05 * continuity_score
  - stale_penalty
```

Signals:

```text
semantic_score:
  Does this memory match the current user message?

lifecycle_score:
  active / waiting_user / waiting_external / resolved / archived

entity_match_score:
  Alice / Vercel / Sarah / LIN-428 / thread_abc

recency_score:
  Time decay based on memory type and status

importance_score:
  User preference, blocker, pending action, critical task

source_tool_match_score:
  Gmail query should prefer Gmail memories/tools

continuity_score:
  Was this recently discussed or touched?

stale_penalty:
  Superseded, archived, resolved, or deactivated memories
```

Supermemory can rerank retrieval results, but application-level reranking is still needed because only OpenPoke knows lifecycle status, stale state, case priority, and current external truth.

Reference: https://supermemory.ai/docs/memory-api/features/reranking

### 12.3 Decay Model

Use lifecycle-aware decay. Do not decay all memories equally.

```python
recency_score = 0.5 ** (age_days / half_life_days)
```

Recommended half-lives:

```python
HALF_LIFE_DAYS = {
    "active_case": 45,
    "waiting_user": 45,
    "waiting_external": 14,
    "agent_event": 7,
    "tool_result_summary": 7,
    "resolved_case": 3,
    "superseded_status": 1,
    "workflow_pattern": 90,
    "user_preference": 180,
}
```

Rules:

```text
active and waiting_user memories decay slowly
waiting_external memories decay moderately
resolved cases decay quickly
superseded memories decay very quickly
workflow patterns decay slowly
user preferences decay very slowly
```

Decay should affect prompt inclusion, not permanent deletion.

## 13. Interaction Agent Prompt Shape

Do not pass this:

```xml
<available_workers>
  <worker name="send-email-to-alice-worker">
    full worker context...
  </worker>
  <worker name="find-vercel-email-worker">
    full worker context...
  </worker>
  ...
</available_workers>
```

Pass this instead:

```xml
<system_instructions>
You are the interaction agent.

Rules:
- Resolve durable cases/entities first.
- Check external truth through connectors.
- Use retrieved memories for historical context.
- Wake execution workers only for new actions.
- Do not assume Supermemory is current truth.
- DB and external connectors are authoritative for current state.
</system_instructions>

<working_memory>
Conversation summary + recent tail.
</working_memory>

<active_cases>
  <case id="case_email_alice_123" source="gmail" status="waiting_external">
    Email sent to Alice about the proposal. Waiting for response.
    Gmail thread: thread_abc.
  </case>
</active_cases>

<retrieved_memories>
  <memory id="mem_123" type="agent_event" score="0.91">
    Gmail worker sent the Alice email and linked it to thread_abc.
  </memory>
</retrieved_memories>

<new_user_message>
Did Alice respond?
</new_user_message>
```

## 14. Query Modes

The interaction agent should classify the user query mode.

```ts
type QueryMode =
  | "current_state"
  | "historical"
  | "action"
  | "preference"
  | "general"
```

### Current State Query

Examples:

```text
Did Alice respond?
Any updates from Sarah?
What is pending?
```

Use:

```text
case DB
external connector
active/pending memories
strong lifecycle weighting
```

### Historical Query

Examples:

```text
What happened with Alice?
Which agent sent that email?
What did the worker do last time?
```

Use:

```text
Supermemory
case events
action summaries
raw logs only if exact detail needed
```

### Action Query

Examples:

```text
Reply to Alice.
Send a follow-up.
Update the Notion doc.
Move the Linear issue.
```

Use:

```text
case resolution
fresh external state
relevant memory
then spin up worker
```

## 15. Case Resolution Algorithm

When the user references something old:

```text
Did Alice respond?
```

Do not search workers first. Resolve the case first.

```python
def resolve_case_for_query(query):
    intent = classify_intent(query)
    entities = extract_entities(query)

    # 1. Exact local lookup
    cases = case_db.search(
        entities=entities,
        statuses=["active", "waiting_user", "waiting_external", "resolved"],
    )

    if confident(cases):
        return cases[0]

    # 2. Fuzzy memory lookup
    memories = supermemory.search(
        query=query,
        filters={
            "memoryType": ["case_summary", "agent_event", "case_status_update"],
        },
        limit=10,
        rerank=True,
    )

    case_ids = extract_case_ids(memories)

    cases = case_db.get_cases(case_ids)

    return rerank_cases(cases, query, entities, intent)
```

## 16. Worker Activation Algorithm

Only activate workers when needed.

```python
def maybe_activate_worker(query, case, mode):
    if mode in ["historical", "current_state"]:
        return None

    if mode == "action":
        context = build_worker_hydration_context(case)
        return agent_runtime_manager.start_worker(
            worker_type=select_worker_type(case),
            case_id=case.id,
            context=context,
        )
```

Do not wake a worker just to check Gmail freshness. Use the Gmail connector for that.

## 17. Gmail Example End-to-End

### Step 1: User Asks To Send Email

```text
User: Send an email to Alice about the proposal.
```

System:

```text
create case_email_alice_123
spin gmail_reply_worker run_001
send email
store gmailThreadId = thread_abc
status = waiting_external
write raw run log
write case event
write Supermemory case_summary + agent_event
shutdown worker
```

### Step 2: Background Gmail Sync Sees Reply

```text
Gmail push/history delta
  |
  v
GmailSyncWorker sees new message in thread_abc
  |
  v
CaseManager finds case_email_alice_123
  |
  v
status waiting_external -> waiting_user
  |
  v
Supermemory writes case_status_update
  |
  v
optionally wake worker if auto-draft is enabled
```

### Step 3: User Asks Later

```text
User: Did Alice respond?
```

System:

```text
extract Alice + response check
resolve case_email_alice_123
check Gmail thread thread_abc if needed
answer:
  "Yes, Alice replied. The case is waiting for your review."
```

No old worker needed.

### Step 4: User Asks For Action

```text
User: Reply to her and say Friday works.
```

System:

```text
resolve case_email_alice_123
fetch latest Gmail thread
build hydration context
spin new gmail_reply_worker run_002
draft/send reply
append run log
update case
write Supermemory event
shutdown worker
```

## 18. Integration Scaling

This architecture should work for Gmail, Notion, Linear, Slack, Calendar, and other integrations.

Each integration implements a connector.

```ts
interface IntegrationConnector {
  source: "gmail" | "linear" | "notion" | "calendar" | "slack"

  receiveWebhook?(payload: unknown): Promise<IntegrationEvent[]>

  pollChanges?(cursor: string): Promise<{
    events: IntegrationEvent[]
    nextCursor: string
  }>

  fetchEntity(entityId: string): Promise<IntegrationEntity>

  executeAction(action: IntegrationAction): Promise<IntegrationActionResult>
}
```

After normalization, every integration produces:

```ts
type IntegrationEvent = {
  id: string

  source: "gmail" | "linear" | "notion" | "calendar" | "slack"

  eventType: string

  entityType: string
  entityId: string

  title?: string
  content?: string
  summary?: string

  actor?: {
    id?: string
    name?: string
    email?: string
  }

  occurredAt: string
  receivedAt: string

  metadata: Record<string, unknown>
}
```

Then the rest of the system is mostly generic:

```text
Event Router
Case Manager
Memory Reconciler
Context Ranker
Agent Runtime Manager
```

Only the connector/tool adapter is integration-specific.

## 19. Final Component Responsibilities

### InteractionAgentRuntime

```text
Owns conversation flow.
Loads working memory.
Requests ranked context pack.
Decides whether to answer, refresh, or act.
Does not receive all worker contexts.
```

### CaseManager

```text
Owns current case state.
Creates cases.
Updates statuses.
Stores external handles.
Maps cases to entities and worker runs.
Source of truth for lifecycle.
```

### ContextCandidateRetriever

```text
Retrieves candidate memories from:
- local DB active cases
- Supermemory
- recent events
- user preferences
```

### ContextRanker

```text
Scores candidates using:
- semantic relevance
- lifecycle status
- entity match
- recency decay
- source/tool match
- importance
- stale penalties
```

### ContextPacker

```text
Fits top context into prompt budget.
Includes:
- active cases
- pending user actions
- relevant retrieved memories
- relevant worker profile only if needed
```

### ExecutionWorker

```text
Temporary runtime.
Receives hydration context.
Performs action.
Writes complete run log.
Updates case state.
Shuts down.
```

### MemoryReconciler

```text
Writes searchable summaries to Supermemory.
Marks stale memories superseded.
Never treats Supermemory as source of truth.
```

### IntegrationConnector

```text
Fetches fresh external state.
Executes source-specific actions.
Handles API/webhook details.
```

## 20. Final Rules

### Rule 1

```text
Do not preserve workers for memory.
Preserve cases, action logs, and external handles.
```

### Rule 2

```text
Do not pass all workers into the interaction agent prompt.
Pass a ranked context pack.
```

### Rule 3

```text
Resolve cases/entities before resolving agents.
```

### Rule 4

```text
Use connectors for freshness.
Use execution workers for action.
```

### Rule 5

```text
Supermemory is recall, not truth.
DB + external APIs are truth.
```

### Rule 6

```text
Raw logs stay local.
Supermemory stores searchable summaries and metadata links.
```

### Rule 7

```text
Workers are disposable.
Worker runs are durable.
Cases are durable.
```

## 21. Final Architecture Summary

```text
Raw logs:
  Complete trace. Local. Used for audit/debug/replay.

Working memory:
  Conversation summary + recent tail. Always injected.

Supermemory:
  Searchable memory/event graph. Used for recall.

State DB:
  Current truth. Cases, statuses, external handles, worker runs.

Connectors:
  Fresh external state. Gmail/Linear/Notion/etc.

Execution workers:
  Temporary action runtimes. Hydrated from case memory.

Interaction agent:
  Receives ranked context pack. Does not know all workers.
```

The final mental model:

```text
The interaction agent does not search for old workers.
It searches for durable cases and ranked memories.

The case points to:
  - external source object
  - current status
  - relevant memory
  - previous worker runs
  - raw action logs

If action is needed:
  spin a fresh worker with hydrated case context.

If freshness is needed:
  use the connector.

If history is needed:
  use Supermemory and raw logs only if necessary.
```

Best one-liner:

```text
Do not make execution agents the memory system. Make cases and ranked memory the memory system, and let execution agents be disposable workers hydrated from that state.
```
