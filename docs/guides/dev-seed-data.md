# Development upstream scenarios

Development data starts as observable upstream behavior, not as platform
database seeding. Start the stack with `make up-dev`, then use the standalone
Next.js upstream mock on `http://127.0.0.1:8094`.

The dashboard and TypeScript CLI call the same authenticated HTTP API. They can
create drafts, append defects/images/archives, publish inspections, update
mutable source fields, inspect current state, and run the deterministic
`dev-showcase` scenario.

```bash
export UPSTREAM_MOCK_URL=http://127.0.0.1:8094
export UPSTREAM_MOCK_TOKEN=local-development-upstream-mock-token
export UPSTREAM_MOCK_TIMEOUT_SECONDS=30

pnpm --filter @devtools/upstream-mock cli -- list
pnpm --filter @devtools/upstream-mock cli -- dev-showcase --file showcase.json
```

There is intentionally no `make seed` or `make seed-dev` wrapper. The mock owns
only upstream records, event timing, PostgreSQL state, and its object fixtures.
It never creates platform users, organizations, Datasets, Collections, jobs,
annotations, or Models.

## Platform effects

After an inspection is published, exercise the real platform behavior:

1. Explicitly provision or register the platform user you intend to use.
2. Configure the SC source connector, import profile, Collection membership
   rule, and automation through platform APIs/UI.
3. Publish or update an inspection through the upstream mock.
4. Observe discovery, import, Collection membership, Snapshot publication, and
   automated prediction through their normal product surfaces.

The five-minute discovery poll may be used for the normal event path. Explicit
Discovery or Backfill controls remain available when testing those operations.
Replaying the same scenario is idempotent and must not create duplicate platform
resources.

## Identity

Scenario tooling never provisions an administrator. `make up-dev` separately
invokes the explicit administrator operation and converges this local-only
development account:

```text
Email: seed@example.com
Password: seed1234
Name: Development Admin
```

The startup rebuilds its selected dependencies and restarts image-parser after
SC upstream is healthy. This prevents a stale parser child process from
blocking migrations or identity provisioning without restarting the stateful
development services.

Override any value when starting the stack:

```bash
make up-dev \
  DEV_SUPERADMIN_EMAIL=developer@example.test \
  DEV_SUPERADMIN_PASSWORD='<local password>' \
  DEV_SUPERADMIN_NAME='Local Developer'
```

The standalone administration operation remains available when needed:

```bash
make create-superadmin \
  EMAIL=developer@example.test \
  PASSWORD='<local password>' \
  NAME='Local Developer'
```

Live smoke and Playwright runs likewise require credentials through
`SMOKE_USER_EMAIL` / `SMOKE_USER_PASSWORD` and `PW_USER_EMAIL` /
`PW_USER_PASSWORD`. No repository default account is assumed. Existing Docker
volumes may retain identities created by older development bootstraps; those
rows are not renamed or deleted automatically.

## Test fixtures and benchmarks

Deterministic sample/image builders retained under `devtools/seedmaker` are
test-only fixtures and explicitly named legacy compatibility tools. They are
not a supported live development command surface.

The SC runtime benchmark consumes an already imported Dataset selected with
`SC_RUNTIME_BENCHMARK_SOURCE_DATASET_NAME`. Create that Dataset through the real
upstream import path first, then run:

```bash
make benchmark-sc-runtime-data-paths
```

The benchmark fails if the requested Dataset or exact sample count is absent;
it does not silently seed or substitute data.
