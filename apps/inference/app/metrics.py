from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest

TASK_KIND_TRAINING = "training"
TASK_KIND_PREDICTION = "prediction"
TASK_KIND_EMBEDDING = "embedding"

jobs_active = Gauge(
    "platform_gpu_worker_jobs_active",
    "Currently active GPU worker training jobs",
    ["task_kind"],
)

jobs_total = Counter(
    "platform_gpu_worker_jobs_total",
    "Total training jobs processed by the GPU worker",
    ["task_kind", "status"],
)

job_duration_seconds = Histogram(
    "platform_gpu_worker_job_duration_seconds",
    "Wall-clock training job duration in seconds",
    ["task_kind"],
)

prediction_batch_duration_seconds = Histogram(
    "platform_gpu_worker_prediction_batch_duration_seconds",
    "End-to-end /v1/predict batch latency in seconds",
)

embedding_batch_duration_seconds = Histogram(
    "platform_gpu_worker_embedding_batch_duration_seconds",
    "End-to-end /v1/embed batch latency in seconds",
)

model_load_duration_seconds = Histogram(
    "platform_gpu_worker_model_load_duration_seconds",
    "Time to load or cache a model from cold start in seconds",
)


def get_metrics() -> bytes:
    return generate_latest()
