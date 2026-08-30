FROM node:22-alpine

RUN corepack enable

WORKDIR /workspace

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY devtools/upstream-mock/package.json ./devtools/upstream-mock/package.json

RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --filter @devtools/upstream-mock...

COPY devtools/upstream-mock ./devtools/upstream-mock

RUN UPSTREAM_MOCK_DATABASE_URL=postgresql://build:build@127.0.0.1/upstream_mock \
    pnpm --filter @devtools/upstream-mock build

WORKDIR /workspace/devtools/upstream-mock

ENV NODE_ENV=production

EXPOSE 8094

CMD ["sh", "-lc", "pnpm migrate && exec pnpm start"]
