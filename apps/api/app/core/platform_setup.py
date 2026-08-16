from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import redis.asyncio as redis_client  # type: ignore[import-untyped]
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import AppConfig
from app.modules.auth.app.services.dev_auth_context import prepare_dev_auth_context
from app.shared.infrastructure.prefect.deployments import (
    platform_prefect_deployment_specs,
    prefect_work_pool_names,
    prefect_work_queue_specs,
    required_prefect_deployment_names,
)
from app.shared.context import SharedInfra, build_shared_infra
from app.shared.infrastructure.storage.minio import (
    MinioArtifactStorage,
    prepare_minio_storage,
    validate_minio_storage,
)

_API_ROOT = Path(__file__).resolve().parents[2]
_PLATFORM_PREPARE_LOCK_ID = 1_480_861_786


async def prepare_platform(config: AppConfig) -> None:
    """Apply every platform-owned initialization step under one global lock."""
    if str(config.app.env) == "test":
        raise RuntimeError("prepare_platform does not support the test profile")

    shared = build_shared_infra(config)
    try:
        async with shared.db_engine.connect() as lock_connection:
            acquired = await lock_connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": _PLATFORM_PREPARE_LOCK_ID},
            )
            await lock_connection.commit()
            if acquired is not True:
                raise RuntimeError("Another platform preparation is already running")
            try:
                await asyncio.to_thread(
                    command.upgrade,
                    _alembic_config(),
                    "head",
                )
                await validate_database_revision(shared)
                if not bool(getattr(config.auth, "enabled", True)):
                    await prepare_dev_auth_context(shared.session_factory)
                await asyncio.to_thread(_prepare_minio, config, shared)
                await prepare_prefect(shared)
                await validate_platform_dependencies(config, shared)
            finally:
                await lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": _PLATFORM_PREPARE_LOCK_ID},
                )
                await lock_connection.commit()
    finally:
        await shared.prefect_client.close()
        await shared.db_engine.dispose()


async def validate_platform_dependencies(
    config: AppConfig,
    shared: SharedInfra,
) -> None:
    """Validate deployable dependencies without mutating external state."""
    await validate_database_revision(shared)
    await asyncio.to_thread(_validate_minio, config, shared)
    await validate_prefect(shared)
    await validate_label_studio(config)
    await validate_redis(config)


async def validate_database_revision(shared: SharedInfra) -> None:
    expected = set(ScriptDirectory.from_config(_alembic_config()).get_heads())
    async with shared.db_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        result = await connection.execute(
            text("SELECT version_num FROM alembic_version")
        )
        actual = {str(row[0]) for row in result}
    if actual != expected:
        raise RuntimeError(
            f"Database revision mismatch: expected {sorted(expected)}, "
            f"got {sorted(actual)}"
        )


async def prepare_prefect(shared: SharedInfra) -> None:
    client = shared.prefect_client
    for pool_name in sorted(prefect_work_pool_names()):
        await client.ensure_work_pool(pool_name, "process")
    for pool_name, queue_name, priority in prefect_work_queue_specs():
        await client.ensure_work_queue(pool_name, queue_name, priority=priority)
    for spec in platform_prefect_deployment_specs():
        await client.ensure_deployment(
            deployment_name=str(spec["deployment_name"]),
            flow_name=str(spec["flow_name"]),
            work_pool_name=str(spec["work_pool_name"]),
            entrypoint=str(spec["entrypoint"]),
            path=str(spec["path"]),
            work_queue_name=(
                str(spec["work_queue_name"]) if "work_queue_name" in spec else None
            ),
        )
    await validate_prefect(shared)


async def validate_prefect(shared: SharedInfra) -> None:
    client = shared.prefect_client
    for pool_name in sorted(prefect_work_pool_names()):
        pool = await client.get_work_pool(pool_name)
        pool_type = str(pool.get("type", "")).lower()
        if pool_type != "process":
            raise RuntimeError(
                f"Prefect work pool {pool_name!r} has type {pool_type!r}, "
                "expected 'process'"
            )

    for pool_name, queue_name, priority in prefect_work_queue_specs():
        queue = await client.get_work_queue_by_name(queue_name, pool_name)
        if queue is None:
            raise RuntimeError(
                f"Required Prefect work queue {queue_name!r} is missing from "
                f"pool {pool_name!r}"
            )
        if queue.get("priority") != priority:
            raise RuntimeError(
                f"Prefect work queue {queue_name!r} has priority "
                f"{queue.get('priority')!r}, expected {priority}"
            )

    owned_specs = {
        spec["deployment_name"]: spec for spec in platform_prefect_deployment_specs()
    }
    required_names = required_prefect_deployment_names()
    for deployment_name in sorted(required_names):
        deployment_id = await client.resolve_deployment_id(deployment_name)
        if deployment_id is None:
            raise RuntimeError(
                f"Required Prefect deployment {deployment_name!r} is missing"
            )
        spec = owned_specs.get(deployment_name)
        if spec is None:
            continue
        deployment = await client.get_deployment(deployment_id)
        flow_id = await client.resolve_existing_flow_id(str(spec["flow_name"]))
        if flow_id is None:
            raise RuntimeError(
                f"Required Prefect flow {spec['flow_name']!r} is missing"
            )
        expected = {
            "flow_id": flow_id,
            "work_pool_name": spec["work_pool_name"],
            "entrypoint": spec["entrypoint"],
            "path": spec["path"],
        }
        if "work_queue_name" in spec:
            expected["work_queue_name"] = spec["work_queue_name"]
        actual = {key: deployment.get(key) for key in expected}
        if actual != expected:
            raise RuntimeError(
                f"Prefect deployment {deployment_name!r} does not match its "
                f"runtime descriptor: expected {expected!r}, got {actual!r}"
            )


async def validate_label_studio(config: AppConfig) -> None:
    timeout = float(config.startup_checks.dependency_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            f"{str(config.label_studio.url).rstrip('/')}/health"
        )
        response.raise_for_status()


async def validate_redis(config: AppConfig) -> None:
    timeout = float(config.startup_checks.dependency_timeout_seconds)
    client = redis_client.Redis(
        host=str(config.redis.host),
        port=int(config.redis.port),
        password=str(config.redis.password) if config.redis.password else None,
        db=int(config.redis.db),
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )
    try:
        await client.ping()  # type: ignore[awaitable]
    finally:
        await client.aclose()


def _prepare_minio(config: AppConfig, shared: SharedInfra) -> None:
    storage = _minio_storage(shared)
    prepare_minio_storage(
        storage.client,
        artifact_bucket=str(config.storage.minio.bucket),
        runtime_bucket=str(config.storage.runtime_bucket),
        export_lifecycle=storage.export_lifecycle,
    )


def _validate_minio(config: AppConfig, shared: SharedInfra) -> None:
    storage = _minio_storage(shared)
    validate_minio_storage(
        storage.client,
        artifact_bucket=str(config.storage.minio.bucket),
        runtime_bucket=str(config.storage.runtime_bucket),
        export_lifecycle=storage.export_lifecycle,
    )


def _minio_storage(shared: SharedInfra) -> MinioArtifactStorage:
    storage = shared.artifact_storage
    if not isinstance(storage, MinioArtifactStorage):
        raise RuntimeError("Deployable platform preparation requires MinIO storage")
    return storage


def _alembic_config() -> AlembicConfig:
    return AlembicConfig(str(_API_ROOT / "alembic.ini"))
