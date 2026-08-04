# INFRA KNOWLEDGE BASE

## OVERVIEW

Operational manifests for local Compose smoke runs and minikube/Kubeflow deployment. Infra is runnable, but defaults are smoke-oriented and storage is ephemeral.

## WHERE TO LOOK

| Task                    | Location                              | Notes                                                                                                           |
| ----------------------- | ------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Compose infrastructure  | `compose/docker-compose.yaml`         | Local PostgreSQL, MinIO, Redis, Prefect, Label Studio, and optional observability                               |
| Compose development     | `compose/docker-compose.dev.yaml`     | Local API, web, workers, SC runtimes, preparation, and pgAdmin; layer on the infrastructure file                |
| Compose split stack     | `compose/production/`                 | `compose.stateful.yaml`, `compose.platform.yaml`, `compose.ops.yaml`, `compose.observability.yaml` (production) |
| Compose usage           | `compose/README.md`                   | Up/down command                                                                                                 |
| K8s base apply          | `k8s/kustomization.yaml`              | Namespace + base resources                                                                                      |
| K8s bootstrap docs      | `k8s/README.md`                       | Apply + verify steps                                                                                            |
| Namespace / RBAC        | `k8s/namespace.yaml`, `k8s/rbac.yaml` | API service account can manage `pytorchjobs`                                                                    |
| Runtime config          | `k8s/configmap.yaml`                  | Local cluster example; sets `APP_CONFIG_PROFILE=dev`                                                            |
| Secrets template        | `k8s/secret.example.yaml`             | Copy to `secret.yaml` and edit                                                                                  |
| In-cluster dependencies | `k8s/postgres.yaml`, `k8s/minio.yaml` | Both use `emptyDir` today                                                                                       |
| API deploy              | `k8s/api-deployment.yaml`             | Uses `finetune-api:latest`                                                                                      |
| Operator smoke job      | `k8s/pytorchjob-smoke.yaml`           | Requires Kubeflow Training Operator CRD                                                                         |

## WORK POOL LAYOUT

The platform uses two Prefect work pools, each with a dedicated Dockerfile:

| Pool          | Service              | GPU | Dockerfile                               |
| ------------- | -------------------- | --- | ---------------------------------------- |
| `default-cpu` | `prefect-worker-cpu` | No  | `apps/api/Dockerfile.prefect-worker-cpu` |
| `default-gpu` | `prefect-worker-gpu` | Yes | `apps/api/Dockerfile.prefect-worker-gpu` |

Both pools and platform-owned deployments are prepared by the one-shot
`prepare-platform` service before the API starts:

```yaml
uv run --directory apps/api python scripts/prepare_platform.py
```

- The GPU worker container (`prefect-worker-gpu`) is **profile-gated** (`profiles: [gpu]`) and only starts when `--profile gpu` is passed to `docker compose up`.
- On macOS / non-NVIDIA hosts the GPU worker is simply omitted; the CPU pool handles all orchestration.

### GPU Worker Race Warning (Host vs Compose)

When running the GPU worker **on the host** (outside Compose) simultaneously with the Compose stack, the host worker can register itself with the same `default-gpu` work pool and steal flow runs from the containerized worker. To avoid this:

- Set `PREFECT_WORKER_NAME` to a unique value on each worker instance.
- Or use separate work queues within the pool (`gpu-compose`, `gpu-host`) and target flows explicitly.
- Or stop the host worker when developing with the Compose stack.

## CONVENTIONS

- Namespace is always `finetune`.
- Kubernetes deploys expect `finetune-config` ConfigMap and `finetune-secrets` Secret.
- Dev profile means Postgres + MinIO + in-cluster Kubeflow client wiring.
- Local Compose uses the same broad service names (`postgres`, `minio`, `api`) as the app config expects.
- Production split-stack uses 4 independent Compose projects sharing an external `finetune-prod` network:
  - `finetune-stateful` (postgres, minio, redis, label-studio)
  - `finetune-platform` (prefect-server, api, web, workers)
  - `finetune-ops` (platform preparation — one-shot)
  - `finetune-observability` (prometheus, grafana, loki, exporters)
- Deployed pre-release uses the exact same split-stack manifests, released
  image digests, health waits, and startup workflow as production, with
  `APP_CONFIG_PROFILE=pre-release` and isolated test credentials, URLs, data
  paths, and Compose project/network names. The overlays under
  `compose/pre-release/` are workstation-only local acceptance helpers.

## ANTI-PATTERNS

- Don’t use `secret.example.yaml` values outside smoke/local testing.
- Don’t treat `emptyDir` Postgres/MinIO volumes as durable; data vanishes on pod restart.
- Don’t apply `pytorchjob-smoke.yaml` before verifying `pytorchjobs.kubeflow.org` exists.
- Don’t forget to make the `finetune-api:latest` image available to the cluster (`minikube image load` or real registry).

## COMMANDS

```bash
# Compose
docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml up -d

# K8s
kubectl apply -k infra/k8s
cp infra/k8s/secret.example.yaml infra/k8s/secret.yaml
kubectl apply -f infra/k8s/secret.yaml
kubectl -n finetune get pods,svc
kubectl get crd pytorchjobs.kubeflow.org
kubectl apply -f infra/k8s/pytorchjob-smoke.yaml
```

## GOTCHAS

- Kubeflow webhook/operator must be healthy before creating `PyTorchJob` resources.
- MinIO exposes both API (`9000`) and console (`9001`).
- Host port conflicts are easy in compose (`5432`, `8000`, `9000`, `9001`).
