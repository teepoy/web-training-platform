# Cron Scheduling Architecture

The UI creates Prefect deployments through the API. The CPU-only `prefect-worker` consumes orchestration queues, and `gpu-worker` remains the runtime API for GPU workloads.
