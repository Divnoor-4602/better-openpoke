# Web (TanStack Start + Nitro) — Railway service.
# Build context MUST be the monorepo root so workspace packages (e.g. @openpoke/sdk) are available.
FROM oven/bun:1.3.4 AS builder

WORKDIR /repo

# Install workspace deps using the root lockfile.
# Root package.json lists `server` as a workspace, so bun needs to see its
# package.json (a tiny dev shim) even though we don't run any JS for it.
COPY package.json bun.lock turbo.json /repo/
COPY apps/web/package.json /repo/apps/web/package.json
COPY server/package.json /repo/server/package.json
COPY packages /repo/packages
RUN bun install --frozen-lockfile

# Source.
COPY apps/web /repo/apps/web

# Vite reads VITE_API_URL at build time and bakes it into the bundle.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN cd /repo/apps/web && bun run build

# --- runtime ---
FROM oven/bun:1.3.4-slim AS runner

WORKDIR /app
ENV NODE_ENV=production

# Nitro's node-server output is self-contained under .output/.
COPY --from=builder /repo/apps/web/.output /app/.output

EXPOSE 3000
# Nitro's default node-server preset listens on $PORT (Railway sets it) and defaults to 3000.
CMD ["node", ".output/server/index.mjs"]
