<p align="center">
  <img src="apps/web/public/web-app-manifest-512x512-light.png" alt="OpenPoke logo" width="120" />
</p>

<h1 align="center">General Poke</h1>


- **FastAPI backend** (Python 3.12) with a two-tier agent split (interaction + execution), powered by [OpenRouter](https://openrouter.ai/) for model access.
- **TanStack Start web app** (React 19 + Vite + shadcn) streaming tool calls and reasoning via the [Vercel AI SDK v6](https://sdk.vercel.ai).
- **Gmail + Calendar tooling** through [Composio](https://composio.dev/)'s `GOOGLESUPER` toolkit.
- **Hybrid memory search** via [Pinecone](https://www.pinecone.io/) (optional, but recommended).
- **Trigger scheduler** and background watchers for reminders and important-email alerts.
- SQLite for persistent state — no external database required.

## Stack

| Layer | Tech |
|---|---|
| Server | FastAPI · Pydantic v2 · Uvicorn · SQLite |
| Web | TanStack Start · React 19 · Vite · Tailwind v4 · shadcn |
| Tooling | bun (workspaces) · turbo (task runner) · basedpyright · eslint + prettier |
| Models | Anthropic Claude Sonnet 4 / Haiku 4.5 via OpenRouter |

## Prerequisites

- **bun** ≥ 1.3.4 ([install](https://bun.sh)) — manages the JS workspace
- **Python** 3.12 — backend runtime
- API keys (see [Get your API keys](#get-your-api-keys) below)

## Get your API keys

### 1. OpenRouter (required — LLM access)

OpenRouter brokers requests to Anthropic / OpenAI / Google models behind a single key.

1. Sign up at [openrouter.ai](https://openrouter.ai/).
2. Open [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) → **Create Key** → give it a name and optional credit limit.
3. Copy the key **immediately** — OpenRouter shows it once.
4. Add credit to your account so requests don't get rejected.

Reference: [Create a new API key](https://openrouter.ai/docs/api/api-reference/api-keys/create-keys) · [Quickstart](https://openrouter.ai/docs/quickstart)

### 2. Composio (required — Gmail + Calendar)

Composio handles OAuth + tool execution for Google services.

1. Sign in at [app.composio.dev](https://app.composio.dev/).
2. **Get your API key:** Settings → API Keys → copy `ak_...`. This is `COMPOSIO_API_KEY`.
3. **Create the Google auth config:**
   - Auth Configs → **Create Auth Config**
   - Select the **Google Super** toolkit ([toolkit page](https://composio.dev/toolkits/googlesuper)) — it bundles Gmail, Calendar, Drive, Meet, etc. under one OAuth flow
   - Choose **OAuth2** as the auth method (use Composio's default OAuth app, or wire your own Google Cloud OAuth credentials — see [Google Apps OAuth2 guide](https://composio.dev/auth/googleapps))
   - Save → copy the `ac_...` id. This is `COMPOSIO_GOOGLE_AUTH_CONFIG_ID`.

Reference: [Authenticating Tools](https://docs.composio.dev/docs/authenticating-tools) · [Google Super toolkit](https://docs.composio.dev/toolkits/googlesuper)

### 3. Pinecone (optional — hybrid memory search)

Pinecone backs OpenPoke's hybrid (dense + sparse) memory recall. Without it the memory worker logs `Memory index worker disabled` and the app runs fine — but assistant context degrades.

1. Sign up at [pinecone.io](https://www.pinecone.io/) → grab an API key from [the console](https://app.pinecone.io/) (Default project → API Keys). This is `PINECONE_API_KEY`.
2. **Create a hybrid serverless index** ([docs](https://docs.pinecone.io/guides/index-data/create-an-index)):
   - **Embedding model:** `llama-text-embed-v2` (dense)
   - **Metric:** `dotproduct` (required for hybrid sparse+dense)
   - **Cloud / region:** any (e.g. AWS / us-east-1)
   - **Capacity mode:** serverless
3. Copy the index **Host URL** (e.g. `https://your-index-xxxxx.svc.aped-1234-abcd.pinecone.io`). This is `PINECONE_INDEX_HOST`.

OpenPoke uses these Pinecone-hosted models (no extra setup needed; they're called via the inference API):
- Dense embeddings: [`llama-text-embed-v2`](https://www.pinecone.io/learn/learn-pinecone-sparse/)
- Sparse embeddings: [`pinecone-sparse-english-v0`](https://www.pinecone.io/learn/learn-pinecone-sparse/)
- Reranker: `bge-reranker-v2-m3`

Reference: [Understanding hybrid search](https://docs.pinecone.io/guides/indexes/pods/understanding-hybrid-search) · [Sparse English model](https://www.pinecone.io/learn/learn-pinecone-sparse/)

## Local quickstart

```bash
git clone https://github.com/Divnoor-4602/better-openpoke
cd better-openpoke

# 1. JS workspace install (installs apps/web + packages/sdk + dev deps)
bun install

# 2. Python env + server deps
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -r server/requirements.txt

# 3. Env vars
cp .env.example .env
# edit .env — fill in DEMO_PASSWORD + your API keys (see table below)

# 4. Run both services with turbo
bun run dev:app
```

Web comes up at **http://localhost:3001**, server at **http://localhost:8001**.

> **Heads up:** `bun run dev:server` invokes plain `python` — make sure your venv is activated in the shell you run it from. `bun run dev:app` works the same way; activate the venv first.

Run individually if you prefer:

```bash
bun run dev:server      # FastAPI with --reload
bun run dev:web         # Vite dev server
```

### Optional: auto-activate Python with direnv

`bun run dev:server` resolves `python` from PATH, so without manual activation it falls back to the system python and breaks. To avoid `conda activate` / `source .venv/bin/activate` every shell:

```bash
brew install direnv
echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc   # bash users: ~/.bashrc with `bash`
cp .envrc.example .envrc                       # edit to point at your env
direnv allow
```

Now `python` resolves to your project env whenever you `cd` into the repo. The committed `.envrc.example` has snippets for both conda and venv.

## Monorepo layout (bun workspaces + turbo)

This is a bun-managed monorepo orchestrated by [turbo](https://turbo.build):

- `server/` — FastAPI app (Python, also a bun workspace just for its `dev` script)
- `apps/web/` — TanStack Start web app
- `packages/sdk/` — generated TypeScript SDK from the server's OpenAPI spec ([hey-api](https://heyapi.dev))

`turbo.json` wires the pipelines. The top-level scripts are:

| Command | What it does |
|---|---|
| `bun run dev:app` | Runs `server` + `web` together via turbo |
| `bun run dev:server` | FastAPI only (`python -m server.server --reload`) |
| `bun run dev:web` | Vite dev server only |
| `bun run build` | Runs `build` in every workspace that has one |
| `bun run lint` | Runs `lint` in every workspace that has one |

Workspace packages reference each other by name — e.g. the web app pulls in `@openpoke/sdk` from `packages/sdk`. Bun resolves these via symlinks at `bun install` time, so changes to the SDK are picked up immediately.

## Environment variables

The **server** reads `.env` at the repo root via `server/config.py`. The **web** app's only env var (`VITE_API_URL`) defaults to `http://localhost:8001` — exactly what the local server runs on — so you don't need a separate web `.env` for local dev. Copy `.env.example` and fill in:

### Required

| Var | What it is |
|---|---|
| `DEMO_PASSWORD` | Any string. Single shared password gates the demo; each tester picks a handle and that becomes their workspace id. |
| `OPENROUTER_API_KEY` | From [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |
| `COMPOSIO_API_KEY` | From [Composio dashboard](https://app.composio.dev/) → Settings → API Keys |
| `COMPOSIO_GOOGLE_AUTH_CONFIG_ID` | The `ac_...` id from the Google auth config you created |

### Optional

| Var | Default | Purpose |
|---|---|---|
| `PINECONE_API_KEY` | — | Enables hybrid memory search. |
| `PINECONE_INDEX_HOST` | — | e.g. `https://your-index.pinecone.io` |
| `MEMORY_SEARCH_BACKEND` | `pinecone_hybrid` | Set to `sqlite` to skip Pinecone even when keys are present. |
| `MEMORY_INDEX_WORKERS` | `2` | Background indexing worker count. |
| `MEMORY_INDEX_BATCH_SIZE` | `50` | Vectors per Pinecone batch. |
| `MEMORY_INDEX_POLL_INTERVAL_SECONDS` | `2` | How often the worker polls for queued items. |
| `OPENPOKE_DATA_DIR` | `server/data/` | Where SQLite + JSON state lives. Override to mount a persistent volume in containers. |
| `OPENPOKE_PORT` / `PORT` | `8001` | Server bind port. Railway/Heroku inject `PORT`; it takes precedence. |
| `OPENPOKE_HOST` | `0.0.0.0` | Server bind host. |
| `OPENPOKE_CORS_ALLOW_ORIGINS` | `*` | Comma-separated allowed origins. Set to your web URL when deployed (`*` won't work with credentialed requests). |
| `OPENPOKE_ENABLE_DOCS` | `1` | Set to `0` to hide `/docs` in production. |
| `VITE_API_URL` | `http://localhost:8001` | Where the web bundle talks to the server. Read at **build time**. |

## Logging in

- Everyone uses the same `DEMO_PASSWORD` from your `.env`.
- Pick any handle on the login screen (`a-z 0-9 _`, max 64 chars). That handle is your `workspace_id` — same handle = same workspace, different handles are fully isolated (threads, memory, Gmail connection).
- First login auto-creates the workspace. Logging back in with the same handle restores it.

## Connect Gmail

1. Log in.
2. Click the Google connect button in the topbar.
3. Complete the Composio OAuth flow.

Each workspace has its own Gmail connection.

## Project layout

```
.
├── apps/web/                # TanStack Start + React 19 + shadcn
│   ├── src/
│   │   ├── components/      # shadcn primitives + app shell
│   │   ├── features/        # assistant, auth, integration, thread
│   │   ├── lib/poke/        # API client hooks (TanStack Query)
│   │   └── routes/          # File-based routes
│   └── Dockerfile           # Web container (multi-stage bun + nitro)
├── packages/sdk/            # Generated OpenPoke API client (hey-api)
├── server/                  # FastAPI app
│   ├── agents/              # interaction + execution agents
│   ├── api/                 # HTTP routes, schemas, dependencies
│   ├── core/                # config, errors, OpenAPI, paths, workspace ctx
│   ├── db/                  # SQLite repositories
│   ├── integrations/        # Google connect/disconnect/status orchestration
│   ├── services/            # Gmail, Calendar, memory, triggers, conversation
│   ├── data/                # Runtime state (gitignored; override with OPENPOKE_DATA_DIR)
│   └── Dockerfile           # Server container (python:3.12-slim)
└── turbo.json               # Task pipeline
```

## Deployment

Both services ship with production Dockerfiles and Railway config. The Docker build context for **both** is the repo root (so bun workspaces resolve correctly) — use `-f <path>/Dockerfile`.

### Local Docker (smoke test)

#### Server

```bash
docker build -f server/Dockerfile -t openpoke-server .
docker run --rm -p 8001:8001 \
  -e DEMO_PASSWORD=demo \
  -e OPENROUTER_API_KEY=... \
  -e COMPOSIO_API_KEY=... \
  -e COMPOSIO_GOOGLE_AUTH_CONFIG_ID=... \
  -e OPENPOKE_CORS_ALLOW_ORIGINS=http://localhost:3001 \
  -v $(pwd)/server/data:/data \
  openpoke-server
```

The mount on `/data` matches the Dockerfile's `OPENPOKE_DATA_DIR=/data`, so SQLite + JSON state survives container restarts.

#### Web

```bash
docker build -f apps/web/Dockerfile \
  --build-arg VITE_API_URL=http://localhost:8001 \
  -t openpoke-web .
docker run --rm -p 3000:3000 openpoke-web
```

`VITE_API_URL` is a **build arg** — baked into the bundle at build time, not read at runtime. Point it at wherever the server will live.

### Railway

The repo ships with `server/railway.json` and `apps/web/railway.json`. Each pins the right Dockerfile, healthcheck path (`/api/health`), and `numReplicas: 1` (SQLite WAL can't have concurrent writers).

1. **Create the project + two services.** New project → Deploy from GitHub repo. That gives you one service. Click into it, rename to `server`, and set **Settings → Build → Railway Config File** to `server/railway.json`. Then **+ Create → GitHub Repo** on the same repo to add a second service; rename to `web`, set its Config File to `apps/web/railway.json`.
2. **Generate domains.** On each service: **Settings → Networking → Generate Domain**. Domains exist immediately — no deploy needed. Copy both URLs.
3. **Attach a Volume to `server`.** **Settings → Volumes → New Volume → Mount Path `/data`**. Without this, SQLite gets wiped on every redeploy.
4. **Set env vars** (Variables tab):
   - **server:** `DEMO_PASSWORD`, `OPENROUTER_API_KEY`, `COMPOSIO_API_KEY`, `COMPOSIO_GOOGLE_AUTH_CONFIG_ID`, `OPENPOKE_CORS_ALLOW_ORIGINS=https://<web-domain>`. Add Pinecone vars if you want memory search. Optionally `OPENPOKE_ENABLE_DOCS=0`. **Do not set `PORT`** — Railway injects it.
   - **web:** `VITE_API_URL=https://<server-domain>` (Railway exposes Variables as build args automatically).
5. **Push to `main`** — both services auto-deploy. Watch each service's **Build Logs** then **Deploy Logs**. Server healthcheck should turn green in ~30s.
6. **Update Composio's OAuth redirect.** No code change needed — the web sends its `window.location.origin` as the callback URL at runtime — but if your Composio auth config has an allowed-origins whitelist, add `https://<web-domain>` to it.

#### Railway CLI shortcuts

If you have the [Railway CLI](https://docs.railway.com/guides/cli):

```bash
railway link                                         # link this repo to your project
railway variables --service server --set "KEY=value" # bulk-set vars
railway logs --service server --build                # tail latest build logs
railway logs --service server                        # tail runtime logs
railway domain --service server                      # generate a domain
railway volume add --service server --mount-path /data
```

## Useful commands

```bash
bun run dev:app          # Server + web together
bun run dev:server       # FastAPI only
bun run dev:web          # Vite only
bun run build            # Production builds (turbo)
bun run lint             # ESLint + perfectionist + prettier (web)
bunx tsc --noEmit        # Web typecheck (run inside apps/web)
.venv/bin/basedpyright server   # Server typecheck (strict)
```

## License

MIT — see [LICENSE](LICENSE).
