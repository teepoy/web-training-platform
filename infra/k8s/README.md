# K8s Config

This folder contains runnable Kubernetes manifests for minikube and Kubeflow integration.

## Files

- `namespace.yaml`: Namespace
- `rbac.yaml`: API service account + role for `pytorchjobs`
- `configmap.yaml`: app profile config
- `secret.example.yaml`: copy to `secret.yaml` and edit values
- `postgres.yaml`: in-cluster postgres
- `minio.yaml`: in-cluster minio
- `api-deployment.yaml`: API deployment/service
- `pytorchjob-smoke.yaml`: manual smoke job
- `kustomization.yaml`: apply base resources

## Apply

```bash
kubectl apply -k infra/k8s
kubectl apply -f infra/k8s/secret.yaml
```

## Verify

```bash
kubectl -n finetune get pods
kubectl -n finetune get svc
kubectl get crd pytorchjobs.kubeflow.org
```

If `pytorchjobs.kubeflow.org` is missing, install Kubeflow Training Operator first.
