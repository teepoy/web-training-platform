# PROJECT KNOWLEDGE BASE

## OVERVIEW
Monorepo for an online finetune platform: FastAPI API, Vue 3 web app, Python SDK/CLI, and local/k8s deployment manifests. Runtime behavior is config-driven: local smoke uses SQLite + local execution, dev mode targets Postgres + MinIO + Kubeflow. Every dataset has a mandatory Label Studio project (`ls_project_id` is NOT NULL).

## STRUCTURE
```text
./
├── apps/api/           # FastAPI backend, config profiles, Alembic migrations, tests
├── apps/api/app/flows/ # Prefect flow definitions and serve entrypoint
├── apps/web/           # Vue 3 SPA — routes, API client, views
├── apps/worker/        # placeholder (not implemented)
├── libs/python-sdk/    # ftctl CLI, FinetuneClient, agent wrappers
├── infra/k8s/          # minikube/kubeflow manifests
├── infra/compose/      # docker compose smoke stack
└── docs/               # architecture and endpoint notes
```

## COMMANDS

**Prefer `make` targets over raw commands.** Run from repo root.

| What | Command | Notes |
|------|---------|-------|
| Install all | `make install` | uv sync + pnpm install |
| Start API + Web | `make dev` | Parallel; Ctrl-C stops both |
| Start API only | `make dev-api` | `API_PORT=9000` to override |
| Start Web only | `make dev-web` | `WEB_PORT=3000` to override |
| **Run all tests** | `make test` | API tests only (no frontend tests) |
| **Run single test** | `make test-api ARGS="-k test_health"` | pytest `-k` filter |
| **Run test file** | `make test-api ARGS="tests/test_vqa_runtime.py -v"` | Verbose single file |
| Build frontend | `make build-web` | vue-tsc + vite build |
| Alembic migrate | `make db-migrate` | `upgrade head` |
| New migration | `make db-revision MSG="add column"` | autogenerate |
| Reset app data | `make reset-app-data` | Drops and recreates app tables in the configured DB |
| SDK CLI | `make ftctl ARGS="jobs ls"` | Wraps `ftctl` |
| Seed ImageNet mock | `make seed-imagenet-mock` | Health-checks `API_URL` first; creates dataset `ImageNet-1K Mock` with 1000 offline synthetic samples |
| Seed ImageNet POC | `make seed-imagenet-poc` | Health-checks `API_URL` first; creates dataset `ImageNet-1K Real` with 64 real samples for prediction proof-of-concept |
| Seed ImageNet full | `make seed-imagenet-full` | Health-checks `API_URL` first; refreshes dataset `ImageNet-1K Real` via the full real ImageNet seeding path |
| Batch dev smoke | `make smoke-dev-batch` | Run after `make seed-imagenet-mock` or `make seed-imagenet-poc`; verifies seeded batch prediction availability |
| Compose up/down | `make up` / `make down` | Postgres + MinIO + API |

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
| Task | Location |
|------|----------|
| API routes | `apps/api/app/main.py` |
| Runtime DI wiring | `apps/api/app/container.py` |
| Config profiles | `apps/api/config/*.yaml` (`APP_CONFIG_PROFILE`) |
| DB schema changes | `apps/api/app/db/models.py` + `apps/api/alembic/` |
| Frontend API calls | `apps/web/src/api.ts` |
| Frontend views | `apps/web/src/views/` + `apps/web/src/router.ts` |
| Prefect flows | `apps/api/app/flows/` |
| Schedule service | `apps/api/app/services/scheduler.py` |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `app` | FastAPI | `apps/api/app/main.py` | HTTP/SSE entrypoint |
| `Container` | DI | `apps/api/app/container.py` | Wires engine/storage/repo |
| `TrainingOrchestrator` | service | `apps/api/app/services/orchestrator.py` | Job persistence + notifications |
| `SchedulerService` | service | `apps/api/app/services/scheduler.py` | Prefect REST client |
| `router` | Vue Router | `apps/web/src/router.ts` | `/datasets`, `/jobs`, `/schedules` |
| `FinetuneClient` | SDK | `libs/python-sdk/ftsdk/client.py` | Sync HTTP wrapper |

## ANTI-PATTERNS — DO NOT

### Architecture
- Don't add route-level persistence; keep handlers thin, push logic into services/repository.
- Don't change ORM models without a corresponding Alembic migration.
- `apps/worker` is the Prefect training-worker package; keep API, training workers, and inference worker separated in dev/prod.
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

## NOTES
- No linter, formatter, or CI pipeline is configured. Conventions are enforced manually.
- Test coverage is backend-only; frontend, SDK, and worker are untested.
- Auth scaffolding exists but route protection is not wired — don't assume auth is enforced.

## DOCUMENTATION RULE
- After completing any non-trivial task, either:
  1) update the relevant docs in `docs/` and/or `AGENTS.md`, or
  2) explicitly ask the user whether they want docs updated in this change.

## TEST RULE
- Always run `make test` after modify code files and resolve any error.

## LOCAL ENV RULE
- Keep the local dev environment newest after code or config changes.
- If changes require rebuilding assets, restarting dev servers, or recreating compose services to take effect, do it proactively without waiting for the user to ask.

## SMOKE TEST REMINDER

**IMPORTANT: Run smoke tests after making significant changes.**

Before considering a feature complete or a bug fixed:
1. Run `make test` to verify backend tests pass
2. Follow the smoke test checklist in [`docs/SMOKE_TEST.md`](docs/SMOKE_TEST.md)
3. At minimum, verify:
   - Auth flow (login/logout)
   - Dataset creation (LS integration)
   - Training job creation (SSE events)
   - No console errors in browser

Many features have broken silently during project evolution. Manual verification catches integration issues that unit tests miss.
