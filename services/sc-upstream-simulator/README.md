# SC Upstream Simulator

This is the development-only owner of simulated SC upstream state. It is a
separate package so production upstream images and entrypoints cannot expose a
simulator mutation surface accidentally.

The current slice provides:

- an owned, versioned PostgreSQL schema;
- explicit draft and published inspection states;
- atomic creation of inspection, defect, review-image, and patch-archive
  metadata;
- a transactionally allocated latest-change token on publication.

It does not yet provide the HTTP control API, CLI, gRPC/Flight read interfaces,
object generation, or development Compose wiring. Those are subsequent tracked
slices in `docs/todos/stateful-upstream-simulator-and-source-automation.md`.

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
