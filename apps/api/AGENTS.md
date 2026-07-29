# API KNOWLEDGE BASE

## OVERVIEW

FastAPI service with async SQLAlchemy persistence, OmegaConf profiles, Protocol-based constructor injection via composition root, SSE job updates, and pluggable execution/storage backends.

## WHERE TO LOOK

| Task                            | Location                                                                                             | Notes                                                                                                                                                                          |
| ------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| HTTP routes                     | `app/main.py`                                                                                        | Main API surface, SSE, export persist endpoint                                                                                                                                 |
| Composition root                | `app/composition.py`                                                                                 | `build_app_context()` + per-module `init_*()` factories                                                                                                                        |
| Module context                  | `app/modules/*/container.py`                                                                         | Per-module `init_*()` factory; creates module-internal repos/services                                                                                                          |
| Shared infra                    | `app/shared/context.py`                                                                              | `SharedInfra` (pure infra) + `AppContext` (all module contexts)                                                                                                                |
| Per-module deps                 | `app/modules/*/port/http/deps.py`                                                                    | Typed FastAPI `Depends()` functions and Annotated types                                                                                                                        |
| Per-module Protocols            | `app/modules/*/domain/repository.py`                                                                 | Domain interfaces for constructor injection                                                                                                                                    |
| Config profile logic            | `app/core/config.py` + `config/*.yaml`                                                               | Env overrides plus profile merge                                                                                                                                               |
| DB session/bootstrap            | `app/shared/db/session.py`                                                                           | Async engine, session factory, optional auto-create in tests                                                                                                                   |
| Schema/migrations               | `app/db/models.py` + `alembic/`                                                                      | Use migration files for non-smoke envs                                                                                                                                         |
| Job execution                   | `app/modules/training/app/services/orchestrator.py`                                                  | Core training lifecycle                                                                                                                                                        |
| Runtime dispatch                | training/prediction orchestrators + Prefect deployment routing                                       | Selects executable deployments by catalog id, data contract, and resource profile; API does not import executable ML callables                                                 |
| Artifact persistence            | `app/shared/infrastructure/storage/`                                                                 | Memory or MinIO backends                                                                                                                                                       |
| Tests                           | `tests/`                                                                                             | Pytest integration tests                                                                                                                                                       |
| Add/manage cron schedules       | `app/modules/jobs/schedules/app/services/scheduler.py`                                               | `SchedulerService` — Prefect REST client                                                                                                                                       |
| Background/runtime jobs         | module orchestrators / runtime service clients                                                       | Prefect, queues, or service APIs are implementation details behind typed ports                                                                                                 |
| Agent runtime                   | `app/modules/agent/`                                                                                 | Domain-oriented agent modules                                                                                                                                                  |
| Dataset type modules            | `app/modules/datasets/{classification,detection,vqa}/`                                               | Unified dataset module with per-type subdomains (models, adapter, upstream, session)                                                                                           |
| Capability catalog              | `app/modules/types/catalog.py`, `capabilities.py`, `registrations/`                                  | Versioned view/materializer/trainer/predictor metadata only. Module bundles are centrally aggregated; executable compatibility code is isolated under `app/runtime_compat/ml`. |
| Registry                        | `app/core/registry.py`                                                                               | `@view`, metadata catalog entries, `@dataset` (dataclass-based); dynamic `_dataset_type_registry` with query API                                                               |
| Mapper registry                 | `app/core/mapper_registry.py`                                                                        | `@mapper.register(from_types, to_types)` — type-to-type conversion; `mapper.get_mapper(src, dst)` for lookup                                                                   |
| Per-module mappers              | `app/modules/*/domain/mapper.py`                                                                     | Conversion functions registered via `@mapper.register`; full conversion logic lives here, not on model classes                                                                 |
| Registration barrel             | `app/registrations.py`                                                                               | Central import file that controls decorator side-effect order                                                                                                                  |
| Dataset storage aggregate       | `app/modules/datasets/domain/storage_agg.py` + `app/modules/datasets/adapter/storage_factory.py`     | `DatasetStorageAgg` Protocol and factory dispatch by `storage_mode`                                                                                                            |
| Dataset storage implementations | `app/modules/datasets/adapter/db_full_storage.py` + `app/modules/datasets/adapter/sparse_storage.py` | `db_full` and `file_shard_sparse` implementations of `DatasetStorageAgg`                                                                                                       |
| Dataset payload store           | `app/modules/datasets/app/services/dataset_payload_store.py`                                         | Shard and manifest management                                                                                                                                                  |
| Dataset image serving           | `app/modules/datasets/port/http/router.py` + `app/modules/datasets/adapter/sparse_storage.py`        | `/samples/{sample_id}/images/{image_id}?dataset_id=...` reads sparse v2 embedded images with column projection                                                                 |
| SC dataset aggregate            | `app/modules/sc/sc_dataset_agg.py`                                                                   | SC-specific domain wrapper over `DatasetStorageAgg` for wafer/defect semantics                                                                                                 |
| SC image compatibility API      | `app/modules/sc/port/http/router.py` + `app/modules/sc/domain/image_fetcher.py`                      | `/sc/images/{inspection_time}/{wafer_key}/{defect_id}/{image_type}` for upstream/mock SC image access                                                                          |
| Canonical transport contract    | `../../openapi/openapi.yaml`                                                                         | Single source of truth for backend/frontend transport types                                                                                                                    |

## STRUCTURE

```text
apps/api/
├── app/
│   ├── composition.py      # build_app_context() + per-module init_*() factories
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

Normative contract: `docs/architecture/composition-contract.md`.

1. **Composition root**: `app/composition.py` builds one `injector.Injector` for the FastAPI process. The FastAPI lifespan stores it on app state through `AppContext` or an equivalent thin runtime holder.

2. **SharedInfra**: `app/shared/context.py` remains pure infrastructure only (DB engine, session factory, artifact storage, external clients). No module repos or services.

3. **Module binders**: Each module owns bindings for its concrete implementations. Binding code may live in `app/modules/<module>/container.py` or a module-local composition file.

4. **Per-module deps**: Each module has `port/http/deps.py` with FastAPI dependency functions that resolve interfaces from the injector. Annotated types are exported: `XxxDep = Annotated[XxxPort, Depends(get_xxx)]`.

5. **Cross-module ports**: When module A needs data from module B, module B exposes a Protocol in `port/local` or `domain`. Module A depends on that Protocol only. No module reaches into a sibling's internal context fields or concrete service classes.

6. **Test overrides**: Override interface bindings in a test injector when possible. FastAPI `dependency_overrides` may still be used at the route boundary. Clear overrides after each test.

7. **Runtime services**: Out-of-process trainer/predictor services use stable runtime/data-plane clients and shared contracts. They must not import API module internals or depend on `AppContext` or the API injector.

### HOW TO ADD A NEW MODULE

1. Create `domain/repository.py` with a Protocol:
   ```python
   class MyRepository(Protocol):
       async def get_item(self, id: str) -> Item | None: ...
   ```
2. Create `app/modules/<module>/container.py` with module bindings:

   ```python
   from injector import Binder, Module, singleton

   class MyModule(Module):
       def configure(self, binder: Binder) -> None:
           binder.bind(MyRepository, to=SqlRepository, scope=singleton)
           binder.bind(MyPort, to=MyService, scope=singleton)
   ```

3. Install the module binder in `build_app_context()` / API injector composition.
4. Export only public Protocols from `port/local`; keep concrete service/repository classes internal to the module.
5. Create `port/http/deps.py`:

   ```python
   def get_my_port(request: Request) -> MyPort:
       injector = request.app.state.app_context.injector
       return injector.get(MyPort)

   MyPortDep = Annotated[MyPort, Depends(get_my_port)]
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
│   └── jobs/                    # Optional background job adapters behind typed ports
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
- API-internal batch paths use `storage.list_samples(return_lazyframe=True, ...)`; out-of-process trainer/predictor services consume dataset views through stable data-plane contracts, manifests, or signed object-store refs. SC import writes generic `BulkSampleRow` streams through `storage.write_samples(...)`.
- Storage, data-plane, and materializer main paths are bulk/table-first: prefer Polars `LazyFrame`, `DataFrame`, or Arrow `Table`; do not move large sample paths through dataclass/Pydantic row DTO lists.
- Do not add Python `for` loops over sample rows unless the data size is explicitly bounded and known small.
- Data-plane manifests follow `docs/architecture/data-plane-manifest-contract.md`; runtime routing follows `docs/architecture/runtime-registration-contract.md`.
- Domain-specific aggregates wrap storage aggregates. SC semantics belong in `app/modules/sc/sc_dataset_agg.py` or SC services, not in generic storage implementations.
- Each subdomain (`classification/`, `detection/`, `vqa/`) is self-contained: models + adapter + upstream + session in one directory.
- Conversion between storage (`Sample`), domain (`ClassificationSample`, etc.), and view (`LabeledImageV1Row`, etc.) types goes through `MapperRegistry`, not through inline methods on model classes.
- Per-dataset-type mappers live in `app/modules/datasets/domain/mapper.py`; SC mappers in `app/modules/sc/domain/mapper.py`.
- `ViewService` delegates per-sample projection to per-type adapters via `adapter.view_for(view_type, sample)`.
- Trainer/predictor entries under `app/modules/types/` are API catalog metadata for listing, schema, compatibility, and authorization. They must not be executable ML callables imported by the API process.
- View types use `@view(id=...)` on canonical Pydantic row classes. Name,
  annotation flag, versioned contract, row import path, and Arrow schema import
  path belong to the module-owned `ViewDefinition`; do not duplicate literal
  metadata in the row class.
- `@dataset` decorator registers dataset types dynamically via `DatasetTypeRegistration` in `app/core/registry.py`; `_dataset_view_types` is the legacy fallback dict for built-in types.
- Central barrel `app/registrations.py` controls import order for all registrations.

## RUNTIME SERVICES

Training, prediction, embedding, image parsing, and other heavy dependency execution should run in root `services/*` processes or equivalent out-of-process runtimes. API orchestrators talk to them through typed ports, runtime clients, transport contracts, manifests, or signed object-store refs.

- API catalog entries describe trainer/predictor metadata; Prefect deployments represent executable capabilities.
- API must not import executable trainer/predictor callables or Torch/CUDA dependencies.
- Runtime services must not import `apps/api/app/modules/*` service/repository/ORM/FastAPI internals.
- Dataset views exposed to runtime services should cross a stable data-plane boundary, not raw Python aggregate objects.

### Torch Discipline

- `torch` / `torchvision` are runtime-service dependencies, not API-server dependencies.
- API server images do NOT include torch.
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

- API modules should not import torch at module level. Runtime service modules may import torch according to their own service-local dependency policy.

## CONVENTIONS

- Run from this directory with `uv run ...`.
- `APP_CONFIG_PROFILE=test` is the test-only profile. Supported runtime profiles are `dev` and `prod`.
- `execution.engine=local` and `storage.kind=memory` are test-only. Dev/prod require Prefect and MinIO/S3-compatible storage.
- Browser-native image requests cannot carry platform auth headers. Image-serving endpoints must support token/org context query parameters, and route dependencies should not assume `X-Organization-ID` is the only org context source.

## ANTI-PATTERNS

- Don't use `container: Any` or `self._container` in service constructors — inject typed Protocol deps.
- Don't import a container from `app.main` in routers or tests — resolve typed interfaces through FastAPI deps or test injector overrides.
- Don't inject concrete service classes across module boundaries. Export and bind Protocol interfaces instead.
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
