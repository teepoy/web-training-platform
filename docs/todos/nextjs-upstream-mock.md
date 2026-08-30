# TODO: Next.js Upstream Mock

## Baseline

- Recorded before implementation at commit
  `941d8ce1b4eabd6481d391bd1951f06cf4fb9092`.
- **Overall status:** Complete.

## Goal

Replace the disposable upstream seed/simulator with an independent Next.js
full-stack mock service and dashboard. Keep it strictly isolated from the
production `services/sc-upstream` service and its production cache logic.

## Current Location

The legacy implementation is `devtools/sc-upstream-simulator`:

- `src/sc_upstream_simulator/api.py`: bearer-authenticated FastAPI mutation API;
- `src/sc_upstream_simulator/repository.py`, `models.py`, and `domain.py`:
  PostgreSQL state and mutation rules;
- `src/sc_upstream_simulator/scenarios.py` and `artifacts.py`: named seed
  scenarios and object-store artifacts;
- `src/sc_upstream_simulator/cli.py`: HTTP-only development CLI;
- `src/sc_upstream_simulator/server.py` and `upstream_adapter.py`: combined
  HTTP process plus platform-facing gRPC and Arrow Flight reads;
- `migrations/`: simulator-owned schema;
- `Dockerfile` and `infra/compose/docker-compose.dev.yaml`: development-only
  packaging and wiring.

## Corrected Boundary

- `devtools/upstream-mock` is a pure Next.js mock service. App Router owns the
  developer UI, HTTP API/route handlers, validation,
  PostgreSQL migrations and writes, named scenarios, and object-store fixture
  publication.
- `services/sc-upstream` remains a separate production-owned process and keeps
  its real cache, gRPC, and Arrow Flight logic. It is not hosted or imported by
  the mock.
- A separate development adapter package calls the mock's read-only HTTP source
  API through the existing `UpstreamDB` port. This adapter is injected only in
  development Compose and is not part of either production code or the mock
  service.
- The platform API continues to call only the separate `services/sc-upstream`
  gRPC/Flight service. Development automation and the CLI call only the Next.js
  mock API.
- Neither service is copied into production images or release manifests.

## Files and Features to Move or Replace

1. Replace the FastAPI control routes in `api.py` with Next.js route handlers.
2. Replace the Python CLI with a TypeScript CLI that calls those HTTP routes.
3. Move PostgreSQL schema/migration ownership and mutation repositories into the
   Next.js package.
4. Move `dev-showcase` scenario construction and S3 fixture publication into
   TypeScript server-only modules.
5. Add a browser UI for readiness, inspection listing, draft creation, record
   append, publication, mutable-field updates, and the named showcase scenario.
6. Run the real `services/sc-upstream` cache/protocol service as its own Compose
   service, injected with a small development HTTP adapter.
7. Split Compose health/dependencies so `upstream-mock` and `sc-upstream` are
   explicit, independently owned services.
8. Replace Python control/repository tests with TypeScript contract tests and
   retain adapter plus separate SC upstream protocol tests.

## Compatibility Rules

- Preserve the current HTTP paths and JSON request/response shapes during the
  migration so the CLI and development automation remain compatible.
- Preserve ports `9091` (gRPC) and `9093` (Flight) on `sc-upstream`. The mock
  control/UI port remains
  `8094`.
- Preserve the PostgreSQL row semantics and HTTP payloads; no database backfill
  is required. The old `sc_simulator` database and legacy environment names are
  not compatibility surfaces.
- Preserve bearer-token authorization for mutation APIs; the browser UI stores
  the token only in its local browser session and never exposes it in rendered
  server output.
- No production package may import or depend on the Next.js upstream mock.

## Acceptance Criteria

- One Next.js development application provides both UI and HTTP control API.
- All mock mutations and named seed behavior live in TypeScript server-only
  modules with PostgreSQL transactions.
- The separate production `sc-upstream` service serves unchanged gRPC and Arrow
  Flight contracts, including its production cache behavior, using the mock as
  an injected development source.
- The TypeScript CLI supports create, append, publish, update, inspect, list,
  and `dev-showcase`; no Make wrapper is added.
- Development Compose starts both pieces and production/release manifests remain
  free of mock code.
- Route, repository, scenario, cross-language schema, gRPC, Flight, Compose, and
  browser smoke tests pass.

## Completion Evidence

- Next.js 16 App Router dashboard, compatibility control routes, read-only
  source routes, Drizzle repository, migrations, deterministic scenario/S3
  publishing, and TypeScript CLI now live in `devtools/upstream-mock`.
- `devtools/sc-upstream-dev-adapter` is the only development bridge. The mock
  does not import or host `services/sc-upstream`; production release manifests
  remain unchanged.
- Development Compose runs healthy `upstream-mock` and `sc-upstream` containers.
  A live scenario produced four published inspections; gRPC returned the
  expected inspection and Arrow Flight streamed all ten requested rows through
  the separate cache service.
- Next.js lint, typecheck, unit tests, production build, both Docker image builds,
  seedmaker tests, adapter tests, Compose configuration checks, Graphify checks,
  and rebuilt `sc-domain`/`architecture-contracts` graphs pass.
