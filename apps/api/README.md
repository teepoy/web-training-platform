# API

Run locally:

```bash
fastapi dev app/main.py
```

Prepare a deployable environment before starting the API:

```bash
uv run python scripts/prepare_platform.py
```

This single-purpose script applies Alembic upgrades, reconciles the API-owned
MinIO buckets and lifecycle rules, registers Prefect pools/deployments, and
then validates every required dependency. For a database-only development
upgrade, use `make db-migrate` from the repository root.

Operational account creation and destructive local reset are separate scripts:

```bash
make create-superadmin EMAIL=admin@example.com PASSWORD=... NAME=Admin
make reset-dev-database
```

Configuration profiles:

- `test`: async SQLite + in-memory storage (tests only)
- `dev`: local development with Postgres, S3-compatible storage, Prefect, and workers
- `pre-release`: deployable test/acceptance environment with production-shaped dependencies
- `prod`: production; credentials, public URLs, and signing secrets are required
- `APP_CONFIG_PROFILE` selects config file in `config/`.

Run tests:

```bash
uv run --extra dev pytest
```
