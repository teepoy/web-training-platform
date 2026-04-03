# PROJECT KNOWLEDGE BASE

**Generated:** 2026-03-31 Asia/Taipei
**Commit:** not-a-git-repo
**Branch:** not-a-git-repo

## OVERVIEW
Monorepo for an online finetune platform: FastAPI API, Vue 3 web app, Python SDK/CLI, and local/k8s deployment manifests. Runtime behavior is config-driven: local smoke uses SQLite + local execution, dev mode targets Postgres + MinIO + Kubeflow.

## STRUCTURE
```text
./
├── apps/api/           # API runtime, config profiles, migrations, tests
├── apps/web/           # Vue app shell, routes, API client, views
├── apps/worker/        # placeholder worker package
├── libs/python-sdk/    # ftctl CLI, FinetuneClient, agent wrappers
├── infra/k8s/          # minikube/kubeflow manifests
├── infra/compose/      # docker compose smoke stack
└── docs/               # architecture and endpoint notes
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Start API / inspect routes | `apps/api/app/main.py` | Includes SSE events and export endpoints |
| Change runtime wiring | `apps/api/app/container.py` | DI selects DB, storage, engine, notifications |
| Tune config profiles | `apps/api/config/*.yaml` | `APP_CONFIG_PROFILE` chooses file |
| Change DB schema | `apps/api/alembic/` + `apps/api/app/db/models.py` | Alembic exists; local-smoke may auto-create |
| Adjust frontend API calls | `apps/web/src/api.ts` | Hardcoded localhost base URL |
| Add frontend screens | `apps/web/src/router.ts` + `apps/web/src/views/` | Three current routes only |
| Use CLI / agent wrappers | `libs/python-sdk/ftsdk/cli.py` + `agent_tools.py` | `ftctl` is the console entry |
| Deploy locally | `infra/compose/docker-compose.yaml` | Postgres + MinIO + API |
| Deploy to minikube | `infra/k8s/` | Requires `pytorchjobs.kubeflow.org` CRD |

## CODE MAP
| Symbol / Surface | Type | Location | Role |
|------------------|------|----------|------|
| `app` | FastAPI app | `apps/api/app/main.py` | HTTP/SSE entrypoint |
| `Container` | DI container | `apps/api/app/container.py` | Selects engine/storage/repository |
| `TrainingOrchestrator` | service | `apps/api/app/services/orchestrator.py` | Persists jobs, emits notifications |
| `KubeflowTrainingOperatorEngine` | engine | `apps/api/app/services/engines.py` | Distributed execution adapter |
| `createApp(...).mount()` | frontend boot | `apps/web/src/main.ts` | Vue entrypoint |
| `router` | router | `apps/web/src/router.ts` | `/datasets`, `/jobs`, `/predictions` |
| `api` / `buildJobEventSource` | frontend client | `apps/web/src/api.ts` | REST + SSE consumer |
| `FinetuneClient` | SDK client | `libs/python-sdk/ftsdk/client.py` | Sync HTTP wrapper |
| `app` (Typer) | CLI | `libs/python-sdk/ftsdk/cli.py` | `ftctl` commands |

## CONVENTIONS
- Python tasks run through `uv run ...`; frontend tasks run through `pnpm`.
- Root uses `uv` workspace for Python packages and `pnpm` only for `apps/web`.
- `APP_CONFIG_PROFILE` defaults to `local-smoke`; tests force it in `apps/api/tests/conftest.py`.
- `execution.engine`: `local` or `kubeflow`; `storage.kind`: `memory` or `minio`.
- K8s namespace is `finetune`; secrets/config are injected via `finetune-config` and `finetune-secrets`.

## ANTI-PATTERNS (THIS PROJECT)
- Don’t assume production infra is live when `kubeflow`/`minio` is configured; several code paths still fall back or use smoke-friendly defaults.
- Don’t hardcode new hostnames casually; frontend SDK already hardcode localhost and that is a known fragility.
- Don’t treat `apps/worker` as implemented runtime logic; it is still a placeholder package.
- Don’t rely on local-smoke auto-create behavior for real deployments; use Alembic migrations.
- Don’t reuse example secrets (`postgres`, `minioadmin`, `replace-me`) outside smoke environments.

## UNIQUE STYLES
- API keeps route handlers thin and pushes runtime branching into `Container` + services.
- Job progress is exposed via SSE, not websockets.
- Export/artifact flows are dataset-oriented and ML-pipeline friendly, even when the backing storage is still smoke-grade.

## COMMANDS

**Prefer `make` targets from the root `Makefile` over raw commands.** All common operations are wrapped:

| What | Command | Notes |
|------|---------|-------|
| Install everything | `make install` | uv sync + pnpm install |
| Install Python only | `make install-api` | uv sync |
| Install frontend only | `make install-web` | pnpm --filter web install |
| Start API + Web | `make dev` | Parallel, Ctrl-C stops both |
| Start API only | `make dev-api` | Port override: `API_PORT=9000` |
| Start Web only | `make dev-web` | Port override: `WEB_PORT=3000` |
| Run all tests | `make test` | Currently API-only |
| Run API tests | `make test-api` | Extra args: `ARGS="-v -k test_health"` |
| Build frontend | `make build-web` | vue-tsc + vite build |
| Run Alembic migrate | `make db-migrate` | upgrade head |
| Create Alembic revision | `make db-revision MSG="add users"` | autogenerate |
| SDK CLI | `make ftctl ARGS="jobs ls"` | Wraps ftctl |
| Compose up | `make up` | Postgres + MinIO + API |
| Compose down | `make down` | |
| Compose logs | `make logs ARGS="api"` | Follows logs |
| K8s apply | `make k8s-apply` | kubectl apply -k |
| Clean caches | `make clean` | __pycache__, node_modules, dist |
| Show all targets | `make help` | |

Raw commands (for reference or when Make is unavailable):
```bash
# API
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
uv run alembic upgrade head
uv run --extra dev pytest

# Web
cd apps/web
pnpm install
pnpm dev
pnpm build

# SDK
cd libs/python-sdk
uv run ftctl jobs status --job-id <job-id>
uv run python -m ftsdk.cli jobs ls

# Compose
docker compose -f infra/compose/docker-compose.yaml up -d

# K8s
kubectl apply -k infra/k8s
kubectl apply -f infra/k8s/secret.yaml
kubectl get crd pytorchjobs.kubeflow.org
```

## NOTES
- This directory is not a git repo in the current environment, so git-derived metadata is unavailable.
- Current automated coverage is backend-only smoke tests; frontend, SDK, worker, and infra paths are mostly untested.
- PyTorchJob smoke was validated on minikube, but only after the operator CRD and image availability were fixed.
