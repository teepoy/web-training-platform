# Image Split Strategy

The runtime uses two images only:

| Service | Role | Image |
|---|---|---|
| `gpu-worker` | GPU runtime API | `apps/inference/Dockerfile` |
| `prefect-worker` | CPU Prefect worker | `apps/worker/Dockerfile.cpu` |

Rules:

- `prefect-worker` stays CPU-only.
- `gpu-worker` owns GPU execution.
