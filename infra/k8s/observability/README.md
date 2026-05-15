# Observability on Kubernetes

Self-contained Kubernetes monitoring stack deployed via `kubectl kustomize`.
All components run in the `finetune` namespace alongside the platform services.

The base platform `kubectl apply -k infra/k8s` does NOT include observability.
Apply it separately:

## Quick start

```bash
# Render and validate
kubectl kustomize infra/k8s/observability

# Apply
kubectl apply -k infra/k8s/observability
```

## Components

| Manifest               | What it deploys                                           |
| ---------------------- | --------------------------------------------------------- |
| `prometheus.yaml`      | Prometheus (ConfigMap + Deployment + Service on :9090)    |
| `alertmanager.yaml`    | Alertmanager (ConfigMap + Deployment + Service on :9093)  |
| `loki.yaml`            | Loki log aggregator (ConfigMap + Deployment + Service on :3100) |
| `promtail.yaml`        | Promtail log collector (DaemonSet + RBAC)                 |
| `grafana.yaml`         | Grafana dashboards (ConfigMap + Deployment + Service on :3000) |
| `prefect-exporter.yaml`| Custom Prefect health exporter (ConfigMap + Deployment + Service on :8000) |
| `dcgm-exporter.yaml`   | NVIDIA DCGM metrics (DaemonSet on GPU nodes only, :9400) |
| `podmonitors.yaml`     | Prometheus Operator PodMonitors — NOT in kustomization; apply separately after installing kube-prometheus-stack |

## Prometheus scrape targets

Scrape configs use cluster-internal DNS names (renders without CRDs):

| Target                                         | Path       | Interval |
| ---------------------------------------------- | ---------- | -------- |
| `finetune-api.finetune.svc.cluster.local:8000`  | `/metrics` | 15s      |
| `gpu-worker.finetune.svc.cluster.local:8010`    | `/metrics` | 15s      |
| `prefect-exporter.finetune.svc.cluster.local:8000` | `/metrics` | 15s   |
| `alertmanager.finetune.svc.cluster.local:9093`  | `/metrics` | 15s      |
| `dcgm-exporter.finetune.svc.cluster.local:9400` | `/metrics` | 15s      |

## Prometheus Operator (kube-prometheus-stack)

The `podmonitors.yaml` file provides PodMonitors for auto-discovery when
kube-prometheus-stack is installed. This is optional — the standalone
Prometheus deployment uses static DNS targets and works without any operator.

PodMonitor endpoints reference **named container ports**:

| Service          | Port name | Container port |
| ---------------- | --------- | -------------- |
| finetune-api     | `http`    | 8000           |
| gpu-worker       | `http`    | 8010           |
| prefect-exporter | `metrics` | 8000           |

`podmonitors.yaml` is NOT included in the `kustomization.yaml` resource list.
Apply it separately only after kube-prometheus-stack CRDs are installed:

```bash
# Install kube-prometheus-stack (includes Prometheus Operator CRDs)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace finetune \
  --create-namespace \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set grafana.adminPassword=admin

# Apply PodMonitors (auto-discovered by the operator)
kubectl apply -f infra/k8s/observability/podmonitors.yaml
```

This deploys:
- Prometheus Operator + Prometheus (discovers PodMonitors with `release: monitoring`)
- Grafana (with Prometheus datasource pre-configured)
- Alertmanager
- Node Exporter (DaemonSet)
- kube-state-metrics

## DCGM exporter (GPU nodes only)

The DCGM exporter DaemonSet uses node affinity to schedule **only on GPU nodes**.
CPU-only nodes are excluded via the `nvidia.com/gpu.present=true` label selector.
The GPU worker runtime pod itself still requires `nvidia.com/gpu: 1`, so it will
remain pending on CPU-only clusters; that is expected and separate from DCGM.

### Prerequisites

1. **NVIDIA GPU Operator** or **nvidia-device-plugin** deployed on the cluster
2. GPU nodes labeled with `nvidia.com/gpu.present=true` (auto-applied by Node Feature Discovery, or set manually)

```bash
# Label GPU nodes manually (if NFD is not installed)
kubectl label node <gpu-node-name> nvidia.com/gpu.present=true

# Verify
kubectl get nodes -l nvidia.com/gpu.present=true
```

### Tolerations

The DaemonSet tolerates `nvidia.com/gpu:NoSchedule` taints. If your GPU nodes
have custom taints, add them to the `tolerations` list in `dcgm-exporter.yaml`.

## Prefect exporter

A minimal Python HTTP server that polls `PREFECT_API_URL/health` and exposes
a `prefect_health` gauge at `/metrics`. The exporter script is embedded in a
ConfigMap and mounted into a `python:3.12-slim` container.

```bash
# Check exporter health
kubectl -n finetune port-forward svc/prefect-exporter 8000:8000
curl http://localhost:8000/metrics
```

## Grafana

Pre-provisioned with Prometheus and Loki datasources.

```bash
kubectl -n finetune port-forward svc/grafana 3000:3000
# Open http://localhost:3000 — login with admin / admin
```

## Alert Rules

Six Prometheus alert rules are defined in `prometheus-rules.yaml` (ConfigMap `prometheus-rules`) and mounted into the Prometheus pod at `/etc/prometheus/rules/`. Prometheus loads them via `rule_files: ['/etc/prometheus/rules/*.yml']`. All alerts carry `severity` (critical/warning) and `group: finetune` labels.

| Alert | Condition | For | Severity |
|---|---|---|---|
| `GPUWorkerDown` | `up{job="gpu-worker"} == 0` | 2m | critical |
| `PrefectExporterDown` | `up{job="prefect-exporter"} == 0` | 2m | warning |
| `QueueBacklogHigh` | `prefect_work_queue_depth > 100` | 5m | warning |
| `GPUWorkerOOM` | GPU worker container restarts > 3 in 15m | 1m | critical |
| `DcgmGpuMemoryHigh` | GPU FB memory > 90% (skipped if DCGM absent) | 5m | warning |
| `ServiceRestartLoop` | Any platform service restarts > 5 in 10m | 1m | critical |

### Silencing Alerts During Maintenance

Use the Alertmanager API to create a time-boxed silence without modifying config files.

```bash
# Port-forward Alertmanager
kubectl -n finetune port-forward svc/alertmanager 9093:9093

# Create a 2-hour silence for all finetune group alerts
curl -s -X POST http://localhost:9093/api/v2/silences \
  -H 'Content-Type: application/json' \
  -d '{
    "matchers": [{"name": "group", "value": "finetune", "isRegex": false}],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "endsAt": "'$(date -u -d '+2 hours' +%Y-%m-%dT%H:%M:%SZ)'",
    "createdBy": "ops",
    "comment": "Maintenance window"
  }'

# Silence a specific alert by name
curl -s -X POST http://localhost:9093/api/v2/silences \
  -H 'Content-Type: application/json' \
  -d '{
    "matchers": [{"name": "alertname", "value": "GPUWorkerDown", "isRegex": false}],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "endsAt": "'$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)'",
    "createdBy": "ops",
    "comment": "GPU node under maintenance"
  }'

# List active silences
curl -s http://localhost:9093/api/v2/silences | jq '.[] | select(.status.state == "active")'

# Expire a silence by ID
curl -s -X DELETE http://localhost:9093/api/v2/silence/<silence-id>
```

Open the Alertmanager UI at http://localhost:9093 after port-forwarding to manage silences interactively.

## Notes

- All volumes use `emptyDir` — data is lost on pod restart. Use PVCs for
  Prometheus TSDB and Loki chunks in production.
- The `kube-prometheus-stack` Helm chart is the community standard for Prometheus
  Operator deployments. The standalone manifests here provide a lightweight
  alternative that renders without Helm or CRD dependencies.
- Alertmanager uses a `dev-null` receiver by default. Configure Slack, PagerDuty,
  or webhook receivers for production alerting.
- Promtail uses `kubernetes_sd_configs` for pod discovery and requires the
  ClusterRole in `promtail.yaml` to list pods and nodes.
- The prefect-exporter is a custom component matching the Compose observability
  stack. It has no external image dependency beyond `python:3.12-slim`.
- GPU metrics (DCGM) are scoped to GPU nodes only via node affinity — the
  DaemonSet will not attempt to schedule on CPU-only nodes.

## Log Collection (Promtail → Loki)

Promtail runs as a DaemonSet and ships pod logs from `/var/log/pods` to Loki. Labels are kept deliberately low-cardinality to prevent Loki index explosion.

### Loki labels applied to every log stream

| Label       | Source                          | Example values                                      |
| ----------- | ------------------------------- | --------------------------------------------------- |
| `namespace` | `__meta_kubernetes_namespace`   | `finetune`                                          |
| `pod`       | `__meta_kubernetes_pod_name`    | `finetune-api-7f4b9-xk2pq`                         |
| `container` | Pod container name              | `finetune-api`, `gpu-worker`                        |
| `service`   | Container name (normalized)     | `api`, `gpu-worker`, `prefect-worker`               |
| `env`       | Static (pipeline stage)         | `finetune`                                          |
| `level`     | JSON field extraction           | `info`, `warn`, `error`, `debug`                    |

### Labels explicitly NOT promoted (high-cardinality)

The following values are **never** Loki stream labels. They remain searchable as log content only:

- `platform_job_id` / `job_id` — platform training/prediction job identifiers
- `gpu_job_id` — GPU worker job identifiers
- `flow_run_id` — Prefect flow run identifiers
- Pod UIDs, controller names, all `__meta_kubernetes_pod_label_*` pod labels

### Querying logs in Grafana / LogQL

```logql
# All logs from the finetune API
{service="api", namespace="finetune"}

# GPU worker error logs
{service="gpu-worker", level="error"}

# All logs for a specific platform job (content filter — no label required)
{service="api"} |= "platform_job_id=<your-job-id>"

# Prefect worker logs for a specific flow run
{service="prefect-worker"} |= "flow_run_id=<your-run-id>"

# All finetune logs across services
{env="finetune"} | json | level="error"
```

## Port summary

| Service           | Port  | Scrape Path   | Notes                |
| ----------------- | ----- | ------------- | -------------------- |
| prometheus        | 9090  | /metrics      | Self-scraped         |
| alertmanager      | 9093  | /metrics      |                      |
| loki              | 3100  | /ready        | Not scraped by Prom  |
| promtail          | 9080  | /metrics      | Per-node DaemonSet   |
| grafana           | 3000  | /api/health   | Not scraped by Prom  |
| prefect-exporter  | 8000  | /metrics      | `prefect_health` gauge |
| dcgm-exporter     | 9400  | /metrics      | GPU nodes only       |
