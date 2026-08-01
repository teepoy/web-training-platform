from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, cast

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import ScDataProviderConfig
from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.sc.data_provider.cache import CacheRedis, ScDataObjectCache
from app.modules.sc.data_provider.engine import (
    DuckDbQueryExecutor,
    ScQueryResponseTooLargeError,
    ScQueryTimeoutError,
)
from app.modules.sc.data_provider.materializer import ScDataMaterializer
from app.modules.sc.data_provider.revision import RevisionRedis, ScDataRevisionStore
from app.modules.sc.data_provider.schemas import (
    ScDataInvalidationEvent,
    ScSqlQueryRequest,
)
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.data_provider.sql_policy import ScSqlPolicyError, validate_sc_sql
from app.shared.api.schemas import Organization, User
from app.shared.infrastructure.redis.event_publisher import (
    ANNOTATION_CHANNEL,
    PREDICTION_CHANNEL,
)


ARROW_STREAM_MEDIA_TYPE = "application/vnd.apache.arrow.stream"


@dataclass(frozen=True)
class ScDataProviderRuntime:
    config: ScDataProviderConfig
    redis: ScDataProviderRedis
    cache: ScDataObjectCache
    revisions: ScDataRevisionStore
    materializer: ScDataMaterializer
    executor: DuckDbQueryExecutor


class ScDataProviderPubSub(Protocol):
    async def subscribe(self, *channels: str) -> None: ...

    async def get_message(
        self, *, ignore_subscribe_messages: bool, timeout: int
    ) -> dict[str, object] | None: ...

    async def unsubscribe(self, *channels: str) -> None: ...

    async def aclose(self) -> None: ...


class ScDataProviderRedis(CacheRedis, RevisionRedis, Protocol):
    async def ping(self) -> bool: ...

    def pubsub(self) -> ScDataProviderPubSub: ...

    async def aclose(self) -> None: ...


router = APIRouter(prefix="/api/v1/sc/data", tags=["sc-data-provider"])


@router.post("/inspections/{inspection_time}/{wafer_key}/query")
async def query_inspection(
    inspection_time: str,
    wafer_key: int,
    query: ScSqlQueryRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> StreamingResponse:
    scope = ScDataScope.inspection(
        inspection_time=inspection_time,
        wafer_key=wafer_key,
        org_id=org.id,
    )
    return await _query_scope(request, scope, query)


@router.post("/datasets/{dataset_id}/query")
async def query_dataset(
    dataset_id: str,
    query: ScSqlQueryRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> StreamingResponse:
    scope = ScDataScope.dataset(dataset_id=dataset_id, org_id=org.id)
    return await _query_scope(request, scope, query)


@router.get("/inspections/{inspection_time}/{wafer_key}/events")
async def inspection_events(
    inspection_time: str,
    wafer_key: int,
    request: Request,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> StreamingResponse:
    scope = ScDataScope.inspection(
        inspection_time=inspection_time,
        wafer_key=wafer_key,
        org_id=org.id,
    )
    return _events_response(request, scope)


@router.get("/datasets/{dataset_id}/events")
async def dataset_events(
    dataset_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> StreamingResponse:
    scope = ScDataScope.dataset(dataset_id=dataset_id, org_id=org.id)
    return _events_response(request, scope)


async def _query_scope(
    request: Request,
    scope: ScDataScope,
    query: ScSqlQueryRequest,
) -> StreamingResponse:
    runtime = _runtime(request)
    try:
        validated_sql = validate_sc_sql(query.sql)
    except ScSqlPolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    materialize_started = time.monotonic()
    revision = await runtime.revisions.current(scope)
    try:
        materialized = await runtime.materializer.materialize(scope, revision=revision)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    materialize_ms = (time.monotonic() - materialize_started) * 1000

    lease = runtime.cache.lease(materialized.objects)
    await lease.__aenter__()
    try:
        prepared = await runtime.executor.prepare_stream(
            sql=validated_sql,
            parameters=query.parameters,
            materialized=materialized,
        )
    except ScQueryTimeoutError as exc:
        await lease.__aexit__(type(exc), exc, exc.__traceback__)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ScQueryResponseTooLargeError as exc:
        await lease.__aexit__(type(exc), exc, exc.__traceback__)
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except duckdb.Error as exc:
        await lease.__aexit__(type(exc), exc, exc.__traceback__)
        raise HTTPException(
            status_code=400, detail=f"DuckDB query failed: {exc}"
        ) from exc
    except BaseException as exc:
        await lease.__aexit__(type(exc), exc, exc.__traceback__)
        raise

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in prepared.body:
                yield chunk
        finally:
            try:
                await prepared.body.aclose()
            finally:
                await lease.__aexit__(None, None, None)

    headers = {
        "X-SC-Data-Revision": str(revision),
        "X-SC-Worker-PID": str(os.getpid()),
        "X-SC-Cache": materialized.cache_status,
        "X-SC-Spill-Bytes": str(runtime.executor.temp_directory_size_bytes()),
        "Server-Timing": (
            f"materialize;dur={materialize_ms:.3f}, "
            f"duckdb;dur={prepared.query_duration_ms:.3f}"
        ),
    }
    return StreamingResponse(
        body(),
        media_type=ARROW_STREAM_MEDIA_TYPE,
        headers=headers,
    )


def _events_response(request: Request, scope: ScDataScope) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(request, scope),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_stream(request: Request, scope: ScDataScope) -> AsyncIterator[str]:
    runtime = _runtime(request)
    pubsub = runtime.redis.pubsub()
    await pubsub.subscribe(ANNOTATION_CHANNEL, PREDICTION_CHANNEL)
    try:
        yield _sse_event(
            ScDataInvalidationEvent(
                scope=scope.public_name,
                revision=await runtime.revisions.current(scope),
                changed_kinds=[],
            )
        )
        while not await request.is_disconnected():
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=runtime.config.sse_heartbeat_seconds,
            )
            if not message:
                yield ": keepalive\n\n"
                continue
            event = _invalidation_from_message(scope, message)
            if event is not None:
                yield _sse_event(event)
    finally:
        await pubsub.unsubscribe(ANNOTATION_CHANNEL, PREDICTION_CHANNEL)
        await pubsub.aclose()


def _invalidation_from_message(
    scope: ScDataScope, message: dict[str, object]
) -> ScDataInvalidationEvent | None:
    raw = message.get("data")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    if scope.kind == "dataset" and data.get("dataset_id") != scope.identity:
        return None
    if scope.kind == "inspection":
        if data.get("inspection_time") != scope.identity.rsplit("/", 1)[0]:
            return None
        try:
            event_wafer_key = int(cast(int | str, data.get("wafer_key", -1)))
        except (TypeError, ValueError):
            return None
        if event_wafer_key != int(scope.identity.rsplit("/", 1)[1]):
            return None
    raw_revision = payload.get("revision")
    if not isinstance(raw_revision, int):
        return None
    raw_channel = message.get("channel")
    if isinstance(raw_channel, bytes):
        raw_channel = raw_channel.decode("utf-8")
    changed_kind: Literal["annotation", "prediction"] = (
        "prediction" if raw_channel == PREDICTION_CHANNEL else "annotation"
    )
    return ScDataInvalidationEvent(
        scope=scope.public_name,
        revision=raw_revision,
        changed_kinds=[changed_kind],
    )


def _sse_event(event: ScDataInvalidationEvent) -> str:
    return f"event: invalidation\ndata: {event.model_dump_json()}\n\n"


def _runtime(request: Request) -> ScDataProviderRuntime:
    runtime = getattr(request.app.state, "sc_data_provider", None)
    if runtime is None:
        raise RuntimeError("SC data-provider runtime was not initialized")
    return cast(ScDataProviderRuntime, runtime)
