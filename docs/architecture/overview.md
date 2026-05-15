# Architecture

## Monorepo layout

- `apps/api`: FastAPI backend with extensible domain interfaces and orchestration APIs
- `apps/web`: Vue 3 frontend for datasets and jobs
- `apps/worker`: Prefect flow-worker package for CPU orchestration and delegated flow execution
- `apps/inference`: long-lived HTTP GPU runtime service for prediction and embedding execution
- `libs/python-sdk`: Python SDK and CLI for automation and agent tool-calling

## Runtime Architecture

The platform uses a **two-role runtime model**:

### Prefect worker (CPU-only)

The `prefect-worker` is a Prefect V2 process worker that handles orchestration: it consumes CPU queues, manages flow runs, and delegates GPU work to the GPU worker via HTTP API calls. It never uses CUDA, never requests GPU resources, and never executes GPU workloads locally.

- Orchestrates flow runs through Prefect
- Executes CPU-bound flows directly (DSPy optimization, dataset drain)
- Delegates GPU work (train, predict, embed) to the GPU worker via HTTP
- Runs on a non-CUDA base image

### GPU worker

The `gpu-worker` is a standalone HTTP API service that owns GPU runtime execution. It exposes `/health`, `/metrics`, `/v1/train`, `/v1/predict`, `/v1/embed`, and train status/cancel/log endpoints.

- Executes training, prediction, and embedding on GPU
- Enforces V1 single-GPU job limits (HTTP 409 on concurrent training)
- Provides idempotent job submission via `platform_job_id`
- Runs on a CUDA-capable PyTorch base image
- On macOS/non-NVIDIA environments, starts with `gpu_info.available: false` (graceful degradation)

### Service map

```
postgres (:5432)          - shared by API, Prefect, Label Studio
minio (:9000, :9001)      - artifact storage
prefect-server (:4200)    - Prefect control plane
embedding (:50051)        - embedding gRPC service
gpu-worker (:8010)        - GPU runtime API (train/predict/embed)
label-studio (:8080)      - annotation UI
finetune-api (:8000)      - platform API
prefect-worker            - CPU-only Prefect orchestration (no exposed port)
```

### Observability

Observability is split across several systems, each with a distinct role:

| System | Role | Scope |
|--------|------|-------|
| **Prometheus** | Operations metrics | Low-cardinality aggregate metrics: queue depth, request rate, error rate, GPU utilization |
| **Grafana / Loki** | Operations dashboards and logs | Correlated log search, service-level dashboards, alert visualization |
| **Alertmanager** | Alert routing | Threshold-based alerts on queue backpressure, worker health, error spikes |
| **DCGM Exporter** | GPU metrics (Linux/NVIDIA only) | GPU utilization, memory, temperature via NVIDIA DCGM |
| **Prefect UI** | Flow orchestration detail | Flow runs, task runs, logs, deployment management |
| **Task Tracker** | Product task view | Per-job status, stages, checks, queue position, output summaries |

Prometheus avoids high-cardinality labels (job IDs, dataset IDs, user IDs). Those belong in Prefect logs and the Task Tracker product view. On macOS ARM64, DCGM exporter is unavailable and GPU metrics are absent; the rest of the observability stack remains functional.

### V1 Limits

- **Single GPU job**: Only one training job active on the GPU worker at a time
- **No multi-GPU**: Distributed/multi-GPU training is out of scope
- **No high-cardinality metrics**: Prometheus labels are low-cardinality only
- **Non-GPU degradation**: On macOS/non-NVIDIA, GPU worker reports `gpu_info.available: false` but stack remains operational
- **GPU worker crash**: Jobs active during crash are marked as failed or lost; no automatic recovery in V1

Full runtime delegation design is documented in `prefect-training-delegation.md`. Observability configuration is in `docs/observability/`.

## Core design choices

- Task type starts with `classification` and supports future expansion through typed enums/contracts.
- Execution in supported runtime environments is delegated: Prefect orchestrates training and batch jobs, while dedicated workers execute them.
- Realtime training progress uses SSE endpoint.
- Notification delivery is a custom sink interface with webhook default.
- Artifacts/export format is ML-pipeline friendly with HF-datasets-compatible payload shape.
- Persistence is implemented with SQLAlchemy 2.0 async repositories.

## Distributed training

- Production target: Kubeflow Training Operator (`PyTorchJob`) via `KubeflowTrainingOperatorEngine`.
- Training is routed through Prefect-owned workers in dev/prod, with GPU execution delegated to the GPU worker.
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

- Prefect-based training delegation is documented in `prefect-training-delegation.md`.
- The target model separates API orchestration from Prefect flow workers (CPU-only) and the GPU worker (runtime execution).
- The Prefect worker orchestrates flows and delegates GPU work to the GPU worker via HTTP API calls.
- CPU-only flows (DSPy optimization, dataset drain) execute directly in the Prefect worker.
