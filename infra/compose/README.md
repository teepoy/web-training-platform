# Compose Config

For production hardening, split-stack deployment, backup, release, and rollback
procedures, see
[`docs/guides/production-compose-deployment.md`](../../docs/guides/production-compose-deployment.md).
The deployable split manifests are:

- `production/compose.stateful.yaml`
- `production/compose.platform.yaml`
- `production/compose.ops.yaml`
- `production/compose.observability.yaml`

## Local Dev vs Release Validation

The compose stack now supports two modes via override files:

| Mode                    | Command               | Compose Files                                             | Hot Reload                | Volume Mounts                  |
| ----------------------- | --------------------- | --------------------------------------------------------- | ------------------------- | ------------------------------ |
| Dev                     | `make up-dev`         | `docker-compose.yaml` + `docker-compose.dev.yaml`         | ✅ fastapi dev + vite dev | ✅ All code mounted            |
| Legacy local validation | `make up-prod`        | `docker-compose.yaml` + `docker-compose.prod.yaml`        | ❌                        | ❌ Baked images                |
| Pre-release acceptance  | `make up-pre-release` | production manifests + `pre-release/` acceptance overlays | ❌                        | ❌ Production-built image code |

### Base Infrastructure (shared by both modes)

`docker-compose.yaml` contains always-on infrastructure:

- **postgres** (`:5432`): PostgreSQL with pgvector
- **minio** (`:9000`, `:9001`): S3-compatible storage
- **redis** (`:6379`): Redis cache/coordination dependency
- **prefect-server** (`:4200`): Prefect 3 control plane
- **label-studio** (`:8080`): Annotation UI
- **sc-upstream** / **image-parser**: local SC upstream and parser services
- Profile `--profile observability`: Prometheus, Grafana, Loki, Promtail, Alertmanager, cAdvisor, Node Exporter, Prefect Exporter
- Profile `--profile gpu`: DCGM exporter

> **Production note:** The split-stack manifests separate stateful services
> (`postgres`, `minio`, `redis`, `label-studio`) into `compose.stateful.yaml`.
> `prefect-server` stays in `compose.platform.yaml` because it is stateless
> (its DB lives in the stateful project's postgres).

### Dev Mode (`make up-dev`)

Adds via `docker-compose.dev.yaml`:

- **api** with bind mounts + `fastapi dev` hot reload
- **web** with bind mount + Vite dev server hot reload
- **prefect-worker-cpu** with bind mounts for flow code changes
- **deployments-bootstrap**: one-shot pool creation + flow deployment registration
- **pgadmin** (`:5050`): optional PostgreSQL admin UI
- Profile `--profile gpu`: GPU Prefect worker (Linux/NVIDIA only)

### Local Release Validation (`make up-prod`)

Adds via `docker-compose.prod.yaml`:

- **api** with `uvicorn --workers 4` (no hot reload, no bind mounts)
- **web** served via nginx (built into image)
- **prefect-worker-cpu** with baked image (no bind mounts)
- Profile `--profile gpu`: GPU Prefect worker (Linux/NVIDIA only)

Prod mode does **not** include pgadmin or a long-running deployments bootstrap.
`make up-prod` performs Alembic migration and idempotent Prefect pool/deployment
registration as one-shot steps before it starts the application services. The local
Prefect auth value defaults to `dangerous:dangerous` and can be overridden with
`LOCAL_PROD_PREFECT_AUTH=...`.

When invoking the two Compose files directly instead of using Make, export the
same value explicitly:

```bash
export PREFECT_SERVER_API_AUTH_STRING=dangerous:dangerous
```

### Pre-release and Production Split-Stack

For a local acceptance run of the production-built services:

```bash
make init-pre-release-env
make up-pre-release
```

This path builds the production Docker targets, then runs them against the same
PostgreSQL, MinIO, Redis, Label Studio, Prefect, SC upstream, and image-parser
boundaries used by the production manifests. The overlays under
`infra/compose/pre-release/` only add local builds, loopback host ports, and
project-scoped named volumes. They do not replace the production topology.

The default endpoints are:

| Service       | URL                      |
| ------------- | ------------------------ |
| Web           | `http://127.0.0.1:15173` |
| API           | `http://127.0.0.1:18000` |
| Prefect       | `http://127.0.0.1:14200` |
| Label Studio  | `http://127.0.0.1:18080` |
| MinIO console | `http://127.0.0.1:19001` |

Use `make verify-pre-release`, `make ps-pre-release`, and
`make logs-pre-release ARGS=api` for inspection. `make down-pre-release` stops
containers but preserves the isolated volumes. Enable the GPU worker only on a
compatible NVIDIA host:

```bash
make up-pre-release PRE_RELEASE_PROFILES="--profile gpu"
```

`infra/compose/pre-release/.env` is ignored by Git. The supplied `env.example`
credentials are safe only for a loopback-bound local machine; replace them
before using the stack on a shared host.

For production use the split-stack manifests under `infra/compose/production/`:

| Step             | Command                      | Description                                                  |
| ---------------- | ---------------------------- | ------------------------------------------------------------ |
| 1. Network       | `make create-prod-network`   | Create shared `finetune-prod` network                        |
| 2. Stateful      | `make up-prod-stateful`      | `postgres`, `minio`, `redis`, `label-studio`                 |
| 3. Platform      | `make up-prod-platform`      | `prefect-server`, `api`, `web`, `workers`                    |
| 4. Ops           | `make db-migrate-prod`       | Alembic migrations (one-shot)                                |
| 5. Ops           | `make deployments-prod`      | Prefect work pools + deployments (one-shot)                  |
| 6. Observability | `make up-prod-observability` | `prometheus`, `grafana`, `loki`, ...                         |
| 7. All-in-one    | `make up-prod-all`           | Steps 2 + 3 + 6 with 60s sleep between stateful and platform |

The API performs startup readiness checks against `postgres`, `redis`, and `label-studio`.
If any dependency is unreachable, the container exits with code 1 so the orchestrator
restarts it after a delay. This replaces cross-project `depends_on` which is silently
ignored across separate Compose projects.

The same split manifests are used for pre-release and production. Set
`APP_CONFIG_PROFILE=pre-release` for the deployable test/acceptance environment
and `APP_CONFIG_PROFILE=prod` for production. Use different Compose project
names, `PLATFORM_NETWORK_NAME`, credentials, URLs, and host data paths so the
environments cannot share state accidentally. The `test` API profile remains
unit/integration-test-only and is never deployed.

Run `make check-config` before starting or releasing a stack. It renders the
dev, local release-validation, pre-release, production, ops, and observability
manifests without starting containers.

### Migration Notes

- `make up` → now redirects to `make up-dev` (deprecated)
- `make up-stack` → now redirects to `make up-dev --scale web=0` (deprecated)
- `make updev` → unchanged (starts compose backend + local Vite on host)
- `make prod` → removed (was deprecated redirect to `make up-prod`)
- Local prod validation: `make up-prod` performs migrations and deployment registration.
- Split-stack production: run `make db-migrate-prod` and `make deployments-prod` explicitly.

`docker-compose.yaml` is at `infra/compose/docker-compose.yaml` and provides always-on
local infrastructure (postgres, minio, redis, prefect-server, label-studio,
sc-upstream, image-parser). Dev and prod overrides add API, web, and workers —
see [Dev vs Prod Modes](#dev-vs-prod-modes) above.

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

The stack is split across multiple Compose files:

- **Base infrastructure** (`docker-compose.yaml`): postgres, minio, redis, prefect-server, label-studio, sc-upstream, image-parser, profile-gated observability, profile-gated dcgm-exporter
- **Dev add-ons** (`docker-compose.dev.yaml`): api (hot-reload), web (Vite dev), prefect-worker-cpu, prefect-worker-gpu (profile), deployments-bootstrap, pgadmin
- **Prod add-ons** (`docker-compose.prod.yaml`): api (uvicorn --workers 4), isolated perspective-ws, web (nginx), prefect-worker-cpu, prefect-worker-gpu (profile)
- **Production stateful** (`production/compose.stateful.yaml`): postgres, minio, redis, label-studio (data plane)
- **Production platform** (`production/compose.platform.yaml`): prefect-server, api, web, prefect-worker-cpu, prefect-worker-gpu (app plane)
- **Production ops** (`production/compose.ops.yaml`): migrate, deployments (one-shot ops)
- **Production observability** (`production/compose.observability.yaml`): prometheus, grafana, loki, promtail, alertmanager, cadvisor, node-exporter, prefect-exporter, dcgm-exporter

Dev, local-prod, production-platform, and production-ops manifests define a
top-level `x-platform-environment` anchor. API, Perspective, workers, and ops
services inherit the same database, Prefect, Label Studio, MinIO/SC object-store,
Redis, LLM, and runtime endpoint settings; service-specific values are merged on top.

All services at a glance:

- **postgres** (:5432): PostgreSQL with pgvector, shared by API, Prefect, and Label Studio
- **minio** (:9000, :9001): S3-compatible artifact storage
- **redis** (no exposed port): Redis with appendonly persistence, used by API and workers
- **prefect-server** (:4200): Prefect 3 control plane
- **label-studio** (:8080): Annotation UI
- **api** (:8000): Platform HTTP API (dev: hot reload with bind mounts; prod: uvicorn workers with baked image)
- **perspective-ws** (:8001–:8004 internally): Isolated Perspective WebSocket container with four Supervisor-managed single-process Uvicorn instances; nginx distributes WebSockets with `least_conn`
- **web** (:5173 → :80): Frontend (dev: Vite dev server with bind mount; prod: nginx-served baked assets)
- **prefect-worker-cpu** (no exposed port): CPU-only Prefect worker. Orchestrates flows from `default-cpu` pool, executes CPU-bound work (DSPy, dataset drain). No GPU resources, no CUDA.
- **prefect-worker-gpu** (no exposed port, profile `gpu`): GPU Prefect worker for CUDA workloads. Starts via `--profile gpu` (Linux/NVIDIA only).
- **deployments-bootstrap** (dev-only): One-shot service that creates work pools and registers flow deployments.
- **pgadmin** (:5050, dev-only): Optional PostgreSQL admin UI
- **migrate** (ops profile, one-shot): Runs Alembic migrations in production.
- **deployments** (ops profile, one-shot): Creates Prefect work pools and applies flow deployments.

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
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml --profile observability up -d
```

This brings up everything in the base stack plus:

| Service          | Port  | Purpose                                      |
| ---------------- | ----- | -------------------------------------------- |
| Prometheus       | :9090 | Operations metrics scrape target             |
| Grafana          | :3000 | Dashboards (admin/admin)                     |
| Loki             | :3100 | Log aggregation API                          |
| Promtail         | —     | Docker-container log collector               |
| Alertmanager     | :9093 | Alert routing (dev-null receiver by default) |
| cAdvisor         | —     | Container resource metrics (scraped :8080)   |
| Node Exporter    | —     | Host-level metrics (scraped :9100)           |
| Prefect Exporter | —     | Prefect server health (scraped :8000)        |

Prometheus scrape targets: `api`, `image-parser`, `gpu-worker`, `prefect-exporter`, `alertmanager`, `cadvisor`, `node-exporter`, `dcgm-exporter`, and self.

### GPU Monitoring (Linux / NVIDIA only)

```bash
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml --profile gpu up -d dcgm-exporter
```

Or combine both profiles:

```bash
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml --profile observability --profile gpu up -d
```

The DCGM exporter (`nvidia/dcgm-exporter`) requires an NVIDIA GPU and the NVIDIA Container Toolkit on the host. On macOS / non-NVIDIA hosts the `gpu` profile is unavailable and the stack operates normally without GPU metrics.

### Alert Rules

Six Prometheus alert rules are defined in `observability/prometheus/alert-rules.yml` and loaded by Prometheus at startup via `rule_files`. The file is bind-mounted into the Prometheus container alongside `prometheus.yml`. All alerts carry `severity` (critical/warning) and `group: finetune` labels.

| Alert                 | Condition                                    | For | Severity |
| --------------------- | -------------------------------------------- | --- | -------- |
| `GPUWorkerDown`       | `up{job="gpu-worker"} == 0`                  | 2m  | critical |
| `PrefectExporterDown` | `up{job="prefect-exporter"} == 0`            | 2m  | warning  |
| `QueueBacklogHigh`    | `prefect_work_queue_depth > 100`             | 5m  | warning  |
| `GPUWorkerOOM`        | GPU worker container restarts > 3 in 15m     | 1m  | critical |
| `DcgmGpuMemoryHigh`   | GPU FB memory > 90% (skipped if DCGM absent) | 5m  | warning  |
| `ServiceRestartLoop`  | Any platform service restarts > 5 in 10m     | 1m  | critical |

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

| Label       | Source                      | Example values                                                               |
| ----------- | --------------------------- | ---------------------------------------------------------------------------- |
| `service`   | Container name (normalized) | `api`, `gpu-worker`, `prefect-worker`, `prefect-exporter`, `loki`, `grafana` |
| `container` | Container name (raw)        | `api`, `gpu-worker`                                                          |
| `env`       | Static (pipeline stage)     | `finetune`                                                                   |
| `level`     | JSON field extraction       | `info`, `warn`, `error`, `debug`                                             |

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
