FROM node:22-alpine

RUN corepack enable

WORKDIR /workspace

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

COPY . .

RUN UPSTREAM_MOCK_DATABASE_URL=postgresql://build:build@127.0.0.1/upstream_mock \
    pnpm build

ENV NODE_ENV=production

EXPOSE 8094

CMD ["sh", "-lc", "pnpm migrate && exec pnpm start"]
