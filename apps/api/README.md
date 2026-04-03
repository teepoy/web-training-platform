# API

Run locally:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Run migrations:

```bash
uv run alembic upgrade head
```

Configuration profiles:

- Local smoke (default): async SQLite via `sqlite+aiosqlite`
- Dev/prod: async Postgres via `postgresql+asyncpg`
- `APP_CONFIG_PROFILE` selects config file in `config/` (default `local-smoke`).

Run tests:

```bash
uv run --extra dev pytest
```
