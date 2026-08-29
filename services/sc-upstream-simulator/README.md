# SC Upstream Simulator

This is the development-only owner of simulated SC upstream state. It is a
separate package so production upstream images and entrypoints cannot expose a
simulator mutation surface accidentally.

The current implementation provides:

- an owned, versioned PostgreSQL schema;
- explicit draft and published inspection states;
- atomic creation of inspection, defect, review-image, and patch-archive
  metadata;
- a transactionally allocated latest-change token on publication.
- a bearer-authenticated HTTP control API for create, append, publish, update,
  list, and inspect operations;
- a thin `sc-upstream-simulator` CLI that calls only that HTTP API.

It does not yet provide the gRPC/Flight read interfaces or object generation.
Those are subsequent tracked slices in
`docs/todos/stateful-upstream-simulator-and-source-automation.md`.

Apply migrations from the repository root:

```bash
SC_SIMULATOR_DATABASE_URL=postgresql+asyncpg://... \
  uv run --package sc-upstream-simulator \
  alembic -c services/sc-upstream-simulator/alembic.ini upgrade head
```

Run the repository unit tests:

```bash
uv run --package sc-upstream-simulator pytest services/sc-upstream-simulator/tests
```

To exercise the same repository suite against a migrated PostgreSQL database,
set `SC_SIMULATOR_TEST_DATABASE_URL` to that isolated database before running
the test command. The suite resets only simulator-owned tables in the selected
database.

The local Compose stack exposes the control API on port `8094`. The CLI requires
the endpoint and bearer credential explicitly:

```bash
export SC_SIMULATOR_API_URL=http://127.0.0.1:8094
export SC_SIMULATOR_API_TOKEN=local-development-sc-simulator-token
export SC_SIMULATOR_HTTP_TIMEOUT_SECONDS=30

uv run --package sc-upstream-simulator sc-upstream-simulator list
uv run --package sc-upstream-simulator sc-upstream-simulator create --file inspection.json
uv run --package sc-upstream-simulator sc-upstream-simulator publish \
  --wafer-key 7 \
  --inspection-time 2026-08-29T01:02:00Z \
  --published-at 2026-08-29T01:05:00Z
```

`create`, `append`, and `update` accept the corresponding JSON request object
through `--file`. There is intentionally no Make wrapper and no direct database
mutation mode.
