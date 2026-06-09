FROM oven/bun:1.3.4-alpine
WORKDIR /app

COPY package.json bun.lock turbo.json ./
COPY services/zelda/package.json services/zelda/
COPY packages/config/package.json packages/config/
COPY packages/db/package.json packages/db/
COPY packages/sdk/package.json packages/sdk/
COPY packages/ui/package.json packages/ui/
COPY apps/legal-poke/package.json apps/legal-poke/

RUN bun install

COPY services/zelda services/zelda

WORKDIR /app/services/zelda

ENV NODE_ENV=production
EXPOSE 8787

CMD ["bun", "src/index.ts"]
