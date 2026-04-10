# Cron Scheduling Architecture

This document describes how the platform wraps Prefect to provide cron-based schedule management from the `/schedules` UI and API.

## Service topology

The Docker Compose setup uses one shared database and a separate Prefect control plane:

- `postgres`: shared Postgres instance with two databases (`finetune` and `prefect`). An init script auto-creates the `prefect` database on first boot.
- `minio`: artifact and log-related storage for platform workflows
- `api`: FastAPI platform API that owns `/schedules`, proxies Prefect REST calls, and runs an embedded Prefect runner for flow execution
- `prefect-server`: Prefect 3 server on port `4200`
- `training-worker` (optional): GPU-capable process worker for training flows (V2 work-pool mode)

```mermaid
flowchart LR
  UI[Platform UI /schedules] --> API[api\nFastAPI + embedded runner]
  API -->|REST proxy| Prefect[prefect-server\nPrefect 3 :4200]
  Prefect -->|metadata DB| Postgres[(postgres\nfinetune + prefect DBs)]
  API -->|app data| Postgres
  API -->|artifacts| MinIO[(minio)]
  Prefect -->|schedule state| Postgres
  API -->|embedded runner\npolls + executes| Prefect
  API -->|executes| Flow[drain-dataset / train-job flows]
```

### What this means

- The platform API is the only client the UI talks to for schedule management.
- Prefect owns deployment, cron, run, and log state.
- The Prefect runner is embedded in the API process, started as a background task during the FastAPI lifespan when `execution.engine` is set to `prefect`. This eliminates a separate flow-worker container.
- The `training-worker` remains a separate container for GPU-bound training workloads using Prefect V2 work pools.

### Compose service dependencies

```
postgres (healthcheck: pg_isready)
  ├── prefect-server (healthcheck: /api/health)
  │     └── training-worker (restart: on-failure, optional)
  ├── api (embedded runner connects to prefect-server)
  └── minio (healthcheck: mc ready)
```

All services wait for their dependencies via `condition: service_healthy`. The `prefect` database is auto-created by an init script mounted into Postgres.

## User workflow

The end-to-end flow is:

1. User opens the UI and navigates to `/schedules`.
2. User submits the Create Schedule form.
3. The platform API creates a Prefect deployment with the cron configuration.
4. Prefect persists the deployment and starts scheduling.
5. The user can trigger a run manually or edit the schedule.
6. The worker picks up the run and executes `drain-dataset`.
7. The user checks run status and logs through the platform UI.

```mermaid
sequenceDiagram
  actor User
  participant UI as Platform UI
  participant API as Platform API + Runner
  participant Prefect as Prefect Server

  User->>UI: Open /schedules
  User->>UI: Fill Create Schedule form
  UI->>API: POST /api/v1/schedules
  API->>Prefect: POST /api/deployments/
  Prefect-->>API: deployment created
  API-->>UI: schedule saved

  User->>UI: Trigger run now
  UI->>API: POST /api/v1/schedules/{id}/run
  API->>Prefect: POST /api/deployments/{id}/create_flow_run
  Prefect-->>API: queued flow run
  Note over API: Embedded runner picks up run
  API->>API: execute drain-dataset flow

  User->>UI: View run status
  UI->>API: GET /api/v1/schedules/{id}/runs
  API->>Prefect: POST /api/flow_runs/filter
  Prefect-->>API: run list

  User->>UI: View logs
  UI->>API: GET /api/v1/runs/{run_id}/logs
  API->>Prefect: POST /api/logs/filter
  Prefect-->>API: logs
```

### What this means

- Schedule creation maps to a Prefect deployment.
- Manual trigger requests create an immediate flow run.
- Run lists and logs are read back from Prefect, not stored in the platform API.

## API endpoint mapping

| Platform Endpoint | Prefect Endpoint | Notes |
|---|---|---|
| `POST /api/v1/schedules` | `POST /api/deployments/` | Create deployment with cron schedule and `flow_id` |
| `GET /api/v1/schedules` | `POST /api/deployments/filter` | List all deployments (enriched with `flow_name`) |
| `GET /api/v1/schedules/{id}` | `GET /api/deployments/{id}` | Get single deployment |
| `PATCH /api/v1/schedules/{id}` | `PATCH /api/deployments/{id}` | Update deployment (cron via `schedules` array, pause via `paused`) |
| `DELETE /api/v1/schedules/{id}` | `DELETE /api/deployments/{id}` | Delete deployment |
| `POST /api/v1/schedules/{id}/run` | `POST /api/deployments/{id}/create_flow_run` | Trigger ad-hoc run |
| `POST /api/v1/schedules/{id}/pause` | `PATCH /api/deployments/{id}` `{"paused": true}` | Pause schedule |
| `POST /api/v1/schedules/{id}/resume` | `PATCH /api/deployments/{id}` `{"paused": false}` | Resume schedule |
| `GET /api/v1/schedules/{id}/runs` | `POST /api/flow_runs/filter` | List runs for deployment |
| `GET /api/v1/runs/{run_id}` | `GET /api/flow_runs/{run_id}` | Get single run |
| `GET /api/v1/runs/{run_id}/logs` | `POST /api/logs/filter` | Get run logs |

### Prefect 3.x field notes

- Deployments use `flow_id` (UUID), not `flow_name`. The platform resolves names via `POST /api/flows/filter` and auto-registers flows if needed.
- Pause/resume uses the `paused` boolean on deployments.
- Cron schedules live in the `schedules` array: `[{"schedule": {"cron": "...", "timezone": "UTC"}, "active": true}]`.
- PATCH returns 204 (no body); the platform re-fetches after patching.

## Embedded runner deployment model

The API process starts an embedded Prefect runner (via `prefect.runner.Runner`) during
its lifespan to register and poll **well-known deployments** for each flow:

| Flow | Served Deployment Name |
|---|---|
| `drain-dataset` | `drain-dataset-deployment` |
| `train-job` | `train-job-deployment` |

The runner starts automatically when `execution.engine` is set to `prefect` in the
config profile. For `local-smoke` mode (`execution.engine: local`), no runner is started
and Prefect is not required.

**Limitation**: Only runs for the served deployment names are executed by the embedded
runner. The UI should create schedules with matching deployment names for automatic
execution. Manually triggered runs (`create_flow_run`) work regardless.

The `training-worker` container (GPU-capable, V2 work-pool mode) remains separate for
heavy training workloads that require dedicated hardware.

## First flow

The first scheduled flow is `drain-dataset`, which exports or drains dataset data on a cron interval.

Typical parameters:

- `dataset_id`
- `target_format` (for example, `jsonl`)
- `destination` (for example, `local`)

The flow calls back to the platform API (`PLATFORM_API_URL`) to fetch export data.

## Dashboard link

The UI header includes a link to the Prefect dashboard at `http://localhost:4200` for deeper inspection.

## Error handling

The platform maps Prefect HTTP errors to standard API responses:

| Prefect Response | Platform Response | Detail |
|---|---|---|
| 404 | 404 | Context-specific: "schedule not found", "flow run not found", etc. |
| 400-499 (not 404) | 422 | Validation error with Prefect's response body |
| 500+ | 502 | Prefect server error |
| Connection error | 503 | Prefect server unavailable |

## Cron validation

- **Backend**: Uses `croniter.is_valid()` Pydantic validator — rejects invalid expressions at the API level with 422.
- **Frontend**: Lightweight check for 5 space-separated fields in the form.
