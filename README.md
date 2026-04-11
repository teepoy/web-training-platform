# Online Finetune Platform

Monorepo for an online finetune platform with:

- Vue 3 frontend (`apps/web`)
- FastAPI backend (`apps/api`)
- Worker scaffold (`apps/worker`)
- Python SDK + CLI (`libs/python-sdk`)

Current implementation focuses on extensible interfaces, classification-first types,
swappable execution engines (local + Kubeflow mock), SSE job progress, webhook
notification sink as the default custom notification function, and async SQLAlchemy
2.0-backed persistence.

## Architecture highlights

- Extensible contracts for dataset/task/model/result with classification-first defaults.
- Swappable worker execution engine interface:
  - `LocalProcessEngine` for smoke tests
  - `KubeflowTrainingOperatorEngine` (mock adapter scaffold for distributed path)
- Real API persistence through async SQLAlchemy repository (SQLite smoke, Postgres-ready).
- Centralized config via OmegaConf and runtime wiring via dependency-injector.
- Lightweight in-app orchestration with SSE event streaming.
- Custom notification sink contract with webhook default implementation.
- Python SDK/CLI for status checks and simple agent-friendly operations.

## Quick start (local smoke)

Backend:

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
```

Run API tests:

```bash
cd apps/api
uv run --extra dev pytest
```

Frontend:

```bash
cd apps/web
pnpm install
pnpm dev
```

SDK CLI:

```bash
cd libs/python-sdk
uv run ftctl jobs status --job-id <job-id>
```

Or run module directly:

```bash
cd libs/python-sdk
uv run python -m ftsdk.cli jobs ls
```

## Notes

- Distributed training target is Kubeflow Training Operator.
- Local smoke uses async SQLite storage and local execution engine.
- Docker/K8s integration is scaffolded but intentionally optional.
- `pnpm` was not available in this environment, so frontend build was scaffolded but not executed.
- Prefect queue-based delegation design is documented in `docs/prefect-training-delegation.md`.
