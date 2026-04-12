# Architecture

## Monorepo layout

- `apps/api`: FastAPI backend with extensible domain interfaces and orchestration APIs
- `apps/web`: Vue 3 frontend for datasets and jobs
- `apps/worker`: worker image/package used for delegated Prefect training workers
- `apps/inference`: long-lived inference worker for prediction and embedding execution
- `libs/python-sdk`: Python SDK and CLI for automation and agent tool-calling

## Core design choices

- Task type starts with `classification` and supports future expansion through typed enums/contracts.
- Execution in supported runtime environments is delegated: Prefect orchestrates training and batch jobs, while dedicated workers execute them.
- Realtime training progress uses SSE endpoint.
- Notification delivery is a custom sink interface with webhook default.
- Artifacts/export format is ML-pipeline friendly with HF-datasets-compatible payload shape.
- Persistence is implemented with SQLAlchemy 2.0 async repositories.

## Distributed training

- Production target: Kubeflow Training Operator (`PyTorchJob`) via `KubeflowTrainingOperatorEngine`.
- Training is routed through Prefect-owned workers in dev/prod.
- Kubeflow remains an adapter path, but dev/prod no longer rely on API-local execution fallbacks.

## Artifact storage

- Storage is selected by config, but `memory` is test-only. Dev/prod use MinIO/S3-compatible storage.
- `ArtifactService` persists exported dataset payloads and job artifacts to storage, then records metadata/checksum in DB.

## Prediction storage and review

- Per-sample predictions are persisted in the API database as platform-owned rows.
- Batch prediction jobs store aggregate progress in `prediction_jobs.summary_json`, while detailed results are read from the prediction table.
- Label Studio is not the prediction source of truth. It is used as a temporary manual-annotation surface when a user syncs a selected prediction collection into the dataset's existing LS project.
- Review provenance points at platform prediction IDs, not LS prediction IDs.

## Config + DI

- OmegaConf files in `apps/api/config/` hold centralized settings.
- `dependency-injector` container wires engines, notification sink, orchestrator, and feature services.
- `test` uses SQLite async and in-memory storage, while `dev` and `prod` use Postgres plus shared object storage.

## Prefect Delegation

- Prefect-based training delegation is documented in `docs/prefect-training-delegation.md`.
- The target model separates API orchestration from training workers and the inference worker.
