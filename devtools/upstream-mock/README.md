# Upstream Mock

This disposable Next.js application mocks upstream records and events for local
development. It owns only mock behavior: a dashboard, HTTP control/read APIs,
PostgreSQL state, named scenarios, and object-store fixtures.

It does **not** host or import `services/sc-upstream`. The separate `sc-upstream`
Compose service keeps the real production cache, gRPC, and Arrow Flight logic
and reaches this mock through `devtools/sc-upstream-dev-adapter`.

The current implementation provides:

- an owned, versioned PostgreSQL schema;
- explicit draft and published inspection states;
- atomic creation of inspection, defect, review-image, and patch-archive
  metadata;
- a transactionally allocated latest-change token on publication.
- a compact operator console for composing upstream events, generating a named
  scenario, inspecting source state, and reviewing local request/response
  activity;
- a bearer-authenticated HTTP control API for create, append, publish, update,
  list, and inspect operations;
- a TypeScript `upstream-mock` CLI that calls only that HTTP API;
- a read-only `/upstream/v1` source API for the separately running SC upstream
  service;
- a named, idempotent `dev-showcase` scenario that owns deterministic defects,
  review images, patch archives, object-store writes, and coherent publication.

Recurring source-discovery automation remains tracked in
`docs/todos/stateful-upstream-simulator-and-source-automation.md`.

Install and apply migrations from the repository root:

```bash
pnpm install
UPSTREAM_MOCK_DATABASE_URL=postgresql://postgres:postgres@localhost/upstream_mock \
  pnpm --filter @devtools/upstream-mock migrate
```

Run checks:

```bash
pnpm --filter @devtools/upstream-mock test
pnpm --filter @devtools/upstream-mock typecheck
```

The local Compose stack exposes the mock UI/control API on `8094`. The separate
SC upstream service exposes gRPC on `9091` and Arrow Flight on `9093`. The CLI
requires the mock endpoint and bearer credential explicitly:

```bash
export UPSTREAM_MOCK_URL=http://127.0.0.1:8094
export UPSTREAM_MOCK_TOKEN=local-development-upstream-mock-token
export UPSTREAM_MOCK_TIMEOUT_SECONDS=30

pnpm --filter @devtools/upstream-mock cli -- list
pnpm --filter @devtools/upstream-mock cli -- create --file inspection.json
pnpm --filter @devtools/upstream-mock cli -- publish \
  --wafer-key 7 \
  --inspection-time 2026-08-29T01:02:00Z \
  --published-at 2026-08-29T01:05:00Z
pnpm --filter @devtools/upstream-mock cli -- dev-showcase --file showcase.json
```

`create`, `append`, `update`, and `dev-showcase` accept their corresponding JSON
request object through `--file`. There is intentionally no mock-specific Make
wrapper and no direct database or object-store mutation mode.
