# WEB KNOWLEDGE BASE

## OVERVIEW

Vue 3 + Vite frontend with Pinia, Vue Router, Vue Query, domain modules under `src/features/datasets/presentation/dataset-types/`, app bootstrap under `src/app/`, and shared UI/API/widget SDK code under `src/shared/`.

## WHERE TO LOOK

| Task                       | Location                                                           | Notes                                                                                           |
| -------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Boot sequence              | `src/app/main.ts` + `index.html`                                   | Mounts app, installs router/query/pinia                                                         |
| Top-level shell            | `src/app/App.vue`                                                  | Navigation and `RouterView`                                                                     |
| Routes                     | `src/app/router.ts`                                                | `/datasets`, `/jobs`, `/datasets/:id` (dataset detail with view type as page-internal dropdown) |
| Dataset detail             | `src/features/datasets/router.ts`                                  | `/datasets/:id` — renders `DatasetDetailView`; view type is a page-internal state, not a route  |
| API + SSE                  | `src/shared/api/`                                                  | API clients, generated/openapi-backed types, SSE helpers                                        |
| API auth transport         | `src/shared/api/client.ts` + `src/shared/api/orval-fetcher.ts`     | `configureTransport`, Orval fetch mutator, Bearer/org headers, image query auth helpers         |
| Image URL resolution       | `src/shared/utils/image-adapters.ts`                               | `resolveImageUri(s)`, storage URI proxying, fallback placeholder, auth query wrapping           |
| Shared types               | `src/types.ts` + `src/contracts.ts`                                | Classification-first shapes                                                                     |
| App registrations          | `src/app/registrations.ts`                                         | Singleton widget registry and explicit descriptor registration                                  |
| Domain modules             | `src/features/datasets/presentation/dataset-types/`                | Per-type dataset modules (classification, detection, vqa)                                       |
| Dataset workflow           | `src/features/datasets/presentation/pages/DatasetListView.vue`     | Import dataset via shared `FlowModal`                                                           |
| Job workflow               | `src/features/training/presentation/pages/TrainingJobsView.vue`    | Start job, consume SSE                                                                          |
| Job detail metrics         | `src/features/training/presentation/pages/JobDetailView.vue`       | Prefer `metrics` artifact JSON; fallback to SSE epoch/loss points if present                    |
| Schedule list              | `src/features/schedules/presentation/pages/SchedulesView.vue`      | CRUD + create modal + pause/resume/delete                                                       |
| Schedule detail            | `src/features/schedules/presentation/pages/ScheduleDetailView.vue` | Config display, run history table, Trigger Now, Prefect deep link                               |
| Run log viewer             | `src/shared/components/run-log-viewer/RunLogViewer.vue`            | Reusable; props: `runId: string`; shows level badges                                            |
| Classify view              | `src/features/classify/presentation/pages/ClassifyView.vue`        | Unified annotate + train + predict + review workflow with shared grid/sidebar                   |
| Classify sidebar           | `src/features/classify/presentation/components/`                   | Widget config, sidebar shell wrapper; see Classify Sidebar Architecture section                 |
| Agent chat drawer          | `src/features/agent/presentation/components/AgentChatDrawer.vue`   | Floating chat UI for agent interaction                                                          |
| Widget implementations     | `src/shared/components/<name>/`                                    | Widget .vue source files — general-purpose shared components                                    |
| Widget descriptor wrappers | `src/shared/components/<name>/index.ts`                            | Widget descriptors co-located with .vue components; each widget directory is self-contained     |
| Widget SDK contracts       | `src/shared/widgets/sdk/`                                          | `defineDashboardWidget`, importer/exporter/preview/agent contracts, descriptor registry         |
| Shared browser core        | `src/shared/components/sample-browser/SampleBrowser.vue`           | Shared virtualized browser core                                                                 |
| Sidebar shell              | `src/shared/components/browser-sidebar/BrowserSidebar.vue`         | Neutral sidebar shell (delegates panels to PanelHost)                                           |
| Panel host                 | `src/shared/components/panel-host/PanelHost.vue`                   | Standalone panel renderer — usable anywhere in a page                                           |
| Page-level provider        | `src/shared/composables/usePagePanels.ts`                          | Provides BROWSER_DASHBOARD_KEY + SIDEBAR_WIDGET_INTERACTION_KEY at page root                    |
| Wafer helpers              | `src/shared/composables/useWaferHelpers.ts`                        | Shared wafer coordinate utilities                                                               |
| Browser preferences        | `src/stores/sampleBrowser.ts`                                      | Shared browser presentation preferences                                                         |
| Browser filter             | `src/shared/composables/useBrowserFilter.ts`                       | Browser-scope item filter pipeline                                                              |
| Sidebar config             | `src/features/classify/presentation/components/sidebarConfig.ts`   | Panel registry; `defaultPanels`, `datasetPanels`, `previewPanels`                               |
| Datasets shim registry     | `src/features/datasets/presentation/pages/registry.ts`             | Maps task types to specialized list shims                                                       |
| SC feature pages           | `src/features/sc/`                                                 | Preview/reclassify pages, SC route module, protobuf adapters, canonical SC image helpers        |

## DATASETS SHIM ARCHITECTURE

The `DatasetListView.vue` uses a shim-based architecture to render specialized list views based on the task type of the datasets.

| Piece                     | Location                                                                             | Role                                                                                       |
| ------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| Host                      | `src/features/datasets/presentation/pages/DatasetListView.vue`                       | Thin container; resolves shim via registry; provides data via adapter                      |
| Registry                  | `src/features/datasets/presentation/pages/registry.ts`                               | `DATASET_SHIM_REGISTRY` map and `resolveDatasetShim` logic                                 |
| Shared UI/API/widget code | `src/shared/`                                                                        | Shared components, flow UI, dataset-list helpers, composables, API clients, and widget SDK |
| Classification Shim       | `src/features/datasets/presentation/dataset-types/classification/views/ListShim.vue` | Specialized list view for classification tasks                                             |
| Detection Shim            | `src/features/datasets/presentation/dataset-types/detection/views/ListShim.vue`      | Specialized list view for detection tasks                                                  |
| VQA Shim                  | `src/features/datasets/presentation/dataset-types/vqa/views/ListShim.vue`            | Specialized list view for VQA tasks                                                        |

**How to add a new shim:**

1. Create `src/features/datasets/presentation/dataset-types/<type>/views/ListShim.vue`.
2. Register it in `src/app/registrations.ts` by importing the module's `registrations.ts` (which calls `registerDatasetSchema`).
3. Export the shim descriptor from the module's `registrations.ts`.

## DATASET TYPE MODULES (FE)

Each dataset type is isolated in `src/features/datasets/presentation/dataset-types/<type>/`:

- `views/ListShim.vue`: Specialized table/list view component
- `views/schema.ts`: Frontend schema descriptor (auto-registers on import)
- `registrations.ts`: Descriptor exports for the global registry
- `views/ListShim.stories.ts`: Storybook examples for the shim component

Modules are registered in `src/app/registrations.ts`.

**View type rendering**: Each view type registered via `views/schema.ts` (e.g. `labeled_image_v1`, `image_input_v1`) determines how samples are rendered inside the dataset detail page. The parent `DatasetDetailView` passes the selected `viewType` as a prop to `DatasetViewPage`, which resolves the view component via `resolveViewComponent()` in `src/features/datasets/presentation/pages/schema-registry.ts`. The backend serves view-specific sample data at `GET /datasets/{dataset_id}/views/{view_type}/samples`.

## IMAGE URLS AND AUTH

Browser-native image consumers (`<img>`, Naive image previews, virtualized blink tables) do not send the API client's `Authorization` or `X-Organization-ID` headers. Any protected image URL must therefore include auth context in query parameters. Use the shared helpers; do not hand-build image proxy URLs in components.

| Image source                             | Use                                                                                         | Do not use                                      |
| ---------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `s3://...` / `memory://...` storage URIs | `resolveImageUri()` / `resolveImageUris()` from `src/shared/utils/image-adapters.ts`        | Raw `/api/v1/images/resolve?uri=...` strings    |
| SC patch images                          | `scPatchUrl()` from `src/features/sc/domain/models.ts`                                      | Raw `patchImageUrl()` as an `<img src>`         |
| SC review images                         | `scReviewUrl()` from `src/features/sc/domain/models.ts`                                     | Raw `reviewImageUrl()` as an `<img src>`        |
| SC blink table bundles                   | `buildScBlinkImageUrls()` and pass the result into `ScBlinkTable` via `imageUrlsByDefectId` | Fallback URL construction inside `ScBlinkTable` |

`patchImageUrl()` and `reviewImageUrl()` intentionally return raw backend paths for tests and composition. They do **not** append `token` or `org_id`; using them directly in the DOM will fail when auth is enabled. Imported SC dataset views should prefer dataset-owned image refs from `/api/v1/samples/{sample_id}/images/{image_id}?dataset_id=...` over upstream inspection-time image paths.

## API AND ORVAL TRANSPORT

- `src/shared/api/client.ts` owns the hand-written request helper (`req`), `configureTransport()`, token lookup, org lookup, and `withAuthQueryParams()`.
- `src/shared/api/orval-fetcher.ts` is the custom mutator for generated Orval hooks. Bootstrap must configure both the hand-written transport and the Orval fetcher before route views mount.
- Generated Orval hooks and models are the preferred typed API surface for Vue Query. Do not hand-write DTOs that already exist in generated OpenAPI artifacts.
- Use Bearer + org headers for normal `fetch`/Orval API calls; use `withAuthQueryParams()` only for browser-native URLs that cannot carry headers.

## SC FRONTEND CONVENTIONS

- SC pages live under `src/features/sc/`; the SC preview route is `/sc/preview`, and imported dataset views are rendered by the dataset detail page `/datasets/:id` with the `patch_image_v1` or `review_image_v1` view type selected via the internal dropdown.
- SC-specific image helpers and transport-facing domain helpers live in `src/features/sc/domain/models.ts`.
- `ScBlinkTable` is a consumer only: it receives already-authenticated image URLs through `imageUrlsByDefectId`. Do not add raw URL fallback construction to the table.
- SC Preview/Reclassify data access goes through `ScWorkbenchDataSource`. The production adapter uses scoped HTTP SQL, Arrow IPC Stream responses, and SSE invalidations; page components do not own server table state.
- Keep map and table selection in workbench state and express it as query constraints. Do not add selection marker columns or server-side update calls.
- Transfer Arrow buffers to map/decoder workers rather than converting 300,000-row results to JavaScript row objects.

## CLASSIFY SIDEBAR ARCHITECTURE

The classify page (`/datasets/:id/classify`) is the one-stop classification workflow and has a collapsible sidebar that renders dashboard widgets dynamically from a typed config.

| Piece                      | Location                                                                 | Role                                                                                                                    |
| -------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| Panel config               | `src/components/classify/sidebarConfig.ts`                               | `SidebarPanelDescriptor` type, `defaultPanels`, `datasetPanels`, `previewPanels`                                        |
| Sidebar shell              | `src/shared/components/browser-sidebar/BrowserSidebar.vue`               | Neutral shell used by all surfaces; delegates panel rendering to PanelHost; injects context via `provide`               |
| Panel host                 | `src/shared/components/panel-host/PanelHost.vue`                         | Standalone renderer — renders `SidebarPanelDescriptor[]` anywhere; used internally by BrowserSidebar                    |
| Page-level provider        | `src/shared/composables/usePagePanels.ts`                                | Provides `BROWSER_DASHBOARD_KEY` + `SIDEBAR_WIDGET_INTERACTION_KEY` at page root so widgets outside sidebar share state |
| Wafer helpers              | `src/shared/composables/useWaferHelpers.ts`                              | `normalizeWaferPoint()`, `injectWaferPanelData()`, `metadataNumber()`, `metadataString()`                               |
| Classify sidebar wrapper   | `src/components/classify/ClassifySidebar.vue`                            | Thin wrapper around `BrowserSidebar.vue` for the classify view                                                          |
| Donut chart widget         | `src/shared/components/annotation-progress/AnnotationProgressWidget.vue` | Donut chart (annotated/remaining/drafts), metric grid, label breakdown                                                  |
| Interactive scatter widget | `src/shared/components/interactive-scatter/InteractiveScatterWidget.vue` | Metadata-driven scatter plot; emits linked selection/filter intents                                                     |
| Browser summary widget     | `src/shared/components/browser-summary/BrowserSummaryWidget.vue`         | Read-only item counts (showing X of Y) for filtered views                                                               |
| Sample preview widget      | `src/shared/components/sample-viewer/SampleViewerWidget.vue`             | Renders sidebar-linked sample previews — can also resolve classify-grid-backed sample previews                          |
| Data composable            | `src/composables/useClassifyDashboard.ts`                                | Vue Query fetch of `/annotation-stats`                                                                                  |

**How to add a new widget:**

1. Create the .vue component in `src/shared/components/<name>/<Name>Widget.vue` for reusable first-party widgets, or in the owning `src/features/` directory if it is domain-specific.
2. Create a descriptor in the same component directory via `defineDashboardWidget({...})` imported from `@/shared/widgets/sdk`. The component directory contains both the .vue source and its descriptor, self-contained.
3. Export reusable descriptors from `src/shared/index.ts`, then import and register the descriptor in `src/app/registrations.ts`.
4. Add a `SidebarPanelDescriptor` entry to `defaultPanels` (or a custom panels array) with the matching `component` key and any `props`.
5. (Optional) Use `<PanelHost :panels="myPanels" :componentResolver="..." />` to render the same panel descriptors anywhere in the page — a toolbar, a drawer, or a floating panel — sharing state with sidebar widgets via `usePagePanels`.

The composable result is injected into widgets via Vue `provide`/`inject` (key: `classifyDashboard`), so widgets don't need individual prop drilling for stats data.

The classify view also provides the live grid items under `classify-grid-items` so linked widgets such as the sidebar scatter plot and sample preview can resolve selected sample IDs without a second API fetch.

The default sidebar now includes an `Interactive Scatter` panel when samples expose numeric `metadata.scatter_x` and `metadata.scatter_y`. Clicking a point updates the shared `classify-samples` collection state and the adjacent `Selected Samples` panel narrows to those sample IDs.

General row and collection interaction rules for future interactive table widgets are documented in `docs/protocols/table-widget-interaction-protocol.md`.

## AGENT DISPLAY SURFACE ARCHITECTURE

The classify page includes an AI agent sidebar system and floating chat drawer:

| Piece                 | Location                                                                 | Role                                                                           |
| --------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------ |
| Chat drawer           | `src/shared/components/agent-chat-drawer/AgentChatDrawer.vue`            | FAB-toggled floating panel; sends messages, renders SSE events                 |
| Core composable       | `src/shared/composables/useAgentCore.ts`                                 | Transport-agnostic: SSE frame iteration, message accumulation, abort, status   |
| App adapter           | `src/features/agent/useAgentAdapter.ts`                                  | Route-derived context builder, auth session wiring, provide/inject panels      |
| Widget error boundary | `src/shared/components/widget-error-boundary/WidgetErrorBoundary.vue`    | Catches widget render errors                                                   |
| Generic ECharts       | `src/shared/components/echarts-generic/GenericEChartsWidget.vue`         | Any ECharts chart from inline option object                                    |
| Interactive scatter   | `src/shared/components/interactive-scatter/InteractiveScatterWidget.vue` | Metadata-driven sample scatter plot with linked sidebar selection              |
| Markdown log          | `src/shared/components/markdown-log/MarkdownLogWidget.vue`               | Scrollable timestamped log entries                                             |
| Data table            | `src/shared/components/data-table/DataTableWidget.vue`                   | Sortable table from columns/rows                                               |
| Metric cards          | `src/shared/components/metric-cards/MetricCardsWidget.vue`               | KPI card grid                                                                  |
| Sample viewer         | `src/shared/components/sample-viewer/SampleViewerWidget.vue`             | Sample image grid/list by ID; can resolve classify-grid-backed sample previews |

**Agent panels** are merged with static dashboard panels via `mergePanels()` in `sidebarConfig.ts`. Agent panels are visually distinguished with a left border accent and "AI" badge.

**SSE pattern**: The agent chat uses `POST → SSE response stream` (not `EventSource`). `useAgentCore` iterates parsed SSE frames from an async generator factory; `useAgentAdapter` provides the factory with route-context and auth-session. `streamGlobalAgentChat()` in `@platform/web-data/agent` handles `fetch` + `ReadableStream`. Event types: `agent-message`, `agent-action`, `sidebar-update`, `done`.

**Agent QA refactor guard.** Any change to an app-shell/layout branch, route-context construction, auth bootstrap, the Agent adapter, or POST-SSE transport must preserve and run `e2e/specs/agent/agent-chat.spec.ts`. Keep the check outcome-based: the global entry is reachable, the request carries the current route/domain context, a configured backend produces a real SSE response, and an unconfigured backend fails visibly. Never weaken it with a silent catch, conditional pass, arbitrary sleep, or selector coupled only to styling; update the component's stable test IDs, POM, spec, and this contract together when the Agent surface is intentionally redesigned.

See `docs/protocols/agent-display-protocol.md` for the full protocol specification.

## CONVENTIONS

- Run with `pnpm` from this directory.
- Views fetch and mutate via Vue Query, then invalidate relevant queries.
- The UI is classification-first; task/model/result enums are intentionally narrow.
- Vite dev server is configured for port `5173`.
- Chrome 108 is the minimum browser target. Keep the Vite legacy, dev transform, dependency optimization, and Lightning CSS targets aligned through `TARGET_CHROME_VERSION`; CSS using runtime custom properties still needs an explicit fallback when it cannot be lowered statically.
- Auth state is bootstrapped synchronously from `localStorage` in `src/app/main.ts` before route views mount, so refreshes keep the current session until the JWT expires.
- Frontend auth uses the JWT `exp` claim to treat tokens as valid for their backend-configured lifetime; the default backend expiry is 60 minutes.

## ANTI-PATTERNS

- Don’t introduce more hardcoded backend URLs; the shared API client already assumes `http://localhost:8000/api/v1`.
- Don’t defer auth hydration until after route views mount; early protected requests can otherwise race, return `401`, and incorrectly clear a still-valid token.
- Don’t pass raw `patchImageUrl()` or `reviewImageUrl()` results to image elements. Use `scPatchUrl()`, `scReviewUrl()`, `buildScBlinkImageUrls()`, `resolveImageUri()`, or `resolveImageUris()` so browser image requests carry auth context.
- Don’t treat placeholder preset values as real training defaults; `createPreset()` is demo scaffolding.
- Don’t expand UI state separately from `src/types.ts` without aligning the API client payloads.

## COMMANDS

```bash
pnpm install
pnpm dev
pnpm build
pnpm preview
pnpm test:unit          # Vitest: unit tests (src/**/*.spec.ts)
pnpm test:e2e           # Playwright: @mock mode (no backend needed)
pnpm test:e2e:live      # Playwright: @live mode (requires make up)
pnpm test:e2e:smoke     # Playwright: @smoke only (fast, mock mode)
```

## TEST CONVENTIONS

**Directory layout.** Tests split across two roots: `e2e/` (all Playwright source, configuration, and ignored run artifacts) and `src/testing/` (Vitest unit-test helpers). The `e2e/` tree is organized into `fixtures/`, `seed/`, `mocks/handlers/`, `mocks/factories/`, `pages/` (POMs), active `specs/`, excluded `legacy/`, `helpers/`, and `scripts/`; Playwright writes auth state, reports, traces, screenshots, videos, and test results only below `e2e/.artifacts/`. The `src/testing/` tree provides `mountWithProviders`, MSW server/handlers/factories, and test setup. Active spec files live in `e2e/specs/<feature>/` for Playwright and co-located `src/**/*.spec.ts` for Vitest.

**Test tags.** Every active Playwright spec under `e2e/specs/` must be tagged with exactly one of `@mock` (mocked backend, no external services) or `@live` (real backend via `make up-dev`). Additional tags: `@smoke` for lightweight critical-path checks (always `@mock`, sub-30s per test, total profile ≤5 min), and `@slow` for tests exceeding 15 seconds. The `mock` Playwright project runs `@mock` specs; the serial `live` command runs `@live` specs and writes its generated auth state below `e2e/.artifacts/`. Files below `e2e/legacy/` are intentionally not collected and retain `@legacy` until migrated to current contracts.

**Timeout policy.** Shared UI, project, backend-operation, and SC workflow budgets live in `e2e/timeouts.ts`. Ordinary mock/live tests use the project defaults; only tests that start a known long-running import, training, prediction, or full workflow may call `test.setTimeout()` with the matching named budget. Do not add anonymous multi-minute literals to specs or POMs. Environment-specific overrides use the documented `PLAYWRIGHT_*_TIMEOUT_MS` variables.

**POM rules.** Page Object Models go in `e2e/pages/`, extend `BasePage`, and implement `waitForLoaded()`. POMs encapsulate locators and actions but never call `expect()` directly (return `Locator` instead). Selectors must use `data-testid`, `getByRole`, `getByPlaceholder`, or `getByTestId`. No CSS class selectors or brittle DOM traversal. Each POM mirrors one page or major component under `src/features/`.

**Seed layer.** `e2e/seed/` helpers interact with a live backend using the orval-typed API client. Raw `fetch('/api/v1/...')` calls are forbidden in seed helpers. Factories in `e2e/mocks/factories/` also use orval-generated model types for type-safe test data.

**MSW for unit tests.** Unit tests use `src/testing/msw/` handlers to intercept API calls at the network level. The MSW server (`src/testing/msw/server.ts`) starts in `src/testing/setup.ts` before each test suite and resets handlers between tests. Component tests should wire MSW handlers rather than using `vi.mock('@/shared/api/...')` to stub API modules.

**mountWithProviders.** Import from `@/testing` to mount Vue components with all platform providers pre-installed: Pinia (fresh store), Vue Router (memory history), Naive UI plugin, and Vue Query (retries disabled). Returns `{ wrapper, queryClient, router, pinia }`. Supports `props`, `routes`/`initialRoute`, and pre-seeded `pinia`/`queryClient` overrides. See `src/testing/README.md` for examples.

**Running tests.** All from `apps/web/`:

- `pnpm test:unit` — Vitest (runs `src/**/*.spec.ts`)
- `pnpm test:e2e` — Playwright mock mode (vite dev server auto-started)
- `pnpm test:e2e:live` — Playwright live mode (requires `make up` from repo root for backend services)
- `pnpm test:e2e:smoke` — smoke specs only (fast, mock mode)
- `pnpm test` — runs both `test:unit` and `test:e2e`

**CI notes.** No `.github/workflows/` test definitions exist yet in this repo. When CI is added, `@mock` tests should run on every PR since they work without backend services. `@live` tests require a running backend stack and are inherently slower, so they should run on merge to main or on a schedule. See `apps/web/e2e/README.md` for the full test infrastructure contract.

## GOTCHAS

- `JobsView.vue` appends raw SSE payload strings to local state; there is no reconnection or typed event parsing.
- Vitest unit tests and Playwright E2E tests are available via `pnpm test:unit` and `pnpm test:e2e`.
- Prediction review now lives inside `ClassifyView.vue` (route: `/datasets/:id/classify`) as review mode. It reads prediction rows from the API DB and only syncs selected prediction collections to Label Studio manually.
- The shared API client may need to read the persisted token directly during startup, because Vue Query requests can fire before async auth validation finishes.
- Current runtimes usually persist aggregate metrics in a downloadable `metrics` artifact rather than streaming per-epoch `loss` events, so the job detail metrics card should not assume a line chart is always available.
