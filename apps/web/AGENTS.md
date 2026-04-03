# WEB KNOWLEDGE BASE

## OVERVIEW
Vue 3 + Vite frontend with Pinia, Vue Router, Vue Query, three route-level views, and a thin API client that currently assumes a local backend.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Boot sequence | `src/main.ts` + `index.html` | Mounts app, installs router/query/pinia |
| Top-level shell | `src/App.vue` | Navigation and `RouterView` |
| Routes | `src/router.ts` | `/datasets`, `/jobs`, `/predictions` |
| API + SSE | `src/api.ts` | Hardcoded `API_BASE`, EventSource helper |
| Shared types | `src/types.ts` + `src/contracts.ts` | Classification-first shapes |
| Dataset workflow | `src/views/DatasetsView.vue` | Create dataset, create default preset |
| Job workflow | `src/views/JobsView.vue` | Start job, consume SSE |
| Prediction view | `src/views/PredictionsView.vue` | Read-only listing today |

## CONVENTIONS
- Run with `pnpm` from this directory.
- Views fetch and mutate via Vue Query, then invalidate relevant queries.
- The UI is classification-first; task/model/result enums are intentionally narrow.
- Vite dev server is configured for port `5173`.

## ANTI-PATTERNS
- Don’t introduce more hardcoded backend URLs; `src/api.ts` already hardcodes `http://localhost:8000/api/v1`.
- Don’t assume auth headers exist; all fetches are currently unauthenticated.
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
- `PredictionsView.vue` only lists predictions; editing still requires backend/API work.
