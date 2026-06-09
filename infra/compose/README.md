# Compose Config

## Dev vs Prod Modes

The compose stack now supports two modes via override files:

| Mode | Command | Compose Files | Hot Reload | Volume Mounts |
|------|---------|--------------|------------|---------------|
| Dev | `make up-dev` | `docker-compose.yaml` + `docker-compose.dev.yaml` | ✅ fastapi dev + vite dev | ✅ All code mounted |
| Prod | `make up-prod` | `docker-compose.yaml` + `docker-compose.prod.yaml` | ❌ | ❌ Baked images |

### Base Infrastructure (shared by both modes)
`docker-compose.yaml` contains always-on infrastructure:
- **postgres** (`:5432`): PostgreSQL with pgvector
- **minio** (`:9000`, `:9001`): S3-compatible storage
- **prefect-server** (`:4200`): Prefect 3 control plane
- **label-studio** (`:8080`): Annotation UI

### Dev Mode (`make up-dev`)
Adds via `docker-compose.dev.yaml`:
- **api** with bind mounts + `fastapi dev` hot reload
- **web** with bind mount + Vite dev server hot reload
- **prefect-worker-cpu** with bind mounts for flow code changes
- **deployments-bootstrap**: one-shot pool creation + flow deployment registration
- **pgadmin** (`:5050`): optional PostgreSQL admin UI
- Profile `--profile observability`: Prometheus, Grafana, Loki, Promtail, Alertmanager, cAdvisor, Node Exporter, Prefect Exporter
- Profile `--profile gpu`: GPU Prefect worker + DCGM exporter (Linux/NVIDIA only)

### Prod Mode (`make up-prod`)
Adds via `docker-compose.prod.yaml`:
- **api** with `uvicorn --workers 4` (no hot reload, no bind mounts)
- **web** served via nginx (built into image)
- **prefect-worker-cpu** with baked image (no bind mounts)
- Profile `--profile observability`: Prometheus, Grafana, Loki, Promtail, Alertmanager, cAdvisor, Node Exporter, Prefect Exporter
- Profile `--profile gpu`: GPU Prefect worker + DCGM exporter (Linux/NVIDIA only)

Prod mode does **not** include: pgadmin, deployments-bootstrap, automatic alembic migrations.

### Migration Notes
- `make up` → now redirects to `make up-dev` (deprecated)
- `make up-stack` → now redirects to `make up-dev --scale web=0` (deprecated)
- `make updev` → unchanged (starts compose backend + local Vite on host)
- Flow deployment in prod: run `make ftctl ARGS="deployments apply"` manually
- Alembic migrations in prod: run `make db-migrate-compose` separately

`docker-compose.yaml` is at `infra/compose/docker-compose.yaml` and provides always-on
infrastructure (postgres, minio, prefect-server, label-studio). Dev and prod overrides
add API, web, and workers — see [Dev vs Prod Modes](#dev-vs-prod-modes) above.

Quick start:

```bash
# Dev mode (recommended for daily work)
make up-dev

# Prod mode
make up-prod

# Interactive dev: compose backend + local Vite frontend
make updev
```

`make updev` is the recommended interactive dev entrypoint. It starts the
compose backend stack without the baked `web` container, ensures the default
mock dataset exists, and then runs the local Vite dev server on `:5173` for
hot reload and stable `/api` proxying to `localhost:8000`.

## Services

The stack is split across three Compose files:

- **Base infrastructure** (`docker-compose.yaml`): postgres, minio, prefect-server, label-studio
- **Dev add-ons** (`docker-compose.dev.yaml`): api (hot-reload), web (Vite dev), prefect-worker-cpu, prefect-worker-gpu (profile), deployments-bootstrap, pgadmin
- **Prod add-ons** (`docker-compose.prod.yaml`): api (uvicorn --workers 4), web (nginx), prefect-worker-cpu, prefect-worker-gpu (profile)

All services at a glance:

- **postgres** (:5432): PostgreSQL with pgvector, shared by API, Prefect, and Label Studio
- **minio** (:9000, :9001): S3-compatible artifact storage
- **prefect-server** (:4200): Prefect 3 control plane
- **label-studio** (:8080): Annotation UI
- **api** (:8000): Platform API (dev: fastapi hot-reload with bind mounts; prod: uvicorn workers with baked image)
- **web** (:5173 → :80): Frontend (dev: Vite dev server with bind mount; prod: nginx-served baked assets)
- **prefect-worker-cpu** (no exposed port): CPU-only Prefect worker. Orchestrates flows from `default-cpu` pool, executes CPU-bound work (DSPy, dataset drain). No GPU resources, no CUDA.
- **prefect-worker-gpu** (no exposed port, profile `gpu`): GPU Prefect worker for CUDA workloads. Starts via `--profile gpu` (Linux/NVIDIA only).
- **deployments-bootstrap** (dev-only): One-shot service that creates work pools and registers flow deployments.
- **pgadmin** (:5050, dev-only): Optional PostgreSQL admin UI

## Notes

- Dev mode uses `fastapi dev` with bind mounts for hot-reload; prod mode uses `uvicorn --workers 4` with baked images.
- Compose services run from the image's prebuilt `/app/.venv` and do not use `uv run` at container startup.
- The `web` service serves assets baked into the image (prod) or via Vite dev server (dev).
- Prefer `make updev` over the baked `web` container during daily development — or use `make up-dev` for the full compose dev stack.
- GPU profile (`--profile gpu`) requires Linux with NVIDIA GPU and NVIDIA Container Toolkit. On macOS/non-NVIDIA hosts, GPU workers are simply omitted.
- The API exposes `/health` for process liveness and `/ready` for database-backed readiness. Compose marks the API healthy only when `/ready` returns HTTP 200.

## Observability

Stack monitoring is profile-gated behind the `observability` Compose profile:

```bash
# Start the full platform + observability stack
docker compose -f infra/compose/docker-compose.yaml --profile observability up -d
```

This brings up everything in the base stack plus:

| Service          | Port  | Purpose                                      |
| ---------------- | ----- | -------------------------------------------- |
| Prometheus       | :9090 | Operations metrics scrape target            |
| Grafana          | :3000 | Dashboards (admin/admin)                    |
| Loki             | :3100 | Log aggregation API                         |
| Promtail         | —     | Docker-container log collector              |
| Alertmanager     | :9093 | Alert routing (dev-null receiver by default) |
| cAdvisor         | —     | Container resource metrics (scraped :8080)  |
| Node Exporter    | —     | Host-level metrics (scraped :9100)          |
| Prefect Exporter | —     | Prefect server health (scraped :8000)       |

Prometheus scrape targets: `api`, `gpu-worker`, `prefect-exporter`, `alertmanager`, `cadvisor`, `node-exporter`, `dcgm-exporter`, and self.

### GPU Monitoring (Linux / NVIDIA only)

```bash
docker compose -f infra/compose/docker-compose.yaml --profile gpu up -d dcgm-exporter
```

Or combine both profiles:

```bash
docker compose -f infra/compose/docker-compose.yaml --profile observability --profile gpu up -d
```

The DCGM exporter (`nvidia/dcgm-exporter`) requires an NVIDIA GPU and the NVIDIA Container Toolkit on the host. On macOS / non-NVIDIA hosts the `gpu` profile is unavailable and the stack operates normally without GPU metrics.

### Alert Rules

Six Prometheus alert rules are defined in `observability/prometheus/alert-rules.yml` and loaded by Prometheus at startup via `rule_files`. The file is bind-mounted into the Prometheus container alongside `prometheus.yml`. All alerts carry `severity` (critical/warning) and `group: finetune` labels.

| Alert | Condition | For | Severity |
|---|---|---|---|
| `GPUWorkerDown` | `up{job="gpu-worker"} == 0` | 2m | critical |
| `PrefectExporterDown` | `up{job="prefect-exporter"} == 0` | 2m | warning |
| `QueueBacklogHigh` | `prefect_work_queue_depth > 100` | 5m | warning |
| `GPUWorkerOOM` | GPU worker container restarts > 3 in 15m | 1m | critical |
| `DcgmGpuMemoryHigh` | GPU FB memory > 90% (skipped if DCGM absent) | 5m | warning |
| `ServiceRestartLoop` | Any platform service restarts > 5 in 10m | 1m | critical |

### Silencing Alerts During Maintenance

Use the Alertmanager API (port 9093) to create a silence that suppresses alerts for a time-boxed maintenance window without modifying any config files.

```bash
# Create a silence for all finetune alerts for 2 hours
curl -s -X POST http://localhost:9093/api/v2/silences \
  -H 'Content-Type: application/json' \
  -d '{
    "matchers": [{"name": "group", "value": "finetune", "isRegex": false}],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "endsAt": "'$(date -u -v+2H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+2 hours' +%Y-%m-%dT%H:%M:%SZ)'",
    "createdBy": "ops",
    "comment": "Maintenance window"
  }'

# List active silences
curl -s http://localhost:9093/api/v2/silences | jq '.[] | select(.status.state == "active")'

# Expire a silence by ID
curl -s -X DELETE http://localhost:9093/api/v2/silence/<silence-id>
```

Alternatively, open the Alertmanager UI at http://localhost:9093 and use the **Silences** tab to create, inspect, and expire silences interactively.

### Log Collection (Promtail → Loki)

Promtail discovers all Docker containers via the Docker socket and ships their logs to Loki. The pipeline applies a deliberate low-cardinality label strategy to prevent Loki index explosion.

#### Loki labels applied to every log stream

| Label       | Source                     | Example values                                      |
| ----------- | -------------------------- | --------------------------------------------------- |
| `service`   | Container name (normalized)| `api`, `gpu-worker`, `prefect-worker`, `prefect-exporter`, `loki`, `grafana` |
| `container` | Container name (raw)       | `api`, `gpu-worker`                                 |
| `env`       | Static (pipeline stage)    | `finetune`                                          |
| `level`     | JSON field extraction      | `info`, `warn`, `error`, `debug`                    |

#### Labels explicitly NOT promoted (high-cardinality)

The following values are **never** Loki stream labels. They remain searchable as log content only:

- `platform_job_id` / `job_id` — platform training/prediction job identifiers
- `gpu_job_id` — GPU worker job identifiers
- `flow_run_id` — Prefect flow run identifiers
- Container IDs, network addresses, Docker metadata (`__meta_docker_*`)

#### Querying logs in Grafana / LogQL

```logql
# All logs from the API service
{service="api"}

# GPU worker error logs
{service="gpu-worker", level="error"}

# All logs for a specific platform job (content filter — no label required)
{service="api"} |= "platform_job_id=<your-job-id>"

# Prefect worker logs for a specific flow run
{service="prefect-worker"} |= "flow_run_id=<your-run-id>"

# All finetune service logs across env
{env="finetune"} | json | level="error"
```

## Rollback & Migration

### Migration from Single Worker
The platform has migrated from a single `training-worker` to a split `gpu-worker` (HTTP API) and `prefect-worker` (CPU orchestration) topology.

### Rollback Procedure
If the split topology causes issues, roll back by:
1. Reverting `docker-compose.yaml` to the previous version containing the unified `training-worker` service.
2. Restarting the stack: `docker compose down && docker compose up -d`.
3. The observability stack remains compatible but will stop receiving metrics for the new service names.
