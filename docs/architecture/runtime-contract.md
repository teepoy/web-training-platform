# GPU Worker Runtime Contract (V1)

## Purpose

This document defines the HTTP API contract between the platform API server and the V1 "fat-enough" GPU worker. The GPU worker is a long-lived HTTP service that exposes training, prediction, and embedding endpoints. The Prefect worker remains the orchestration owner (CPU-only) and delegates GPU work to this service.

## V1 "Fat-Enough" Boundary

The V1 GPU worker is intentionally "fat" — it reuses existing runtime/package code and has direct access to artifact storage and platform configuration. This minimizes migration risk and lets us ship a working split quickly.

| Responsibility | Owner |
|---|---|
| Orchestration (job lifecycle, scheduling, queue management) | Prefect worker (CPU-only) |
| Training execution (GPU compute, model checkpointing) | GPU worker (HTTP API) |
| Batch prediction (GPU inference) | GPU worker (HTTP API) |
| Batch embedding (GPU embedding generation) | GPU worker (HTTP API) |
| Artifact storage access (model weights, datasets) | GPU worker (shared MinIO/S3) |
| Config loading (presets, runtime settings) | GPU worker (shared OmegaConf) |
| Status polling and job progress | Prefect worker → GPU worker |
| Metrics export | GPU worker (Prometheus `/metrics` endpoint) |

### What the GPU worker reuses from the platform codebase

- **Preset registry** — loads training presets from `apps/api/presets/`
- **Artifact storage client** — reads/writes to the same MinIO/S3 bucket as the API
- **OmegaConf config** — reads `apps/api/config/` for runtime settings
- **Flow task code** — reuses `apps/worker/` training and prediction modules
- **Runtime runners** — reuses `apps/api/app/runtime/` training/prediction logic

### What the Prefect worker owns and never delegates

- Job state transitions in the API database (`PENDING → RUNNING → COMPLETED/FAILED`)
- Work pool and queue management
- Prefect flow run lifecycle
- Notification dispatch (webhook sink)

## Endpoints

### Health

```
GET /health
```

Returns GPU worker health status and available capabilities.

**Response 200:**
```json
{
  "status": "ok",
  "service": "gpu-worker",
  "capabilities": ["train", "predict", "embed"],
  "active_jobs": 1
}
```

### Metrics

```
GET /metrics
```

Prometheus-compatible metrics endpoint. Exports job counters, GPU utilization, and request latencies. Format: Prometheus text exposition.

### Train

#### Start Training

```
POST /v1/train
```

Submits a training job to the GPU worker. The GPU worker must be running on a machine with GPU access. Exactly one training job may be active at a time — `concurrency_limit: 1`.

**Request:**
```json
{
  "platform_job_id": "uuid-string",
  "preset_id": "resnet50-cls-v1",
  "dataset_id": "uuid-string",
  "model_id": "uuid-string",
  "hyperparameters": {},
  "artifact_prefix": "jobs/{platform_job_id}/"
}
```

**Response 202 (accepted):**
```json
{
  "job_id": "uuid-string",
  "status": "accepted",
  "position": 0
}
```

**Response 409 (conflict — another training job is active):**
```json
{
  "detail": "A training job is already running. Only one training job may be active at a time."
}
```

**Response 409 (idempotent resubmit — platform_job_id already known):**
```json
{
  "job_id": "uuid-string",
  "status": "already_submitted",
  "detail": "Job with this platform_job_id already exists"
}
```

#### Get Training Status

```
GET /v1/train/{job_id}
```

Returns the current status of a training job.

**Response 200:**
```json
{
  "job_id": "uuid-string",
  "platform_job_id": "uuid-string",
  "status": "running",
  "progress": 0.45,
  "metrics": {
    "loss": 1.23,
    "accuracy": 0.67,
    "epoch": 3,
    "total_epochs": 10
  },
  "error": null,
  "created_at": "2025-01-01T00:00:00Z",
  "started_at": "2025-01-01T00:00:05Z",
  "updated_at": "2025-01-01T00:05:00Z"
}
```

**Status values:** `pending`, `running`, `completed`, `failed`, `cancelled`, `lost`

#### Cancel Training

```
POST /v1/train/{job_id}/cancel
```

Requests cancellation of a running training job. Best-effort — the GPU worker will attempt to stop the training process but may not be able to immediately interrupt GPU kernels.

**Response 200:**
```json
{
  "job_id": "uuid-string",
  "status": "cancelling"
}
```

**Response 409 (job not in cancellable state):**
```json
{
  "detail": "Job is in terminal state: completed"
}
```

#### Get Training Logs

```
GET /v1/train/{job_id}/logs?tail=100
```

Returns recent log lines from the training process.

**Response 200:**
```json
{
  "job_id": "uuid-string",
  "logs": [
    {"timestamp": "2025-01-01T00:00:01Z", "level": "INFO", "message": "Loading dataset..."},
    {"timestamp": "2025-01-01T00:00:02Z", "level": "INFO", "message": "Starting epoch 1/10"}
  ]
}
```

### Predict

```
POST /v1/predict
```

Runs batch prediction using a trained model.

**Request:**
```json
{
  "model": {
    "id": "uuid-string",
    "uri": "s3://bucket/models/model.pt",
    "format": "pytorch",
    "metadata": {},
    "content_b64": "<base64-encoded-model-bytes>"
  },
  "target": "classification",
  "label_space": ["cat", "dog"],
  "samples": [
    {
      "sample_id": "uuid-string",
      "image_bytes_b64": "<base64-encoded-image>",
      "metadata": {},
      "image_uris": [],
      "question": "",
      "text": null
    }
  ]
}
```

**Response 200:**
```json
{
  "predictions": [
    {
      "sample_id": "uuid-string",
      "label": "cat",
      "confidence": 0.95,
      "scores": {"cat": 0.95, "dog": 0.05},
      "error": null
    }
  ]
}
```

### Embed

```
POST /v1/embed
```

Generates embeddings for a batch of samples.

**Request:**
```json
{
  "model_name": "openai/clip-vit-base-patch32",
  "samples": [
    {
      "sample_id": "uuid-string",
      "image_bytes_b64": "<base64-encoded-image>"
    }
  ]
}
```

**Response 200:**
```json
{
  "embeddings": [
    {
      "sample_id": "uuid-string",
      "embedding": [0.1, 0.2, 0.3],
      "error": null
    }
  ]
}
```

## Idempotency Semantics

The GPU worker uses `platform_job_id` (the API database job UUID) as the idempotency key for all training requests.

- **First submission**: Creates a new training job record. Returns 202.
- **Duplicate submission**: Worker detects the same `platform_job_id` already exists. Returns 409 with `"status": "already_submitted"`. The original job continues unaffected.
- **Prediction/Embedding**: These are stateless batch operations — each request is independent. No idempotency key is required or enforced.

## Crash / Lost Semantics

The GPU worker is a single process running on a GPU machine. In V1, crash/lost handling is simple:

| Scenario | Behavior |
|---|---|
| GPU worker process crashes mid-training | All in-progress jobs are lost. On restart, no jobs are recovered. The Prefect worker detects the training flow run failed and marks the platform job as `failed`. |
| GPU machine is unreachable | After timeout, the Prefect worker marks the flow run as failed, which cascades to the platform job status `failed`. |
| GPU worker returns error response | The Prefect worker propagates the error and marks the platform job as `failed`. |
| GPU worker restarts cleanly | Starts with empty job queue. No persistent state survives restart. |

**V1 Limitation**: There is no persistence of training job state across GPU worker restarts. A crash during training means the job must be resubmitted from scratch. This is acceptable for V1 because:
- Training jobs are initiated by users and can be retried manually
- The model artifact is not recovered from a crashed worker
- Prefect flow runs provide an audit trail of what was submitted

## Single-GPU Active Training Constraint

The V1 GPU worker enforces `concurrency_limit: 1` for training jobs:

- Only one training job may be in `running` or `pending` state at any time.
- Additional training submissions while a job is active receive 409 Conflict.
- This constraint is dictated by GPU memory — a single training job typically consumes all available GPU memory.
- Prediction and embedding requests are accepted concurrently with an active training job (they use smaller model footprints or share the GPU through batching).

## Config Integration

The API server configures the GPU worker URL via OmegaConf:

```yaml
# base.yaml
gpu_worker:
  base_url: "http://localhost:8010"
```

Environment variable override: `GPU_WORKER_BASE_URL`.

The legacy `inference.base_url` key is deprecated but still accepted as a fallback. New deployments must set `gpu_worker.base_url`.

## Migration and Removal

The direct API → inference worker path has been removed in favor of the unified GPU worker contract. The legacy client and its corresponding service boundary mocks have been deleted.

The GPU worker retains the same prediction/embedding endpoints and response schemas for forward compatibility. For a detailed audit of the removal and the transition to the unified worker model, see `docs/architecture/api-sync-worker-callsites.md`.

## Verification Checklist

1. Start the GPU worker and verify `GET /health` returns `200` with capabilities
2. Submit a training job via `POST /v1/train` and verify 202 response
3. Poll `GET /v1/train/{job_id}` and verify status progresses through `pending → running → completed`
4. Submit a second training job while one is running — verify 409 Conflict
5. Resubmit the same `platform_job_id` — verify 409 with `already_submitted`
6. Cancel a running job via `POST /v1/train/{job_id}/cancel` — verify status transitions to `cancelled`
7. Run a batch prediction via `POST /v1/predict` — verify correct response shape
8. Run a batch embedding via `POST /v1/embed` — verify correct response shape
9. Verify `GET /metrics` returns Prometheus-compatible output
10. Kill the GPU worker process — verify the Prefect worker marks the job as failed
