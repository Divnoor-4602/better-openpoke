# Demo-grade Auth & Workspace Isolation

## Goal

This app is **not** production multi-user. We do not want login flows, accounts, password resets, audit logs, or permission models. What we *do* want is enough separation that several demo testers can hit the same deployment without cross-pollution of:

- threads and messages
- agent runs and execution events
- memory (records, events, links)
- Gmail / Composio connections
- conversation and working-memory logs
- timezone state

A tester picks a handle, gets a private workspace. Another tester picks a different handle, gets a different private workspace. Same deployment, no shared state.

## Decision: HTTP Basic + shared password, user-chosen handle

We gate the entire app behind HTTP Basic auth:

- **Password**: one shared secret in env (`DEMO_PASSWORD=…`). Same for every tester.
- **Username**: chosen freely by the tester. Becomes their `workspace_id`.

The browser handles the prompt natively (no login UI to build). The `Authorization` header rides every subsequent request, including the SSE streaming endpoint (which uses `fetch`, not `EventSource`).

### Why not the alternatives

| Option | Why rejected |
|---|---|
| Cookie auto-mint + UUID workspaces | No gate (anyone who hits the URL is in); UUIDs in URLs are awkward to share; need a `/workspace/me` endpoint and frontend bootstrapping. |
| Per-user passwords (`DEMO_USERS=alice:pw1,…`) | More provisioning for zero benefit at demo scale. |
| Real OIDC (Google login) | Heavy. We do not need real identity. |
| No auth | No isolation possible without an identity axis. |

### Honest downsides we accept

- Native Basic prompt is visually crude (1995 vibes). Fine for tester-handed demos, not for public landings.
- Logout = close tab. Browsers cache Basic creds for the origin per session.
- Two testers in one browser need incognito.
- Treat the password as a bearer secret over HTTPS only.

## Identity model

```
HTTP request
  → HTTPBasic dependency
  → validate password (constant-time compare)
  → normalize username  → workspace_id
  → attached to request, passed to every store call
```

- `workspace_id` is the username, lowercased, alphanumeric + `_`, max 64 chars.
- Composio `userId` = `workspace_id`. Each tester OAuths their own Gmail under their handle.
- No user table. The workspace exists implicitly the moment its first row is written.

## Server changes required

### 1. Auth dependency (~15 LOC)

```python
# server/api/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

def get_workspace_id(
    credentials: HTTPBasicCredentials = Depends(security),
) -> str:
    expected = get_settings().demo_password.encode()
    if not secrets.compare_digest(credentials.password.encode(), expected):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})
    handle = credentials.username.strip().lower()
    if not handle or len(handle) > 64 or not all(
        c.isalnum() or c == "_" for c in handle
    ):
        raise HTTPException(400, "bad handle")
    return handle
```

Add `demo_password: str` to `server/config.py` `Settings`.

### 2. Schema migrations (additive, sentinel backfill)

All three SQLite stores gain a `workspace_id` column. Existing rows backfill to `"default"`. Use the existing `_ensure_column` helpers.

- `threads.db`:
  - `threads.workspace_id TEXT NOT NULL DEFAULT 'default'`
  - `messages.workspace_id` (denormalized for fast filtering)
  - Indexes: `(workspace_id, updated_at)` on threads; `(workspace_id, thread_id, turn_index)` on messages.
- `execution_events.db`:
  - `execution_runs.workspace_id`
  - `execution_events.workspace_id`
  - Indexes: `(workspace_id, updated_at)`, `(workspace_id, thread_id, updated_at)`, `(workspace_id, request_id, id)`.
- `memory.db`:
  - `memories.workspace_id`
  - `events.workspace_id`
  - `links.workspace_id`
  - Unique link index becomes `(workspace_id, memory_id, kind, value)`.
  - Idempotency key check on `events` becomes scoped: `WHERE workspace_id = ? AND idempotency_key = ?`.

Pinecone (when enabled) uses `namespace=workspace_id` everywhere in `services/memory/indexer.py` and `services/memory/hybrid_search.py`.

### 3. Scope every store query

Mechanical pass. Every read/write method on:

- `ThreadRepository` — list/get/create/update/delete thread + message ops
- `ExecutionEventStore` — `list_runs`, `get_run`, `record_event`, `record_submitted`, subscription buckets
- `MemoryStore` — `search`, `create_memory`, `record_event`, `find_memory_by_link`, `ensure_memory_for_links`, `add_links`, `render_memory_context`

All gain a `workspace_id: str` parameter and apply `WHERE workspace_id = ?` to every SELECT, and write it on every INSERT.

Subscription indexing in `ExecutionEventStore` adds a `(workspace_id, thread_id)` bucket so live event fan-out doesn't cross workspaces.

### 4. File-based singletons → per-workspace

These are currently process-global at fixed paths:

- `services/conversation/log.py` → `data/conversation/{workspace_id}/{thread_id}.log`
- `services/conversation/summarization/working_memory_log.py` → `data/working_memory/{workspace_id}/{thread_id}.log`
- `services/timezone_store.py` → `data/timezone/{workspace_id}.json`
- `agents/execution_agent/log_store.py` → per workspace

Replace `_singleton` with a `_cache: dict[str, Instance]` keyed factory: `get_conversation_log(workspace_id, thread_id)`. Threaded together with the per-thread log refactor (see thread-architecture notes) so both axes are isolated in one pass.

### 5. Plumb `workspace_id` through runtimes

- Every route: `workspace_id: str = Depends(get_workspace_id)`.
- `InteractionAgentRuntime.__init__(workspace_id, …)`.
- `ExecutionAgentRuntime.__init__(workspace_id, …)`.
- Tools that grab `get_conversation_log()` directly (4 callsites in `interaction_agent/tools.py`, 1 in `execution_agent/batch_manager.py`): use a `ContextVar[str]` set at request entry. Tools read `current_workspace.get()` — avoids threading the id through every tool signature.
- Composio `initiate_connect` / status / disconnect: pass `user_id=workspace_id` (field already exists in `IntegrationConnectRequest`).

### 6. Background jobs iterate workspaces

`services/gmail/importance_watcher.py` and `services/trigger_scheduler.py` are currently process-global loops. Change to:

```python
while True:
    for workspace_id in list_workspaces_with_gmail():
        await tick_for_workspace(workspace_id)
    await asyncio.sleep(N)
```

`list_workspaces_with_gmail()` = `SELECT DISTINCT workspace_id FROM …` over whichever store tracks Composio connections. One serial loop is fine for demo scale.

## Frontend changes required

- `apps/web/src/lib/poke/client.ts`: configure the generated client's `fetch` with `credentials: 'include'` so the `Authorization` header rides cross-origin requests.
- No login UI. The browser's native Basic prompt is the entire gate.
- CORS on the server: `Access-Control-Allow-Credentials: true` and a non-wildcard `Access-Control-Allow-Origin`.
- Optional: a "you are signed in as X" chip somewhere, derived from a `GET /me` endpoint that just returns `{ workspaceId: <handle> }`.

### SSE / streaming

The streaming endpoint (`POST /threads/{id}/messages/stream`) is consumed via `fetch` with `parseAs: 'stream'`, not `EventSource`. Basic auth headers ride along automatically once the browser has cached creds. No special handling needed.

Verify reverse proxy / CDN does not strip `Authorization` from streaming responses (nginx and Cloudflare defaults are fine).

## Implementation order

1. **Schema migrations + scope every query**, with `workspace_id="default"` hardcoded everywhere it's needed. Backfill existing rows to `"default"`. App still behaves single-user. (~half day)
2. **Auth dependency + ContextVar plumbing**. Routes start reading the workspace from `Depends(get_workspace_id)`. Hardcoded `"default"` only remains in background jobs. (~half day)
3. **Per-workspace file singletons + per-thread log refactor** in one pass. (~half day)
4. **Background jobs iterate workspaces**. (~couple hours)
5. **Frontend: `credentials: 'include'`** and optional `/me` chip. (~1 hour)

Total: ~1.5 days end-to-end.

## What we explicitly do **not** build

- Login UI / signup / password reset
- User table / accounts / profile pages
- Permission checks beyond "do you know the password"
- Email verification
- Account recovery / handle takeover protection
- GDPR / data export / deletion flows
- Per-user rate limiting
- Audit logging
- Role-based access

If any of these become real requirements later, this design is the right scaffolding to graduate from — `workspace_id` becomes the foreign key to a real `users` table, the Basic gate becomes a session, the env password becomes per-user credentials. No data migration required, just additive auth.

## Risks and accepted constraints

- **Handle collision**: two testers both pick `alice` → they share a workspace. Acceptable for a demo; tell testers to use distinct handles. Could be mitigated with a "register handle" step that errors on collision, but that adds state we don't want.
- **Password leak**: anyone with the password can impersonate any handle, including reading another tester's data by guessing their handle. Acceptable for a demo with a trusted invite list.
- **Composio re-OAuth**: if existing single-user Composio connections are tied to an empty or default `userId`, demo testers will need to OAuth their own Gmail under their handle. Existing connections stay on the `"default"` workspace.
- **No graceful logout**: testers close the browser tab or use incognito. Document this in demo instructions.
