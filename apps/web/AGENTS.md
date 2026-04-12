# WEB KNOWLEDGE BASE

## OVERVIEW
Vue 3 + Vite frontend with Pinia, Vue Router, Vue Query, three route-level views, and a thin API client that currently assumes a local backend.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Boot sequence | `src/main.ts` + `index.html` | Mounts app, installs router/query/pinia |
| Top-level shell | `src/App.vue` | Navigation and `RouterView` |
| Routes | `src/router.ts` | `/datasets`, `/jobs` |
| API + SSE | `src/api.ts` | Hardcoded `API_BASE`, EventSource helper |
| Shared types | `src/types.ts` + `src/contracts.ts` | Classification-first shapes |
| Dataset workflow | `src/views/DatasetsView.vue` | Create dataset, create default preset |
| Job workflow | `src/views/JobsView.vue` | Start job, consume SSE |
| Job detail metrics | `src/views/JobDetailView.vue` + `src/components/TrainingChart.vue` | Prefer `metrics` artifact JSON; fallback to SSE epoch/loss points if present |
| Schedule list | `src/views/SchedulesView.vue` | CRUD + create modal + pause/resume/delete |
| Schedule detail | `src/views/ScheduleDetailView.vue` | Config display, run history table, Trigger Now, Prefect deep link |
| Run log viewer | `src/components/RunLogViewer.vue` | Reusable; props: `runId: string`; shows level badges |
| Classify view | `src/views/ClassifyView.vue` | Annotation table + sidebar; uses TanStack Table/Virtual for virtualized infinite scroll |
| Classify sidebar | `src/components/classify/` | Widget registry, sidebar shell, widget components; see Classify Sidebar Architecture section |
| Agent chat drawer | `src/components/AgentChatDrawer.vue` | Floating chat UI for agent interaction |
| Agent widgets | `src/components/classify/widgets/` | GenericECharts, MarkdownLog, DataTable, MetricCards, SampleViewer, WidgetErrorBoundary |
| Agent composables | `src/composables/useAgentSurface.ts`, `src/composables/useAgentChat.ts` | Surface state management, chat SSE streaming |

## CLASSIFY SIDEBAR ARCHITECTURE
The classify page (`/datasets/:id/classify`) has a collapsible sidebar that renders dashboard widgets dynamically from a typed config.

| Piece | Location | Role |
|-------|----------|------|
| Widget registry & config | `src/components/classify/sidebarConfig.ts` | `SidebarPanelDescriptor` type, `WIDGET_COMPONENTS` map, `defaultPanels` array |
| Sidebar shell | `src/components/classify/ClassifySidebar.vue` | Renders panels from config; per-panel collapse; sidebar collapse; injects context via `provide` |
| Donut chart widget | `src/components/classify/widgets/AnnotationProgressWidget.vue` | Donut chart (annotated/remaining/drafts), metric grid, label breakdown |
| Data composable | `src/composables/useClassifyDashboard.ts` | Vue Query fetch of `/annotation-stats`, merged with local transient state (drafts, selection) |

**How to add a new widget:**
1. Create a `.vue` component in `src/components/classify/widgets/`.
2. Register it in `WIDGET_COMPONENTS` in `sidebarConfig.ts`.
3. Add a `SidebarPanelDescriptor` entry to `defaultPanels` (or a custom panels array) with the matching `widget` key and any `props`.

The composable result is injected into widgets via Vue `provide`/`inject` (key: `classifyDashboard`), so widgets don't need individual prop drilling for stats data.

## AGENT DISPLAY SURFACE ARCHITECTURE
The classify page includes an AI agent sidebar system and floating chat drawer:

| Piece | Location | Role |
|-------|----------|------|
| Chat drawer | `src/components/AgentChatDrawer.vue` | FAB-toggled floating panel; sends messages, renders SSE events |
| Surface composable | `src/composables/useAgentSurface.ts` | Manages agent panel state, refresh, import/export, live updates |
| Chat composable | `src/composables/useAgentChat.ts` | SSE streaming, conversation state, sidebar update emission |
| Widget error boundary | `src/components/classify/widgets/WidgetErrorBoundary.vue` | Catches widget render errors |
| Generic ECharts | `src/components/classify/widgets/GenericEChartsWidget.vue` | Any ECharts chart from inline option object |
| Markdown log | `src/components/classify/widgets/MarkdownLogWidget.vue` | Scrollable timestamped log entries |
| Data table | `src/components/classify/widgets/DataTableWidget.vue` | Sortable table from columns/rows |
| Metric cards | `src/components/classify/widgets/MetricCardsWidget.vue` | KPI card grid |
| Sample viewer | `src/components/classify/widgets/SampleViewerWidget.vue` | Sample image grid/list by ID |

**Agent panels** are merged with static dashboard panels via `mergePanels()` in `sidebarConfig.ts`. Agent panels are visually distinguished with a left border accent and "AI" badge.

**SSE pattern**: The agent chat uses `POST → SSE response stream` (not `EventSource`). The `streamAgentChat()` function in `api.ts` uses `fetch` + `ReadableStream` and parses SSE frames via an async generator. Event types: `agent-message`, `agent-action`, `sidebar-update`, `done`.

See `docs/agent-display-protocol.md` for the full protocol specification.

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
```

## GOTCHAS
- `JobsView.vue` appends raw SSE payload strings to local state; there is no reconnection or typed event parsing.
- There are no frontend tests or test scripts in `package.json`.
- Prediction review is now platform-prediction-first. The UI reads prediction rows from the API DB and only syncs selected prediction collections to Label Studio manually.
- `src/api.ts` may need to read the persisted token directly during startup, because Vue Query requests can fire before async auth validation finishes.
- Current runtimes usually persist aggregate metrics in a downloadable `metrics` artifact rather than streaming per-epoch `loss` events, so the job detail metrics card should not assume a line chart is always available.
