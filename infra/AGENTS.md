# INFRA KNOWLEDGE BASE

## OVERVIEW
Operational manifests for local Compose smoke runs and minikube/Kubeflow deployment. Infra is runnable, but defaults are smoke-oriented and storage is ephemeral.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Compose stack | `compose/docker-compose.yaml` | Postgres, MinIO, API |
| Compose usage | `compose/README.md` | Up/down command |
| K8s base apply | `k8s/kustomization.yaml` | Namespace + base resources |
| K8s bootstrap docs | `k8s/README.md` | Apply + verify steps |
| Namespace / RBAC | `k8s/namespace.yaml`, `k8s/rbac.yaml` | API service account can manage `pytorchjobs` |
| Runtime config | `k8s/configmap.yaml` | Sets `APP_CONFIG_PROFILE=dev` |
| Secrets template | `k8s/secret.example.yaml` | Copy to `secret.yaml` and edit |
| In-cluster dependencies | `k8s/postgres.yaml`, `k8s/minio.yaml` | Both use `emptyDir` today |
| API deploy | `k8s/api-deployment.yaml` | Uses `finetune-api:latest` |
| Operator smoke job | `k8s/pytorchjob-smoke.yaml` | Requires Kubeflow Training Operator CRD |

## CONVENTIONS
- Namespace is always `finetune`.
- Kubernetes deploys expect `finetune-config` ConfigMap and `finetune-secrets` Secret.
- Dev profile means Postgres + MinIO + in-cluster Kubeflow client wiring.
- Local Compose uses the same broad service names (`postgres`, `minio`, `api`) as the app config expects.

## ANTI-PATTERNS
- Don’t use `secret.example.yaml` values outside smoke/local testing.
- Don’t treat `emptyDir` Postgres/MinIO volumes as durable; data vanishes on pod restart.
- Don’t apply `pytorchjob-smoke.yaml` before verifying `pytorchjobs.kubeflow.org` exists.
- Don’t forget to make the `finetune-api:latest` image available to the cluster (`minikube image load` or real registry).

## COMMANDS
```bash
# Compose
docker compose -f infra/compose/docker-compose.yaml up -d

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
