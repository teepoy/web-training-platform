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
- `dev` / `prod`: async Postgres + S3-compatible object storage + Prefect + workers
- `APP_CONFIG_PROFILE` selects config file in `config/`.

Run tests:

```bash
uv run --extra dev pytest
```
