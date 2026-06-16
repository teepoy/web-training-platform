# Project Agent Guide

This file is the root working guide for agents in this repository. Keep it concise. Stable product and architecture decisions belong in `CORE_DESIGNS.md`; detailed subsystem notes belong in the nearest subdirectory `AGENTS.md`.

If this file conflicts with `CORE_DESIGNS.md`, treat `CORE_DESIGNS.md` as authoritative and surface the conflict instead of silently choosing a side.

## Project Shape

Monorepo for an online finetune platform:

| Area | Path | Role |
| --- | --- | --- |
| API | `apps/api` | FastAPI control plane, metadata, auth, jobs, SSE, persistence |
| Web | `apps/web` | Vue 3 + Vite frontend, widgets, dataset/job/schedule UI |
| ML | `libs/ml` | Torch-first model implementations and training/prediction logic |
| Platform runtime | `libs/platform-runtime` | Shared contracts, SDK/CLI, runtime clients |
| SDK shim | `libs/python-sdk` | Compatibility re-exports; new code should prefer `platform_runtime` |
| Infra | `infra` | Compose and Kubernetes manifests |
| Docs | `docs` | Architecture, guides, protocols |

Runtime topology:

```text
apps/api -> Prefect flows co-located under apps/api -> executable trainer/predictor registries
apps/api -> libs/platform-runtime
```

## Core Rules

- Read `CORE_DESIGNS.md` before non-trivial architecture, runtime, storage, dataset, auth, widget, or API contract work.
- Keep route handlers thin; push persistence and business logic into services/repositories.
- Do not add executable training/prediction logic to `apps/api`.
- Do not import FastAPI/API internals from `libs/ml`.
- Do not put module-private domain models in `libs/platform-runtime`; keep them in the owning module.
- Do not change ORM schema without an Alembic migration.
- Do not infer storage behavior from `dataset_type`; use `storage_mode` explicitly.
- Do not couple platform `Sample.id` to upstream/domain IDs such as SC defect IDs.
- Do not assume auth is enforced just because auth scaffolding exists.
- Do not add hardcoded backend URLs; existing hardcodes are known debt.
- Unless explicitly requested or required by `CORE_DESIGNS.md`, do not add fallback behavior, implicit limits, assumptions, or defaults; surface the missing decision/error so the underlying problem can be discovered.
- Do not create new YAML preset mechanisms; use the registry/descriptor mechanisms described below.
- Do not delete Alembic migrations unless the database state is intentionally reset too.

## Commands

Prefer `make` targets from the repository root.

| Task | Command |
| --- | --- |
| Install dependencies | `make install` |
| Start compose dev stack | `make up-dev` |
| Start API only | `make dev-api` |
| Start web only | `make dev-web` |
| Run backend tests + OpenAPI sync | `make test` |
| Run one API test/filter | `make test-api ARGS="-k test_name"` |
| Run frontend unit tests | `make test-web` |
| Run frontend E2E tests | `make test-e2e` |
| Full local verification | `make full-test` |
| Build web | `make build-web` |
| Generate OpenAPI spec + artifacts | `make generate` |
| Apply migrations | `make db-migrate` |
| Create migration | `make db-revision MSG="describe change"` |
| Start compose backend only | `make up-dev --scale web=0` |
| Start compose backend + local web | `make updev` |
| Stop compose | `make down` |
| Run CLI | `make ftctl ARGS="jobs ls"` |

Seed dev data with `make seed-dev`. Run smoke tests with `make smoke-tests`.

## Verification

- After modifying code, run the narrowest relevant tests first, then the required broader checks before handing off.
- For backend Python changes, run `ruff check apps/api`, `uv run --directory apps/api pyright .`, and `make test`.
- For frontend changes, run `make test-web` and `make build-web`; run `make test-e2e` when route/user-flow behavior changes.
- For API contract changes, update route/schema code, run `make generate` to re-export `openapi/openapi.yaml` and regenerate all artifacts, then let `make test` run the OpenAPI sync check.
- For Docker-relevant backend/frontend changes, verify the relevant compose image build when feasible: `docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml build api` or `docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml build web`.
- If a required check cannot be run, state why and what remains unverified.

## Code Style

Python:

- Start new Python files with `from __future__ import annotations`.
- Use `X | None`, not `Optional[X]`.
- Annotate function signatures and returns.
- Keep imports ordered stdlib, third-party, local.
- Repository methods are async and use explicit session scopes.
- Prefer typed Protocol dependencies over `Any` containers or global service lookups.

TypeScript/Vue:

- Keep `strict: true`; do not suppress type errors with `as any`, `@ts-ignore`, or `@ts-expect-error`.
- Use Vue 3 Composition API and `<script setup lang="ts">`.
- Use Vue Query for server state and Pinia for app state.
- Use Naive UI and existing shared components unless a task explicitly requires new visual design.
- Import widget contracts from `@/shared/widgets/sdk`.

## Extension Patterns

Backend:

- Views use `@view` and are imported by the API registration barrel.
- Trainer/predictor metadata belongs to the API catalog; executable runtime callables belong to worker/inference runtime registries.
- Dataset type integration must go through the dataset registry and per-type adapters, not shared hardcoded switch statements.
- Dataset view sample APIs should resolve dataset type -> dataset class -> view adapter dynamically, not add one hardcoded route per view.
- Dataset storage/operator code owns `db_full`, sparse shard, Parquet, manifest, and locator persistence details; domain import modules should produce generic dataset samples/import streams.
- Prediction/training flows should execute via the runtime registry callable, not `container.gpu_worker` or hardcoded direct ML implementation calls.
- Backend extension routers live under `apps/api/app/routers/<name>/router.py` and are listed in the extension router registry.

Frontend:

- Register widgets/importers/exporters/preview launchers/agent skills through descriptors and app-level registration.
- Do not register widgets directly in `main.ts`, page views, or sidebar shells.
- Lazy-load widget components in descriptors when possible.
- Use `FlowModal` and `FlowTypeSelector` for import/export/preview selection flows.
- For page design-only iteration, use the `page-design-contract` skill and keep `*.design.vue` files out of production routes.

## OpenAPI Contract

`openapi/openapi.yaml` is the transport contract source of truth, re-exported from FastAPI routes by `make generate`.

When changing request/response DTOs:

1. Update route/schema DTO code.
2. Run `make generate` (or the narrow generation target) to re-export `openapi/openapi.yaml` and regenerate backend/frontend artifacts.
3. Update UI usage.
4. Run `make test` to verify OpenAPI sync.

Do not hand-write duplicate transport DTOs that already exist in generated OpenAPI artifacts. Internal helper models and UI-only models are fine. Do not manually edit `openapi/openapi.yaml` — it is overwritten by `make generate`.

## Local Knowledge

- Root details: this file and `CORE_DESIGNS.md`.
- API specifics: `apps/api/AGENTS.md`.
- Web specifics: `apps/web/AGENTS.md`.
- SDK shim specifics: `libs/python-sdk/AGENTS.md`.
- Infra specifics: `infra/AGENTS.md`.

If local `AGENTS.md` files conflict with `CORE_DESIGNS.md`, follow `CORE_DESIGNS.md` and report the conflict.

## Git And Docs

- Never revert or overwrite user changes unless explicitly asked.
- Do not revert unrelated "wrong file write" changes; parallel agents may be working in unrelated domains, and these are often false alarms.
- Do not commit unless the user explicitly asks.
- After non-trivial code changes, update relevant docs or ask whether docs should be updated.
- Before committing, inspect status, diff, and recent log; show the `CORE_DESIGNS.md` diff if that file changed.
