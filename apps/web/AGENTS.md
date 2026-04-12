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
- Prediction CRUD has been removed from both backend and frontend. Predictions are read from Label Studio only.
- `src/api.ts` may need to read the persisted token directly during startup, because Vue Query requests can fire before async auth validation finishes.
- Current runtimes usually persist aggregate metrics in a downloadable `metrics` artifact rather than streaming per-epoch `loss` events, so the job detail metrics card should not assume a line chart is always available.
