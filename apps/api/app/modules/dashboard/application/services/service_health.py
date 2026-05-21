from __future__ import annotations

import time

import httpx
from omegaconf import DictConfig
from pydantic import BaseModel

from app.core.config import _resolve_gpu_worker_url
from app.shared.domain.protocols import EmbeddingClient, PrefectClient


class ServiceCheckResult(BaseModel):
    name: str
    kind: str
    status: str
    detail: str = ""
    latency_ms: int | None = None
    endpoint: str | None = None


class ServiceHealthService:
    def __init__(
        self,
        config: DictConfig,
        prefect_client: PrefectClient,
        embedding_client: EmbeddingClient,
    ) -> None:
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
            await self._check_prefect_worker(),
            await self._check_gpu_worker(),
        ]

    async def _check_postgres(self) -> ServiceCheckResult:
        db_url = str(self._config.db.url)
        if not db_url.startswith("postgresql"):
            return ServiceCheckResult(
                name="postgres",
                kind="database",
                status="down",
                detail="non-PostgreSQL database configured",
            )
        return ServiceCheckResult(
            name="postgres",
            kind="database",
            status="healthy",
            detail="PostgreSQL configured",
        )

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
            return ServiceCheckResult(
                name="object-storage",
                kind="storage",
                status="down",
                detail=str(exc),
                endpoint=endpoint,
            )

    async def _check_prefect(self) -> ServiceCheckResult:
        endpoint = str(self._config.prefect.api_url)
        start = time.perf_counter()
        try:
            await self._prefect_client.get_work_pool(
                str(self._config.prefect.work_pool_name)
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(
                name="prefect",
                kind="orchestrator",
                status="healthy",
                detail="work pool reachable",
                latency_ms=latency_ms,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ServiceCheckResult(
                name="prefect",
                kind="orchestrator",
                status="down",
                detail=str(exc),
                endpoint=endpoint,
            )

    async def _check_label_studio(self) -> ServiceCheckResult:
        endpoint = str(self._config.label_studio.url)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{endpoint.rstrip('/')}/health")
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(
                name="label-studio",
                kind="annotation",
                status="healthy" if response.is_success else "degraded",
                detail=f"HTTP {response.status_code}",
                latency_ms=latency_ms,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ServiceCheckResult(
                name="label-studio",
                kind="annotation",
                status="down",
                detail=str(exc),
                endpoint=endpoint,
            )

    async def _check_embedding(self) -> ServiceCheckResult:
        endpoint = str(self._config.embedding.grpc_target)
        start = time.perf_counter()
        try:
            healthy = await self._embedding_client.health()
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(
                name="embedding",
                kind="worker",
                status="healthy" if healthy else "degraded",
                detail="gRPC health"
                if healthy
                else "embedding healthcheck returned false",
                latency_ms=latency_ms,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ServiceCheckResult(
                name="embedding",
                kind="worker",
                status="down",
                detail=str(exc),
                endpoint=endpoint,
            )

    async def _check_prefect_worker(self) -> ServiceCheckResult:
        """Check Prefect worker health via work pool and work queue availability."""
        endpoint = str(self._config.prefect.api_url)
        work_pool_name = str(self._config.prefect.work_pool_name)
        start = time.perf_counter()
        try:
            await self._prefect_client.get_work_pool(work_pool_name)
            queues = await self._prefect_client.list_work_queues(work_pool_name)
            latency_ms = int((time.perf_counter() - start) * 1000)
            queue_count = len(queues) if isinstance(queues, list) else 0
            return ServiceCheckResult(
                name="prefect-worker",
                kind="worker",
                status="healthy" if queue_count > 0 else "degraded",
                detail=f"work pool reachable, {queue_count} work queue(s)",
                latency_ms=latency_ms,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ServiceCheckResult(
                name="prefect-worker",
                kind="worker",
                status="down",
                detail=str(exc),
                endpoint=endpoint,
            )

    async def _check_gpu_worker(self) -> ServiceCheckResult:
        """Check GPU worker health via /health endpoint, parsing gpu_info.available.

        Non-GPU environments report "degraded" (available but no GPU),
        not "down" — the stack remains operational.
        """
        endpoint = _resolve_gpu_worker_url(self._config).rstrip("/")
        start = time.perf_counter()
        if not endpoint:
            return ServiceCheckResult(
                name="gpu-worker",
                kind="worker",
                status="down",
                detail="gpu_worker.base_url is not configured",
            )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{endpoint}/health")
            latency_ms = int((time.perf_counter() - start) * 1000)
            if not response.is_success:
                return ServiceCheckResult(
                    name="gpu-worker",
                    kind="worker",
                    status="degraded",
                    detail=f"HTTP {response.status_code}",
                    latency_ms=latency_ms,
                    endpoint=endpoint,
                )
            # Parse gpu_info.available from the /health response
            try:
                body = response.json()
                gpu_info = body.get("gpu_info", {})
                gpu_available = gpu_info.get("available", False)
            except Exception:
                gpu_available = False

            if gpu_available:
                return ServiceCheckResult(
                    name="gpu-worker",
                    kind="worker",
                    status="healthy",
                    detail="GPU available",
                    latency_ms=latency_ms,
                    endpoint=endpoint,
                )
            return ServiceCheckResult(
                name="gpu-worker",
                kind="worker",
                status="degraded",
                detail="GPU not available (non-GPU environment)",
                latency_ms=latency_ms,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ServiceCheckResult(
                name="gpu-worker",
                kind="worker",
                status="down",
                detail=str(exc),
                endpoint=endpoint,
            )
