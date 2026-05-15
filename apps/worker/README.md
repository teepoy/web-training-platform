# Worker

Prefect flow-worker package. This package runs the CPU-only Prefect worker
(`prefect-worker`) for orchestration and flow management.

## Role

The `prefect-worker` is a **CPU-only** Prefect V2 process worker. It:

- consumes CPU/orchestration queues and manages Prefect flow runs
- executes CPU-bound flows directly (DSPy optimization, dataset drain)
- delegates GPU work (train, predict, embed) to the `gpu-worker` via HTTP API calls
- never uses CUDA, never requests GPU resources, never executes GPU workloads locally

GPU runtime execution (training, prediction, embedding) is handled by the separate
`gpu-worker` service. See `docs/architecture/prefect-training-delegation.md` for
the full topology.

## Image

The Prefect worker image uses a non-CUDA base. It must not include NVIDIA runtime
dependencies, `nvidia.com/gpu` resource requests, or `NVIDIA_VISIBLE_DEVICES`
environment variables.

## Related

- GPU worker: `apps/inference/` (evolving into the GPU runtime API)
- Architecture: `docs/architecture/prefect-training-delegation.md`
- Observability: `docs/observability/`
