# Backend DDD Convention

Legacy docs may still mention `ViewRow`; it is a documentation artifact, not an active Python base class.

## Layer Structure

Each bounded context under `apps/api/app/modules/<context>/` uses four layers:

```
apps/api/app/modules/<context>/
├── domain/          # Entities, value objects, repository Protocols
├── app/             # Use-case services, orchestrators
├── adapter/         # Concrete implementations: DB repos, external clients, flows, engines, runtime
└── port/
    └── http/        # FastAPI routers, request/response schemas, Depends() functions
```

| Layer | Directory | Role |
|-------|-----------|------|
| Domain | `domain/` | Pure business rules. Defines entity models and repository Protocols that upper layers depend on. No IO, no ORM, no framework imports. |
| Application | `app/` | Orchestration and use-case logic. Depends on `domain/` Protocols. Services take typed Protocol parameters only. No HTTP or DB session imports. |
| Adapter | `adapter/` | Implements contracts from `domain/` and `app/`. Contains DB repositories, external API clients, execution engines, Prefect flows, and runtime logic. Imports IO libraries freely. |
| Port (HTTP) | `port/http/` | Delivery layer. FastAPI routers, Pydantic request/response schemas, and `Depends()` functions that read from `request.app.state.app_context.<module>.<field>`. Thin handlers only; no business logic. |

Additional port flavors (`port/consumer/`, `port/grpc/`) are reserved for future use and not yet implemented.

## Dataset-Type Module Layout

Dataset context modules (`dataset_classification`, `dataset_detection`, `dataset_vqa`) have the same four-layer structure with type-specific subdirectories:

```
apps/api/app/modules/dataset_<type>/
├── domain/             # Per-type entities and protocols
├── app/
│   └── presets/        # @register-decorated preset classes (engineer-authored)
├── adapter/
│   ├── data/           # Per-type seed data and mock item generators
│   ├── runtime/        # Engine-specific execution logic (torch, dspy, etc.)
│   └── mocks/          # Synthetic data generators for smoke tests
│   └── flows/          # Prefect flow definitions
└── port/
    └── http/           # Type-specific routers (if applicable)
```

## Dataset Storage Aggregate Pattern

The unified dataset module has a storage aggregate boundary in addition to the generic DDD layers:

```text
app/modules/datasets/
├── domain/storage_agg.py          # DatasetStorageAgg Protocol, Capabilities
├── adapter/storage_factory.py     # storage_mode -> concrete aggregate
├── adapter/db_full_storage.py     # SampleORM-backed implementation
├── adapter/sparse_storage.py      # Parquet shard / manifest implementation
└── app/session.py                 # view/session projection over storage rows
```

`DatasetStorageAgg` belongs to the dataset module because it expresses storage-mode behavior, not a specific dataset type. It is the boundary for sample enumeration, lazyframe reads, generic bulk writes, annotations, predictions, features, and deletion.

Domain-specific aggregates live in their owning module and wrap `DatasetStorageAgg`. For example, `app/modules/sc/sc_dataset_agg.py` owns SC wafer/defect semantics and must not push those semantics into `DbFullDatasetStorage` or `SparseDatasetStorage`.

Routes and services should receive a factory or service from DI, open the storage aggregate, and call Protocol methods. They should not instantiate storage concretes, shard readers, or repository bypasses directly outside composition/factory code.

## Migration from Old Names

These renames apply uniformly across all bounded contexts:

| Old path | New path | Notes |
|----------|----------|-------|
| `application/` | `app/` | All modules |
| `infrastructure/` | `adapter/` | All modules |
| `interfaces/controllers/` | `port/http/` | Routers move here |
| `interfaces/dtos/` | `port/http/` | Schemas move here; may be `port/http/schemas.py` |
| `api/deps.py` | `port/http/deps.py` | DI dependency functions |
| `data/` | `adapter/data/` | Dataset-type modules only |
| `runtime/` | `adapter/runtime/` | Dataset-type modules only |
| `mocks/` | `adapter/mocks/` | Dataset-type modules only |
| `presets/` | `app/presets/` | Dataset-type modules only |

These old directories must not exist as committed paths after migration. No `__init__.py` re-exports, no compatibility shims, no alias packages.

## Dependency Rules

1. **`port → app → domain`** is the allowed dependency direction. `port` depends on `app`; `app` depends on `domain`. Reverse dependencies are forbidden.
2. **`adapter` implements contracts** defined in `domain` (Protocols) and `app` (service interfaces). Adapters import IO libraries and ORM models freely.
3. **Only `composition.py` imports concrete implementations.** Per-module `init_*()` functions wire `adapter/` concretes into `app/` services. No other module imports from `adapter/` directly.
4. **Services take Protocols, not concretes.** Every service constructor parameter is typed to a `domain/` Protocol or a shared `app/` interface. This makes DI and test mocking trivial.
5. **No compatibility layer.** Old paths (`application/`, `infrastructure/`, `interfaces/`, module-level `api/`) are removed entirely after migration. Imports across the repo reference only final paths.

## Composition Root

`apps/api/app/composition.py` is the single wiring point. It defines `build_app_context(cfg)` which returns an `AppContext` containing per-module contexts built via `init_<module>(shared, ...)` factories. The FastAPI lifespan sets `app.state.app_context`. Per-module `port/http/deps.py` functions use `request.app.state.app_context` to resolve services. Test overrides use `app.dependency_overrides[get_xxx] = lambda: mock`. No `dependency-injector`, no `@inject`, no `Provide[]`.

## Scope

This convention applies to all bounded contexts under `apps/api/app/modules/<context>/`. The `apps/api/app/shared/` directory follows its own conventions and is not a bounded context in the DDD sense. `apps/api/app/modules/types/` and `apps/api/app/core/` are cross-cutting registries, not bounded contexts.
