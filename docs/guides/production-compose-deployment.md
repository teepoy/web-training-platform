# Production Docker Compose Deployment

This guide describes a single-host production deployment. For high availability,
multiple GPU nodes, or independent horizontal scaling, use Kubernetes or another
container orchestrator instead.

## Deployment Boundaries

Use four independently managed Compose projects:

| Project | Services | Lifecycle |
| --- | --- | --- |
| Stateful | PostgreSQL, MinIO, Redis, Label Studio | Long-lived; backed up before upgrades |
| Platform | API, web, Prefect server, workers | Released with application versions |
| Ops | Migrations, Prefect deployments | Run once per release |
| Observability | Prometheus, Grafana, Loki, Alertmanager, exporters | Upgraded independently |

The repository provides split production manifests under
`infra/compose/production/`:

- `compose.stateful.yaml`
- `compose.platform.yaml`
- `compose.ops.yaml`
- `compose.observability.yaml`

The older base plus prod override files (`docker-compose.yaml` + `docker-compose.prod.yaml`)
still deploy services as one logical project and contain literal development credentials.
Use those files for local validation, not as the final production manifests.

## Required Hardening

Before deployment:

- Replace all default PostgreSQL, MinIO, Grafana, and Label Studio credentials.
- Remove public port mappings for PostgreSQL, MinIO API, Redis, Loki, and
  Prometheus unless an external firewall explicitly restricts them.
- Put TLS termination and authentication in front of web, API, Prefect,
  Label Studio, Grafana, and the MinIO console.
- Use immutable image tags or digests. Do not deploy `latest`.
- Store secrets outside Git using protected environment files, Docker secrets,
  or a secrets manager.
- Use host paths or managed volumes on storage designed for durability.
- Configure off-host PostgreSQL and object-storage backups.
- Configure a real Alertmanager receiver.

The values currently committed in `infra/compose/docker-compose.yaml` and
`infra/compose/docker-compose.prod.yaml` are development defaults.

## Host Preparation

Install Docker Engine with the Compose plugin. For GPU workers, also install the
NVIDIA driver and NVIDIA Container Toolkit.

Create a shared network used by the three projects:

```bash
docker network create finetune-prod
```

Create deployment directories outside the repository:

```text
/srv/finetune/
  data/
  platform/
  observability/
  backups/
```

Restrict secret files:

```bash
chmod 600 /srv/finetune/*/.env
```

The supplied split manifests join this external network and provide stable
aliases such as `postgres`, `minio`, and `prefect-server`.

The manifests intentionally publish no host ports. Run a TLS reverse proxy on
the `finetune-prod` network and route public hostnames to `web:80`, `api:8000`,
`prefect-server:4200`, `label-studio:8080`, and `grafana:3000` as needed.

## Configuration

Data environment:

```dotenv
POSTGRES_USER=finetune
POSTGRES_PASSWORD=<strong-password>
MINIO_ROOT_USER=<access-key>
MINIO_ROOT_PASSWORD=<strong-secret-key>
```

Platform environment:

```dotenv
DATABASE_URL=postgresql+asyncpg://finetune:<password>@postgres:5432/finetune
PREFECT_DATABASE_URL=postgresql+asyncpg://finetune:<password>@postgres:5432/prefect
PREFECT_UI_URL=https://prefect.example.com
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=<access-key>
MINIO_SECRET_KEY=<secret-key>
MINIO_BUCKET=finetune-artifacts
SC_PATCH_S3_ACCESS_KEY=<access-key>
SC_PATCH_S3_SECRET_KEY=<secret-key>
SC_REVIEW_S3_ACCESS_KEY=<access-key>
SC_REVIEW_S3_SECRET_KEY=<secret-key>
POSTGRES_USER=finetune
POSTGRES_PASSWORD=<strong-password>
LABEL_STUDIO_IMAGE=heartexlabs/label-studio:<immutable-tag>
LABEL_STUDIO_USERNAME=<admin-email>
LABEL_STUDIO_PASSWORD=<strong-password>
LABEL_STUDIO_API_KEY=<token>
LABEL_STUDIO_EXTERNAL_URL=https://labels.example.com
LABEL_STUDIO_DATABASE_URL=postgresql+asyncpg://finetune:<password>@postgres:5432/labelstudio
FINETUNE_API_IMAGE=registry.example.com/finetune-api:<release>
FINETUNE_WEB_IMAGE=registry.example.com/finetune-web:<release>
FINETUNE_CPU_WORKER_IMAGE=registry.example.com/finetune-cpu-worker:<release>
FINETUNE_GPU_WORKER_IMAGE=registry.example.com/finetune-gpu-worker:<release>
PLATFORM_DATA_DIR=/srv/finetune/platform/data
PLATFORM_LOG_DIR=/srv/finetune/platform/logs
SC_UPSTREAM_DATA_DIR=/srv/finetune/platform/sc-upstream
SC_UPSTREAM_LOG_DIR=/srv/finetune/platform/logs/sc-upstream
IMAGE_PARSER_DATA_DIR=/srv/finetune/platform/image-parser
IMAGE_PARSER_LOG_DIR=/srv/finetune/platform/logs/image-parser
API_MEMORY=8g
API_SHM_SIZE=1g
WEB_MEMORY=1g
CPU_WORKER_MEMORY=8g
CPU_WORKER_SHM_SIZE=1g
GPU_WORKER_MEMORY=16g
GPU_WORKER_SHM_SIZE=2g
SC_UPSTREAM_MEMORY=8g
SC_UPSTREAM_SHM_SIZE=1g
IMAGE_PARSER_MEMORY=32g
IMAGE_PARSER_SHM_SIZE=2g
```

Stateful data paths and resource limits can also be set in the data
environment file:

```dotenv
POSTGRES_DATA_DIR=/srv/finetune/data/postgres
POSTGRES_LOG_DIR=/srv/finetune/data/logs/postgres
POSTGRES_MEMORY=8g
POSTGRES_SHM_SIZE=1g
MINIO_DATA_DIR=/srv/finetune/data/minio
MINIO_LOG_DIR=/srv/finetune/data/logs/minio
MINIO_MEMORY=4g
MINIO_SHM_SIZE=512m
REDIS_DATA_DIR=/srv/finetune/data/redis
REDIS_LOG_DIR=/srv/finetune/data/logs/redis
REDIS_MEMORY=2g
REDIS_SHM_SIZE=256m
REDIS_MAXMEMORY=1536mb
REDIS_MAXMEMORY_POLICY=allkeys-lru
LABEL_STUDIO_DATA_DIR=/srv/finetune/data/label-studio
LABEL_STUDIO_LOG_DIR=/srv/finetune/data/logs/label-studio
LABEL_STUDIO_MEMORY=4g
LABEL_STUDIO_SHM_SIZE=512m
```

Observability environment:

```dotenv
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<strong-password>
ALERTMANAGER_CONFIG_PATH=/srv/finetune/observability/alertmanager.yml
```

The supplied platform manifest requires credentials for the SC patch and review
buckets. Public URLs such as `PREFECT_UI_URL` and
`LABEL_STUDIO_EXTERNAL_URL` must use externally reachable HTTPS hostnames, not
`localhost`.

Prefer managed PostgreSQL and S3-compatible object storage where available. In
that case, omit local `postgres` and `minio` services and use provider endpoints.

Do not assume shell variables override values written literally under a Compose
service's `environment` section. The current repository files must be replaced
or overlaid with variable-based production configuration.

Use separate protected environment files:

```text
/srv/finetune/data/.env
/srv/finetune/platform/.env
/srv/finetune/observability/.env
```

Render each manifest with its environment file before starting services. Compose
will fail fast when a required value is missing.

Build and publish the four application images from these Dockerfiles:

| Variable | Dockerfile target |
| --- | --- |
| `FINETUNE_API_IMAGE` | `apps/api/Dockerfile`, target `prod` |
| `FINETUNE_WEB_IMAGE` | `apps/web/Dockerfile`, target `prod` |
| `FINETUNE_CPU_WORKER_IMAGE` | `apps/api/Dockerfile.prefect-worker-cpu`, target `prod` |
| `FINETUNE_GPU_WORKER_IMAGE` | `apps/api/Dockerfile.prefect-worker-gpu`, target `prod` |

## Validate The Current Bundle

The existing combined stack can be used on a private host to validate images and
runtime integration while the hardened split overlays are being prepared:

```bash
docker compose \
  -p finetune-prod \
  -f infra/compose/docker-compose.yaml \
  -f infra/compose/docker-compose.prod.yaml \
  config

docker compose \
  -p finetune-prod \
  -f infra/compose/docker-compose.yaml \
  -f infra/compose/docker-compose.prod.yaml \
  build
```

Review the rendered configuration carefully. Do not expose this stack to
production traffic while default credentials or `localhost` public URLs remain.

Start stateful services first:

```bash
docker compose \
  -p finetune-prod \
  -f infra/compose/docker-compose.yaml \
  -f infra/compose/docker-compose.prod.yaml \
  up -d postgres minio prefect-server label-studio redis
```

Run database migrations as a one-shot production container:

```bash
docker compose \
  -p finetune-prod \
  -f infra/compose/docker-compose.yaml \
  -f infra/compose/docker-compose.prod.yaml \
  run --rm api \
  /bin/sh -lc 'cd /app/apps/api && uv run --no-dev alembic upgrade head'
```

Create Prefect pools and apply deployments:

```bash
docker compose \
  -p finetune-prod \
  -f infra/compose/docker-compose.yaml \
  -f infra/compose/docker-compose.prod.yaml \
  run --rm api \
  /bin/sh -lc \
  'uv run --no-dev prefect work-pool create default-cpu --type process || true; uv run --no-dev prefect work-pool create default-gpu --type process || true'

docker compose \
  -p finetune-prod \
  -f infra/compose/docker-compose.yaml \
  -f infra/compose/docker-compose.prod.yaml \
  run --rm api \
  /bin/sh -lc 'cd /app/apps/api && uv run --no-dev ftapi deployments apply'
```

Start the application:

```bash
docker compose \
  -p finetune-prod \
  -f infra/compose/docker-compose.yaml \
  -f infra/compose/docker-compose.prod.yaml \
  up -d api web prefect-worker-cpu
```

On a Linux NVIDIA host, add the GPU profile:

```bash
docker compose \
  -p finetune-prod \
  -f infra/compose/docker-compose.yaml \
  -f infra/compose/docker-compose.prod.yaml \
  --profile gpu up -d prefect-worker-gpu dcgm-exporter
```

## Split-Stack Startup

Manage the supplied split manifests with distinct project names:

```bash
# 1. Create the shared network
make create-prod-network

# 2. Start the stateful data plane
make up-prod-stateful

# 3. Run ops (migrations + deployments)
make db-migrate-prod
make deployments-prod

# 4. Start the app platform
make up-prod-platform

# 5. Start observability
make up-prod-observability

# Or start everything in one shot (with 60s sleep between stateful and platform)
make up-prod-all
```

The API performs startup readiness checks against `postgres`, `redis`, and
`label-studio`. If any dependency is unreachable, the container exits with code 1
so the orchestrator restarts it. This replaces the silently ignored `depends_on`
that used to span across separate Compose projects.

Start GPU services on a Linux NVIDIA host:

```bash
docker compose \
  --env-file /srv/finetune/platform/.env \
  -p finetune-platform \
  -f infra/compose/production/compose.platform.yaml \
  --profile gpu up -d prefect-worker-gpu

docker compose \
  --env-file /srv/finetune/observability/.env \
  -p finetune-observability \
  -f infra/compose/production/compose.observability.yaml \
  --profile gpu up -d dcgm-exporter
```

The current Prometheus configuration still contains the legacy
`gpu-worker:8010` scrape target. Until the dashboards and alert rules are
migrated to Prefect-worker and DCGM metrics, expect the `GPUWorkerDown` alert to
be inaccurate and disable that alert in the production rule set.

## Verification

Verify containers and health endpoints:

```bash
docker compose -p finetune-stateful -f infra/compose/production/compose.stateful.yaml ps
docker compose -p finetune-platform -f infra/compose/production/compose.platform.yaml ps
docker compose -p finetune-observability -f infra/compose/production/compose.observability.yaml ps
curl --fail https://api.finetune.example.com/health
curl --fail https://api.finetune.example.com/ready
```

Then verify:

1. PostgreSQL and MinIO backups complete successfully.
2. The API can create and read a dataset.
3. Prefect shows both expected work pools and active workers.
4. A small training or prediction smoke job completes.
5. Prometheus targets are healthy and Grafana receives logs.
6. Alertmanager delivers a test alert to the configured receiver.

## Release Procedure

For each release:

1. Build and scan immutable images.
2. Back up PostgreSQL and verify object-storage replication or backup status.
3. Pull or load the new images on the host.
4. Render and review `docker compose config`.
5. Run Alembic migrations once.
6. Apply Prefect deployments from the new API image.
7. Recreate API, web, and workers.
8. Run readiness and smoke checks.
9. Monitor errors, queue depth, and worker health.

Do not recreate PostgreSQL or MinIO as part of a routine application release.

## Backup And Restore

PostgreSQL backups must include the `finetune`, `prefect`, and `labelstudio`
databases. Store dumps off-host and periodically perform a restore drill.

MinIO backup must cover all artifact, SC patch, and SC review buckets. Prefer
bucket versioning plus replication to another host or object-storage provider.
Copying a live Docker volume is not a reliable backup strategy.

Prometheus and Loki retention data is operationally useful but is not the
platform business source of truth. Back it up according to the required
incident-history retention period.

## Rollback

Application rollback:

1. Stop new job submissions if the release affects runtime contracts.
2. Reapply the previous immutable platform image tags.
3. Reapply the previous Prefect deployments.
4. Recreate API, web, and workers.
5. Run smoke checks before reopening traffic.

Database migrations require a specific rollback plan. Do not automatically run
Alembic downgrade in an incident. Prefer backward-compatible expand-and-contract
migrations so the previous application version can continue using the upgraded
schema. Restore PostgreSQL only when the migration is destructive and a tested
forward fix is not viable.
