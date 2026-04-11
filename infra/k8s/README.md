# K8s Config

This folder contains runnable Kubernetes manifests for minikube and Kubeflow integration.
The manifests mirror the docker-compose stack so both environments run the same services.

## Files

| File | What it deploys |
|------|-----------------|
| `namespace.yaml` | `finetune` namespace |
| `rbac.yaml` | API service account + role for `pytorchjobs` |
| `configmap.yaml` | Non-secret env vars (`APP_CONFIG_PROFILE`, Prefect/LS/embedding URLs) |
| `secret.example.yaml` | Copy to `secret.yaml` — DB URLs, MinIO creds, LS keys |
| `postgres.yaml` | PostgreSQL (pgvector) with init script for `prefect` + `labelstudio` DBs |
| `minio.yaml` | MinIO (API :9000, console :9001) |
| `prefect-server.yaml` | Prefect 3 server (:4200) |
| `embedding.yaml` | Embedding gRPC service (:50051) |
| `inference-worker.yaml` | Prediction/embedding inference worker (:8010) |
| `label-studio.yaml` | Label Studio (:8080) |
| `api-deployment.yaml` | Platform API (:8000) |
| `training-worker-gpu.yaml` | GPU training worker (Prefect V2 work-pool mode) |
| `training-worker-dspy.yaml` | DSPy training worker (Prefect V2 work-pool mode) |
| `prediction-worker.yaml` | Batch prediction worker (Prefect V2 work-pool mode) |
| `pytorchjob-smoke.yaml` | Manual Kubeflow smoke job |
| `kustomization.yaml` | Kustomize entrypoint — applies all base resources |

## Service map (mirrors docker-compose)

```
postgres (:5432)          — shared by API, Prefect, Label Studio
minio (:9000, :9001)      — artifact storage
prefect-server (:4200)    — Prefect control plane
embedding (:50051)        — embedding gRPC service
inference-worker (:8010)  — prediction/embedding worker
label-studio (:8080)      — annotation UI
finetune-api (:8000)      — platform API
training-worker           — GPU worker (no exposed port)
prediction-worker         — batch prediction worker (no exposed port)
```

## Apply

```bash
# 1. Apply base resources (namespace, RBAC, infra, services)
kubectl apply -k infra/k8s

# 2. Create secrets (edit values first!)
cp infra/k8s/secret.example.yaml infra/k8s/secret.yaml
# Edit secret.yaml with real credentials
kubectl apply -f infra/k8s/secret.yaml
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

| Image | Built from |
|-------|-----------|
| `finetune-api:latest` | `apps/api/Dockerfile` |
| `finetune-embedding:latest` | `apps/embedding/Dockerfile` |
| `finetune-inference:latest` | `apps/inference/Dockerfile` |
| `finetune-worker:latest` | `apps/worker/Dockerfile` |

Third-party images (`pgvector/pgvector:pg16`, `prefecthq/prefect:3.6.25-python3.12`,
`minio/minio:RELEASE.2025-02-18T16-25-55Z`, `heartexlabs/label-studio:latest`) are
pulled from public registries.

## Notes

- All volumes use `emptyDir` — data is lost on pod restart. Use PVCs for persistence.
- The `LABEL_STUDIO_EXTERNAL_URL` in the configmap should be updated to the actual
  browser-accessible URL for your cluster (e.g. via Ingress or NodePort).
- The inference worker requires `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` for VQA workloads.
- API, workers, and orchestration run as separate services in both dev and prod topologies.
