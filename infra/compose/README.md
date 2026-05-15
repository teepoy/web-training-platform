# Compose Config

`docker-compose.yaml` is now included at `infra/compose/docker-compose.yaml`.

Run:

```bash
docker compose -f infra/compose/docker-compose.yaml up -d
```

From repo root, equivalent Make targets:

```bash
make up
make updev
```

`make updev` is the recommended interactive dev entrypoint. It starts the
compose backend stack without the baked `web` container, ensures the default
mock dataset exists, and then runs the local Vite dev server on `:5173` for
hot reload and stable `/api` proxying to `localhost:8000`.

## Services

This stack includes:

- **postgres** (:5432): PostgreSQL with pgvector, shared by API, Prefect, and Label Studio
- **minio** (:9000, :9001): S3-compatible artifact storage
- **prefect-server** (:4200): Prefect 3 control plane
- **embedding** (:50051): Embedding gRPC service
- **gpu-worker** (:8010): GPU runtime API for train/predict/embed. On macOS/non-NVIDIA, starts with `gpu_info.available: false` and GPU workloads are unavailable but the service remains healthy.
- **label-studio** (:8080): Annotation UI
- **api** (:8000): Platform API. Health depends on all services; calls GPU worker via `GPU_WORKER_BASE_URL=http://gpu-worker:8010`.
- **prefect-worker**: CPU-only Prefect V2 worker. Orchestrates flows from `default-pool` / queue `optimize-llm-cpu`, executes CPU-bound work (DSPy, dataset drain), and delegates GPU work to the GPU worker via HTTP. No GPU resources, no CUDA, no exposed port.
- **web** (:5173 → :80): Pre-built web frontend (baked into image)
- **pgadmin** (:5050): Optional PostgreSQL admin UI

## V1 GPU Degradation (macOS / non-NVIDIA)

On macOS ARM64 or any environment without NVIDIA GPU support:

- The GPU worker container starts and reports `gpu_info.available: false` in its `/health` endpoint. The health check is best-effort: it uses `torch.cuda.is_available()` when torch exists, and falls back to `CUDA not available` when torch or `nvidia-smi` is missing.
- Training, prediction, and embedding endpoints return clear "GPU unavailable" errors rather than crashing or hanging.
- The rest of the stack (API, Prefect, Label Studio, database, object storage) operates normally.
- GPU metrics collection (DCGM exporter) is unavailable and is not required for basic operation.
- No NVIDIA host dependencies (`nvidia-container-toolkit`, `nvidia-smi`) are needed to start the stack.

To enable GPU metrics on Linux/NVIDIA hosts, start the exporter with the GPU profile:

```bash
docker compose -f infra/compose/docker-compose.yaml --profile gpu up -d dcgm-exporter
```

The `dcgm-exporter` service is profile-gated and does not start in the default compose stack.

## Notes

- Compose services run from the image's prebuilt `/app/.venv` and do not use `uv run` at container startup.
- The embedding image installs `torch` during image build, not at container startup.
- The `web` service serves assets baked into the image; it does not bind-mount `apps/web/dist`.
- Prefer `make updev` over the baked `web` container during daily development.
- The Prefect worker is CPU-only. It does not use CUDA, request GPU resources, or set NVIDIA environment variables.
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
