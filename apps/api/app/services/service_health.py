from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import BaseModel


class ServiceCheckResult(BaseModel):
    name: str
    kind: str
    status: str
    detail: str = ""
    latency_ms: int | None = None
    endpoint: str | None = None


class ServiceHealthService:
    _WORKER_DEPLOYMENTS = {
        "training-worker-gpu": "train-job-torch-deployment",
        "training-worker-dspy": "train-job-dspy-deployment",
        "prediction-worker": "predict-job-batch-deployment",
        "embedding-worker": "embed-job-batch-deployment",
    }

    def __init__(self, config: Any, prefect_client: Any, embedding_client: Any) -> None:
        self._config = config
        self._prefect_client = prefect_client
        self._embedding_client = embedding_client

    async def check_all(self) -> list[ServiceCheckResult]:
        return [
            await self._check_postgres(),
            await self._check_object_storage(),
            await self._check_prefect(),
            await self._check_label_studio(),
            await self._check_embedding(),
            await self._check_training_worker("training-worker-gpu"),
            await self._check_training_worker("training-worker-dspy"),
            await self._check_training_worker("prediction-worker"),
            await self._check_training_worker("embedding-worker"),
            await self._check_inference_worker(),
        ]

    async def _check_postgres(self) -> ServiceCheckResult:
        db_url = str(self._config.db.url)
        if not db_url.startswith("postgresql"):
            return ServiceCheckResult(name="postgres", kind="database", status="down", detail="non-PostgreSQL database configured")
        return ServiceCheckResult(name="postgres", kind="database", status="healthy", detail="PostgreSQL configured")

    async def _check_object_storage(self) -> ServiceCheckResult:
        endpoint = str(self._config.storage.minio.endpoint)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"http://{endpoint}/minio/health/live")
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(
                name="object-storage",
                kind="storage",
                status="healthy" if response.is_success else "degraded",
                detail=f"HTTP {response.status_code}",
                latency_ms=latency_ms,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ServiceCheckResult(name="object-storage", kind="storage", status="down", detail=str(exc), endpoint=endpoint)

    async def _check_prefect(self) -> ServiceCheckResult:
        endpoint = str(self._config.prefect.api_url)
        start = time.perf_counter()
        try:
            await self._prefect_client.get_work_pool(str(self._config.prefect.work_pool_name))
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(name="prefect", kind="orchestrator", status="healthy", detail="work pool reachable", latency_ms=latency_ms, endpoint=endpoint)
        except Exception as exc:
            return ServiceCheckResult(name="prefect", kind="orchestrator", status="down", detail=str(exc), endpoint=endpoint)

    async def _check_label_studio(self) -> ServiceCheckResult:
        endpoint = str(self._config.label_studio.url)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{endpoint.rstrip('/')}/health")
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(name="label-studio", kind="annotation", status="healthy" if response.is_success else "degraded", detail=f"HTTP {response.status_code}", latency_ms=latency_ms, endpoint=endpoint)
        except Exception as exc:
            return ServiceCheckResult(name="label-studio", kind="annotation", status="down", detail=str(exc), endpoint=endpoint)

    async def _check_embedding(self) -> ServiceCheckResult:
        endpoint = str(self._config.embedding.grpc_target)
        start = time.perf_counter()
        try:
            healthy = await self._embedding_client.health()
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(name="embedding", kind="worker", status="healthy" if healthy else "degraded", detail="gRPC health" if healthy else "embedding healthcheck returned false", latency_ms=latency_ms, endpoint=endpoint)
        except Exception as exc:
            return ServiceCheckResult(name="embedding", kind="worker", status="down", detail=str(exc), endpoint=endpoint)

    async def _check_training_worker(self, worker_name: str) -> ServiceCheckResult:
        endpoint = str(self._config.prefect.api_url)
        deployment_name = self._WORKER_DEPLOYMENTS.get(worker_name)
        if not deployment_name:
            return ServiceCheckResult(name=worker_name, kind="worker", status="down", detail="no deployment mapped for worker", endpoint=endpoint)
        start = time.perf_counter()
        try:
            deployment_id = await self._prefect_client.resolve_deployment_id(deployment_name)
            latency_ms = int((time.perf_counter() - start) * 1000)
            if deployment_id is None:
                return ServiceCheckResult(
                    name=worker_name,
                    kind="worker",
                    status="down",
                    detail=f"Prefect deployment is not registered: {deployment_name}",
                    latency_ms=latency_ms,
                    endpoint=endpoint,
                )
            return ServiceCheckResult(
                name=worker_name,
                kind="worker",
                status="healthy",
                detail=f"Prefect deployment registered: {deployment_name}",
                latency_ms=latency_ms,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ServiceCheckResult(name=worker_name, kind="worker", status="down", detail=str(exc), endpoint=endpoint)

    async def _check_inference_worker(self) -> ServiceCheckResult:
        endpoint = str(getattr(self._config.inference, "base_url", "")).rstrip("/")
        start = time.perf_counter()
        if not endpoint:
            return ServiceCheckResult(name="inference-worker", kind="worker", status="down", detail="inference.base_url is not configured")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{endpoint}/health")
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(name="inference-worker", kind="worker", status="healthy" if response.is_success else "degraded", detail=f"HTTP {response.status_code}", latency_ms=latency_ms, endpoint=endpoint)
        except Exception as exc:
            return ServiceCheckResult(name="inference-worker", kind="worker", status="down", detail=str(exc), endpoint=endpoint)
