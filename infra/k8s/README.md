# K8s Config

This folder contains runnable Kubernetes manifests for minikube and Kubeflow integration.
The manifests mirror the docker-compose stack so both environments run the same services.

## Files

| File                        | What it deploys                                                                 |
| --------------------------- | ------------------------------------------------------------------------------- |
| `namespace.yaml`            | `finetune` namespace                                                            |
| `rbac.yaml`                 | API service account + role for `pytorchjobs`                                    |
| `configmap.yaml`            | Non-secret env vars (`APP_CONFIG_PROFILE`, Prefect/LS/embedding URLs)           |
| `secret.example.yaml`       | Copy to `secret.yaml` — DB URLs, MinIO creds, LS keys                           |
| `postgres.yaml`             | PostgreSQL (pgvector) with init script for `prefect` + `labelstudio` DBs        |
| `minio.yaml`                | MinIO (API :9000, console :9001)                                                |
| `prefect-server.yaml`       | Prefect 3 server (:4200)                                                        |
| `embedding.yaml`            | Embedding gRPC service (:50051)                                                 |
| `gpu-worker.yaml`           | GPU runtime API for train/predict/embed (:8010), requests `nvidia.com/gpu: 1`   |
| `label-studio.yaml`         | Label Studio (:8080)                                                            |
| `api-deployment.yaml`       | Platform API (:8000)                                                            |
| `platform-prepare-job.yaml` | One-shot migrations, MinIO policy, and Prefect registration                     |
| `prefect-worker.yaml`       | CPU-only Prefect V2 worker (orchestration, flow management, CPU queues)         |
| `pytorchjob-smoke.yaml`     | Manual Kubeflow smoke job                                                       |
| `kustomization.yaml`        | Kustomize entrypoint — applies all base resources                               |
| `observability/`            | Monitoring stack manifests (Prometheus, Grafana, Loki, Alertmanager, exporters) |

Legacy worker manifests have been removed. Prefect flows now run in-process
within `apps/api`.

## Service map (mirrors docker-compose)

```
postgres (:5432)          — shared by API, Prefect, Label Studio
minio (:9000, :9001)      — artifact storage
prefect-server (:4200)    — Prefect control plane
embedding (:50051)        — embedding gRPC service
gpu-worker (:8010)        — GPU runtime API (train/predict/embed)
label-studio (:8080)      — annotation UI
finetune-api (:8000)      — platform API
prefect-worker            — CPU-only Prefect V2 worker (no exposed port)
```

## Apply

```bash
# 1. Create secrets (edit values first!)
cp infra/k8s/secret.example.yaml infra/k8s/secret.yaml
# Edit secret.yaml with real credentials
kubectl apply -f infra/k8s/secret.yaml

# 2. Apply dependencies, run preparation, then start API/runtime workloads
make k8s-apply
```

## Verify

```bash
kubectl -n finetune get pods
kubectl -n finetune get svc
kubectl get crd pytorchjobs.kubeflow.org
```

If `pytorchjobs.kubeflow.org` is missing, install Kubeflow Training Operator first.

## Images

The following images must be available to the cluster (via registry or `minikube image load`):

| Image                 | Built from            | Notes |
| --------------------- | --------------------- | ----- |
| `finetune-api:latest` | `apps/api/Dockerfile` |       |

Third-party images (`pgvector/pgvector:pg16`, `prefecthq/prefect:3.6.25-python3.12`,
`minio/minio:RELEASE.2025-02-18T16-25-55Z`, `heartexlabs/label-studio:latest`) are
pulled from public registries.

## Notes

- All volumes use `emptyDir` — data is lost on pod restart. Use PVCs for persistence.
- The `LABEL_STUDIO_EXTERNAL_URL` in the configmap should be updated to the actual
  browser-accessible URL for your cluster (e.g. via Ingress or NodePort).
- The GPU worker requests `nvidia.com/gpu: 1`. On clusters without NVIDIA GPU support,
  the GPU worker pod will not schedule unless this resource request is removed or
  the node has GPU capacity.
- The GPU worker health endpoint degrades gracefully: if CUDA or `nvidia-smi` is
  unavailable, it still returns 200 with `gpu_info.available: false`.
- The Prefect worker is CPU-only and must not have `nvidia.com/gpu` resource requests
  or NVIDIA environment variables.
- API, workers, and orchestration run as separate services in both dev and prod topologies.
- The API never applies migrations or external configuration. `make k8s-apply`
  waits for dependencies, runs `platform-prepare-job.yaml`, then applies the API
  and runtime workloads. `make k8s-prepare` reruns that one-shot for an upgrade.

## Observability

The `observability/` directory contains a self-contained Prometheus + Grafana + Loki
monitoring stack. Observability is **opt-in** — the base `kubectl apply -k infra/k8s`
deploys only the platform services, not the monitoring stack.

### Apply (self-contained path — no CRD dependencies)

```bash
# Render and validate
kubectl kustomize infra/k8s/observability

# Apply the observability stack independently
kubectl apply -k infra/k8s/observability
```

This deploys Prometheus, Alertmanager, Loki, Promtail, Grafana, Prefect exporter,
and DCGM exporter. All scrape targets use static K8s DNS — no Prometheus Operator
CRDs are required.

### Service map (observability)

```
prometheus (:9090)        — metrics collection and alerting
grafana (:3000)           — dashboards (admin/admin)
loki (:3100)              — log aggregation API
alertmanager (:9093)      — alert routing (dev-null receiver)
prefect-exporter (:8000)  — Prefect server health metrics
dcgm-exporter (:9400)     — NVIDIA GPU metrics (GPU nodes only)
```

### Components

| Component        | Port  | Image                                    | Notes                                    |
| ---------------- | ----- | ---------------------------------------- | ---------------------------------------- |
| Prometheus       | :9090 | `prom/prometheus:v2.55.0`                | Static scrape configs via K8s DNS        |
| Grafana          | :3000 | `grafana/grafana:11.5.0`                 | admin/admin, Prometheus + Loki pre-wired |
| Loki             | :3100 | `grafana/loki:3.3.0`                     | In-memory storage, single replica        |
| Promtail         | —     | `grafana/promtail:3.3.0`                 | DaemonSet, ships pod logs to Loki        |
| Alertmanager     | :9093 | `prom/alertmanager:v0.28.0`              | Dev-null receiver; configure for prod    |
| Prefect exporter | :8000 | `python:3.12-slim`                       | Custom health exporter for Prefect       |
| DCGM exporter    | :9400 | `nvcr.io/nvidia/k8s/dcgm-exporter:4.0.0` | GPU nodes only via node affinity         |

### Scrape targets

Prometheus scrapes these services via cluster DNS:

| Target                  | Path       | Interval |
| ----------------------- | ---------- | -------- |
| `finetune-api:8000`     | `/metrics` | 15s      |
| `image-parser:8090`     | `/metrics` | 15s      |
| `gpu-worker:8010`       | `/metrics` | 15s      |
| `prefect-exporter:8000` | `/metrics` | 15s      |
| `alertmanager:9093`     | `/metrics` | 15s      |
| `dcgm-exporter:9400`    | `/metrics` | 15s      |

### Prometheus Operator / kube-prometheus-stack (optional)

For ServiceMonitor/PodMonitor-based discovery (auto-discovery of services via labels),
install kube-prometheus-stack separately, then apply the optional PodMonitors:

```bash
# 1. Install kube-prometheus-stack (includes Prometheus Operator CRDs)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace finetune \
  --create-namespace \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false

# 2. Apply optional PodMonitors (requires CRDs from step 1)
kubectl apply -f infra/k8s/observability/podmonitors.yaml
```

The `podmonitors.yaml` file is NOT included in the self-contained kustomization.
It is only applied when kube-prometheus-stack is installed.

PodMonitor endpoints reference named container ports:

| Service          | Port name | Container port |
| ---------------- | --------- | -------------- |
| finetune-api     | `http`    | 8000           |
| image-parser     | `http`    | 8090           |
| gpu-worker       | `http`    | 8010           |
| prefect-exporter | `metrics` | 8000           |

### DCGM exporter prerequisites

The DCGM exporter DaemonSet uses `nodeAffinity` with label
`nvidia.com/gpu.present=true` to target only GPU nodes. On clusters without
Node Feature Discovery (NFD), label GPU nodes manually:

```bash
kubectl label node <gpu-node-name> nvidia.com/gpu.present=true
```

The DCGM exporter also requires the NVIDIA GPU Operator or
`nvidia-device-plugin` to make `nvidia.com/gpu` allocatable on GPU nodes.

On CPU-only clusters, the GPU worker pod remains unavailable until GPU capacity
exists, but the rest of the observability stack still renders without DCGM.

### Grafana access

Port-forward to Grafana:

```bash
kubectl -n finetune port-forward svc/grafana 3000:3000
```

Open http://localhost:3000 — login with `admin` / `admin`.

## Rollback & Migration

### Migration from Legacy Workers

Legacy worker manifests have been removed. Prefect flows now run in-process within `apps/api`.

### Rollback Procedure

If the new split topology fails in your cluster:

1. Delete the new deployments: `kubectl delete -f infra/k8s/gpu-worker.yaml -f infra/k8s/prefect-worker.yaml`.
2. Apply the current manifests: `kubectl apply -k infra/k8s`.
3. Revert the API `configmap.yaml` to point to the legacy worker endpoints if necessary.
4. The observability stack remains compatible but will stop receiving metrics for the new service names.
