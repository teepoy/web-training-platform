# WEB KNOWLEDGE BASE

## OVERVIEW
Vue 3 + Vite frontend with Pinia, Vue Router, Vue Query, three route-level views, and a thin API client that currently assumes a local backend.

## WHERE TO LOOK
| Task                           | Location                                                                | Notes                                                                                        |
| ------------------------------ | ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Boot sequence                  | `src/main.ts` + `index.html`                                            | Mounts app, installs router/query/pinia                                                      |
| Top-level shell                | `src/App.vue`                                                           | Navigation and `RouterView`                                                                  |
| Routes                         | `src/router.ts`                                                         | `/datasets`, `/jobs`                                                                         |
| API + SSE                      | `src/api.ts`                                                            | Hardcoded `API_BASE`, EventSource helper                                                     |
| Shared types                   | `src/types.ts` + `src/contracts.ts`                                     | Classification-first shapes                                                                  |
| Dataset workflow               | `src/views/DatasetsView.vue`                                            | Import dataset via `PluginFlowModal`                                                         |
| Job workflow                   | `src/views/JobsView.vue`                                                | Start job, consume SSE                                                                       |
| Job detail metrics             | `src/views/JobDetailView.vue` + `../../libs/web-ui/src/components/training-chart/TrainingChart.vue` | Prefer `metrics` artifact JSON; fallback to SSE epoch/loss points if present                 |
| Schedule list                  | `src/views/SchedulesView.vue`                                           | CRUD + create modal + pause/resume/delete                                                    |
| Schedule detail                | `src/views/ScheduleDetailView.vue`                                      | Config display, run history table, Trigger Now, Prefect deep link                            |
| Run log viewer                 | `src/components/RunLogViewer.vue`                                       | Reusable; props: `runId: string`; shows level badges                                         |
| Classify view                  | `src/views/ClassifyView.vue`                                            | Unified annotate + train + predict + review workflow with shared grid/sidebar                |
| Classify sidebar               | `src/components/classify/`                                              | Widget registry, sidebar shell, widget components; see Classify Sidebar Architecture section |
| Agent chat drawer              | `../../libs/web-ui/src/components/agent-chat-drawer/AgentChatDrawer.vue` | Floating chat UI for agent interaction                                                       |
| Sidebar plugin implementations | `../../libs/web-ui/src/plugins/sidebar-*/`                              | First-party widget descriptors and `.vue` implementations                                    |
| Agent composables              | `src/composables/useAgentSurface.ts`, `src/composables/useAgentChat.ts` | Surface state management, chat SSE streaming                                                 |
| Shared browser core            | `../../libs/web-ui/src/components/sample-browser/SampleBrowser.vue`     | Shared virtualized browser core                                                              |
| Sidebar shell                  | `../../libs/web-ui/src/components/browser-sidebar/BrowserSidebar.vue`   | Neutral sidebar shell used by all surfaces                                                   |
| Browser preferences            | `src/stores/sampleBrowser.ts`                                           | Shared browser presentation preferences                                                      |
| Browser filter                 | `src/composables/useBrowserFilter.ts`                                   | Browser-scope item filter pipeline                                                           |
| Sidebar config                 | `src/components/classify/sidebarConfig.ts`                              | Panel registry; `defaultPanels`, `datasetPanels`, `previewPanels`                            |
| Datasets shim registry         | `src/views/datasets/registry.ts`                                        | Maps task types to specialized list shims                                                   |

## DATASETS SHIM ARCHITECTURE
The `DatasetsView.vue` uses a shim-based architecture to render specialized list views based on the task type of the datasets.

| Piece                 | Location                                     | Role                                                                        |
| --------------------- | -------------------------------------------- | --------------------------------------------------------------------------- |
| Host                  | `src/views/DatasetsView.vue`                 | Thin container; resolves shim via registry; provides data via adapter       |
| Registry              | `src/views/datasets/registry.ts`             | `DATASET_SHIM_REGISTRY` map and `resolveDatasetShim` logic                  |
| Shared UI package     | `../../libs/web-ui/src/`                     | `@platform/web-ui` components, plugin flow UI, and dataset-list helpers     |
| Classification Shim   | `src/views/datasets/shims/ClassificationDatasetsShim.vue` | Default list view for classification tasks                                  |
| VQA Shim              | `src/views/datasets/shims/VqaDatasetsShim.vue` | Specialized list view for VQA tasks                                         |

**How to add a new shim:**
1. Create `src/views/datasets/shims/<Name>DatasetsShim.vue`.
2. Register it in `src/views/datasets/registry.ts` under `DATASET_SHIM_REGISTRY`.
3. Update `resolveDatasetShim` in `registry.ts` to handle the new task type.

## CLASSIFY SIDEBAR ARCHITECTURE
The classify page (`/datasets/:id/classify`) is the one-stop classification workflow and has a collapsible sidebar that renders dashboard widgets dynamically from a typed config.

| Piece                      | Location                                                               | Role                                                                                                                                |
| -------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Panel config               | `src/components/classify/sidebarConfig.ts`                             | `SidebarPanelDescriptor` type, `defaultPanels`, `datasetPanels`, `previewPanels`                                                    |
| Sidebar shell              | `../../libs/web-ui/src/components/browser-sidebar/BrowserSidebar.vue`  | Neutral shell used by all surfaces; renders panels from injected resolver; injects context via `provide` |
| Classify sidebar wrapper   | `src/components/classify/ClassifySidebar.vue`                          | Thin wrapper around `BrowserSidebar.vue` for the classify view                                                                      |
| Donut chart widget         | `../../libs/web-ui/src/plugins/sidebar-annotation-progress/AnnotationProgressWidget.vue` | Donut chart (annotated/remaining/drafts), metric grid, label breakdown                                              |
| Interactive scatter widget | `../../libs/web-ui/src/plugins/sidebar-interactive-scatter/InteractiveScatterWidget.vue` | Metadata-driven scatter plot; emits linked selection/filter intents                                                 |
| Browser summary widget     | `../../libs/web-ui/src/plugins/sidebar-browser-summary/BrowserSummaryWidget.vue`         | Read-only item counts (showing X of Y) for filtered views                                                           |
| Sample preview widget      | `../../libs/web-ui/src/plugins/sidebar-sample-viewer/SampleViewerWidget.vue`             | Renders sidebar-linked sample previews                                                                              |
| Data composable            | `src/composables/useClassifyDashboard.ts`                              | Vue Query fetch of `/annotation-stats`                                                                                              |

**How to add a new widget:**
1. Create `../../libs/web-ui/src/plugins/sidebar-<name>/<Name>Widget.vue` for reusable first-party widgets, or `src/plugins/sidebar-<name>/<Name>Widget.vue` if the widget is app-specific.
2. Create the matching `index.ts`, export a named descriptor via `defineSidebarPlugin({...})`.
3. Export reusable descriptors from `../../libs/web-ui/src/index.ts`, then import and register the descriptor in `src/plugins/index.ts`.
4. Add a `SidebarPanelDescriptor` entry to `defaultPanels` (or a custom panels array) with the matching `component` key and any `props`.

The composable result is injected into widgets via Vue `provide`/`inject` (key: `classifyDashboard`), so widgets don't need individual prop drilling for stats data.

The classify view also provides the live grid items under `classify-grid-items` so linked widgets such as the sidebar scatter plot and sample preview can resolve selected sample IDs without a second API fetch.

The default sidebar now includes an `Interactive Scatter` panel when samples expose numeric `metadata.scatter_x` and `metadata.scatter_y`. Clicking a point updates the shared `classify-samples` collection state and the adjacent `Selected Samples` panel narrows to those sample IDs.

General row and collection interaction rules for future interactive table widgets are documented in `docs/protocols/table-widget-interaction-protocol.md`.

## AGENT DISPLAY SURFACE ARCHITECTURE
The classify page includes an AI agent sidebar system and floating chat drawer:

| Piece                 | Location                                                               | Role                                                                           |
| --------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Chat drawer           | `../../libs/web-ui/src/components/agent-chat-drawer/AgentChatDrawer.vue` | FAB-toggled floating panel; sends messages, renders SSE events                 |
| Surface composable    | `src/composables/useAgentSurface.ts`                                   | Manages agent panel state, refresh, import/export, live updates                |
| Chat composable       | `src/composables/useAgentChat.ts`                                      | SSE streaming, conversation state, sidebar update emission                     |
| Widget error boundary | `../../libs/web-ui/src/components/widget-error-boundary/WidgetErrorBoundary.vue` | Catches widget render errors                                                   |
| Generic ECharts       | `../../libs/web-ui/src/plugins/sidebar-echarts-generic/GenericEChartsWidget.vue`         | Any ECharts chart from inline option object                                    |
| Interactive scatter   | `../../libs/web-ui/src/plugins/sidebar-interactive-scatter/InteractiveScatterWidget.vue` | Metadata-driven sample scatter plot with linked sidebar selection              |
| Markdown log          | `../../libs/web-ui/src/plugins/sidebar-markdown-log/MarkdownLogWidget.vue`               | Scrollable timestamped log entries                                             |
| Data table            | `../../libs/web-ui/src/plugins/sidebar-data-table/DataTableWidget.vue`                   | Sortable table from columns/rows                                               |
| Metric cards          | `../../libs/web-ui/src/plugins/sidebar-metric-cards/MetricCardsWidget.vue`               | KPI card grid                                                                  |
| Sample viewer         | `../../libs/web-ui/src/plugins/sidebar-sample-viewer/SampleViewerWidget.vue`             | Sample image grid/list by ID; can resolve classify-grid-backed sample previews |

**Agent panels** are merged with static dashboard panels via `mergePanels()` in `sidebarConfig.ts`. Agent panels are visually distinguished with a left border accent and "AI" badge.

**SSE pattern**: The agent chat uses `POST → SSE response stream` (not `EventSource`). The `streamAgentChat()` function in `api.ts` uses `fetch` + `ReadableStream` and parses SSE frames via an async generator. Event types: `agent-message`, `agent-action`, `sidebar-update`, `done`.

See `docs/protocols/agent-display-protocol.md` for the full protocol specification.

## CONVENTIONS
- Run with `pnpm` from this directory.
- Views fetch and mutate via Vue Query, then invalidate relevant queries.
- The UI is classification-first; task/model/result enums are intentionally narrow.
- Vite dev server is configured for port `5173`.
- Auth state is bootstrapped synchronously from `localStorage` in `src/main.ts` before route views mount, so refreshes keep the current session until the JWT expires.
- Frontend auth uses the JWT `exp` claim to treat tokens as valid for their backend-configured lifetime; the default backend expiry is 60 minutes.

## ANTI-PATTERNS
- Don’t introduce more hardcoded backend URLs; `src/api.ts` already hardcodes `http://localhost:8000/api/v1`.
- Don’t defer auth hydration until after route views mount; early protected requests can otherwise race, return `401`, and incorrectly clear a still-valid token.
- Don’t treat placeholder preset values as real training defaults; `createPreset()` is demo scaffolding.
- Don’t expand UI state separately from `src/types.ts` without aligning the API client payloads.

## COMMANDS
```bash
pnpm install
pnpm dev
pnpm build
pnpm preview
pnpm run test:widgets   # Vitest: widget, composable, store specs
pnpm run test:e2e       # Playwright: E2E browser flows
```

## GOTCHAS
- `JobsView.vue` appends raw SSE payload strings to local state; there is no reconnection or typed event parsing.
- Vitest widget tests and Playwright E2E tests are available via `pnpm run test:widgets` and `pnpm run test:e2e`.
- Prediction review now lives inside `ClassifyView.vue` (route: `/datasets/:id/classify`) as review mode. It reads prediction rows from the API DB and only syncs selected prediction collections to Label Studio manually.
- `src/api.ts` may need to read the persisted token directly during startup, because Vue Query requests can fire before async auth validation finishes.
- Current runtimes usually persist aggregate metrics in a downloadable `metrics` artifact rather than streaming per-epoch `loss` events, so the job detail metrics card should not assume a line chart is always available.
