# Compose Config

For production hardening, split-stack deployment, backup, release, and rollback
procedures, see
[`docs/guides/production-compose-deployment.md`](../../docs/guides/production-compose-deployment.md).
The deployable split manifests are:

- `production/compose.stateful.yaml`
- `production/compose.platform.yaml`
- `production/compose.ops.yaml`
- `production/compose.observability.yaml`

## Compose Modes

The repository separates canonical deployed releases from local override stacks:

| Mode                 | Command                     | Compose files                                    | Code source          |
| -------------------- | --------------------------- | ------------------------------------------------ | -------------------- |
| Dev                  | `make up-dev`               | infrastructure + dev                             | Bind-mounted source  |
| Local pre-release    | `make up-pre-release-local` | production manifests + local acceptance overlays | Locally built images |
| Deployed pre-release | `make up-pre-release`       | production manifests only                        | Released images      |
| Production           | `make up-prod-all`          | production manifests only                        | Same released images |

### How the files compose

There is one local development stack and one canonical release stack:

| Manifest                     | Role                           | Use alone?                        |
| ---------------------------- | ------------------------------ | --------------------------------- |
| `docker-compose.yaml`        | Local infrastructure           | Yes                               |
| `docker-compose.dev.yaml`    | Local application/runtime      | No; layer on local infrastructure |
| `production/compose.*.yaml`  | Canonical deployed split stack | Yes, as separate Compose projects |
| `pre-release/compose.*.yaml` | Workstation acceptance overlay | No; layer on production manifests |

The local base contains no application or SC runtime services. The pre-release
overlays state only local build, port, and volume differences from production.
Use `docker compose ... config` to inspect a merged result.

Configuration ownership is also split by concern:

- Compose manifests own container topology, commands, dependencies, mounts,
  health checks, and resource limits.
- `apps/api/config/*.yaml` owns application-profile defaults; Compose
  environment variables provide deployment-specific overrides.
- `x-platform-environment` is repeated where services run as separate Compose
  projects because YAML anchors are file-local. In particular, platform and
  one-shot ops manifests cannot share an anchor; `make check-config` enforces
  parity for the settings they must share.

### Base Infrastructure (local stacks)

`docker-compose.yaml` contains always-on infrastructure:

- **postgres** (`:5432`): PostgreSQL with pgvector
- **minio** (`:9000`, `:9001`): S3-compatible storage
- **redis** (`:6379`): Redis cache/coordination dependency
- **prefect-server** (`:4200`): Prefect 3 control plane
- **label-studio** (`:8080`): Annotation UI
- Profile `--profile observability`: Prometheus, Grafana, Loki, Promtail, Alertmanager, cAdvisor, Node Exporter, Prefect Exporter
- Profile `--profile gpu`: DCGM exporter

> **Production note:** The split-stack manifests separate stateful services
> (`postgres`, `minio`, `redis`, `label-studio`) into `compose.stateful.yaml`.
> `prefect-server` stays in `compose.platform.yaml` because it is stateless
> (its DB lives in the stateful project's postgres).

### Dev Mode (`make up-dev`)

Adds via `docker-compose.dev.yaml`:

- **api** with bind mounts + `uvicorn --reload`
- **sc-data-provider** with bind mounts and its isolated Uvicorn process
- **web** with bind mount + Vite dev server hot reload
- **prefect-worker-cpu** with bind mounts for flow code changes
- **prepare-platform** (ops profile): one-shot database, dev auth identity, MinIO, and Prefect preparation
- **pgadmin** (`:5050`): optional PostgreSQL admin UI
- **sc-upstream** with `watchfiles` reload for Python service and protobuf changes
- **image-parser** with Air reload for Go source changes
- Profile `--profile gpu`: GPU Prefect worker (Linux/NVIDIA only)

### Deployed Pre-release and Production

Deployed pre-release and production use the exact same four manifests under
`production/`. Prepare three isolated pre-release environment files, then run:

```bash
make up-pre-release
```

The default deployed pre-release paths are
`/srv/finetune-pre-release/{stateful,platform,observability}/.env`. Override
`PRE_RELEASE_STATEFUL_ENV`, `PRE_RELEASE_PLATFORM_ENV`, or
`PRE_RELEASE_OBSERVABILITY_ENV` when needed. The platform env must reference
the same candidate immutable image digests that will be promoted to prod.

The intended release-environment differences are deliberately narrow:

| Concern                        | Pre-release                                          | Production                                  |
| ------------------------------ | ---------------------------------------------------- | ------------------------------------------- |
| Application profile            | `pre-release`                                        | `prod`                                      |
| Application code               | Pulls candidate immutable image digests              | Promotes the accepted digests               |
| Service topology and commands  | Same production manifests                            | Canonical production manifests              |
| Dependencies and health checks | Same as production                                   | Canonical                                   |
| Capacity                       | May use lower memory, worker, and concurrency values | Sized for production load                   |
| Persistent storage source      | Explicit isolated durable test paths                 | Explicit durable production paths           |
| Public access                  | No host ports; test TLS reverse proxy                | No host ports; production TLS reverse proxy |
| Credentials and URLs           | Isolated test values                                 | Production secrets and public URLs          |
| Observability                  | Same manifest, optionally lower capacity             | Same manifest, production capacity          |

`make check-config` enforces identical deployed service membership and runtime
behavior across pre-release and prod.

### Local Pre-release Acceptance

The overlays under `infra/compose/pre-release/` are now workstation-only. They
add local builds, loopback ports, and project-scoped named volumes:

```bash
make init-pre-release-local-env
make up-pre-release-local
```

The default endpoints are:

| Service       | URL                      |
| ------------- | ------------------------ |
| Web           | `http://127.0.0.1:15173` |
| API           | `http://127.0.0.1:18000` |
| Prefect       | `http://127.0.0.1:14200` |
| Label Studio  | `http://127.0.0.1:18080` |
| MinIO console | `http://127.0.0.1:19001` |

Use `make verify-pre-release-local`, `make ps-pre-release-local`, and
`make logs-pre-release-local ARGS=api` for inspection. Enable the GPU worker
only on a compatible NVIDIA host:

```bash
make up-pre-release-local PRE_RELEASE_LOCAL_PROFILES="--profile gpu"
```

`infra/compose/pre-release/.env` is ignored by Git. The supplied `env.example`
credentials are safe only for a loopback-bound local machine; replace them
before using the stack on a shared host.

For production, these compatibility targets delegate to the same generic
release workflow used by `make up-pre-release`:

| Step             | Command                      | Description                                     |
| ---------------- | ---------------------------- | ----------------------------------------------- |
| 1. Network       | `make create-prod-network`   | Create shared `finetune-prod` network           |
| 2. Stateful      | `make up-prod-stateful`      | `postgres`, `minio`, `redis`, `label-studio`    |
| 3. Prepare       | `make prepare-platform-prod` | Migrations, MinIO policy, Prefect registrations |
| 4. Platform      | `make up-prod-platform`      | `prefect-server`, `api`, `web`, `workers`       |
| 5. Observability | `make up-prod-observability` | `prometheus`, `grafana`, `loki`, ...            |
| 6. All-in-one    | `make up-prod-all`           | Stateful, prepare, platform, and observability  |

The API performs read-only startup checks against the database revision, MinIO
buckets/ILM, Prefect pools/deployments, Redis, and Label Studio.
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
dev, local pre-release, deployed pre-release, production, ops, and observability
manifests without starting containers. It also runs
`scripts/check_compose_parity.py`, which rejects pre-release drift in service
sets, commands, dependencies, health checks, environment keys, mount targets,
shared environment values, or other runtime behavior. Lower resource limits,
environment-specific credentials and public URLs, local build metadata,
loopback ports, image names, and volume sources are intentional differences.

`docker-compose.yaml` is at `infra/compose/docker-compose.yaml` and provides always-on
local infrastructure (postgres, minio, redis, prefect-server, and label-studio).
`docker-compose.dev.yaml` owns all local application and runtime services.

Quick start:

```bash
# Dev mode (recommended for daily work)
make up-dev

# Production-shaped local acceptance
make init-pre-release-local-env
make up-pre-release-local

# Deployed pre-release (requires deployed pre-release env files)
make up-pre-release

# Actual split-stack production (requires production env files)
make up-prod-all

```

`make up-dev` starts the complete Compose development stack, including the
bind-mounted Vite service on `:5173`. Run `make seed-dev` separately when the
default demo datasets are needed.

## Services

The stack is split across multiple Compose files:

- **Local infrastructure** (`docker-compose.yaml`): postgres, minio, redis, prefect-server, label-studio, profile-gated observability, profile-gated dcgm-exporter
- **Local development** (`docker-compose.dev.yaml`): api, sc-data-provider, web, sc-upstream, image-parser, workers, prepare-platform (ops profile), pgadmin
- **Production stateful** (`production/compose.stateful.yaml`): postgres, minio, redis, label-studio (data plane)
- **Production platform** (`production/compose.platform.yaml`): prefect-server, api, web, prefect-worker-cpu, prefect-worker-gpu (app plane)
- **Production ops** (`production/compose.ops.yaml`): prepare-platform (one-shot ops)
- **Production observability** (`production/compose.observability.yaml`): prometheus, grafana, loki, promtail, alertmanager, cadvisor, node-exporter, prefect-exporter, dcgm-exporter

Dev, production-platform, and production-ops manifests define a top-level
`x-platform-environment` anchor. API, SC data-provider, workers, and ops
services inherit the same database, Prefect, Label Studio, MinIO/SC object-store,
Redis, LLM, and runtime endpoint settings; service-specific values are merged on top.

Every Compose service has an explicit memory ceiling using the current Compose
Spec form `deploy.resources.limits.memory`; the legacy `mem_limit` key is not
used. Each ceiling is configurable through the service-specific `*_MEMORY`
variable shown in the manifests. Use `docker compose ... config` to inspect the
effective limits after base, environment, profile, and pre-release overlays are
merged.

All services at a glance:

- **postgres** (:5432): PostgreSQL with pgvector, shared by API, Prefect, and Label Studio
- **minio** (:9000, :9001): S3-compatible artifact storage
- **redis** (no exposed port): Redis with appendonly persistence, used by API and workers
- **prefect-server** (:4200): Prefect 3 control plane
- **label-studio** (:8080): Annotation UI
- **api** (:8000): Platform HTTP API (dev: hot reload with bind mounts; prod: uvicorn workers with baked image)
- **sc-data-provider** (:8001): Isolated DuckDB SQL/Arrow/SSE service; the development overlay runs one hot-reloading process, while production uses four Uvicorn-managed workers sharing one listening socket
- **web** (:5173 → :80): Frontend (dev: Vite dev server with bind mount; prod: nginx-served baked assets)
- **prefect-worker-cpu** (no exposed port): CPU-only Prefect worker. Orchestrates flows from `default-cpu` pool, executes CPU-bound work (DSPy, dataset drain). No GPU resources, no CUDA.
- **prefect-worker-gpu** (no exposed port, profile `gpu`): GPU Prefect worker for CUDA workloads. Starts via `--profile gpu` (Linux/NVIDIA only).
- **prepare-platform** (one-shot): Applies migrations, prepares the development user/org for auth-disabled profiles, reconciles managed MinIO lifecycle rules, and creates Prefect pools/deployments under a global lock.
- **pgadmin** (:5050, dev-only): Optional PostgreSQL admin UI

## Notes

- Dev mode uses `uvicorn --reload` with bind mounts; release modes use baked images without source mounts.
- Release services run from the image's prebuilt `/app/.venv`. The dev API uses `uv run` to execute the bind-mounted workspace environment.
- The `web` service serves assets baked into the image (prod) or via Vite dev server (dev).
- Use `make up-dev` for the complete bind-mounted development stack.
- GPU profile (`--profile gpu`) requires Linux with NVIDIA GPU and NVIDIA Container Toolkit. On macOS/non-NVIDIA hosts, GPU workers are simply omitted.
- The API exposes `/health` for process liveness and `/ready` for database-backed readiness. Compose marks the API healthy only when `/ready` returns HTTP 200.
- `SC_DATA_PROVIDER_CONTAINER_MEMORY_LIMIT_MB` sets the Compose memory limit
  for the entire `sc-data-provider` container and defaults to `6144` MiB.
  `SC_DATA_PROVIDER_WORKER_COUNT` defaults to four in production and one in
  development. Each worker has an explicit 1 GiB DuckDB limit, a 1280 MiB
  connection-recycle watermark, and a 1536 MiB readiness RSS ceiling. Startup
  rejects worker/memory combinations that exceed the declared container limit.
- The object cache uses a 10 GiB high watermark, cleans down to 8 GiB, and is
  stored in the shared `sc-data-provider-cache` volume in development or below
  the platform data mount in release deployments.
- `SC_WAFER_MOCK_DEFECTS` controls both the inspection fixture and patch zip
  generation (300,000 by default); zip seeding validates the source defect IDs
  are the contiguous range `1..N` before uploading objects or metadata, then
  clears stale SC upstream inspection/zip metadata after the replacement
  succeeds.
- Dev services default `LOG_LEVEL` to `INFO`, so data-provider memory records
  are visible. Set `LOG_LEVEL=DEBUG` when additional diagnostics are
  needed.

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
