# Architecture

## Monorepo layout

- `apps/api`: FastAPI backend with extensible domain interfaces and in-app orchestration
- `apps/web`: Vue 3 frontend for datasets and jobs
- `apps/worker`: worker scaffold for training/inference code paths
- `libs/python-sdk`: Python SDK and CLI for automation and agent tool-calling

## Core design choices

- Task type starts with `classification` and supports future expansion through typed enums/contracts.
- Execution engine is swappable via config and DI (`local` and `kubeflow` adapters).
- Realtime training progress uses SSE endpoint.
- Notification delivery is a custom sink interface with webhook default.
- Artifacts/export format is ML-pipeline friendly with HF-datasets-compatible payload shape.
- Persistence is implemented with SQLAlchemy 2.0 async repositories.

## Distributed training

- Production target: Kubeflow Training Operator (`PyTorchJob`) via `KubeflowTrainingOperatorEngine`.
- Local smoke target: `LocalProcessEngine` with deterministic mock event stream.
- Kubeflow adapter now contains real submit/status/delete client calls and falls back to mock flow when cluster client is unavailable.

## Artifact storage

- Storage is selected by config (`memory` or `minio`).
- `ArtifactService` persists exported dataset payloads and job artifacts to storage, then records metadata/checksum in DB.

## Config + DI

- OmegaConf files in `apps/api/config/` hold centralized settings.
- `dependency-injector` container wires engines, notification sink, orchestrator, and feature services.
- `local-smoke` config uses SQLite async, while `dev` config is Postgres async-ready.
