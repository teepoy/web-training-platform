# API

Run locally:

```bash
fastapi dev app/main.py
```

Run migrations:

```bash
uv run alembic upgrade head
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
