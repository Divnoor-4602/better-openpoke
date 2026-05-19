# Workspace Isolation — Implementation Notes

Companion to [`auth-demo-isolation.md`](./auth-demo-isolation.md), which describes the *design*. This doc describes the *code* — what was actually built, where it lives, and the design calls that came up during implementation.

## Goal recap

Gate the whole server behind a single shared `DEMO_PASSWORD`. The username portion of the Basic auth credentials becomes a `workspace_id` that scopes every piece of per-user data: threads, agent runs, memories, triggers, Composio Gmail connections, conversation logs, timezone, execution logs, Pinecone namespace. Two testers pointing the same browser at the same deployment never see each other's data.

Frontend login UI and deployment plumbing are explicitly out of scope for this doc; both are tracked as follow-ups.

---

## Architectural decisions

### 1. Two layers of `workspace_id` resolution

Every store method that touches per-workspace data has the same signature shape:

```python
def list_threads(
    self, *, workspace_id: str | None = None, offset: int, limit: int,
) -> ...:
    workspace_id = _resolve_workspace(workspace_id)
    ...
```

`_resolve_workspace` returns `workspace_id or require_current_workspace()` — i.e. the explicit arg if given, otherwise the `ContextVar` set by the FastAPI dependency. This keeps the migration ergonomic:

- **Request-bound callers** (routes, runtimes invoked from routes, tools running inside the request task) — just don't pass `workspace_id`; the dep already bound the ContextVar.
- **Background tasks** (trigger scheduler, email watcher) — explicitly `set_current_workspace(...)` before each tick.

Trade-off: implicit ContextVar resolution is less obvious than threading the value everywhere, but it would have been ~100 call sites otherwise. The cost is that forgetting to set the ContextVar in a new background task surfaces as a `RuntimeError` at the first store call, not at code-review time. The error message is loud enough.

### 2. Async dep, not middleware

`get_workspace_id` is an `async def` FastAPI dependency, not a Starlette middleware. The reason: sync dependencies run in a threadpool via `run_in_threadpool`, which creates a fresh `Context` copy that doesn't propagate ContextVar mutations back to the route handler. An async dep runs in the request's own asyncio task, so the `set_current_workspace(...)` side-effect *does* propagate to the (possibly sync) route handler that follows.

### 3. Health stays unauth, everything else gated globally

`api/__init__.py` mounts two routers:
- `public_router` (prefix `/api`) → just `/api/health` (Railway etc. need it without creds).
- `api_router` (prefix `/api`, `dependencies=[Depends(get_workspace_id)]`) → everything else; the dep runs once per request, gates and binds the ContextVar.

Individual routes don't need to declare `Depends(get_workspace_id)` themselves. Routes that need the *value* (e.g. integrations to pass it to Composio) can still declare it as a parameter or call `require_current_workspace()` directly.

### 4. Drop DBs, no migration code

Pre-existing app is in dev. `rm -rf server/data/` before first boot; schemas re-created with `workspace_id TEXT NOT NULL` baked into the `CREATE TABLE` from the start. No `_ensure_column` dance, no backfill, no `'default'` sentinel. Cleaner schemas, faster work, accepted re-OAuth cost for testers.

### 5. Pinecone namespace = workspace_id

Rather than partitioning vectors by metadata filter inside a single shared namespace, each workspace gets its own Pinecone namespace. The queue table (`memory_index_queue`) carries `workspace_id` per row, the indexer groups rows by workspace before issuing upsert/delete calls, and the search path passes `namespace=workspace_id` on queries. `settings.pinecone_namespace` is no longer read anywhere.

### 6. Handle collision: observability, not enforcement

In a shared-password world, two testers can pick the same handle and accidentally share a workspace. Solving this properly requires per-user passwords (rejected as too much provisioning for demo scale). Instead, `workspace_registry` records the first IP that registered each handle and logs a warning if a second IP shows up. Doesn't reject — gives operators visibility.

### 7. SDK stays dumb about auth

Basic auth is stateless server-side; there is no `POST /auth/login`. The generated SDK (`@openpoke/sdk`) gets:
- `retrieveMe` query (for the frontend to validate credentials).
- The existing `fetch` injection point for the frontend's `authFetch` wrapper.

No `login()` / `logout()` methods — those are pure client-side concepts (write or clear `sessionStorage`).

---

## Server layout

```
server/
  app.py                       # lifespan; mounts public + api routers; CORS allow_credentials=True
  config.py                    # adds demo_password (required)
  api/
    __init__.py                # public_router (health) + api_router with global get_workspace_id dep
    dependencies.py            # get_workspace_id (async, validates, binds ContextVar, registers in workspace_registry)
    routes/
      me.py                    # GET /api/me → {workspaceId}
      admin.py                 # GET /api/admin/workspaces → list all registered handles
      dev.py                   # POST /api/dev/reset → clears the caller's workspace
      integrations.py          # forces Composio user_id = workspace_id
      threads.py, agent_runs.py, gmail/, calendar/, meta.py  # existing routes, now auto-gated
  core/
    workspace_context.py       # ContextVar + set/get/require helpers
  db/
    threads.py                 # workspace_id column on threads + messages
    workspace_registry.py      # observability table (handle → first IP / first seen)
  services/
    memory/
      store.py                 # workspace_id on memories/events/links/memory_index_queue
      hybrid_search.py         # query + exact-link + recent-unindexed scoped by workspace
      indexer.py               # upsert/delete batches per workspace; namespace=workspace_id
      worker.py                # unchanged (queue claiming is workspace-agnostic; indexer groups)
      ranking.py               # PromptContextRanker + SearchResultRanker take workspace_id
    triggers/
      store.py + service.py + models.py    # workspace_id on triggers
    execution/
      event_store.py           # workspace_id on execution_runs + execution_events; subscription buckets keyed by (workspace_id, …)
      log_store.py             # per-workspace dict cache → data/execution_agents/{workspace_id}/
    conversation/
      log.py                   # per-workspace cache → data/conversation/{workspace_id}/poke_conversation.log
      summarization/
        working_memory_log.py  # per-workspace cache → data/working_memory/{workspace_id}/...
        scheduler.py           # per-workspace pending/running sets; binds ContextVar before dispatch
        summarizer.py          # accepts optional workspace_id (defaults to ContextVar)
    timezone_store.py          # per-workspace cache → data/timezone/{workspace_id}.txt
    gmail/
      importance_watcher.py    # outer-loops workspaces, per-workspace seen store, per-tick timeout
      connections.py           # JSON-file registry of workspaces with Gmail (data/gmail_workspaces.json)
      seen_store.py            # unchanged (path-scoped); now instantiated per workspace
    trigger_scheduler.py       # binds ContextVar per trigger dispatch; clear_next_fire passes workspace
  integrations/
    google.py                  # register_workspace/unregister_workspace hooks around Composio calls
  tests/
    conftest.py                # demo password env, dep override, ContextVar fallback patch
```

---

## Phase-by-phase log

### Phase 1 — Auth primitives + CORS

**Goal:** server boots gated; `/api/me` works end-to-end.

- `server/config.py` — `demo_password: str = Field(default=os.getenv("DEMO_PASSWORD", ""))`. `server/app.py` raises `RuntimeError` at import time if it's empty.
- `server/core/workspace_context.py` — single `ContextVar[str | None]` named `openpoke_current_workspace` + `set_/get_/require_current_workspace`.
- `server/api/dependencies.py` — `HTTPBasic(auto_error=True)` security; constant-time password compare via `secrets.compare_digest`; handle normalized to lowercase `[a-z0-9_]{1,64}`; binds ContextVar as a side effect; registers in `workspace_registry` (added in Phase E).
- `server/api/routes/me.py` — `GET /me` returning `MeResponse` (`workspaceId: str`). Operation ID `retrieve_me`.
- `server/api/schemas.py` — adds `MeResponse`.
- `server/api/__init__.py` — splits into `public_router` (health, unauth) and `api_router` (everything else, global `Depends(get_workspace_id)`).
- `server/app.py` — flips `allow_credentials=True` on CORS; mounts both routers.
- `.env.example` — adds `DEMO_PASSWORD=change_me` and documents `OPENPOKE_CORS_ALLOW_ORIGINS`.

**Behavior:** No auth on `/api/health` (200). Anything else without auth → 401 with `WWW-Authenticate: Basic`. Bad password → 401. Bad handle → 400.

### Phase 2 — Schema rewrite (destructive)

`rm -rf server/data/` before first boot. Re-created with `workspace_id TEXT NOT NULL` in every `CREATE TABLE` and workspace-prefixed indexes from the start:

| Table | Indexes added |
|---|---|
| `threads` | `(workspace_id, updated_at DESC)` |
| `messages` | `(workspace_id, thread_id, turn_index, created_at)` |
| `execution_runs` | `(workspace_id, updated_at)`, `(workspace_id, thread_id, updated_at)` |
| `execution_events` | `(workspace_id, request_id, id)` |
| `memories` | `(workspace_id, updated_at DESC)` |
| `events` | `(workspace_id, memory_id)`, `(workspace_id, type)`, `(workspace_id, timestamp)`, unique `(workspace_id, idempotency_key)` |
| `links` | `(workspace_id, kind, value)`, `(workspace_id, memory_id)`, unique `(workspace_id, memory_id, kind, value)` |
| `memory_index_queue` | `(workspace_id, entity_type, entity_id)`, unique `(workspace_id, idempotency_key)` where active |
| `triggers` | `(workspace_id, agent_name, next_trigger)`, `(status, next_trigger)` |
| `workspace_registry` | `(first_seen_at)` |

### Phase 3 — Query scoping (mechanical)

Every public method on `ThreadRepository`, `ExecutionEventStore`, `MemoryStore`, `TriggerStore`, `TriggerService` gained `workspace_id: str | None = None` + `workspace_id = _resolve_workspace(workspace_id)` at the top. Every `SELECT` filters by it; every `INSERT` writes it.

A few non-obvious bits:
- `ExecutionEventStore` subscription buckets are now keyed by `(workspace_id, thread_id)` and `(workspace_id, request_id)`. `_wildcard_subs` and `_compound_subs` are dicts keyed by workspace_id. The `subscribe()` API takes `workspace_id`; `unsubscribe()` reads it back from the subscription instance. SSE fan-out never crosses workspaces even if two testers happen to share a thread or request id by accident.
- `MemoryStore._enqueue_index` includes workspace in the idempotency key (`{workspace}:{operation}:{entity_type}:{entity_id}`) so two workspaces enqueueing the same memory don't collide.
- `find_memory_by_link` / `find_event_by_link` join on `(workspace_id, memory_id)` / `(workspace_id, event_id)` so the JOIN itself is workspace-isolated.
- Each store also got `clear_workspace(workspace_id)` and `list_workspaces()` helpers; used by dev reset and by background workers respectively.

### Phase 4 — Per-workspace file singletons

Same pattern in four modules:

```python
_cache: dict[str, ConversationLog] = {}
_cache_lock = threading.Lock()

def get_conversation_log(workspace_id: str | None = None) -> ConversationLog:
    workspace_id = _resolve_workspace(workspace_id)
    cached = _cache.get(workspace_id)
    if cached is not None:
        return cached
    with _cache_lock:
        cached = _cache.get(workspace_id)
        if cached is None:
            cached = ConversationLog(_conversation_log_path(workspace_id), workspace_id)
            _cache[workspace_id] = cached
        return cached
```

Modules converted: `conversation/log.py`, `conversation/summarization/working_memory_log.py`, `timezone_store.py`, `execution/log_store.py`. Each also exports a `reset_*_cache()` test helper.

**The hidden module-level captures.** Four agent-tool files had `_LOG_STORE = get_execution_agent_logs()` at *module import time*. After Phase B, `get_execution_agent_logs()` raises `RuntimeError` when no ContextVar is bound — and import time has no ContextVar. Fix: kill the module-level capture; replace `_LOG_STORE.record_action(...)` with `get_execution_agent_logs().record_action(...)` per call. Affected:
- `server/agents/execution_agent/tools/gmail.py`
- `server/agents/execution_agent/tools/calendar.py`
- `server/agents/execution_agent/tools/triggers.py`
- `server/agents/execution_agent/tasks/search_email/tool.py`

The cache makes the per-call lookup essentially free (dict hit).

**Summarization scheduler rewrite** (`conversation/summarization/scheduler.py`): the old `_pending`/`_running` bools became `set[str]` keyed by workspace_id. `schedule_summarization(workspace_id)` enqueues; `_run_worker(workspace_id)` binds `set_current_workspace` before calling `summarize_conversation(workspace_id)`. The summarizer accepts an optional `workspace_id` and falls back to ContextVar if omitted (used by tests).

### Phase 5 — Routes + Composio + runtimes

- Global dep on `api_router` covers routes. Composio per-workspace:
- `server/api/routes/integrations.py` — `connect_integration` / `retrieve_integration_status` / `disconnect_integration` all overwrite `payload.userId` with `require_current_workspace()` before calling into `integrations/google.py`. Testers cannot impersonate each other's Gmail even if they tamper with the request body.
- `server/integrations/google.py` — `connect_google` calls `register_workspace(user_id)` after Composio returns a success; `disconnect_google` calls `unregister_workspace(user_id)`. Maintains `data/gmail_workspaces.json` so the importance watcher knows who to poll.
- Runtimes (`InteractionAgentRuntime`, `ExecutionAgentRuntime`) and their tools work via ContextVar — instantiated inside request tasks, so they inherit the binding. No explicit `workspace_id` plumbing needed in their constructors.

### Phase 6 — Background jobs iterate workspaces

**Trigger scheduler** (`services/trigger_scheduler.py`):
- `get_due_triggers(before=now)` was extended to scan across all workspaces when `workspace_id=None`. `TriggerRecord.workspace_id` is part of the model, so each due trigger carries the right scope.
- `_execute_trigger` calls `set_current_workspace(trigger.workspace_id)` before dispatching to `ExecutionBatchManager`. Every store call the agent makes downstream is then scoped correctly.
- `clear_next_fire`, `schedule_next_occurrence`, `record_failure` pass `workspace_id=trigger.workspace_id` explicitly so they work regardless of the calling Context.

**Importance email watcher** (`services/gmail/importance_watcher.py`):
- Single instance, but per-workspace state: `_workspace_state: dict[str, _WorkspaceState]` where each state holds a per-workspace `GmailSeenStore` (`data/gmail_seen/{workspace_id}.json`), `has_seeded_initial_snapshot`, and `last_poll_timestamp`.
- Outer `_run` loop: `for workspace_id in list_workspaces_with_gmail()` (sourced from `services/gmail/connections.py`).
- Each tick wrapped in `asyncio.wait_for(self._poll_workspace(workspace_id), timeout=30.0)` + `try/except` so one stuck workspace doesn't stall the others.
- `_poll_workspace` calls `set_current_workspace(workspace_id)` first, then `composio_user_id = workspace_id` (since the integrations route guarantees this mapping).
- Replaced the global `get_active_google_user_id()` lookup with `resolve_workspace_gmail_user_id()` in `services/gmail/client.py`. The new helper reads the workspace ContextVar and checks `services/gmail/connections.list_workspaces_with_gmail()` for registration — no shared global state. The old `_active_user_id` module variable, its lock, the setter, and the startup `hydrate_active_google_user_id()` call are all deleted. `initiate_connect` / `fetch_status` / `disconnect_account` no longer mutate global state as a side effect.

### Phase 7 — SDK regen

`cd packages/sdk && bun run generate` — exports OpenAPI from FastAPI → `server/generated/openapi.json` → runs `openapi-ts` with the hey-api config. New exports in `packages/sdk/src/generated/`:
- `sdk.gen.ts` — `retrieveMe()`, `listWorkspaces()`
- `zod.gen.ts` — `zRetrieveMeResponse`, `zListWorkspacesResponse`
- `@tanstack/react-query.gen.ts` — `retrieveMeOptions()`, `retrieveMeQueryKey()`, `listWorkspacesOptions()`, etc.
- `types.gen.ts` — `MeResponse`, `WorkspaceListEntry`, `WorkspaceListResponse`

Existing endpoint shapes unchanged (workspace_id is a FastAPI dep, not a request parameter). `bun run build` clean.

### Phase 8 — Handle collision guard

**`/dev/reset` scope.** Per-workspace targets cleared by `POST /api/dev/reset`: `threads`, `execution_events`, `memory` (SQLite), `pinecone_namespace`, `triggers`, `conversation_log`, `timezone`, `execution_logs` (`data/execution_agents/{ws}/`), `working_memory` (`data/working_memory/{ws}/`), `gmail_seen` (file + in-memory watcher state), `gmail_registry` (`data/gmail_workspaces.json` entry), `summarization_scheduler` (in-memory pending/running sets). The cross-workspace `data/workspace_registry.db` is intentionally not cleared (it's the global audit trail).

`server/db/workspace_registry.py` — its own SQLite file (`data/workspace_registry.db`), one table:

```sql
CREATE TABLE workspace_registry (
    workspace_id TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL,
    first_ip TEXT
);
```

`get_workspace_id` calls `get_workspace_registry().register(workspace_id, _client_ip(request))` after auth succeeds. `_client_ip` honors the first `X-Forwarded-For` entry (Railway proxy) before falling back to `request.client.host`. On IP mismatch for an existing handle, logs a warning at `WARNING` level — no rejection.

`GET /api/admin/workspaces` (route at `server/api/routes/admin.py`) exposes the table for demo-time visibility. Gated by the same auth as everything else.

### Phase F — Tests

`server/tests/conftest.py` (new):
- Sets `DEMO_PASSWORD` before `server.app` is imported.
- Autouse fixture monkey-patches `require_current_workspace` to default to `"test_workspace"` when no ContextVar value is set. This handles `IsolatedAsyncioTestCase` event-loop isolation (the test method runs in a new loop with a fresh Context that doesn't inherit the pytest setup binding).
- Autouse `_override_workspace_dep` installs `app.dependency_overrides[get_workspace_id]` for the duration of each test, returning the default workspace + setting the ContextVar. Tests using `TestClient(app)` skip Basic auth entirely.
- Provides `client`, `workspace_id`, `auth` convenience fixtures.

Other fixes:
- `test_openapi_contract.py` — snapshot updated with `/me`, `/admin/workspaces`, plus gmail/calendar/meta endpoints that were already missing from the pre-existing snapshot.
- `test_public_api.py` — added `server.api.routes.threads.get_execution_event_store` to the patch list (pre-existing bug exposed by my changes); made `FakeRuntime.stream_execute` accept `**kwargs` and become async.
- `test_memory_hybrid.py` — `INSERT INTO memory_index_queue` literal updated with `workspace_id`; `exact_link_candidates` callsite passes `workspace_id="test_workspace"`; sensitive-text-not-in-logs assertion swapped from `level="INFO"` to `level="DEBUG"` (the lexical search logs at DEBUG).

`pytest server/tests/` → **43 passed**.

### Phase 9 — Post-merge isolation audit & fixes

A code-trace audit after the initial work landed surfaced one critical hole and several smaller issues that the original phases either missed or papered over. This phase closes them.

**9.1 — Cross-workspace Gmail/Calendar leak via process-global.** The earlier work scoped Composio's `user_id` to `workspace_id` only inside `api/routes/integrations.py`. Every actual *tool* action (gmail send/draft/forward/reply/list, calendar list-events, the `gmail/drafts.py` and `calendar/events.py` service helpers, and the interaction-agent "is Google connected?" preflight) still read a process-global `_active_user_id` from `services/gmail/client.py`. That global was mutated by `initiate_connect`, `fetch_status`, `disconnect_account`, and pre-seeded at startup from a hardcoded `"openpoke-web"` fallback by `hydrate_active_google_user_id()`. Outcome: whichever workspace most recently hit `/integrations/google/connect|status|disconnect` overwrote the user_id every tool call read. Alice in a thread + bob clicks Connect → alice's next gmail tool talks to bob's mailbox.

Fix:
- Deleted the global (`_active_user_id`, `_ACTIVE_USER_ID_LOCK`, `_set_active_gmail_user_id`, `get_active_google_user_id`, `hydrate_active_google_user_id`) from `services/gmail/client.py`. Removed the three side-effect mutations from `initiate_connect` / `fetch_status` / `disconnect_account`. Dropped the lifespan `hydrate_active_google_user_id()` call from `server/app.py`.
- Added `resolve_workspace_gmail_user_id() -> str | None` in `services/gmail/client.py`:
  ```python
  def resolve_workspace_gmail_user_id() -> str | None:
      workspace_id = get_current_workspace()
      if not workspace_id:
          return None
      if workspace_id not in set(list_workspaces_with_gmail()):
          return None
      return workspace_id
  ```
  Reads the workspace ContextVar and verifies registration via `services/gmail/connections.list_workspaces_with_gmail()`. Returns `None` for unregistered workspaces so the existing "Gmail not connected" UX is preserved at every callsite.
- Renamed 18 callsites: `execution_agent/tools/{gmail,calendar}.py`, `execution_agent/tasks/search_email/{tool,gmail_internal}.py`, `interaction_agent/tools.py`, `services/gmail/drafts.py`, `services/calendar/events.py`, lazy re-exports in `services/__init__.py` and `services/gmail/__init__.py`, plus the patch target in `tests/test_execution_fanout.py`.

**9.2 — `register_workspace` was called on OAuth *initiation*, not completion.** `connect_google` registered the workspace in `gmail_workspaces.json` the moment `initiate_connect` returned a redirect URL — before the user had even hit the OAuth page. The importance watcher would then start polling a not-yet-connected workspace and log warnings every 60s until OAuth completed.

Fix: `server/integrations/google.py::get_google_status` now calls `register_workspace(payload.user_id)` only when the response payload reports `connected: True` *and* `status == "ACTIVE"`. The frontend's existing status-polling lands on the first ACTIVE poll, so registration matches reality. `connect_google` no longer registers.

**9.3 — `/dev/reset` was incomplete.** The earlier route cleared SQLite + pinecone + a few logs, but several per-workspace artifacts the rest of the doc lists as workspace-scoped were untouched: the execution-agent log directory, the working-memory log directory, the gmail seen-store file + watcher in-memory poll state, the workspace's entry in `gmail_workspaces.json`, and the summarization scheduler's pending/running sets.

Fix: added targets `execution_logs`, `working_memory`, `gmail_seen`, `gmail_registry`, `summarization_scheduler` to `server/api/routes/dev.py`. New helpers:
- `services/conversation/summarization/scheduler.reset_workspace(workspace_id)` — discards the workspace from `_pending` / `_running`.
- `services/gmail/importance_watcher.ImportantEmailWatcher.reset_workspace(workspace_id)` — pops the per-workspace state and deletes `data/gmail_seen/{workspace_id}.json`.

`data/workspace_registry.db` is intentionally left alone (cross-workspace audit row).

**9.4 — Dead `pinecone_namespace` setting removed.** The original work derived Pinecone namespaces from `workspace_id`, but `settings.pinecone_namespace` lingered in `server/config.py` and `.env.example` with a comment claiming env compatibility. Nothing read it. Deleted both.

**9.5 — Doc correction: `server/routes/` is not dead.** The earlier follow-up bullet claimed `server/routes/` was dead code; in fact `server/api/routes/agent_runs.py:10` imports `execution_run_stream` from `server.routes.execution`. That import is the live SSE stream handler. The follow-up section is amended to scope the cleanup correctly: port `execution_run_stream` into `server/api/routes/` first, then delete the rest of `server/routes/`.

**9.6 — Confirmed *not* a bug (audited and withdrawn).**
- CORS `allow_origins=["*"]` + `allow_credentials=True`: Starlette's `CORSMiddleware` sets `allow_all_origins=True` and echoes the request `Origin` header with `Vary: Origin`. Works in browsers despite the spec violation. Operators still need to set `OPENPOKE_CORS_ALLOW_ORIGINS` explicitly in production for hygiene.
- 400-vs-401 ordering in `get_workspace_id`: password is checked before handle normalization. This *prevents* handle enumeration by unauthenticated probers — a 400 only surfaces when the password is correct. Intentional.

**Verification.** Import smoke test (`DEMO_PASSWORD=test python -c 'import server.app'`) clean. `pytest server/tests/` → **43 passed**, same as Phase F. No SDK regen needed since no API shape changed.

---

## What runs where (request-time vs background-time)

| Path | Where `workspace_id` comes from |
|---|---|
| HTTP request handlers (all `/api/*` except `/api/health`) | `get_workspace_id` dep runs first, binds ContextVar; route + downstream tools read it implicitly |
| Tools called from inside the interaction/execution agent during a request | Inherit ContextVar via async task lineage |
| `trigger_scheduler._execute_trigger` | `set_current_workspace(trigger.workspace_id)` explicitly before agent dispatch |
| `importance_watcher._poll_workspace` | `set_current_workspace(workspace_id)` explicitly per tick |
| `summarization_scheduler._run_worker` | `set_current_workspace(workspace_id)` explicitly before summarizer call |
| Memory indexer (`MemoryIndexer.sync_pending`) | Doesn't use ContextVar; reads `workspace_id` directly from each `memory_index_queue` row and groups batches by it |
| Tests | conftest's `_bind_test_workspace` patches `require_current_workspace` to return `"test_workspace"` when unset |

---

## What does *not* isolate (intentional or accepted)

- **Process-global caches inside Composio SDK / OpenRouter client** — these are app-level credentials, not per-user. Composio uses `user_id=workspace_id` so the data they access *is* isolated.
- **`gmail_workspaces.json`** is a shared file (one row per workspace) — it's a registry, not workspace data.
- **`workspace_registry.db`** is shared by design — it's the cross-workspace index of who exists.
- **Settings (`server/config.py`)** — singletons, intended.
- **System prompts, agent definitions, model configs** — app code, not per-user.

---

## Verification

End-to-end (TestClient):
```
GET  /api/threads           no auth → 401
GET  /api/health            no auth → 200
GET  /api/me  bad handle    → 400
GET  /api/me  bad password  → 401
GET  /api/me  alice good    → {"workspaceId": "alice"}
POST /api/threads alice     → 201 (creates a thread)
GET  /api/threads alice     → 1 item
GET  /api/threads bob       → 0 items (isolation confirmed)
GET  /api/admin/workspaces  → both alice and bob listed
POST /api/dev/reset alice   → 200 (clears only alice's data)
GET  /api/threads alice     → 0 items
GET  /api/threads bob       → still has bob's data
```

`pytest server/tests/` → 43 passed.

---

## Follow-up scope (not in this work)

- **Frontend** (`apps/web/src/features/auth/*`): `AuthProvider` reading from `sessionStorage`, `authFetch` wrapper that injects `Authorization` and redirects on 401, login form using the regenerated `retrieveMe` query, `routes/login.tsx`, `__root.tsx` guard, signed-in chip.
- **Deployment**: Dockerfile for `server/`, Railway service config with a volume mounted at `/app/server/data`, Vercel project for `apps/web` with `VITE_API_URL` set, `OPENPOKE_CORS_ALLOW_ORIGINS` set on Railway.
- **Legacy cleanup**: `server/routes/execution.py` still hosts `execution_run_stream`, imported by `server/api/routes/agent_runs.py`. Port it into `server/api/routes/` and then delete the rest of `server/routes/`. (Earlier note that the directory was fully dead was incorrect.)

---

## File index (touched in this work)

Each file appears once with the full set of changes across all phases.

### New
- `server/api/dependencies.py` — `HTTPBasic` + `get_workspace_id` async dep; binds ContextVar; registers in workspace_registry; honors `X-Forwarded-For` for proxy-aware IP
- `server/api/routes/me.py` — `GET /api/me` → `{workspaceId}`
- `server/api/routes/admin.py` — `GET /api/admin/workspaces` → list registered handles
- `server/core/workspace_context.py` — `ContextVar` + `set_/get_/require_current_workspace`
- `server/db/workspace_registry.py` — observability table (handle → first IP / first seen)
- `server/services/gmail/connections.py` — JSON registry of workspaces with Gmail (`data/gmail_workspaces.json`)
- `server/tests/conftest.py` — `DEMO_PASSWORD` env, dep override, `require_current_workspace` patch for async tests

### Modified
- `.env.example` — added `DEMO_PASSWORD`, documented `OPENPOKE_CORS_ALLOW_ORIGINS`; dropped unused `PINECONE_NAMESPACE`
- `server/app.py` — required `demo_password` check at startup; flipped CORS `allow_credentials=True`; mounts `public_router` + `api_router`; dropped lifespan `hydrate_active_google_user_id` call
- `server/config.py` — added `demo_password`; dropped unused `pinecone_namespace`
- `server/api/__init__.py` — split into `public_router` (unauth `/health`) + `api_router` (global `Depends(get_workspace_id)`); registered `me`, `admin` routers
- `server/api/schemas.py` — added `MeResponse`
- `server/api/routes/integrations.py` — forces Composio `user_id = require_current_workspace()` on connect/status/disconnect
- `server/api/routes/dev.py` — caller-scoped reset over 12 targets (threads, execution_events, memory, pinecone, triggers, conversation_log, timezone, execution_logs, working_memory, gmail_seen, gmail_registry, summarization_scheduler)
- `server/db/threads.py` — `workspace_id` column on threads + messages; scoped queries; `clear_workspace`
- `server/integrations/google.py` — `register_workspace` on first ACTIVE status (not on connect); `unregister_workspace` on disconnect
- `server/services/gmail/client.py` — removed `_active_user_id` global + lock + setter + `get_active_google_user_id` + `hydrate_active_google_user_id`; added `resolve_workspace_gmail_user_id()` (reads ContextVar + verifies registration)
- `server/services/gmail/__init__.py` — re-exports updated to new helper name
- `server/services/gmail/importance_watcher.py` — outer-loops workspaces; per-workspace `_WorkspaceState` (seen-store + bookkeeping); `asyncio.wait_for` per tick; `set_current_workspace` per tick; added `ImportantEmailWatcher.reset_workspace`
- `server/services/__init__.py` — re-exports updated
- `server/services/execution/event_store.py` — `workspace_id` on `execution_runs` + `execution_events`; subscription buckets keyed by `(workspace_id, …)`; `clear_workspace`, `list_workspaces`
- `server/services/execution/log_store.py` — per-workspace cache → `data/execution_agents/{workspace_id}/`
- `server/services/memory/store.py` — `workspace_id` on `memories`/`events`/`links`/`memory_index_queue`; idempotency keys prefixed; scoped joins; `clear_workspace`, `list_workspaces`
- `server/services/memory/hybrid_search.py` — `hybrid_candidates`/`pinecone_candidates`/`exact_link_candidates`/`recent_unindexed_candidates` all take `workspace_id`; Pinecone `namespace=workspace_id`
- `server/services/memory/indexer.py` — upsert/delete batches grouped by `workspace_id`; `clear_pinecone_workspace`, `clear_all_pinecone_namespaces`
- `server/services/memory/ranking.py` — `PromptContextRanker` + `SearchResultRanker` carry `workspace_id`; passed through to `get_memories` and event lookup
- `server/services/triggers/models.py` — `workspace_id` field on `TriggerRecord`
- `server/services/triggers/store.py` — `workspace_id` column + scoped queries; `clear_workspace`, `list_workspaces`
- `server/services/triggers/service.py` — workspace-aware methods; `get_due_triggers` scans all workspaces when unbound
- `server/services/trigger_scheduler.py` — binds ContextVar per trigger dispatch; explicit `workspace_id` on lifecycle store calls
- `server/services/timezone_store.py` — per-workspace cache → `data/timezone/{workspace_id}.txt`
- `server/services/conversation/log.py` — per-workspace cache → `data/conversation/{workspace_id}/poke_conversation.log`
- `server/services/conversation/summarization/working_memory_log.py` — per-workspace cache → `data/working_memory/{workspace_id}/…`
- `server/services/conversation/summarization/scheduler.py` — per-workspace `_pending`/`_running` sets; binds ContextVar before summarizer; added `reset_workspace`
- `server/services/conversation/summarization/summarizer.py` — accepts optional `workspace_id`
- `server/services/gmail/drafts.py`, `server/services/calendar/events.py` — call `resolve_workspace_gmail_user_id()`
- `server/agents/execution_agent/tools/gmail.py` — killed module-level `_LOG_STORE` capture; `resolve_workspace_gmail_user_id()` at every callsite
- `server/agents/execution_agent/tools/calendar.py` — killed module-level `_LOG_STORE` capture; `resolve_workspace_gmail_user_id()` at every callsite
- `server/agents/execution_agent/tools/triggers.py` — killed module-level `_LOG_STORE` capture
- `server/agents/execution_agent/tasks/search_email/tool.py` — killed module-level `_LOG_STORE` capture; `resolve_workspace_gmail_user_id()`
- `server/agents/execution_agent/tasks/search_email/gmail_internal.py` — `resolve_workspace_gmail_user_id()`
- `server/agents/interaction_agent/tools.py` — `resolve_workspace_gmail_user_id()` for "is Gmail connected?" preflight
- `server/tests/test_openapi_contract.py` — snapshot updated (`/me`, `/admin/workspaces`, plus pre-existing gmail/calendar/meta gaps)
- `server/tests/test_public_api.py` — added `threads.get_execution_event_store` patch; `FakeRuntime.stream_execute` accepts `**kwargs` and is async
- `server/tests/test_memory_hybrid.py` — `memory_index_queue` insert literal carries `workspace_id`; `exact_link_candidates` gets `workspace_id`; sensitive-text-in-logs assertion at `level="DEBUG"`
- `server/tests/test_execution_fanout.py` — patch target renamed to `resolve_workspace_gmail_user_id`

### Regenerated
- `server/generated/openapi.json`
- `packages/sdk/src/generated/*`
