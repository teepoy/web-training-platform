# Production Docker Compose Deployment

This guide describes a single-host production deployment. For high availability,
multiple GPU nodes, or independent horizontal scaling, use Kubernetes or another
container orchestrator instead.

## Deployment Boundaries

Use four independently managed Compose projects:

| Project       | Services                                           | Lifecycle                             |
| ------------- | -------------------------------------------------- | ------------------------------------- |
| Stateful      | PostgreSQL, MinIO, Redis, Label Studio             | Long-lived; backed up before upgrades |
| Platform      | API, web, Prefect server, workers                  | Released with application versions    |
| Ops           | Migrations, Prefect deployments                    | Run once per release                  |
| Observability | Prometheus, Grafana, Loki, Alertmanager, exporters | Upgraded independently                |

The repository provides split production manifests under
`infra/compose/production/`:

- `compose.stateful.yaml`
- `compose.platform.yaml`
- `compose.ops.yaml`
- `compose.observability.yaml`

The former combined local release-validation stack was removed. Production and
pre-release now have one source of truth: the split manifests above.

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

The values committed in `infra/compose/docker-compose.yaml` are local
development defaults and are unrelated to the production manifests.

## Host Preparation

Install Docker Engine with the Compose plugin. For GPU workers, also install the
NVIDIA driver and NVIDIA Container Toolkit.

Create a shared network used by the four projects:

```bash
docker network create finetune-prod
```

Set `PLATFORM_NETWORK_NAME=finetune-prod` in every environment file. For a
pre-release deployment, use an isolated name such as
`finetune-pre-release`; do not attach pre-release services to the production
network.

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
`prefect-server:4200`, `label-studio:8080`, and `grafana:3000` as needed. If
operators need the MinIO console, expose `minio:9001` through a separate
TLS-protected, authenticated admin hostname or a private VPN/tunnel. Keep the
MinIO API on `minio:9000` private unless an external S3 client explicitly
requires access; neither MinIO endpoint is published by the supplied manifests.

The application does not create or guess operator-console addresses. To show a
link under `Admin > Infrastructure`, configure `OPERATOR_PREFECT_UI_URL` and/or
`OPERATOR_MINIO_CONSOLE_URL` in the platform environment. These optional values
must be HTTPS URLs. Leave either value empty to hide its launch action. The
target still needs its own authorization, enforced by an authenticated reverse
proxy or a private VPN; being an application administrator does not grant
Prefect or MinIO access. Label Studio remains a contextual action on supported
Dataset pages and is not added to the global application or Admin navigation.

For workstation acceptance of production-built images, use the local
pre-release overlays instead of adding ports or build directives to these
production manifests:

```bash
make init-pre-release-local-env
make up-pre-release-local
```

The command forces the `pre-release` API profile, builds every application and
runtime service from its production Docker target, and uses isolated Compose
projects, network, and named volumes. See
`infra/compose/pre-release/env.example` for the loopback endpoints. The example
credentials must be replaced before running on a shared host.

For a deployed pre-release environment, do not use those overlays. Prepare
isolated stateful, platform, and observability env files under
`/srv/finetune-pre-release/`, reference the candidate production image digests,
and run:

```bash
make up-pre-release
```

This invokes the same manifests, health waits, preparation step, and startup
order as `make up-prod-all`. Only environment inputs and Compose project/network
names differ.

## Configuration

Data environment:

```dotenv
PLATFORM_NETWORK_NAME=finetune-prod
POSTGRES_USER=finetune
POSTGRES_PASSWORD=<strong-password>
MINIO_ROOT_USER=<access-key>
MINIO_ROOT_PASSWORD=<strong-secret-key>
```

Platform environment:

```dotenv
APP_CONFIG_PROFILE=prod
PLATFORM_NETWORK_NAME=finetune-prod
FRONTEND_URL=https://finetune.example.com
JWT_SECRET_KEY=<random-secret-at-least-32-bytes>
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
SC_UPSTREAM_DATA_DIR=/srv/finetune/platform/sc-upstream
IMAGE_PARSER_DATA_DIR=/srv/finetune/platform/image-parser
IMAGE_SOURCE_PROFILES_JSON={"sc_upstream":{"provider":"sc_upstream"}}
SC_UPSTREAM_IMAGE_SOURCE_PROFILE=sc_upstream
SC_COMPAT_IMAGE_SOURCE_PROFILE=sc_upstream
PREFECT_SERVER_MEMORY=4g
API_MEMORY=8g
API_SHM_SIZE=1g
SC_DATA_PROVIDER_WORKER_COUNT=4
SC_DATA_PROVIDER_CONTAINER_MEMORY_LIMIT_MB=6144
SC_DATA_PROVIDER_SHM_SIZE=1g
WEB_MEMORY=1g
CPU_WORKER_MEMORY=8g
CPU_WORKER_SHM_SIZE=1g
GPU_WORKER_MEMORY=16g
GPU_WORKER_SHM_SIZE=2g
SC_UPSTREAM_MEMORY=8g
SC_UPSTREAM_SHM_SIZE=1g
IMAGE_PARSER_MEMORY=32g
IMAGE_PARSER_SHM_SIZE=2g
PLATFORM_PREPARE_MEMORY=2g
```

`IMAGE_SOURCE_PROFILES_JSON` is the deployment-owned patch archive resolver
registry. A mounted local/SMB archive may be added with
`{"provider":"sc_patch_zip_folder","root":"/data/<mounted-directory>"}`; mount
that directory read-only into the image-parser container. Dataset metadata stores
only the chosen profile name, never the root path or credentials. The compatibility
profile must name one entry in the registry, and providers never fall back to a
different entry after a failure.

`SC_UPSTREAM_IMAGE_SOURCE_PROFILE` is the API-owned binding for datasets created
from the direct SC preview/import flow. It must name the intended upstream entry in
`IMAGE_SOURCE_PROFILES_JSON`; browsers never choose or submit this deployment-owned
name. Versioned Source Discovery import profiles continue to carry their own explicit
`image_source_profile` setting.

SC training does not call the shared image-parser HTTP/gRPC service. The GPU worker
starts the baked `/usr/local/bin/image-parser-batch` process once per materialization
and sends ordered, bounded protobuf batches over stdin/stdout. Configure its per-job
cache with `SC_TRAINING_IMAGE_PARSER_CACHE_SIZE_MB` (default `256`). If a profile uses
`sc_patch_zip_folder`, the same `${IMAGE_PARSER_DATA_DIR}` is mounted read-only at
`/data` in the GPU worker, so the profile root must use that shared absolute path.

All service ceilings use `deploy.resources.limits.memory`, which is honored by
current Docker Compose without requiring Swarm mode. Do not reintroduce the
legacy service-level `mem_limit` key.

For the deployable test/acceptance environment, copy all three production env
examples and set `APP_CONFIG_PROFILE=pre-release`, test-environment public URLs,
unique credentials, separate host data paths, and
`PLATFORM_NETWORK_NAME=finetune-pre-release`. The `test` profile is reserved
for automated tests using SQLite and memory storage and must not be deployed.

Stateful data paths and resource limits can also be set in the data
environment file:

```dotenv
POSTGRES_DATA_DIR=/srv/finetune/data/postgres
POSTGRES_MEMORY=8g
POSTGRES_SHM_SIZE=1g
MINIO_DATA_DIR=/srv/finetune/data/minio
MINIO_MEMORY=4g
MINIO_SHM_SIZE=512m
REDIS_DATA_DIR=/srv/finetune/data/redis
REDIS_MEMORY=2g
REDIS_SHM_SIZE=256m
REDIS_MAXMEMORY=1536mb
REDIS_MAXMEMORY_POLICY=allkeys-lru
LABEL_STUDIO_DATA_DIR=/srv/finetune/data/label-studio
LABEL_STUDIO_MEMORY=4g
LABEL_STUDIO_SHM_SIZE=512m
```

Observability environment:

```dotenv
PLATFORM_NETWORK_NAME=finetune-prod
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<strong-password>
ALERTMANAGER_CONFIG_PATH=/srv/finetune/observability/alertmanager.yml
PROMETHEUS_MEMORY=2g
GRAFANA_MEMORY=1g
LOKI_MEMORY=2g
PROMTAIL_MEMORY=512m
ALERTMANAGER_MEMORY=512m
CADVISOR_MEMORY=1g
NODE_EXPORTER_MEMORY=256m
PREFECT_EXPORTER_MEMORY=1g
DCGM_EXPORTER_MEMORY=1g
```

The supplied platform manifest requires credentials for the SC patch and review
buckets. Public URLs such as `PREFECT_UI_URL` and
`LABEL_STUDIO_EXTERNAL_URL` must use externally reachable HTTPS hostnames, not
`localhost`.

`OPERATOR_PREFECT_UI_URL` and `OPERATOR_MINIO_CONSOLE_URL` are optional public
operator-console URLs consumed by the web container at startup. They are not
service-discovery endpoints and must never contain credentials. The web image
rejects configured values that are not HTTPS or contain unsafe URL characters.

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

From a repository checkout, `make check-config` renders every supported local
and split-stack variant with the committed example files. It also compares the
rendered pre-release and production projects. The check permits lower resource
limits, local build metadata, loopback ports, image names, and different volume
sources, while requiring identical services, commands, dependency conditions,
health checks, environment keys, shared environment values, mount targets, and
other runtime behavior. Credentials, public URLs, database connection strings,
and the selected application profile remain environment-specific.

Build and publish the four application images from these Dockerfiles:

| Variable                    | Dockerfile target                                       |
| --------------------------- | ------------------------------------------------------- |
| `FINETUNE_API_IMAGE`        | `apps/api/Dockerfile`, target `prod`                    |
| `FINETUNE_WEB_IMAGE`        | `apps/web/Dockerfile`, target `prod`                    |
| `FINETUNE_CPU_WORKER_IMAGE` | `apps/api/Dockerfile.prefect-worker-cpu`, target `prod` |
| `FINETUNE_GPU_WORKER_IMAGE` | `apps/api/Dockerfile.prefect-worker-gpu`, target `prod` |

## Split-Stack Startup

Manage the supplied split manifests with distinct project names:

```bash
# 1. Create the shared network
make create-prod-network

# 2. Start the stateful data plane
make up-prod-stateful

# 3. Prepare database, MinIO, and Prefect
make prepare-platform-prod

# 4. Start the app platform
make up-prod-platform

# 5. Start observability
make up-prod-observability

# Or use the generic production wrapper
make up-prod-all
```

The two complete deployed release commands are therefore:

```bash
make up-pre-release  # pre-release env files and isolated project/network
make up-prod-all     # production env files and production project/network
```

The API performs read-only startup checks against the database revision, MinIO,
Prefect, Redis, and Label Studio. If any dependency is unavailable or stale,
the container exits with code 1
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
5. Run `make prepare-platform-prod` once from the new API image.
6. Recreate API, web, and workers.
7. Run readiness and smoke checks.
8. Monitor errors, queue depth, and worker health.

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
