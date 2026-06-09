# Architecture

## Runtime layer responsibilities

| Layer | Package | Role |
|-------|---------|------|
| **Control plane** | `apps/api` | HTTP API, metadata catalog, auth, job creation, SSE events, result persistence |
| **Flow runtime** | `apps/worker` | Prefect flow definitions, `flow_serve` bootstrap, CPU orchestration, delegates compute to inference |
| **Compute plane** | `apps/inference` | Train/predict/embed HTTP endpoints, GPU resource management, model loading |
| **ML library** | `libs/ml` | Torch-first model implementations, training loops, transforms |
| **Shared runtime** | `libs/platform-runtime` | Contracts, DTOs, Protocols, SDK/CLI, cross-process client wrappers |

Execution topology:

```
apps/api (control plane)
  → Prefect server (orchestration)
  → apps/worker (flow runtime)
  → apps/inference (compute plane, GPU)
  → libs/ml (model implementations)

apps/api ──(shared contracts)──→ libs/platform-runtime ←── apps/worker, apps/inference
```

Future gRPC between worker and inference is documented but not yet implemented; HTTP is the current transport.

## Monorepo layout

- `apps/api`: FastAPI backend with extensible domain interfaces and orchestration APIs
- `apps/web`: Vue 3 frontend for datasets and jobs
- `apps/worker`: Prefect flow-worker package for CPU orchestration and delegated flow execution
- `apps/inference`: canonical GPU compute worker — FastAPI HTTP service for train, prediction, and embedding execution
- `libs/platform-runtime`: Python SDK and CLI for automation and agent tool-calling (primary)
- `libs/python-sdk`: Compatibility shim re-exporting from platform-runtime

## Service Architecture

The platform uses a **two-role service model**:

### Prefect worker (CPU orchestration; code in `apps/worker`)

The Prefect worker is the flow runtime: it consumes CPU queues, manages flow runs, and delegates GPU work to the inference worker via HTTP API calls. It never uses CUDA, never requests GPU resources, and never executes GPU workloads locally.

- Serves and executes Prefect flows (`train_job_flow`, `predict_job_flow`, etc.)
- Executes CPU-bound flows directly (dataset drain, sensor polling)
- Delegates GPU work (train, predict, embed) to `apps/inference` via HTTP
- Owns the executable trainer/predictor registry (`worker.runtime.registry`)
- Runs on a non-CUDA base image

### GPU worker (compute plane; code in `apps/inference`)

The inference worker is a standalone HTTP API service that owns GPU runtime execution. It exposes `/health`, `/metrics`, `/v1/train`, `/v1/predict`, `/v1/embed`, and train status/cancel/log endpoints.

- Executes training, prediction, and embedding on GPU
- Enforces V1 single-GPU job limits (HTTP 409 on concurrent training)
- Provides idempotent job submission via `platform_job_id`
- Loads executable trainers/predictors from `worker.runtime.registry`
- Runs on a CUDA-capable PyTorch base image
- On macOS/non-NVIDIA environments, starts with `gpu_info.available: false` (graceful degradation)

### Service map

```text
postgres (:5432)          - shared by API, Prefect, Label Studio
minio (:9000, :9001)      - artifact storage
prefect-server (:4200)    - Prefect control plane
embedding (:50051)        - embedding service (future gRPC; not yet implemented)
gpu-worker (:8010)        - GPU runtime API (train/predict/embed); built from apps/inference
label-studio (:8080)      - annotation UI
finetune-api (:8000)      - platform API (control plane)
prefect-worker            - CPU Prefect flow runtime (no exposed port); built from apps/worker
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

Full runtime contract is documented in [`runtime-contract.md`](runtime-contract.md). Observability configuration is in [`observability/`](../observability/metrics-and-logs-conventions.md).

## Core design choices

- Task type starts with `classification` and supports future expansion through typed enums/contracts.
- Execution in supported runtime environments is delegated: Prefect orchestrates training and batch jobs, while dedicated workers execute them.
- Realtime training progress uses SSE endpoint.
- Notification delivery is a custom sink interface with webhook default.
- Artifacts/export format is ML-pipeline friendly with HF-datasets-compatible payload shape.
- Persistence is implemented with SQLAlchemy 2.0 async repositories.

## Distributed training

- Production target: Kubeflow Training Operator (`PyTorchJob`) via `KubeflowTrainingOperatorEngine`.
- Training is routed through Prefect flows running in `apps/worker`, with GPU execution delegated to `apps/inference`.
- Kubeflow remains an adapter path; dev/prod do not rely on API-local execution fallbacks.

## Artifact storage

- Storage is selected by config, but `memory` is test-only. Dev/prod use MinIO/S3-compatible storage.
- `ArtifactService` persists exported dataset payloads and job artifacts to storage, then records metadata/checksum in DB.

## Dataset storage aggregate

Dataset sample access is unified behind `DatasetStorageAgg` in `apps/api/app/modules/datasets/domain/storage_agg.py`. Callers open a dataset through `DatasetStorageFactory.open(dataset_id, org_id)`, which dispatches by `storage_mode` to `DbFullDatasetStorage` or `SparseDatasetStorage`.

The aggregate is the only storage-mode boundary for sample listing, lazyframe reads, bulk sample writes, annotation persistence, prediction result persistence, feature search, and dataset deletion. Training and prediction flows use `list_samples(return_lazyframe=True, ...)`; SC import uses `write_samples(...)`. Legacy read layers such as `SampleAccessFactory`, `DatasetSampleService`, `SampleBulkAccess.open/materialize`, `BulkViewLoader`, and `RuntimeMaterializer` are not runtime fallbacks.

Domain aggregates wrap storage aggregates for domain semantics. For SC, `ScDatasetAgg` is the intended home for wafer/defect-specific operations such as wafer point computation and `defect_id` annotation semantics; generic storage implementations stay type-agnostic.

## Prediction storage and review

- Per-sample predictions are persisted in the API database as platform-owned rows.
- Batch prediction jobs store aggregate progress in `prediction_jobs.summary_json`, while detailed results are read from the prediction table.
- Label Studio is not the prediction source of truth. It is used as a temporary manual-annotation surface when a user syncs a selected prediction collection into the dataset's existing LS project.
- Review provenance points at platform prediction IDs, not LS prediction IDs.

## Config + DI

- OmegaConf files in `apps/api/config/` hold centralized settings.
- `AppContainer` dataclass in `apps/api/app/composition.py` wires services and repositories; built by `build_app_container(cfg)` in the FastAPI lifespan.
- Worker-side composition uses `build_worker_container(cfg)` in `apps/worker/worker/composition.py`, which is API-free and loads config YAML directly via OmegaConf.
- `test` uses SQLite async and in-memory storage, while `dev` and `prod` use Postgres plus shared object storage.

## Prefect / Worker / GPU Execution

- The target model separates API orchestration from Prefect flow workers (CPU-only) and the GPU worker (runtime execution).
- `apps/worker` owns Prefect flow definitions, the `flow_serve` bootstrap, and the executable trainer/predictor registry. Flows coordinate CPU orchestration (sample chunking, status polling, cancel detection, result persistence) and delegate GPU work to `apps/inference` via HTTP.
- `apps/inference` is the canonical GPU compute plane. It exposes `/v1/train`, `/v1/predict`, `/v1/embed` endpoints, enforces V1 single-GPU limits, and loads executables from `worker.runtime.registry`.
- API (`apps/api`) creates flow runs through the Prefect REST client but does not define `@flow` functions, does not serve flows, and does not import executable trainers/predictors. API-side trainer/predictor registrations are metadata catalogs only.
- CPU-only flows (dataset drain, sensor polling) execute directly in the Prefect worker.
- Cron-scheduled deployments are created through the API and consumed by the Prefect worker.
- Full contract: [`runtime-contract.md`](runtime-contract.md).
