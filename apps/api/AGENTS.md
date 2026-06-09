# API KNOWLEDGE BASE

## OVERVIEW
FastAPI service with async SQLAlchemy persistence, OmegaConf profiles, Protocol-based constructor injection via composition root, SSE job updates, and pluggable execution/storage backends.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| HTTP routes | `app/main.py` | Main API surface, SSE, export persist endpoint |
| Composition root | `app/composition.py` | `build_app_context()` + per-module `init_*()` factories; `AppContainer` kept only for Prefect flow workers |
| Module context | `app/modules/*/container.py` | Per-module `init_*()` factory; creates module-internal repos/services |
| Shared infra | `app/shared/context.py` | `SharedInfra` (pure infra) + `AppContext` (all module contexts) |
| Per-module deps | `app/modules/*/port/http/deps.py` | Typed FastAPI `Depends()` functions and Annotated types |
| Per-module Protocols | `app/modules/*/domain/repository.py` | Domain interfaces for constructor injection |
| Config profile logic | `app/core/config.py` + `config/*.yaml` | Env overrides plus profile merge |
| DB session/bootstrap | `app/shared/db/session.py` | Async engine, session factory, optional auto-create in tests |
| Schema/migrations | `app/db/models.py` + `alembic/` | Use migration files for non-smoke envs |
| Job execution | `app/modules/training/app/services/orchestrator.py` | Core training lifecycle |
| Training runner (subprocess) | `app/modules/training/adapter/runtime/training_runner.py` | CLI entrypoint spawned as subprocess by Prefect `train-job` flow; resolves registered trainers via `@trainer` decorator registry |
| Artifact persistence | `app/shared/infrastructure/storage/` | Memory or MinIO backends |
| Tests | `tests/` | Pytest integration tests |
| Add/manage cron schedules | `app/modules/schedules/app/services/scheduler.py` | `SchedulerService` — Prefect REST client |
| Register Prefect flows | `app/modules/*/adapter/flows/` | Flow definitions co-located with modules |
| Agent runtime | `app/modules/agent/` | Domain-oriented agent modules |
| Dataset type modules | `app/modules/datasets/{classification,detection,vqa}/` | Unified dataset module with per-type subdomains (models, adapter, upstream, session) |
| Type registration | `app/modules/types/trainers/` and `app/modules/types/predictors/` | Registered trainers and predictors. Views and datasets are co-located in `app/modules/datasets/{type}/models.py`. |
| Registry | `app/core/registry.py` | `@view`, `@trainer`, `@predictor`, `@dataset` (dataclass-based); dynamic `_dataset_type_registry` with query API |
| Mapper registry | `app/core/mapper_registry.py` | `@mapper.register(from_types, to_types)` — type-to-type conversion; `mapper.get_mapper(src, dst)` for lookup |
| Per-module mappers | `app/modules/*/domain/mapper.py` | Conversion functions registered via `@mapper.register`; full conversion logic lives here, not on model classes |
| Registration barrel | `app/registrations.py` | Central import file that controls decorator side-effect order |
| Dataset storage aggregate | `app/modules/datasets/domain/storage_agg.py` + `app/modules/datasets/adapter/storage_factory.py` | `DatasetStorageAgg` Protocol and factory dispatch by `storage_mode` |
| Dataset storage implementations | `app/modules/datasets/adapter/db_full_storage.py` + `app/modules/datasets/adapter/sparse_storage.py` | `db_full` and `file_shard_sparse` implementations of `DatasetStorageAgg` |
| Dataset payload store | `app/modules/datasets/app/services/dataset_payload_store.py` | Shard and manifest management |
| Dataset image serving | `app/modules/datasets/port/http/router.py` + `app/modules/datasets/adapter/sparse_storage.py` | `/samples/{sample_id}/images/{image_id}?dataset_id=...` reads sparse v2 embedded images with column projection |
| SC dataset aggregate | `app/modules/sc/sc_dataset_agg.py` | SC-specific domain wrapper over `DatasetStorageAgg` for wafer/defect semantics |
| SC image compatibility API | `app/modules/sc/port/http/router.py` + `app/modules/sc/domain/image_fetcher.py` | `/sc/images/{inspection_time}/{wafer_key}/{defect_id}/{image_type}` for upstream/mock SC image access |
| Canonical transport contract | `../../openapi/openapi.yaml` | Single source of truth for backend/frontend transport types |

## STRUCTURE
```text
apps/api/
├── app/
│   ├── composition.py      # build_app_context() + per-module init_*() factories; AppContainer for Prefect flows only
│   ├── main.py             # FastAPI app, lifespan, health endpoint
│   ├── core/               # config loading, registry, mapper_registry
│   ├── shared/
│   │   ├── context.py           # SharedInfra + AppContext dataclasses
│   │   ├── domain/protocols.py  # shared infra Protocols
│   │   ├── api/utils.py         # shared utility functions
│   │   └── db/                  # SQLAlchemy base/models/session
│   └── modules/            # domain-oriented modules
│       └── <module>/
│           ├── container.py             # Per-module init_*() factory
│           ├── port/http/deps.py        # FastAPI Depends() functions
│           ├── domain/
│           │   ├── mapper.py            # Type-to-type conversion mappers (@mapper.register)
│           │   └── repository.py        # Protocol definitions
│           ├── app/services/         # service classes
│           ├── adapter/              # DB repos, external clients
│           └── port/http/router.py
├── config/                 # base/dev/prod/test profiles
├── alembic/                # migrations
├── tests/                  # pytest integration tests
```

## DEPENDENCY INJECTION

1. **Composition root**: `app/composition.py` defines `build_app_context(cfg)` which builds `AppContext` — a dataclass holding `shared: SharedInfra` plus per-module contexts. The FastAPI lifespan calls `build_app_context(cfg)` and sets `app.state.app_context = ctx`.

2. **SharedInfra**: `app/shared/context.py` — pure infrastructure only (DB engine, session factory, artifact storage, external clients). No module repos or services.

3. **Per-module contexts**: Each module has `app/modules/<module>/container.py` with `init_<module>(shared, ...explicit_ports...)`. This factory creates all module-internal repos and services. The result is stored on `AppContext.<module>`.

4. **Per-module deps**: Each module has `port/http/deps.py` with `get_xxx(request: Request)` functions reading from `request.app.state.app_context.<module>.<field>`. Annotated types are exported: `XxxDep = Annotated[XxxType, Depends(get_xxx)]`.

5. **Cross-module ports**: When module A needs data from module B, module B exposes a Protocol port. Module A's `init_*()` receives the port as an explicit parameter. No module reaches into a sibling's internal context fields.

6. **Test overrides**: Use `app.dependency_overrides[get_xxx] = lambda: mock_xxx` in tests. Clear overrides after each test.

7. **Prefect flow workers**: Standalone Prefect workers use `build_flow_container(cfg)` which returns an `AppContainer` with flat fields. This is separate from the API server runtime.

### HOW TO ADD A NEW MODULE
1. Create `domain/repository.py` with a Protocol:
   ```python
   class MyRepository(Protocol):
       async def get_item(self, id: str) -> Item | None: ...
   ```
2. Create `app/modules/<module>/container.py`:
   ```python
   @dataclass
   class MyContext:
       my_service: MyService

   def init_my_module(shared: SharedInfra) -> MyContext:
       repo = SqlRepository(session_factory=shared.session_factory)
       svc = MyService(repository=repo, ...)
       return MyContext(my_service=svc)
   ```
3. Add `my_module: MyContext | None = None` to `AppContext` in `app/shared/context.py`.
4. Call `init_my_module(shared)` in `build_app_context()` in `composition.py` and assign to `AppContext.my_module`.
5. Create `port/http/deps.py`:
   ```python
   def get_my_service(request: Request) -> MyService:
       return request.app.state.app_context.my_module.my_service
   MyServiceDep = Annotated[MyService, Depends(get_my_service)]
   ```
6. Create router and add to `app/modules/registry.py`.

## DATASET MODULE (unified)

The unified dataset module at `app/modules/datasets/` consolidates all dataset code:

```
app/modules/datasets/
├── domain/
│   ├── storage_agg.py           # DatasetStorageAgg Protocol + capabilities
│   ├── sample_row.py            # SampleRow, BulkSampleRow, PredictionResult
│   ├── mapper.py                # storage/domain/view mapper registrations
│   └── repository.py            # Dataset repository Protocols
├── adapter/
│   ├── storage_factory.py       # storage_mode -> DatasetStorageAgg implementation
│   ├── db_full_storage.py       # SampleORM-backed storage aggregate
│   ├── sparse_storage.py        # Parquet shard / manifest storage aggregate
│   └── flows/                   # Prefect flows
├── app/
│   ├── session.py               # DatasetSession view projection over storage rows
│   └── services/                # DatasetService and storage-adjacent services
├── port/http/                   # Routes, deps, schemas
├── classification/              # Classification subdomain
├── detection/                   # Detection subdomain
├── vqa/                         # VQA subdomain
├── compatibility.py             # Compatibility gates (view/trainer/predictor)
└── tests/
```

**Key patterns:**
- Open dataset storage through `DatasetStorageFactory.open(dataset_id, org_id)` and program against `DatasetStorageAgg`; do not bypass through `SqlRepository`, shard readers, or deleted sample-access services.
- Training/prediction flows consume `storage.list_samples(return_lazyframe=True, ...)`; SC import writes generic `BulkSampleRow` streams through `storage.write_samples(...)`.
- Domain-specific aggregates wrap storage aggregates. SC semantics belong in `app/modules/sc/sc_dataset_agg.py` or SC services, not in generic storage implementations.
- Each subdomain (`classification/`, `detection/`, `vqa/`) is self-contained: models + adapter + upstream + session in one directory.
- Conversion between storage (`Sample`), domain (`ClassificationSample`, etc.), and view (`LabeledImageV1Row`, etc.) types goes through `MapperRegistry`, not through inline methods on model classes.
- Per-dataset-type mappers live in `app/modules/datasets/domain/mapper.py`; SC mappers in `app/modules/sc/domain/mapper.py`.
- `ViewService` delegates per-sample projection to per-type adapters via `adapter.view_for(view_type, sample)`.
- Trainers/predictors are registered in `app/modules/types/` as `@dataclass Trainer[R]` / `Predictor[R]` generic callables via `functools.partial`.
- View types are declared as `@view`-decorated Pydantic classes with `ClassVar` fields (`view_id`, `view_name`, `is_annotation_view`) in subdomain `models.py`.
- `@dataset` decorator registers dataset types dynamically via `DatasetTypeRegistration` in `app/core/registry.py`; `_dataset_view_types` is the legacy fallback dict for built-in types.
- Central barrel `app/registrations.py` controls import order for all registrations.

## PREFECT FLOW DEPLOYMENTS

Flow definitions live at `apps/api/app/modules/*/adapter/flows/` co-located with each module:

```
app/modules/
├── datasets/adapter/flows/drain_dataset.py
├── sc/adapter/flows/sc_import.py
└── sensors/adapter/flows/
    ├── sensor_base.py
    ├── timer_sensor.py
    └── dataset_size_sensor.py
```

Flows are registered with Prefect via `ftapi deployments apply`, which reads module-level deployment descriptors and creates/updates Prefect deployment records. The bootstrap process creates two work pools:

| Pool | Worker | GPU | Dockerfile |
|------|--------|-----|-----------|
| `default-cpu` | `prefect-worker-cpu` | No | `Dockerfile.prefect-worker-cpu` |
| `default-gpu` | `prefect-worker-gpu` | Yes | `Dockerfile.prefect-worker-gpu` |

### `[gpu]` extra and torch discipline

- `torch` / `torchvision` are **optional** dependencies gated behind the `[gpu]` extra in `pyproject.toml`.
- Only the `prefect-worker-gpu` image installs `[gpu]` extras. The CPU worker and API server images do NOT include torch.
- Code that imports torch must do so inside a guarded block:
  ```python
  try:
      import torch
  except ImportError:
      torch = None  # type: ignore[assignment]

  def _use_torch() -> None:
      if torch is None:
          raise RuntimeError("torch not available (install with [gpu] extra)")
  ```
- Flow definition files themselves should not import torch at module level; keep torch imports inside the flow body or a lazy helper.

## CONVENTIONS
- Run from this directory with `uv run ...`.
- `APP_CONFIG_PROFILE=test` is the test-only profile. Supported runtime profiles are `dev` and `prod`.
- `execution.engine=local` and `storage.kind=memory` are test-only. Dev/prod require Prefect and MinIO/S3-compatible storage.
- Browser-native image requests cannot carry platform auth headers. Image-serving endpoints must support token/org context query parameters, and route dependencies should not assume `X-Organization-ID` is the only org context source.

## ANTI-PATTERNS
- Don't use `container: Any` or `self._container` in service constructors — inject typed Protocol deps.
- Don't import `container` from `app.main` in routers or tests — use `app.dependency_overrides` or `request.app.state.app_context`.
- Don't use `@inject` or `Provide[Container.xxx]` — the `dependency-injector` library is removed.
- Don't add route-level persistence; keep handlers thin and push logic into services/repository.
- Don't trust Kubeflow/MinIO fallbacks as production behavior.
- Don't overload `dataset_type` with storage semantics — use `storage_mode` (`db_full` vs `file_shard_sparse`).
- Don't reintroduce `SampleAccessFactory`, `DatasetSampleService`, `RuntimeMaterializer`, `BulkViewLoader`, or `SampleBulkAccess.open/materialize` as read-path fallbacks; extend `DatasetStorageAgg` or the owning domain aggregate instead.
- Don't add `from_sample` / `to_sample` / `get_adapter` / `as_*` conversion methods to model classes — register standalone mapper functions via `@mapper.register()` in `<module>/domain/mapper.py`.
- Don't call `model_cls.from_sample()` or `model_cls.get_adapter()` directly — use `mapper.get_mapper(src, dst)` or the `_resolve_projector` / `_resolve_from_sample` helpers in session layer.

## COMMANDS
```bash
# Start API
fastapi dev app/main.py
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
- If a transport shape belongs in the API contract, update the FastAPI route DTOs, then run `make generate` to re-export `openapi/openapi.yaml`.
