# Prefect Topology V2 — CPU-Only Worker Model

## Summary

Active runtime roles:

- `prefect-worker` for CPU orchestration and CPU-bound flows
- `gpu-worker` for train/predict/embed execution

## Verification

- `docker compose -f infra/compose/docker-compose.yaml config`
- `kubectl kustomize infra/k8s`
