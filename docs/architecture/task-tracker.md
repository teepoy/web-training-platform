# Task Tracker Architecture

## Scope

The task tracker provides a business-facing view over long-running backend work while using Prefect as the runtime status source.

V1 covers:

- training jobs
- prediction jobs
- embedding batch jobs routed through the prediction pipeline

The current implementation also includes schedule runs in the same explorer.

V2 can extend the same protocol to schedule runs and other Prefect-managed flows.

## Design

The frontend only talks to platform APIs. It does not consume Prefect REST payloads directly.

The backend returns two layers:

- `raw`: minimally transformed platform + Prefect payloads for compatibility and admin debugging
- `derived`: business-facing status, stages, capacity, queue position, checks, and output summaries

This keeps the UI flexible without throwing away Prefect fields too early.

### Task Tracker vs Observability Stack

The Task Tracker is a **product task view**. It answers questions like "what stage is my training job in?" and "did the prediction job finish?". It is not an operations monitoring tool.

The observability responsibilities are split across several systems:

| System | Role | Scope |
|--------|------|-------|
| **Task Tracker** | Product task detail | Per-job status, stages, checks, queue position, output summaries |
| **Prefect UI** | Flow orchestration detail | Flow runs, task runs, logs, deployment management |
| **Prometheus** | Operations metrics | Low-cardinality aggregate metrics: queue depth, request rate, error rate, GPU utilization |
| **Grafana / Loki** | Operations dashboards and logs | Correlated log search, service-level dashboards, alert visualization |
| **Alertmanager** | Alert routing | Threshold-based alerts on queue backpressure, worker health, error spikes |

Task Tracker is NOT Prometheus. It does not store time-series metrics or emit alerts. It provides a business-facing view over individual tasks. Prometheus avoids high-cardinality labels (job IDs, dataset IDs, user IDs) because those belong in the Task Tracker product view and in Prefect logs, not in the metrics pipeline.

## APIs

- `GET /api/v1/task-tracker/tasks`
- `GET /api/v1/task-tracker/tasks/{task_id}`
- `GET /api/v1/task-tracker/tasks/{task_id}/stream`
- `POST /api/v1/task-tracker/tasks/{task_id}/cancel`

## Task Kinds

The tracker normalizes multiple platform job types into a single explorer.

- `training`
- `prediction`
- `schedule_run`

For prediction jobs, `target=embedding` is shown as an embedding batch execution kind instead of a separate top-level task type.

## Prefect Mapping

Prefect is the runtime truth source for:

- flow run state
- task run execution order and state
- queue name
- work pool name
- deployment metadata
- logs

Platform persistence remains the source for:

- org access control
- dataset/model/preset references
- stored artifacts
- prediction summaries

## Work Pool And Queue Semantics

The target topology uses CPU/orchestration queues consumed by the `prefect-worker`, while GPU execution (train, predict, embed) is delegated to the `gpu-worker` via HTTP API calls.

CPU queues consumed by the Prefect worker:

- `training-pool`
  - `optimize-llm-cpu` (DSPy optimization, CPU-bound)

GPU execution is no longer queued through Prefect work pools. The Prefect flow submits work to the GPU worker via `POST /v1/train`, `POST /v1/predict`, or `POST /v1/embed` and polls for status. The GPU worker manages its own single-job queue for training.

Queue priority is displayed as read-only metadata from Prefect work queue objects.

The tracker also exposes a derived capacity label:

- `normal`
- `busy`
- `at_capacity`
- `unknown`

Capacity is derived from Prefect work pool slot usage and concurrency limit.

### GPU Worker Correlation

In the target architecture, each GPU worker job has a `gpu_job_id` (local to the GPU worker) in addition to the platform `platform_job_id` and the Prefect `flow_run_id`. The Task Tracker may correlate these IDs in a future update to provide richer runtime detail, but in V1 the tracker continues using Prefect flow run state as the primary runtime source. GPU worker status transitions are reflected through Prefect flow logs and the platform job status table.

## Stage Model

Every tracked task is rendered through three standard stages:

1. `queue_allocation`
2. `execution_flow`
3. `validation_output`

`execution_flow` is derived dynamically from Prefect task runs when a flow run is available.

This lets the inspect view render a waterfall-style runtime sequence from the actual Prefect run instead of backend hardcoded node definitions.

Each execution node now includes optional timing fields:

- `expected_start_at`
- `started_at`
- `ended_at`

If Prefect task runs are unavailable, the API falls back to a minimal single-node execution stage so the UI can still render a stable detail view.

## Checks

The tracker always returns a scorecard interface.

If no asset or validation checks are available, the API returns an empty checks array instead of placeholder copy.

## UI

The web app exposes:

- `/tasks` task explorer
- `TaskInsightModal` for per-task detail

Existing training and prediction pages link into the explorer instead of duplicating tracker logic.

The inspect modal uses Prefect deep links derived from a browser-facing Prefect URL.

- prefer `prefect.ui_url` when configured
- otherwise normalize `prefect.api_url` by stripping `.../api` or `.../api/v1`

This avoids leaking internal service names such as `prefect-server` into browser links.

## Handoff

The web app supports a lightweight handoff mode for tracked tasks.

- handoff can be enabled from the task insight modal
- watched task ids are persisted in browser storage
- app-level polling keeps watching those tasks even after the modal closes
- terminal transitions trigger:
  - browser notification
  - document title flashing
  - short success or alert tone

The current implementation uses tracker polling plus the per-task stream endpoint. It does not yet use a service worker or background push channel.
