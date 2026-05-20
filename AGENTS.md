# PROJECT KNOWLEDGE BASE

## OVERVIEW
Monorepo for an online finetune platform: FastAPI API, Vue 3 web app, Python SDK/CLI, and local/k8s deployment manifests. Runtime behavior is config-driven: local smoke uses SQLite + local execution, dev mode targets Postgres + MinIO + Kubeflow. Every dataset has a mandatory Label Studio project (`ls_project_id` is NOT NULL).

## STRUCTURE
```text
./
├── apps/api/           # FastAPI backend, config profiles, Alembic migrations, tests
├── apps/api/app/flows/ # Prefect flow definitions and serve entrypoint
├── apps/api/app/routers/  # Backend extension routes — explicit registry.py
├── apps/web/           # Vue 3 SPA — routes, API client, views
├── apps/web/.storybook/ # Storybook config + mock helpers
├── libs/web-ui/src/components/sample-browser/ # Shared virtualized browser core
├── apps/web/src/core/  # Singleton widget registry
├── apps/web/src/registrations/  # Frontend widget descriptors (one subdirectory per widget)
├── apps/worker/        # Prefect flow-worker package (training/prediction/embedding)
├── libs/widget-sdk/    # @platform/widget-sdk — TypeScript widget contract types & factories
├── libs/web-ui/        # @platform/web-ui — shared Vue/Naive UI components and composables
├── libs/python-sdk/    # ftctl CLI, FinetuneClient, agent wrappers
├── infra/k8s/          # minikube/kubeflow manifests
├── infra/compose/      # docker compose smoke stack
└── docs/               # architecture and endpoint notes
```

## COMMANDS

**Prefer `make` targets over raw commands.** Run from repo root.

| What                    | Command                                             | Notes                                                                                                                  |
| ----------------------- | --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Install all             | `make install`                                      | uv sync + pnpm install                                                                                                 |
| Start API + Web         | `make dev`                                          | Parallel; Ctrl-C stops both                                                                                            |
| Start API only          | `make dev-api`                                      | `API_PORT=9000` to override                                                                                            |
| Start Web only          | `make dev-web`                                      | `WEB_PORT=3000` to override                                                                                            |
| **Run all tests**       | `make test`                                         | API tests only (no frontend tests)                                                                                     |
| **Run single test**     | `make test-api ARGS="-k test_health"`               | pytest `-k` filter                                                                                                     |
| **Run test file**       | `make test-api ARGS="tests/test_vqa_runtime.py -v"` | Verbose single file                                                                                                    |
| Build frontend          | `make build-web`                                    | vue-tsc + vite build                                                                                                   |
| Alembic migrate         | `make db-migrate`                                   | `upgrade head`                                                                                                         |
| Compose Alembic migrate | `make db-migrate-compose`                           | Runs `alembic upgrade head` in Compose API container                                                                   |
| New migration           | `make db-revision MSG="add column"`                 | autogenerate                                                                                                           |
| Reset app data          | `make reset-app-data`                               | Drops and recreates app tables in the configured DB                                                                    |
| SDK CLI                 | `make ftctl ARGS="jobs ls"`                         | Wraps `ftctl`                                                                                                          |
| Seed ImageNet mock      | `make seed-imagenet-mock`                           | Health-checks `API_URL` first; creates dataset `ImageNet-1K Mock` with 1000 offline synthetic samples                  |
| Seed ImageNet POC       | `make seed-imagenet-poc`                            | Health-checks `API_URL` first; creates dataset `ImageNet-1K Real` with 64 real samples for prediction proof-of-concept |
| Seed ImageNet full      | `make seed-imagenet-full`                           | Health-checks `API_URL` first; refreshes dataset `ImageNet-1K Real` via the full real ImageNet seeding path            |
| Batch dev smoke         | `make smoke-dev-batch`                              | Run after `make seed-imagenet-mock` or `make seed-imagenet-poc`; verifies seeded batch prediction availability         |
| Compose up/down         | `make up` / `make down`                             | Full Compose stack (dev profile, includes baked web container)                                                         |
| Compose backend only    | `make up-stack`                                     | Compose stack without the baked web container                                                                          |
| Ensure mock datasets    | `make ensure-mock-datasets`                         | Waits for API health and idempotently ensures `ImageNet-1K Mock` dataset exists (no model creation)                    |
| Compose dev entrypoint  | `make updev`                                        | Starts compose backend, ensures mock datasets exist, then runs local Vite web dev server                               |

| Widget SDK tests | `pnpm test:plugin-sdk` | vitest in `libs/widget-sdk/` (20 tests) |
| Web UI package tests | `pnpm test:web-ui` | vitest in `libs/web-ui/` |
| Widget integration tests | `pnpm test:plugins` | vitest for widget registrations |
| Build widget SDK | `pnpm build:plugin-sdk` | tsup build of `@platform/widget-sdk` |
| **Storybook** | `pnpm storybook` | Widget component stories on port 6006 |
| Build Storybook | `pnpm build-storybook` | Static build of Storybook |

Raw single-test (when Make is unavailable):
```bash
cd apps/api && uv run --extra dev pytest tests/test_datasets.py::test_create_dataset -v
```

`make seed-imagenet-mock`, `make seed-imagenet-poc`, and `make seed-imagenet-full` now check `$(API_URL)/health` before running. Override with `API_URL=http://localhost:9000` when needed.

## CODE STYLE — PYTHON

No linter/formatter is configured. Follow these observed conventions exactly.

- **Future annotations**: Every file starts with `from __future__ import annotations`.
- **Type unions**: `X | None` (PEP 604), never `Optional[X]`.
- **Type annotations**: All function signatures and return types annotated.
- **Import order**: stdlib → third-party → local (`app.domain`, `app.db`, `app.services`). No enforced tool — keep consistent manually.
- **Naming**: `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` constants.
- **ORM models**: `XxxORM` suffix (`DatasetORM`, `SampleORM`, `AnnotationORM`).
- **Domain models**: Plain `BaseModel` — `Dataset`, `Sample`, `Annotation`.
- **Request/Response schemas**: `XxxRequest` / `XxxResponse` suffix.
- **Async**: All repository methods are `async def`. DB access via `async with self.session_factory() as session`.
- **Error handling**: `raise HTTPException(status_code=N, detail="message")` in route handlers. Keep handlers thin; push logic into services.

## CODE STYLE — TYPESCRIPT / VUE

- **Strict mode**: `tsconfig.json` has `strict: true`. Never weaken it.
- **Components**: Vue 3 Composition API with `<script setup lang="ts">`.
- **Types**: All API types in `src/types.ts` as `export interface Xxx { ... }`.
- **Naming**: `PascalCase` interfaces/components, `camelCase` variables/functions.
- **Data fetching**: Vue Query (`@tanstack/vue-query`). State: Pinia.
- **UI library**: Naive UI (`naive-ui`).
- **API client**: `src/api.ts` — hardcodes `http://localhost:8000/api/v1`.

## TEST INFRASTRUCTURE

- **Framework**: pytest + `fastapi.testclient.TestClient` (sync client over async app).
- **Config**: Tests force `APP_CONFIG_PROFILE=test` in `conftest.py`.
- **Auth mock**: `_mock_auth_deps` autouse fixture overrides auth for all tests. Use marker `@pytest.mark.no_auth_override` to skip.
- **LS mock**: `_mock_ls_client` autouse fixture mocks Label Studio client. LS-specific tests (`test_ls_*.py`) manage their own overrides.
- **Pattern**: `with TestClient(app) as c:` inside each test function.
- **Markers**: `no_auth_override` — defined in `apps/api/pyproject.toml`.

## WHERE TO LOOK
| Task                      | Location                                                                     |
| ------------------------- | ---------------------------------------------------------------------------- |
| API routes                | `apps/api/app/main.py`                                                       |
| Runtime DI wiring         | `apps/api/app/container.py`                                                  |
| Config profiles           | `apps/api/config/*.yaml` (`APP_CONFIG_PROFILE`)                              |
| DB schema changes         | `apps/api/app/db/models.py` + `apps/api/alembic/`                            |
| Frontend API calls        | `apps/web/src/api.ts`                                                        |
| Frontend views            | `apps/web/src/views/` + `apps/web/src/router.ts`                             |
| Prefect flows             | `apps/api/app/flows/`                                                        |
| Schedule service          | `apps/api/app/services/scheduler.py`                                         |
| Agent runtime             | `apps/api/app/agent/`                                                        |
| Preset definitions         | `apps/api/app/presets/*.py`                      | Decorator-based single-file presets (`@register`) — one .py = one complete preset |
| Preset registry decorator  | `apps/api/app/presets/_registry.py`               | `@register` decorator + `get_preset()` / `list_presets()` API |
| Preset registry (bridge)   | `apps/api/app/presets/registry.py`                | Legacy `PresetRegistry` — bridges YAML + decorator presets; `list_presets()`/`get_preset()`/`preset_to_api_dict()` |
| Preset schema (legacy)     | `apps/api/app/presets/schema.py`                  | Pydantic models for preset YAML validation (still used for backward compat bridge) |
| Agent display protocol    | `docs/protocols/agent-display-protocol.md`        |                                                                     |
| Preview launch form       | `apps/web/src/views/PreviewLaunchView.vue`                                   |                                                                     |
| Preview workspace         | `apps/web/src/views/PreviewClassifyView.vue`                                 |                                                                     |
| Preview item drawer       | `libs/web-ui/src/components/preview-item-drawer/PreviewItemDrawer.vue`       |                                                                     |
| Preview loader composable | `apps/web/src/composables/usePreviewLoader.ts`                               |                                                                     |
| Preview domain models     | `apps/api/app/domain/preview.py`                                             |                                                                     |
| Preview service           | `apps/api/app/services/preview_service.py`                                   | Session lifecycle, item pagination, persist handoff                 |
| Preview TTL store         | `apps/api/app/services/preview_store.py`                                     | In-memory TTL session store                                         |
| Upstream adapter          | `apps/api/app/services/preview_upstream.py`                                  | 50-item mock upstream; replace with real adapter                    |
| Shared browser core       | `libs/web-ui/src/components/sample-browser/`                                 | Shared virtualized browser core                                     |
| Sidebar shell             | `libs/web-ui/src/components/browser-sidebar/BrowserSidebar.vue`              | Shared sidebar shell with injected widget resolver                  |
| Browser preferences       | `apps/web/src/stores/sampleBrowser.ts`                                       | Presentation persistence (layout, thumbSize)                        |
| Browser filter            | `apps/web/src/composables/useBrowserFilter.ts`                               | Browser-scope item filter pipeline                                  |
| Browser architecture      | `docs/architecture/sample-browser.md`                                        | Shared browser architecture doc                                     |
| Datasets architecture     | `docs/architecture/datasets-shim-architecture.md`                            | Specialized list view shim architecture                             |
| Dataset schema system     | `docs/architecture/dataset-schema-system.md`                                 | Unified DatasetSchema descriptor — types, LS config, annotation, mocks |
| Backend schema dataclass  | `apps/api/app/domain/dataset_schema.py`                                      | `DatasetSchema` dataclass definition                                |
| Backend schema registry   | `apps/api/app/domain/schema_registry.py`                                     | register / get / list_all / get_allowed_pairs                       |
| Backend schema modules    | `apps/api/app/domain/schemas/`                                               | One Python module per dataset type; auto-registers on import        |
| Frontend schema registry  | `apps/web/src/views/datasets/schema-registry.ts`                             | `registerDatasetSchema` / `resolveDatasetShim` — keyed by dataset_type |
| Frontend schema modules   | `apps/web/src/views/datasets/schemas/`                                       | One TS module per dataset type; self-registers on import            |
| Dataset list shims        | `apps/web/src/views/datasets/shims/`                                         | Per-type dataset list Vue components                                |
| Seed scripts              | `libs/seedmaker/src/seedmaker/datasets/`                                     | Per-type seed scripts; share mock_item_generator logic with schema  |
| Dataset storage modes     | `docs/architecture/dataset-storage-modes.md`                                 | Capability matrix for `db_full` vs `file_shard_sparse`, intent origin, and deferred scope |
| Sparse dataset payload     | `apps/api/app/services/dataset_payload_store.py` + `apps/api/app/domain/dataset_payload.py` | Shard manifest, parquet payload storage, deterministic delete |
| Sparse capability guards   | `apps/api/app/services/dataset_capability_guard.py`                           | `assert_not_sparse` guard for operations incompatible with `file_shard_sparse` |
| Widget SDK contracts      | `libs/widget-sdk/src/`                                                       | TypeScript widget type definitions and factories                    |
| Web UI package            | `libs/web-ui/src/`                                                           | Shared Vue/Naive UI components and dataset-list helpers             |
| Widget SDK templates      | `libs/widget-sdk/src/templates/`                                             | Copy-paste starter templates for new widgets                        |
| Frontend widget registry  | `apps/web/src/core/registry.ts`                                              | Singleton `widgetRegistry` instance                                 |
| Frontend widget barrel    | `apps/web/src/registrations/index.ts`                                              | Explicit registration of all widgets before app mount               |
| Shared sidebar widgets    | `libs/web-ui/src/components/<name>/index.ts`                           | Widget descriptors co-located with .vue components; self-contained directories |
| Frontend importers        | `apps/web/src/registrations/import-*/`                                             | Import flow widgets (e.g. `import-manual`, `import-dataset-manual`) |
| Frontend exporters        | `apps/web/src/registrations/export-*/`                                             | Export flow widgets (e.g. `export-preview`, `export-persist`)       |
| Frontend preview launchers | `apps/web/src/registrations/preview-*/`                                            | Preview launcher descriptors (e.g. `preview-upstream`)                  |
| Flow modal                | `libs/web-ui/src/components/flow-modal/FlowModal.vue`           | 2-step modal: select type, then execute component                   |
| Flow type selector        | `libs/web-ui/src/components/flow-type-selector/FlowTypeSelector.vue`     | Card grid for selecting a flow type                               |
| Backend extension registry | `apps/api/app/routers/registry.py`                                           | Explicit list of backend extension routers                             |
| Backend extension routes  | `apps/api/app/routers/*/router.py`                                           | One FastAPI router per backend extension                               |
| Extension guide           | `docs/guides/extension-guide.md`                                      | Step-by-step guide for all 4 extension types                           |
| Sensor registry         | `apps/api/app/sensors/registry.py`                                           | SensorRegistry — loads YAML sensor definitions |
| Sensor YAML definitions | `apps/api/sensors/`                                                          | Engineer-authored sensor YAML files |
| Sensor domain models    | `apps/api/app/domain/sensor.py`                                              | SensorSubscription, SensorCheckpoint, SensorEvent |
| Sensor repository       | `apps/api/app/repositories/sensor_repository.py`                             | Async CRUD for subscriptions + checkpoints |
| Sensor dispatch service | `apps/api/app/services/sensor_dispatch.py`                                   | Dispatch events to matching subscriptions |
| Sensor API router       | `apps/api/app/routers/sensors/router.py`                                     | CRUD + event ingestion endpoints |
| Sensor Prefect flow     | `apps/api/app/flows/dataset_size_sensor.py`                                  | Example sensor flow (polls dataset counts) |
| Sensor pub/sub arch     | `docs/architecture/sensor-pubsub.md`                                         | Architecture overview |
| Sensors frontend view   | `apps/web/src/views/SensorsView.vue`                                         | Sensor subscription management UI |
| Widget contract shim      | `apps/web/src/components/classify/widgetContract.ts`                         | Re-exports SDK types; kept for backward compatibility               |
| Storybook config          | `apps/web/.storybook/`                                                       | Storybook main.ts, preview.ts, mock helpers                         |
| Widget stories            | `apps/web/src/registrations/**/*.stories.ts` and `libs/web-ui/src/**/*.stories.ts` | Story files for app widgets and shared web-ui components            |

## CODE MAP
| Symbol                  | Type       | Location                                                                 | Role                                                         |
| ----------------------- | ---------- | ------------------------------------------------------------------------ | ------------------------------------------------------------ |
| `app`                   | FastAPI    | `apps/api/app/main.py`                                                   | HTTP/SSE entrypoint                                          |
| `Container`             | DI         | `apps/api/app/container.py`                                              | Wires engine/storage/repo; `WiringConfiguration` enables `@inject` on route handlers |
| `TrainingOrchestrator`  | service    | `apps/api/app/services/orchestrator.py`                                  | Job persistence + notifications                              |
| `SchedulerService`      | service    | `apps/api/app/services/scheduler.py`                                     | Prefect REST client                                          |
| `SurfaceStore`          | service    | `apps/api/app/agent/surface_store.py`                                    | In-memory agent panel state                                  |
| `SessionStore`          | service    | `apps/api/app/agent/session_store.py`                                    | In-memory conversation persistence (TTL-based)               |
| `ClassifyAgent`         | service    | `apps/api/app/agent/runtime.py`                                          | LLM tool-calling loop for classify sidebar                   |
| `GlobalAgent`           | service    | `apps/api/app/agent/global_runtime.py`                                   | Platform-wide LLM agent (read/write/sidebar)                 |
| `useAgentCore`          | composable | `libs/web-ui/src/composables/useAgentCore.ts`                            | Shared SSE frame iteration, message accumulation, abort, status |
| `useAgentAdapter`       | composable | `apps/web/src/features/agent/useAgentAdapter.ts`                         | App adapter: route context, auth wiring, panel orchestration |
| `router`                | Vue Router | `apps/web/src/router.ts`                                                 | `/datasets`, `/jobs`, `/schedules`                           |
| `FinetuneClient`        | SDK        | `libs/python-sdk/ftsdk/client.py`                                        | Sync HTTP wrapper                                            |
| `PreviewService`        | service    | `apps/api/app/services/preview_service.py`                               | Session lifecycle, item pagination, persist handoff          |
| `PreviewStore`          | service    | `apps/api/app/services/preview_store.py`                                 | In-memory TTL session store                                  |
| `MockUpstreamAdapter`   | service    | `apps/api/app/services/preview_upstream.py`                              | 50-item mock upstream; replace with real adapter             |
| `usePreviewLoader`      | composable | `apps/web/src/composables/usePreviewLoader.ts`                           | Cursor-based preview item loader                             |
| `PreviewClassifyView`   | view       | `apps/web/src/views/PreviewClassifyView.vue`                             | Preview workspace with grid + persist flow                   |
| `widgetRegistry`        | singleton  | `apps/web/src/core/registry.ts`                                          | Runtime registry of all frontend widgets                     |
| `createDescriptorRegistry`  | factory    | `libs/widget-sdk/src/registry.ts`                                        | Creates the `DescriptorRegistry` instance                        |
| `useDatasetListSurface` | composable | `libs/web-ui/src/datasets/surface.ts`                                    | Shared dataset list normalization, permissions, and UI props |
| `buildDatasetColumns`   | function   | `libs/web-ui/src/datasets/surface.ts`                                    | Shared dataset table column/action factory                   |
| `defineDashboardWidget`   | factory    | `libs/widget-sdk/src/sidebar.ts`                                         | Declares a dashboard widget                             |
| `defineImporter`    | factory    | `libs/widget-sdk/src/importer.ts`                                        | Declares an importer                               |
| `defineExporter`    | factory    | `libs/widget-sdk/src/exporter.ts`                                        | Declares an exporter                               |
| `defineAgentSkill`      | factory    | `libs/widget-sdk/src/agent.ts`                                           | Declares an agent skill                               |
| `definePreviewLauncher`   | factory    | `libs/widget-sdk/src/preview.ts`                                         | Declares a preview launcher                           |
| `FlowModal`       | component  | `libs/web-ui/src/components/flow-modal/FlowModal.vue`       | 2-step modal: select type, then execute component            |
| `FlowTypeSelector`    | component  | `libs/web-ui/src/components/flow-type-selector/FlowTypeSelector.vue` | Card grid for selecting a flow type                        |
| `PanelHost`             | component  | `libs/web-ui/src/components/panel-host/PanelHost.vue`                     | Standalone panel renderer — renders SidebarPanelDescriptor[] anywhere |
| `usePagePanels`         | composable | `libs/web-ui/src/composables/usePagePanels.ts`                            | Page-level provider for BROWSER_DASHBOARD_KEY + SIDEBAR_WIDGET_INTERACTION_KEY |
| `PageProvider`          | component  | `libs/web-ui/src/components/page-provider/PageProvider.vue`               | Template-friendly wrapper for usePagePanels                   |
| `useWaferHelpers`       | composable | `libs/web-ui/src/composables/useWaferHelpers.ts`                          | Shared wafer coordinate utilities (normalizeWaferPoint, injectWaferPanelData) |
| `EXTENSION_ROUTERS`        | list       | `apps/api/app/routers/registry.py`                                       | Explicit list of all backend extension routers                  |
| `register`               | decorator  | `apps/api/app/presets/_registry.py`                                    | `@register` decorator: single-file preset registration (replaces YAML) |
| `get_preset`             | function   | `apps/api/app/presets/_registry.py`                                    | Look up registered preset class by ID |
| `get_preset_meta`        | function   | `apps/api/app/presets/_registry.py`                                    | Look up registered preset metadata by ID |
| `PresetRegistry`         | class      | `apps/api/app/presets/registry.py`                                     | Legacy YAML registry — bridges YAML + decorator presets |
| `PresetSpec`             | model      | `apps/api/app/presets/schema.py`                                       | Pydantic model for preset YAML (legacy compat) |
| `SensorRegistry`        | class      | `apps/api/app/sensors/registry.py`                                           | Loads sensor YAML definitions; exposes get(id), list_all() |
| `SensorDispatchService` | service    | `apps/api/app/services/sensor_dispatch.py`                                   | Dispatches sensor events to matching subscriptions; isolation per subscription |
| `SensorRepository`      | repository | `apps/api/app/repositories/sensor_repository.py`                             | Async CRUD for SensorSubscriptionORM and SensorCheckpointORM |
| `provideWidgetContext`  | decorator  | `apps/web/.storybook/mocks/widgetContext.ts`                             | Storybook decorator providing sidebar-widget injection keys  |
| `mockImportProps`       | factory    | `apps/web/.storybook/mocks/flowProps.ts`                               | Storybook mock factory for importer props               |
| `mockExportProps`       | factory    | `apps/web/.storybook/mocks/flowProps.ts`                               | Storybook mock factory for exporter props               |
| `mockPreviewProps`      | factory    | `apps/web/.storybook/mocks/flowProps.ts`                               | Storybook mock factory for preview launcher props            |

## ANTI-PATTERNS — DO NOT

### Architecture
- Don't add route-level persistence; keep handlers thin, push logic into services/repository.
- Don't change ORM models without a corresponding Alembic migration.
- `apps/worker` is the Prefect flow-worker package; keep API, flow workers, and the inference service separated in dev/prod.
- Don't assume Kubeflow/MinIO are live; smoke paths degrade gracefully.
- Don't hardcode new backend URLs; the existing `localhost:8000` hardcode is a known debt.
- Don't reuse example secrets (`postgres`, `minioadmin`) outside smoke.
- Don't create new YAML-based presets — use the `@register` decorator in a single `.py` file under `apps/api/app/presets/`.
- Don't use `importlib.import_module()` or string-based entrypoints for new preset trainers/predictors — import classes directly in the preset file.

### Label Studio (LS)
- Dataset = LS project. Every dataset has a mandatory `ls_project_id` (NOT NULL).
- `ls_project_url` is computed at response time from config — never stored.
- Platform predictions live in the API DB. Label Studio is only a temporary manual-annotation surface for synced prediction collections.
- Don't use `cfg.label_studio.enabled` — it was removed. LS is always required; check `cfg.label_studio.url`.
- Don't re-add the "link to LS" manual flow — it was intentionally removed.
- VQA predictions are stored as Label Studio `textarea` results, not classification choices.
- Prediction collection sync to LS is one-way and manual. Do not treat LS prediction IDs as durable platform provenance.

### Widget Architecture
- Don't register widgets directly in `main.ts`, `BrowserSidebar.vue`, or `DatasetDetailView.vue` — always add to `apps/web/src/registrations/index.ts`.
- Each registration `index.ts` exports a named descriptor; the barrel file does the registration. Don't call `widgetRegistry.register*()` inside registration modules.
- Don't import widget `.vue` files statically in registration `index.ts` — use `() => import(...)` (async) so the registry resolves components lazily.
- Don't bypass `widgetRegistry` for sidebar rendering — app surfaces pass `widgetRegistry.getWidgetComponent(key)` into the shared `BrowserSidebar.vue` resolver prop.
- Don't add new widget cases to `sidebarConfig.ts` — `SIDEBAR_WIDGETS` and `WIDGET_COMPONENTS` were intentionally removed; use `defineDashboardWidget` instead.
- Don't import from `widgetContract.ts` for new widget code — import from `@platform/widget-sdk` directly; the shim is kept only for backward compatibility.
- Don't add hardcoded import/export/preview modals to views — use `FlowModal` and `FlowTypeSelector` for the 2-step flow selection.
- Backend extension routes must live under `apps/api/app/routers/<name>/router.py`; they must be added to `EXTENSION_ROUTERS` in `apps/api/app/routers/registry.py` — don't manually import them in `main.py`.

### Code Quality
- Don't suppress type errors with `as any`, `@ts-ignore`, `@ts-expect-error`.
- Don't weaken `strict: true` in tsconfig.
- Don't skip `from __future__ import annotations` in new Python files.
- Don't use `Optional[X]` — use `X | None`.

## CONVENTIONS
- Python packages managed by `uv`; frontend by `pnpm`.
- `APP_CONFIG_PROFILE=test` is test-only; supported runtime profiles are `dev` and `prod`.
- `execution.engine=local` and `storage.kind=memory` are test-only. Dev/prod require Prefect + shared S3-compatible storage.
- K8s namespace: `finetune`; config via `finetune-config` and `finetune-secrets`.
- Job progress exposed via SSE, not websockets.
- Presets are engineer-managed **single Python files** (`apps/api/app/presets/<id>.py`) decorated with `@register(...)`. YAML presets are legacy — new presets must use the decorator.
- To add a new training preset: create `apps/api/app/presets/<my_preset>.py`, decorate the class with `@register(id=..., name=..., ...)`, implement `.train()`, `.predict()`, and `.pipeline()` static methods, then add `from . import <my_preset>` to `apps/api/app/presets/__init__.py`. Config, model metadata, trainer/predictor references are all direct Python imports — no YAML, no string importlib entries.
- Seed scripts must resolve bundled presets from the read-only preset registry; they must not POST new training presets.
- Active DSPy runtime path is VQA (`dspy-vqa-v1`); do not add placeholder DSPy trainer/predictor configs.
- `storage_mode` (`db_full` | `file_shard_sparse`) is the dataset-level distinction for storage semantics. It is orthogonal to `dataset_type` — a classification dataset and a VQA dataset can each be either mode. Never infer storage behavior from the semantic type; always branch on `storage_mode`.
- See `apps/api/AGENTS.md` and `apps/web/AGENTS.md` for sub-project details.
- Widget SDK (`@platform/widget-sdk`) is a workspace TypeScript package in `libs/widget-sdk/`. It is path-aliased in `apps/web/tsconfig.json` (`@platform/widget-sdk → ../../libs/widget-sdk/src/index.ts`) and built with `tsup`.
- To add a reusable first-party widget: create the .vue component in `libs/web-ui/src/components/<name>/<Name>Widget.vue`, create a widget descriptor in `libs/web-ui/src/components/<name>/index.ts` via `defineDashboardWidget({...})`, export both the component default and the widget descriptor from `libs/web-ui/src/index.ts`, then register the descriptor in `apps/web/src/registrations/index.ts`. Widget components are now general-purpose — they can be rendered via `PanelHost` anywhere in a page, imported directly by other components, or registered as sidebar widgets from the same source. App-specific widgets can still live under `apps/web/src/registrations/sidebar-<name>/`. See `docs/guides/extension-guide.md`.
- To add a new importer: create `apps/web/src/registrations/import-<name>/index.ts`, export a named descriptor via `defineImporter({...})`, then register in `apps/web/src/registrations/index.ts`. Importers use `FlowModal` with `kind="import"` for a 2-step type-selection flow.
- To add a new exporter: create `apps/web/src/registrations/export-<name>/index.ts`, export a named descriptor via `defineExporter({...})`, then register in `apps/web/src/registrations/index.ts`. Exporters use `FlowModal` with `kind="export"`.
- To add a new preview launcher: create `apps/web/src/registrations/preview-<name>/index.ts`, export a named descriptor via `definePreviewLauncher({...})`, then register in `apps/web/src/registrations/index.ts`. Preview launchers use `FlowTypeSelector` for a 2-step flow.
- To add a new backend extension route: create `apps/api/app/routers/<name>/router.py` with an `APIRouter` named `router`, then add it to `EXTENSION_ROUTERS` in `apps/api/app/routers/registry.py`.

### Route Handler DI Patterns
- **Preferred** (simple routers, 1-2 services per handler): `@inject` + `Annotated[Service, Depends(Provide[Container.xxx])]`. Requires adding the module to `WiringConfiguration` in `app/container.py`. Injected params must precede all `= Depends(...)` / `= Query(...)` params with defaults.
- **Pragmatic** (complex routers, 3+ services): `c = Depends(get_container)` — `get_container()` returns typed `Container` (via lazy `from app.main import container`). Available from `app.routers._common`.
- Both patterns coexist; choose per handler. `deps.py` and `scheduler.py` keep `get_container()` (infrastructure, not routes).
- `# type: ignore` comments are NOT recognized by `ty`; suppress pre-existing type-gap diagnostics via pyproject.toml `[tool.ty.src.exclude]`.

## SERVICE BOUNDARY TESTING
- Every external-service boundary (Prefect, inference worker, embedding gRPC, LLM) must have a corresponding autouse mock fixture in `apps/api/tests/conftest.py`. Current fixtures: `_mock_ls_client`, `_mock_embedding_service`, `_mock_inference_worker`.
- Worker-side flow functions (`apps/api/app/flows/`, `apps/api/app/runtime/`) must have direct unit tests that call them as plain Python with a real test DB and mocked external services. See `test_training_runner.py` and `test_prediction_flow.py` for the established pattern.
- When adding a new external service integration, add the mock fixture FIRST, then write the flow/service code.
- Flow tasks that create their own `Container()` (e.g. `predict_job.py`) need `unittest.mock.patch` on the Container import in tests to share the app container's DB and storage. See `test_prediction_flow.py:_use_app_container()` for the pattern.

## NOTES
- No CI pipeline is configured. Conventions are enforced manually.
- Test coverage is backend-only; frontend, SDK, and worker are untested.
- Auth scaffolding exists but route protection is not wired — don't assume auth is enforced.

## DOCUMENTATION RULE
- After completing any non-trivial task, either:
  1) update the relevant docs in `docs/` and/or `AGENTS.md`, or
  2) explicitly ask the user whether they want docs updated in this change.

## TEST RULE
- Always run `make test` after modify code files and resolve any error.

## TYPE CHECK & LINT RULE
- After modifying Python code, run `uv run --directory apps/api pyright .` from repo root. Resolve all newly introduced diagnostics.
  - Use `# pyright: ignore[...]` or `# type: ignore[report...]` to suppress false positives from third-party stub issues.
  - If `pyright` is unavailable, use `uv tool run pyright apps/api`.
- After modifying Python code, run `ruff check apps/api` from repo root. Fix all newly introduced errors.
  - Run `ruff check apps/api --fix` for auto-fixable issues (unused imports, etc.).
  - If `ruff` is unavailable, use `uv tool run ruff check apps/api`.
- These commands replace the former "no linter" convention. Treat type/lint errors the same as test failures.

## DOCKER BUILD RULE
- After modifying backend or frontend code, verify Docker images build successfully:
  - **API**: `docker compose -f infra/compose/docker-compose.yaml build api`
  - **Web**: `docker compose -f infra/compose/docker-compose.yaml build web`
- Treat Docker build failures the same as test failures — fix before committing.
- If Docker is unavailable, run `make build-web` for frontend build verification as fallback.

## COMMIT RULE
- After completing code changes, remind the user to ask you to commit. Do not commit automatically — wait for the user to explicitly request it.

## LOCAL ENV RULE
- Keep the local dev environment newest after code or config changes.
- If changes require rebuilding assets, restarting dev servers, or recreating compose services to take effect, do it proactively without waiting for the user to ask.

## SMOKE TEST REMINDER

**IMPORTANT: Run smoke tests after making significant changes.**

Before considering a feature complete or a bug fixed:
1. Run `make test` to verify backend tests pass
2. Follow the verification steps: run `make test`, check auth/dataset/training flows in the browser, verify no console errors
3. At minimum, verify:
   - Auth flow (login/logout)
   - Dataset creation (LS integration)
   - Training job creation (SSE events)
   - No console errors in browser

Many features have broken silently during project evolution. Manual verification catches integration issues that unit tests miss.
