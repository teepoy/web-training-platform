# Observability: Metrics & Logging Conventions

## Purpose

This document establishes **universal conventions** for all platform services. Every
service — API, GPU worker, Prefect flows, cron scheduler — MUST follow these rules
when emitting metrics or structured logs. The goal is a **usable, low-toil**
observability stack: aggregate health from Prometheus, detailed forensics from Loki,
product-facing status from Task Tracker, and deep task execution from Prefect.

These are **conventions only**. This document does not prescribe a client library
or deployment mechanism.

---

## 1. Observability Surface — Who Owns What

| System           | What It Provides                                      | Cardinality        | Consumer         |
| ---------------- | ----------------------------------------------------- | ------------------ | ---------------- |
| **Prometheus**   | Aggregate service/queue/job-type health and SLOs      | Low (label-controlled) | Platform SRE, Grafana dashboards |
| **Loki**         | Structured JSON logs for per-job forensics            | High (job ids in log body) | Developer debugging, incident forensics |
| **Task Tracker** | Product-facing task status, stages, summaries         | Medium             | Platform web UI  |
| **Prefect**      | Flow-run state, task-run DAG, queue assignment, logs  | High               | Task Tracker (data source), admin debugging |

### Separation Rule

- Prometheus **MUST NOT** be used to look up individual job state. Use
  Task Tracker or Prefect.
- Task Tracker **MUST NOT** scrape Prometheus to derive task status.
  Prefect is the runtime truth source.
- Logs go to Loki (and optionally mirrored to Prefect for in-run log access).
  Prometheus is for metrics, NOT log-derived counters.

---

## 2. Prometheus — Metric Naming Convention

### Naming Format

```
platform_<service>_<metric>_<unit>
```

| Component     | Rules                                                                 |
| ------------- | --------------------------------------------------------------------- |
| `platform_`   | Fixed prefix for all platform-originated metrics                      |
| `<service>`   | Lowercase snake_case service name: `api`, `gpu_worker`, `prefect`    |
| `<metric>`    | Describes what is measured: `jobs_active`, `request_duration`, `queue_depth` |
| `<unit>`      | Prometheus base unit suffix: `_seconds`, `_bytes`, `_total` (for counter), `_ratio` |

### Allowed Metric Names

#### GPU Worker (`gpu_worker`)

| Metric                                      | Type      | Description                                     |
| ------------------------------------------- | --------- | ----------------------------------------------- |
| `platform_gpu_worker_jobs_active`            | Gauge     | Currently executing jobs                        |
| `platform_gpu_worker_jobs_queued`            | Gauge     | Jobs waiting in the GPU work queue              |
| `platform_gpu_worker_jobs_total`             | Counter   | Total jobs processed (labeled by status)        |
| `platform_gpu_worker_job_duration_seconds`   | Histogram | Wall-clock job duration                         |
| `platform_gpu_worker_predict_batch_duration_seconds` | Histogram | End-to-end `/v1/predict` batch latency |
| `platform_gpu_worker_embed_batch_duration_seconds`  | Histogram | End-to-end `/v1/embed` batch latency    |
| `platform_gpu_worker_model_load_duration_seconds`   | Histogram | Time to load/cache a model from cold start |
| `platform_gpu_worker_model_cache_hits_total` | Counter   | Successful model cache lookups                  |
| `platform_gpu_worker_model_cache_misses_total` | Counter | Model cache misses requiring load               |

#### Prefect (via exporter sidecar or Prefect-native metrics)

| Metric                                      | Type      | Description                                     |
| ------------------------------------------- | --------- | ----------------------------------------------- |
| `platform_prefect_flow_runs_by_state`       | Gauge     | Flow runs grouped by state label                |
| `platform_prefect_queue_depth`              | Gauge     | Items queued in each work queue                 |
| `platform_prefect_worker_status`            | Gauge     | Worker liveness (1=healthy, 0=down)             |
| `platform_prefect_flow_duration_seconds`    | Histogram | Wall-clock flow run duration                    |

#### API Server (`api`)

| Metric                                            | Type      | Description                                |
| ------------------------------------------------- | --------- | ------------------------------------------ |
| `platform_api_request_duration_seconds`            | Histogram | HTTP request duration                      |
| `platform_api_requests_total`                      | Counter   | HTTP requests (labeled by route, status)   |
| `platform_api_jobs_dispatched_total`               | Counter   | Jobs submitted to Prefect                  |

---

## 3. Prometheus — Label Policy

### Allowed Labels (Low Cardinality Only)

Labels MUST be drawn from this allowlist. No other label keys are permitted
on platform Prometheus metrics.

| Label        | Description                                 | Example Values                                    |
| ------------ | ------------------------------------------- | ------------------------------------------------- |
| `service`    | Originating service name                    | `api`, `gpu_worker`, `prefect`                    |
| `task_kind`  | Platform job category                       | `training`, `prediction`, `schedule_run`, `embedding` |
| `queue`      | Prefect work queue name                     | `train-gpu`, `predict-batch`, `embed-batch`       |
| `status`     | High-level outcome bucket                   | `success`, `failure`, `cancelled`                 |
| `stage`      | Pipeline stage (if applicable)              | `queue_allocation`, `execution_flow`, `validation_output` |
| `target`     | Prediction target modality                  | `classification`, `vqa`, `embedding`              |
| `runtime`    | Execution engine or runtime variant         | `torch`, `dspy-vqa-v1`, `kubernetes`              |

All label values MUST be drawn from a bounded set. Never tag a metric with
dynamically-generated or user-supplied values (e.g. model names, dataset names).

### FORBIDDEN Labels (High-Cardinality / Unbounded)

These identifiers **MUST NOT** appear as Prometheus label keys or values.
They belong in JSON log bodies or Loki fields — never in metric label sets.

- `job_id`
- `platform_job_id`
- `dataset_id`
- `model_id`
- `preset_id`
- `user_id`
- `org_id`
- `gpu_job_id`
- `prefect_flow_run_id`
- `schedule_id`
- `sample_id`
- `prediction_id`
- Any user-supplied string (model name, dataset name, etc.)

### Rationale

Prometheus stores every unique label combination as a separate time series.
A label set containing a job id would explode cardinality — each job
creating new series that persist until tombstone TTL. This degrades query
performance, inflates storage, and makes dashboards unusable.

Job/entity identifiers are **forensic** data — they belong in log bodies
and Loki stream labels at query-time, not in the metric index.

---

## 4. Loki — Logging Conventions

### Log Format

All services MUST emit structured JSON logs. The top-level log record SHALL
include a standard set of **correlation fields**:

```json
{
  "timestamp": "2026-05-14T12:34:56.789Z",
  "level": "info",
  "service": "gpu_worker",
  "env": "dev",
  "message": "Job started",
  "org_id": "org_abc123",
  "platform_job_id": "j-8f3a1b2c",
  "prefect_flow_run_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "gpu_job_id": "gpu-job-42",
  "task_kind": "prediction",
  "queue": "predict-batch",
  "stage": "execution_flow",
  "status": "running",
  "error_type": null,
  "duration_ms": null,
  "context": {}
}
```

### Correlation Field Reference

| Field                 | Type     | Description                                        | Required |
| --------------------- | -------- | -------------------------------------------------- | -------- |
| `timestamp`           | ISO 8601 | Log event time                                     | Yes      |
| `level`               | string   | `debug` / `info` / `warning` / `error`             | Yes      |
| `service`             | string   | Service name (`api`, `gpu_worker`, `prefect`)      | Yes      |
| `env`                 | string   | Deployment environment (`dev`, `prod`)             | Yes      |
| `message`             | string   | Human-readable summary                             | Yes      |
| `org_id`              | string   | Platform org identifier                            | When available |
| `platform_job_id`     | string   | Platform DB job id                                 | When available |
| `prefect_flow_run_id` | UUID     | Prefect flow run id                                | When available |
| `gpu_job_id`          | string   | GPU worker's internal job id                       | When available |
| `task_kind`           | string   | `training` / `prediction` / `schedule_run`         | When available |
| `queue`               | string   | Prefect work queue name                            | When available |
| `stage`               | string   | Pipeline stage                                     | When available |
| `status`              | string   | `running` / `success` / `failure` / `cancelled`    | When available |
| `error_type`          | string   | Exception class name or error code                 | On error        |
| `duration_ms`         | number   | Operation duration in milliseconds                 | Optional        |
| `context`             | object   | Additional structured data (key-value)             | Optional        |

### Loki Stream Labels (Low-Cardinality Only)

Loki stream labels index the log stream for efficient querying. Keep labels
low-cardinality following the same discipline as Prometheus:

**Allowed stream labels:**
- `service` — always
- `env` — always
- `task_kind` — when available
- `status` — when available

**Forbidden stream labels:**
- `org_id`, `platform_job_id`, `prefect_flow_run_id`, `gpu_job_id`
- Any high-cardinality identifier

These job identifiers belong in the JSON log body and can be filtered at
query time via LogQL label filters (e.g.
`{service="gpu_worker"} | json | platform_job_id="j-8f3a1b2c"`).

---

## 5. Service-Specific Obligations

### GPU Worker (`apps/inference/`)

The GPU worker MUST expose:
1. A `/metrics` endpoint (Prometheus scrape target) with the metrics listed
   in Section 2.
2. All log lines MUST be structured JSON with correlation fields from Section 4.

Label usage:
- `service=gpu_worker` on all metrics
- `task_kind` labeled by the job type (`prediction`, `embedding`)
- `status` labeled by outcome bucket (`success`, `failure`)
- `target` labeled by prediction modality (`classification`, `vqa`, `embedding`)
- `runtime` labeled by engine variant (`torch`, `dspy-vqa-v1`)

### API Server (`apps/api/`)

The API server MUST expose:
1. A `/metrics` endpoint with `platform_api_request_duration_seconds`,
   `platform_api_requests_total`, `platform_api_jobs_dispatched_total`.
2. All log lines MUST be structured JSON with correlation fields.

Label usage:
- `service=api` on all metrics
- `status` for HTTP response status and job dispatch outcome
- `task_kind` for job dispatch counter

### Prefect Metrics

Prefect metrics SHOULD be collected via Prefect's native Prometheus exporter
or a sidecar exporter. The platform MUST NOT implement its own Prefect flow
state scraper — this is Prefect's responsibility.

Prefect metrics use `service=prefect`. Queue depth and worker status labels
use the `queue` and `status` allowlist labels.

---

## 6. Anti-Patterns

### Do NOT

- Add `job_id`, `dataset_id`, `model_id`, `user_id`, `org_id` as
  Prometheus label keys or values
- Use Prometheus counters/gauge to track per-job progress — that is what
  Task Tracker stages are for
- Scrape Prometheus from Task Tracker to derive task status — Prefect is
  the truth source
- Create dynamic metrics at runtime (e.g. `platform_job_j_8f3a1b2c_progress`)
- Add high-cardinality Loki stream labels; prefer LogQL `| json` filters
  in query expressions
- Log secrets, tokens, or full image bytes in log bodies

### Do

- Use the correlation fields to join logs across services during incident
  forensics
- Derive dashboards exclusively from Prometheus metrics (aggregate health)
- Use Task Tracker for product-facing status, Prefect for execution detail
- When in doubt about a label: if it could exceed ~100 unique values at
  steady-state, it belongs in the log body, NOT as a label

---

## 7. References

- **Task Tracker architecture**: `docs/architecture/task-tracker.md` —
  separation of Prefect runtime truth from platform product view
- **Prefect work pools**: `docs/architecture/task-tracker.md:63-85` —
  work pool and queue topology (`train-gpu`, `predict-batch`, `embed-batch`)
- **Stage model**: `docs/architecture/task-tracker.md:87-105` —
  `queue_allocation` → `execution_flow` → `validation_output`
- **Inference worker health**: `apps/inference/app/main.py:148-160` —
  current health check (no metrics endpoint yet)
- **Task Tracker summary metrics**: `apps/api/app/services/task_tracker.py:413-460` —
  existing product-view summary fields (not Prometheus)
