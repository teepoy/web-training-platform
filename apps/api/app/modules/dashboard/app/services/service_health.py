from __future__ import annotations

import time

import httpx
from omegaconf import DictConfig
from pydantic import BaseModel

from app.shared.domain.protocols import PrefectClient


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
    ) -> None:
        self._config = config
        self._prefect_client = prefect_client

    async def check_all(self) -> list[ServiceCheckResult]:
        return [
            await self._check_postgres(),
            await self._check_object_storage(),
            await self._check_prefect(),
            await self._check_label_studio(),
            await self._check_prefect_worker(),
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
