# API KNOWLEDGE BASE

## OVERVIEW
FastAPI service with async SQLAlchemy persistence, OmegaConf profiles, dependency-injector wiring, SSE job updates, and pluggable execution/storage backends.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| HTTP routes | `app/main.py` | Main API surface, SSE, export persist endpoint |
| Dependency wiring | `app/container.py` | Engine/storage/repository selection |
| Config profile logic | `app/core/config.py` + `config/*.yaml` | Env overrides plus profile merge |
| DB session/bootstrap | `app/db/session.py` | Async engine, session factory, optional auto-create |
| Schema/migrations | `app/db/models.py` + `alembic/` | Use migration files for non-smoke envs |
| Job execution | `app/services/orchestrator.py` + `services/engines.py` | Local vs Kubeflow path |
| Artifact persistence | `app/services/artifacts.py` + `app/storage/` | Memory or MinIO backends |
| Tests | `tests/` | Smoke integration only |
| Add/manage cron schedules | `app/services/scheduler.py` | `SchedulerService` — pure httpx Prefect REST client, no SDK |
| Register Prefect flows | `app/flows/` | `drain_dataset.py` flow definition + `serve.py` serve entrypoint |

## STRUCTURE
```text
apps/api/
├── app/api/         # request schemas
├── app/core/        # config loading
├── app/db/          # SQLAlchemy base/models/session
├── app/domain/      # enums, Pydantic models, interfaces
├── app/repositories/# async SQL repository
├── app/services/    # orchestrator, engines, notifications, artifacts
├── app/services/scheduler.py  # Prefect REST API client wrapper (httpx, no SDK)
├── app/flows/       # Prefect flow definitions and serve entrypoint
├── config/          # base/dev/local-smoke profiles
├── alembic/         # migrations
└── tests/           # pytest smoke flows
```

## CONVENTIONS
- Run from this directory with `uv run ...`.
- `APP_CONFIG_PROFILE=local-smoke` is the default assumption for tests and quick local runs.
- `db.auto_create` is only a smoke convenience; dev/prod should use Alembic.
- `execution.engine` picks `LocalProcessEngine` vs `KubeflowTrainingOperatorEngine` in `container.py`.
- `storage.kind` picks in-memory artifact storage vs MinIO.

## ANTI-PATTERNS
- Don’t add new route-level persistence shortcuts; keep handlers thin and push logic into services/repository.
- Don’t trust Kubeflow/MinIO fallbacks as production behavior; some adapters degrade to smoke-friendly behavior on infra failure.
- Don’t assume auth is enforced yet; OAuth config exists but route protection is not wired.
- Don’t forget that several async services still wrap blocking client libraries; treat them as operationally fragile.
- Don’t change schema only in ORM models; update Alembic too.

## COMMANDS
```bash
uv run uvicorn app.main:app --reload --port 8000
uv run alembic upgrade head
uv run --extra dev pytest
```

## TESTS & COVERAGE
- Tests use `pytest` + `fastapi.testclient.TestClient`.
- Coverage is limited to backend smoke paths (`/health`, dataset/preset/job create/get).
- SSE edge cases, Kubeflow engine, MinIO persistence, webhooks, SDK flows, and feature-op logic are not meaningfully tested.

## GOTCHAS
- `main.py` allows all CORS origins right now.
- SSE endpoint polls repository state every 0.5s per client.
- `config/base.yaml` contains placeholder/insecure defaults; real deployments must override via env or secrets.
