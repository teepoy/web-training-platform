# API KNOWLEDGE BASE

## OVERVIEW
FastAPI service with async SQLAlchemy persistence, OmegaConf profiles, Protocol-based constructor injection via composition root, SSE job updates, and pluggable execution/storage backends.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| HTTP routes | `app/main.py` | Main API surface, SSE, export persist endpoint |
| Composition root | `app/composition.py` | `AppContainer` dataclass + builders; central wiring point |
| Per-module deps | `app/modules/*/api/deps.py` | Typed FastAPI `Depends()` functions and Annotated types |
| Per-module Protocols | `app/modules/*/domain/repository.py` | Domain interfaces for constructor injection |
| Config profile logic | `app/core/config.py` + `config/*.yaml` | Env overrides plus profile merge |
| DB session/bootstrap | `app/shared/db/session.py` | Async engine, session factory, optional auto-create in tests |
| Schema/migrations | `app/db/models.py` + `alembic/` | Use migration files for non-smoke envs |
| Job execution | `app/modules/training/application/services/orchestrator.py` | Core training lifecycle |
| Artifact persistence | `app/shared/infrastructure/storage/` | Memory or MinIO backends |
| Tests | `tests/` | Pytest integration tests |
| Add/manage cron schedules | `app/modules/schedules/application/services/scheduler.py` | `SchedulerService` — Prefect REST client |
| Register Prefect flows | `app/flows/` | Shared flow definitions |
| Agent runtime | `app/modules/agent/` | Domain-oriented agent modules |
| Dataset type modules | `app/modules/dataset_*/` | Per-type schema, presets, and runtime logic |
| Dataset payload store | `app/modules/datasets/application/services/dataset_payload_store.py` | Shard and manifest management |
| Canonical transport contract | `../../openapi/openapi.yaml` | Single source of truth for backend/frontend transport types |

## STRUCTURE
```text
apps/api/
├── app/
│   ├── composition.py      # AppContainer dataclass + build_app_container()
│   ├── main.py             # FastAPI app, lifespan, health endpoint
│   ├── core/               # config loading
│   ├── shared/
│   │   ├── domain/protocols.py  # shared infra Protocols
│   │   ├── api/utils.py         # shared utility functions
│   │   └── db/                  # SQLAlchemy base/models/session
│   └── modules/            # domain-oriented modules
│       └── <module>/
│           ├── api/deps.py           # FastAPI Depends() functions
│           ├── domain/repository.py  # Protocol definitions
│           ├── application/services/ # service classes
│           ├── infrastructure/       # DB repos, external clients
│           └── interfaces/controllers/router.py
├── config/                 # base/dev/prod/test profiles
├── alembic/                # migrations
└── tests/                  # pytest integration tests
```

## DEPENDENCY INJECTION
1. **Composition root**: `app/composition.py` defines the `AppContainer` dataclass holding all singletons. `build_app_container(cfg)` constructs it. The FastAPI lifespan sets `app.state.container = build_app_container(cfg)`.
2. **Per-module deps**: Each module has `api/deps.py` with `get_xxx(request: Request)` functions reading from `request.app.state.container.xxx`. Annotated types are exported: `XxxDep = Annotated[XxxType, Depends(get_xxx)]`.
3. **Protocol-typed services**: Service constructors take Protocol-typed parameters only. This allows easy mocking and prevents circular dependencies.
4. **Test overrides**: Use `app.dependency_overrides[get_xxx] = lambda: mock_xxx` in tests. Clear overrides after each test.
5. **Non-HTTP entrypoints**: Prefect flows use `_app_container_ref` module-level references set by the lifespan; CLI tools use `build_cli_container(cfg)`.

### HOW TO ADD A NEW MODULE
1. Create `domain/repository.py` with a Protocol:
   ```python
   class MyRepository(Protocol):
       async def get_item(self, id: str) -> Item | None: ...
   ```
2. Create `api/deps.py`:
   ```python
   def get_my_service(request: Request) -> MyService:
       c = request.app.state.container
       return MyService(repository=c.my_repository, ...)
   MyServiceDep = Annotated[MyService, Depends(get_my_service)]
   ```
3. Add field to `AppContainer` in `composition.py`:
   ```python
   my_repository: MyRepository
   ```
4. Wire in `_build_base_container()` in `composition.py`:
   ```python
   container.my_repository = MyRepositoryImpl(session_factory=container.session_factory)
   ```
5. Use in router:
   ```python
   @router.get("/items/{id}")
   async def get_item(id: str, service: MyServiceDep) -> Item:
       return await service.get(id)
   ```
6. Test override:
   ```python
   app.dependency_overrides[get_my_service] = lambda: FakeMyService()
   ```

## DATASET TYPE MODULES
Each dataset type (classification, detection, vqa) is isolated in `app/modules/dataset_<type>/`:
- `domain/schema.py`: `DatasetSchema` definition (auto-registers on import)
- `presets/`: Trainer/predictor presets decorated with `@register`
- `runtime/`: Engine-specific execution logic (e.g. torch, dspy)
- `mocks/`: Synthetic data generators for smoke tests

Modules are auto-discovered and registered via imports in `app/main.py` lifespan.

## CONVENTIONS
- Run from this directory with `uv run ...`.
- `APP_CONFIG_PROFILE=test` is the test-only profile. Supported runtime profiles are `dev` and `prod`.
- `execution.engine=local` and `storage.kind=memory` are test-only. Dev/prod require Prefect and MinIO/S3-compatible storage.

## ANTI-PATTERNS
- Don't use `container: Any` or `self._container` in service constructors — inject typed Protocol deps.
- Don't import `container` from `app.main` in routers or tests — use `app.dependency_overrides` or `request.app.state.container`.
- Don't use `@inject` or `Provide[Container.xxx]` — the `dependency-injector` library is removed.
- Don't add new fields to `AppContainer` without wiring them in `_build_base_container()`.
- Don't make Protocols `@runtime_checkable` without justification.
- Don't add route-level persistence; keep handlers thin and push logic into services/repository.
- Don't trust Kubeflow/MinIO fallbacks as production behavior.
- Don't overload `dataset_type` with storage semantics — use `storage_mode` (`db_full` vs `file_shard_sparse`).

## COMMANDS
```bash
# Start API
uv run uvicorn app.main:app --reload --port 8000
# Migrations
uv run alembic upgrade head
# Tests
uv run --extra dev pytest
# Type check
uv run --directory apps/api pyright .
# Lint
ruff check apps/api
```

## GOTCHAS
- `main.py` allows all CORS origins.
- SSE endpoint polls repository state every 0.5s per client.
- Per-sample predictions live in the API DB (`platform_predictions`) instead of Label Studio.
- If a transport shape belongs in the API contract, change `openapi/openapi.yaml` first and regenerate.
