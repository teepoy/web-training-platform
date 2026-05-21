## Port from libs/web-data/src/client/apiClient.ts → libs/web-ui/src/api/client.ts
- Exact 1:1 port. No interface changes. `configureTransport()` shape matches `apps/web/src/main.ts` call site (getToken, getOrgId, onAuthError, apiBase, authEnabled).
- `req<T>()`, `ApiError`, `uploadFile`, `getApiBase()`, `getAuthToken()` all ported verbatim.
- Module-level private state (`_getToken`, `_getOrgId`, `_onAuthError`, `_apiBase`, `_authEnabled`) preserved.

## Stub domain modules
- All 8 domain modules created with `export {}` placeholder — TypeScript-compliant empty modules.
- Barrel `index.ts` uses both named exports for client and wildcard exports for domain stubs.
- `libs/web-ui/src/index.ts` updated: added `export * from "./api"` at top.

## LSP diagnostics
- Zero diagnostics across all 10 files in `api/` directory and the parent `index.ts`.

## Dataset classification scaffold
- Created `apps/api/app/modules/dataset_classification/` with the standard DDD subdir layout (`domain/`, `presets/`, `runtime/`, `mocks/`, `data/`).
- Kept each `__init__.py` minimal with only `from __future__ import annotations` so the package imports cleanly without adding behavior.
- Import verification succeeded with `uv run python -c "import app.modules.dataset_classification; print('ok')"`.
