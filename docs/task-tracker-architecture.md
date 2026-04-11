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

The current topology uses a single work pool and a few specialized queues.

- work pool: `training-pool`
- queues:
  - `train-gpu`
  - `optimize-llm-cpu`
  - `predict-batch`

Queue priority is displayed as read-only metadata from Prefect work queue objects.

The tracker also exposes a derived capacity label:

- `normal`
- `busy`
- `at_capacity`
- `unknown`

Capacity is derived from Prefect work pool slot usage and concurrency limit.

## Stage Model

Every tracked task is rendered through three standard stages:

1. `queue_allocation`
2. `execution_flow`
3. `validation_output`

Training and prediction tasks use different node labels inside the same stage skeleton.

## Checks

The tracker always returns a scorecard interface.

If no asset or validation checks are available, the API returns an empty checks array instead of placeholder copy.

## UI

The web app exposes:

- `/tasks` task explorer
- `TaskInsightModal` for per-task detail

Existing training and prediction pages link into the explorer instead of duplicating tracker logic.

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
