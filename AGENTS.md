# PROJECT KNOWLEDGE BASE

## OVERVIEW
Monorepo for an online finetune platform: FastAPI API, Vue 3 web app, Python SDK/CLI, and local/k8s deployment manifests. Runtime behavior is config-driven: local smoke uses SQLite + local execution, dev mode targets Postgres + MinIO + Kubeflow. Every dataset has a mandatory Label Studio project (`ls_project_id` is NOT NULL).

## STRUCTURE
```text
./
├── apps/api/           # FastAPI backend, config profiles, Alembic migrations, tests
├── apps/api/app/flows/ # Prefect flow definitions and serve entrypoint
├── apps/api/app/plugins/  # Backend plugin routes — explicit registry.py
├── apps/web/           # Vue 3 SPA — routes, API client, views
├── apps/web/.storybook/ # Storybook config + mock helpers
├── libs/web-ui/src/components/sample-browser/ # Shared virtualized browser core
├── apps/web/src/core/  # Singleton plugin registry
├── apps/web/src/plugins/  # Frontend plugin descriptors (one subdirectory per plugin)
├── apps/worker/        # Prefect flow-worker package (training/prediction/embedding)
├── libs/plugin-sdk/    # @platform/plugin-sdk — TypeScript plugin contract types & factories
├── libs/web-ui/        # @platform/web-ui — shared Vue/Naive UI components and composables
├── libs/python-sdk/    # ftctl CLI, FinetuneClient, agent wrappers
├── libs/mcp-server/    # MCP server — exposes platform tools to external agents
├── libs/mcp-server/finetune_mcp/plugins/  # MCP tool plugins — auto-discovered by loader.py
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

| Plugin SDK tests | `pnpm test:plugin-sdk` | vitest in `libs/plugin-sdk/` (20 tests) |
| Web UI package tests | `pnpm test:web-ui` | vitest in `libs/web-ui/` |
| Plugin integration tests | `pnpm test:plugins` | vitest for plugin registrations |
| Build plugin SDK | `pnpm build:plugin-sdk` | tsup build of `@platform/plugin-sdk` |
| **Storybook** | `pnpm storybook` | Plugin component stories on port 6006 |
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
| Agent display protocol    | `docs/protocols/agent-display-protocol.md`                                   |                                                                     |
| MCP server                | `libs/mcp-server/`                                                           |                                                                     |
| Preview launch form       | `apps/web/src/views/PreviewLaunchView.vue`                                   |                                                                     |
| Preview workspace         | `apps/web/src/views/PreviewClassifyView.vue`                                 |                                                                     |
| Preview item drawer       | `libs/web-ui/src/components/preview-item-drawer/PreviewItemDrawer.vue`       |                                                                     |
| Preview loader composable | `apps/web/src/composables/usePreviewLoader.ts`                               |                                                                     |
| Preview domain models     | `apps/api/app/domain/preview.py`                                             |                                                                     |
| Preview service           | `apps/api/app/services/preview_service.py`                                   | Session lifecycle, item pagination, persist handoff                 |
| Preview TTL store         | `apps/api/app/services/preview_store.py`                                     | In-memory TTL session store                                         |
| Upstream adapter          | `apps/api/app/services/preview_upstream.py`                                  | 50-item mock upstream; replace with real adapter                    |
| Shared browser core       | `libs/web-ui/src/components/sample-browser/`                                 | Shared virtualized browser core                                     |
| Sidebar shell             | `libs/web-ui/src/components/browser-sidebar/BrowserSidebar.vue`              | Shared sidebar shell with injected plugin resolver                  |
| Browser preferences       | `apps/web/src/stores/sampleBrowser.ts`                                       | Presentation persistence (layout, thumbSize)                        |
| Browser filter            | `apps/web/src/composables/useBrowserFilter.ts`                               | Browser-scope item filter pipeline                                  |
| Browser architecture      | `docs/architecture/sample-browser.md`                                        | Shared browser architecture doc                                     |
| Datasets architecture     | `docs/architecture/datasets-shim-architecture.md`                            | Specialized list view shim architecture                             |
| Plugin SDK contracts      | `libs/plugin-sdk/src/`                                                       | TypeScript plugin type definitions and factories                    |
| Web UI package            | `libs/web-ui/src/`                                                           | Shared Vue/Naive UI components and dataset-list helpers             |
| Plugin SDK templates      | `libs/plugin-sdk/src/templates/`                                             | Copy-paste starter templates for new plugins                        |
| Frontend plugin registry  | `apps/web/src/core/registry.ts`                                              | Singleton `pluginRegistry` instance                                 |
| Frontend plugin barrel    | `apps/web/src/plugins/index.ts`                                              | Explicit registration of all plugins before app mount               |
| Shared sidebar plugins    | `libs/web-ui/src/plugins/sidebar-*/`                                         | First-party sidebar widget plugin descriptors and components        |
| Frontend import plugins   | `apps/web/src/plugins/import-*/`                                             | Import flow plugins (e.g. `import-manual`, `import-dataset-manual`) |
| Frontend export plugins   | `apps/web/src/plugins/export-*/`                                             | Export flow plugins (e.g. `export-preview`, `export-persist`)       |
| Frontend preview plugins  | `apps/web/src/plugins/preview-*/`                                            | Preview launcher plugins (e.g. `preview-upstream`)                  |
| Plugin flow modal         | `libs/web-ui/src/components/plugin-flow-modal/PluginFlowModal.vue`           | 2-step modal: select type, then execute component                   |
| Plugin type selector      | `libs/web-ui/src/components/plugin-type-selector/PluginTypeSelector.vue`     | Card grid for selecting a plugin type                               |
| Backend plugin registry   | `apps/api/app/plugins/registry.py`                                           | Explicit list of backend plugin routers                             |
| Backend plugin routes     | `apps/api/app/plugins/*/router.py`                                           | One FastAPI router per backend plugin                               |
| MCP plugin loader         | `libs/mcp-server/finetune_mcp/plugins/loader.py`                             | Auto-discovers modules with `TOOLS` + `dispatch()`                  |
| Plugin extension guide    | `docs/guides/plugin-extension-guide.md`                                      | Step-by-step guide for all 4 plugin types                           |
| Widget contract shim      | `apps/web/src/components/classify/widgetContract.ts`                         | Re-exports SDK types; kept for backward compatibility               |
| Storybook config          | `apps/web/.storybook/`                                                       | Storybook main.ts, preview.ts, mock helpers                         |
| Plugin stories            | `apps/web/src/plugins/**/*.stories.ts` and `libs/web-ui/src/**/*.stories.ts` | Story files for app plugins and shared web-ui components            |

## CODE MAP
| Symbol                  | Type       | Location                                                                 | Role                                                         |
| ----------------------- | ---------- | ------------------------------------------------------------------------ | ------------------------------------------------------------ |
| `app`                   | FastAPI    | `apps/api/app/main.py`                                                   | HTTP/SSE entrypoint                                          |
| `Container`             | DI         | `apps/api/app/container.py`                                              | Wires engine/storage/repo                                    |
| `TrainingOrchestrator`  | service    | `apps/api/app/services/orchestrator.py`                                  | Job persistence + notifications                              |
| `SchedulerService`      | service    | `apps/api/app/services/scheduler.py`                                     | Prefect REST client                                          |
| `SurfaceStore`          | service    | `apps/api/app/agent/surface_store.py`                                    | In-memory agent panel state                                  |
| `SessionStore`          | service    | `apps/api/app/agent/session_store.py`                                    | In-memory conversation persistence (TTL-based)               |
| `ClassifyAgent`         | service    | `apps/api/app/agent/runtime.py`                                          | LLM tool-calling loop for classify sidebar                   |
| `GlobalAgent`           | service    | `apps/api/app/agent/global_runtime.py`                                   | Platform-wide LLM agent (read/write/sidebar)                 |
| `useGlobalAgent`        | composable | `apps/web/src/composables/useGlobalAgent.ts`                             | Global agent chat + panel injection                          |
| `PlatformClient`        | MCP        | `libs/mcp-server/finetune_mcp/client.py`                                 | HTTP client for MCP server                                   |
| `router`                | Vue Router | `apps/web/src/router.ts`                                                 | `/datasets`, `/jobs`, `/schedules`                           |
| `FinetuneClient`        | SDK        | `libs/python-sdk/ftsdk/client.py`                                        | Sync HTTP wrapper                                            |
| `PreviewService`        | service    | `apps/api/app/services/preview_service.py`                               | Session lifecycle, item pagination, persist handoff          |
| `PreviewStore`          | service    | `apps/api/app/services/preview_store.py`                                 | In-memory TTL session store                                  |
| `MockUpstreamAdapter`   | service    | `apps/api/app/services/preview_upstream.py`                              | 50-item mock upstream; replace with real adapter             |
| `usePreviewLoader`      | composable | `apps/web/src/composables/usePreviewLoader.ts`                           | Cursor-based preview item loader                             |
| `PreviewClassifyView`   | view       | `apps/web/src/views/PreviewClassifyView.vue`                             | Preview workspace with grid + persist flow                   |
| `pluginRegistry`        | singleton  | `apps/web/src/core/registry.ts`                                          | Runtime registry of all frontend plugins                     |
| `createPluginRegistry`  | factory    | `libs/plugin-sdk/src/registry.ts`                                        | Creates the `PluginRegistry` instance                        |
| `useDatasetListSurface` | composable | `libs/web-ui/src/datasets/surface.ts`                                    | Shared dataset list normalization, permissions, and UI props |
| `buildDatasetColumns`   | function   | `libs/web-ui/src/datasets/surface.ts`                                    | Shared dataset table column/action factory                   |
| `defineSidebarPlugin`   | factory    | `libs/plugin-sdk/src/sidebar.ts`                                         | Declares a sidebar widget plugin                             |
| `defineImportPlugin`    | factory    | `libs/plugin-sdk/src/importer.ts`                                        | Declares an import flow plugin                               |
| `defineExportPlugin`    | factory    | `libs/plugin-sdk/src/exporter.ts`                                        | Declares an export flow plugin                               |
| `defineAgentSkill`      | factory    | `libs/plugin-sdk/src/agent.ts`                                           | Declares an agent skill plugin                               |
| `definePreviewPlugin`   | factory    | `libs/plugin-sdk/src/preview.ts`                                         | Declares a preview launcher plugin                           |
| `PluginFlowModal`       | component  | `libs/web-ui/src/components/plugin-flow-modal/PluginFlowModal.vue`       | 2-step modal: select type, then execute component            |
| `PluginTypeSelector`    | component  | `libs/web-ui/src/components/plugin-type-selector/PluginTypeSelector.vue` | Card grid for selecting a plugin type                        |
| `PLUGIN_ROUTERS`        | list       | `apps/api/app/plugins/registry.py`                                       | Explicit list of all backend plugin routers                  |
| `load_plugin_tools`     | function   | `libs/mcp-server/finetune_mcp/plugins/loader.py`                         | Returns merged MCP tool list from all plugin modules         |
| `providePluginContext`  | decorator  | `apps/web/.storybook/mocks/pluginContext.ts`                             | Storybook decorator providing sidebar-widget injection keys  |
| `mockImportProps`       | factory    | `apps/web/.storybook/mocks/pluginProps.ts`                               | Storybook mock factory for import plugin props               |
| `mockExportProps`       | factory    | `apps/web/.storybook/mocks/pluginProps.ts`                               | Storybook mock factory for export plugin props               |
| `mockPreviewProps`      | factory    | `apps/web/.storybook/mocks/pluginProps.ts`                               | Storybook mock factory for preview launcher props            |

## ANTI-PATTERNS — DO NOT

### Architecture
- Don't add route-level persistence; keep handlers thin, push logic into services/repository.
- Don't change ORM models without a corresponding Alembic migration.
- `apps/worker` is the Prefect flow-worker package; keep API, flow workers, and the inference service separated in dev/prod.
- Don't assume Kubeflow/MinIO are live; smoke paths degrade gracefully.
- Don't hardcode new backend URLs; the existing `localhost:8000` hardcode is a known debt.
- Don't reuse example secrets (`postgres`, `minioadmin`) outside smoke.

### Label Studio (LS)
- Dataset = LS project. Every dataset has a mandatory `ls_project_id` (NOT NULL).
- `ls_project_url` is computed at response time from config — never stored.
- Platform predictions live in the API DB. Label Studio is only a temporary manual-annotation surface for synced prediction collections.
- Don't use `cfg.label_studio.enabled` — it was removed. LS is always required; check `cfg.label_studio.url`.
- Don't re-add the "link to LS" manual flow — it was intentionally removed.
- VQA predictions are stored as Label Studio `textarea` results, not classification choices.
- Prediction collection sync to LS is one-way and manual. Do not treat LS prediction IDs as durable platform provenance.

### Plugin Architecture
- Don't register plugins directly in `main.ts`, `BrowserSidebar.vue`, or `DatasetDetailView.vue` — always add to `apps/web/src/plugins/index.ts`.
- Each plugin `index.ts` exports a named descriptor; the barrel file does the registration. Don't call `pluginRegistry.register*()` inside plugin modules.
- Don't import widget `.vue` files statically in plugin `index.ts` — use `() => import(...)` (async) so the registry resolves components lazily.
- Don't bypass `pluginRegistry` for sidebar rendering — app surfaces pass `pluginRegistry.getSidebarComponent(key)` into the shared `BrowserSidebar.vue` resolver prop.
- Don't add new widget cases to `sidebarConfig.ts` — `SIDEBAR_WIDGETS` and `WIDGET_COMPONENTS` were intentionally removed; use `defineSidebarPlugin` instead.
- Don't import from `widgetContract.ts` for new plugin code — import from `@platform/plugin-sdk` directly; the shim is kept only for backward compatibility.
- Don't add hardcoded import/export/preview modals to views — use `PluginFlowModal` and `PluginTypeSelector` for the 2-step plugin selection flow.
- Backend plugin routes must live under `apps/api/app/plugins/<name>/router.py`; they must be added to `PLUGIN_ROUTERS` in `apps/api/app/plugins/registry.py` — don't manually import them in `main.py`.
- MCP plugin modules must export `TOOLS: list[dict]` and `dispatch(name, args)` — the loader merges these automatically.

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
- Presets are engineer-managed YAML (`apps/api/presets/`) and read-only via API/UI.
- Seed scripts must resolve bundled presets from the read-only preset registry; they must not POST new training presets.
- Active DSPy runtime path is VQA (`dspy-vqa-v1`); do not add placeholder DSPy trainer/predictor configs.
- See `apps/api/AGENTS.md` and `apps/web/AGENTS.md` for sub-project details.
- Plugin SDK (`@platform/plugin-sdk`) is a workspace TypeScript package in `libs/plugin-sdk/`. It is path-aliased in `apps/web/tsconfig.json` (`@platform/plugin-sdk → ../../libs/plugin-sdk/src/index.ts`) and built with `tsup`.
- To add a reusable first-party sidebar widget: create `libs/web-ui/src/plugins/sidebar-<name>/index.ts`, export a named descriptor via `defineSidebarPlugin({...})`, export it from `libs/web-ui/src/index.ts`, then import and register it in `apps/web/src/plugins/index.ts`. App-specific sidebar widgets can still live under `apps/web/src/plugins/sidebar-<name>/`. See `docs/guides/plugin-extension-guide.md`.
- To add a new importer: create `apps/web/src/plugins/import-<name>/index.ts`, export a named descriptor via `defineImportPlugin({...})`, then register in `apps/web/src/plugins/index.ts`. Importers use `PluginFlowModal` with `kind="import"` for a 2-step type-selection flow.
- To add a new exporter: create `apps/web/src/plugins/export-<name>/index.ts`, export a named descriptor via `defineExportPlugin({...})`, then register in `apps/web/src/plugins/index.ts`. Exporters use `PluginFlowModal` with `kind="export"`.
- To add a new preview launcher: create `apps/web/src/plugins/preview-<name>/index.ts`, export a named descriptor via `definePreviewPlugin({...})`, then register in `apps/web/src/plugins/index.ts`. Preview launchers use `PluginTypeSelector` for a 2-step flow.
- To add a new backend plugin route: create `apps/api/app/plugins/<name>/router.py` with an `APIRouter` named `router`, then add it to `PLUGIN_ROUTERS` in `apps/api/app/plugins/registry.py`.

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
- After modifying Python code, run `ty check apps/api` from repo root. Resolve all newly introduced diagnostics.
  - Use `# type: ignore` (not bracket syntax) to suppress false positives from third-party stub issues.
  - If `ty` is unavailable, use `uv tool run ty check apps/api`.
- After modifying Python code, run `ruff check apps/api` from repo root. Fix all newly introduced errors.
  - Run `ruff check apps/api --fix` for auto-fixable issues (unused imports, etc.).
  - If `ruff` is unavailable, use `uv tool run ruff check apps/api`.
- These commands replace the former "no linter" convention. Treat type/lint errors the same as test failures.

## COMMIT RULE
- After completing code changes, remind the user to ask you to commit. Do not commit automatically — wait for the user to explicitly request it.

## LOCAL ENV RULE
- Keep the local dev environment newest after code or config changes.
- If changes require rebuilding assets, restarting dev servers, or recreating compose services to take effect, do it proactively without waiting for the user to ask.

## SMOKE TEST REMINDER

**IMPORTANT: Run smoke tests after making significant changes.**

Before considering a feature complete or a bug fixed:
1. Run `make test` to verify backend tests pass
2. Follow the smoke test checklist in [`docs/guides/smoke-test.md`](docs/guides/smoke-test.md)
3. At minimum, verify:
   - Auth flow (login/logout)
   - Dataset creation (LS integration)
   - Training job creation (SSE events)
   - No console errors in browser

Many features have broken silently during project evolution. Manual verification catches integration issues that unit tests miss.
