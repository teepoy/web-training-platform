# Alembic

Run migrations:

```bash
cd apps/api
uv run alembic upgrade head
```

Notes:

- In `local-smoke`, app startup may auto-create tables for fast smoke runs.
- For dev/prod, keep `db.auto_create=false` and use Alembic migrations.
