# Learnings & Conventions

## [INIT] Project Setup
- Runtime: `APP_CONFIG_PROFILE=local-smoke` → SQLite at `apps/api/finetune-local-smoke.db`
- Python: `uv` package manager. Run: `uv run --extra dev pytest`
- Head Alembic revision: `"2b3c4d5e6f7a"` (migration 0006)
- ORM pattern: `Mapped[]`, `mapped_column()`, `utc_now()` default, `from __future__ import annotations`
- ORM models inherit from `Base` in `apps/api/app/db/base.py`
- All ORM models use String(64) PKs (UUID as string)
- Migration chaining: new T1 migration sets `down_revision = "2b3c4d5e6f7a"`
- SQLite compatibility: ALWAYS use `op.batch_alter_table()` for ALTER operations
- Config: OmegaConf YAML, add new sections under `apps/api/config/base.yaml`
- Container DI: `providers.Singleton(ServiceClass, ...)` pattern in `apps/api/app/container.py`
- Tests: pytest + fastapi.testclient.TestClient (sync); conftest.py forces `APP_CONFIG_PROFILE=local-smoke`
- Frontend: Vue 3 + Vite + Naive UI, `@tanstack/vue-query`, Pinia stores
- API client: `src/api.ts` typed `req<T>()` fetch wrapper
- New org RBAC tables use UUID string PKs, `users.email` and `organizations.slug` unique constraints, and `org_memberships` enforces `(user_id, org_id)` uniqueness.
- Alembic SQLite smoke verification can be done with `uv run python` when `sqlite3` CLI is unavailable.
- Domain models use `Field(default_factory=lambda: str(uuid4()))` for IDs and `datetime.now(UTC)` for timestamps.
- New auth/org domain types belong in `app/domain/types.py` + `app/domain/models.py`; existing tests still pass after adding them.

## [T3] Auth Service
- auth.py has module-level functions + AuthService class wrapper
- JWT: python-jose HS256; bcrypt used directly (passlib dropped - incompatible with bcrypt 5.x)
- Config keys: `auth.jwt_secret_key`, `auth.jwt_algorithm`, `auth.access_token_expire_minutes`
- JWT_SECRET_KEY env var overrides config value (via `os.environ.get("JWT_SECRET_KEY") or str(...)`)
- Container: `auth_service = providers.Singleton(AuthService)`
- decode_access_token raises JWTError/ExpiredSignatureError on failure (not caught)
- bcrypt >= 4.0.0 added to pyproject.toml (NOT passlib — incompatible with bcrypt 5.x on Python 3.13)
- python-jose[cryptography] >= 3.3.0 added to pyproject.toml

## [T6] Test conftest helpers
- helpers added: _register_user, _login_user, _auth_headers, _org_headers, _create_org, _add_member
- stubs: _create_org, _add_member use endpoints from T12 (not yet wired)
- conftest location: apps/api/tests/conftest.py

## [T4] PersonalAccessToken
- migration 0008 revision: "def3abc4def5"
- token format: ftp_ + secrets.token_hex(32) (total length ~68)
- PAT functions in auth.py: create_personal_access_token, verify_personal_access_token
- list/delete PAT ops belong in repository layer (not auth.py)
