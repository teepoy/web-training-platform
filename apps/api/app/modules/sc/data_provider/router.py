from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar, cast

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sampling_rules import InvalidSamplingRuleError
from starlette.types import Receive, Scope, Send

from app.core.config import ScDataProviderConfig
from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.sc.data_provider.cache import CacheRedis, ScDataObjectCache
from app.modules.sc.data_provider.engine import (
    DuckDbQueryExecutor,
    ScQueryResponseTooLargeError,
    ScQueryTimeoutError,
)
from app.modules.sc.data_provider.materializer import (
    ScCollectionTooLargeError,
    ScDataMaterializer,
)
from app.modules.sc.data_provider.revision import RevisionRedis, ScDataRevisionStore
from app.modules.sc.data_provider.sample_table_descriptor import (
    SC_SAMPLE_TABLE_DESCRIPTOR,
)
from app.modules.sc.data_provider.schemas import (
    ScDataInvalidationEvent,
    ScClassifyLimitsResponse,
    ScSampleTableDescriptor,
    ScSqlQueryRequest,
)
from app.modules.sc.data_provider.sampling import compile_sc_sampling_query
from app.modules.sc.data_provider.scope import ScDataScope
from app.modules.sc.data_provider.sql_policy import ScSqlPolicyError, validate_sc_sql
from app.shared.api.schemas import Organization, User
from app.shared.infrastructure.redis.event_publisher import (
    ANNOTATION_CHANNEL,
    PREDICTION_CHANNEL,
)


ARROW_STREAM_MEDIA_TYPE = "application/vnd.apache.arrow.stream"
_logger = logging.getLogger(__name__)
_T = TypeVar("_T")


class _ScQueryClientDisconnected(Exception):
    """Stop work quietly when the downstream HTTP client has gone away."""


class _ManagedStreamingResponse(StreamingResponse):
    """Close query resources even when the ASGI transport drops mid-stream."""

    def __init__(
        self,
        content: AsyncIterator[bytes],
        *,
        on_close: Callable[[], Awaitable[None]],
        media_type: str,
        headers: dict[str, str],
    ) -> None:
        super().__init__(content, media_type=media_type, headers=headers)
        self._on_close = on_close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._on_close()


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


@router.get("/classify-limits", response_model=ScClassifyLimitsResponse)
async def classify_limits(
    request: Request,
    _user: User = Depends(get_current_user),
) -> ScClassifyLimitsResponse:
    return ScClassifyLimitsResponse(max_rows=_runtime(request).config.classify_max_rows)


@router.get("/sample-table-descriptor", response_model=ScSampleTableDescriptor)
async def sample_table_descriptor(
    _user: User = Depends(get_current_user),
) -> ScSampleTableDescriptor:
    return SC_SAMPLE_TABLE_DESCRIPTOR


@router.post("/inspections/{inspection_time}/{wafer_key}/query")
async def query_inspection(
    inspection_time: str,
    wafer_key: int,
    query: ScSqlQueryRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
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
) -> Response:
    scope = ScDataScope.dataset(dataset_id=dataset_id, org_id=org.id)
    return await _query_scope(request, scope, query)


@router.post("/collections/{collection_id}/revisions/{revision_id}/query")
async def query_collection(
    collection_id: str,
    revision_id: str,
    query: ScSqlQueryRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> Response:
    scope = ScDataScope.collection(
        collection_id=collection_id,
        revision_id=revision_id,
        org_id=org.id,
    )
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


@router.get("/collections/{collection_id}/revisions/{revision_id}/events")
async def collection_events(
    collection_id: str,
    revision_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> StreamingResponse:
    scope = ScDataScope.collection(
        collection_id=collection_id,
        revision_id=revision_id,
        org_id=org.id,
    )
    return _events_response(request, scope)


async def _query_scope(
    request: Request,
    scope: ScDataScope,
    query: ScSqlQueryRequest,
) -> Response:
    runtime = _runtime(request)
    try:
        validated_sql = validate_sc_sql(query.sql)
        parameters = query.parameters
        if query.sampling is not None:
            validated_sql, parameters = compile_sc_sampling_query(
                validated_sql,
                query.parameters,
                query.sampling,
            )
    except (InvalidSamplingRuleError, ScSqlPolicyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    materialize_started = time.monotonic()
    revision = await runtime.revisions.current(scope)
    try:
        materialized = await runtime.materializer.materialize(scope, revision=revision)
    except ScCollectionTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    materialize_ms = (time.monotonic() - materialize_started) * 1000
    if await request.is_disconnected():
        return Response(status_code=499)

    lease = runtime.cache.lease(materialized.objects)
    await lease.__aenter__()
    try:
        prepared = await _await_or_disconnect(
            request,
            runtime.executor.prepare_stream(
                sql=validated_sql,
                parameters=parameters,
                materialized=materialized,
            ),
        )
    except _ScQueryClientDisconnected as exc:
        await lease.__aexit__(type(exc), exc, exc.__traceback__)
        return Response(status_code=499)
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

    close_task: asyncio.Task[None] | None = None

    async def close_response() -> None:
        nonlocal close_task
        if close_task is None:

            async def cleanup() -> None:
                try:
                    await prepared.close()
                finally:
                    await lease.__aexit__(None, None, None)

            close_task = asyncio.create_task(
                cleanup(), name="sc-data-provider-response-cleanup"
            )
        await asyncio.shield(close_task)

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in prepared.body:
                yield chunk
        finally:
            await close_response()

    headers = {
        "X-SC-Data-Revision": str(revision),
        "X-SC-Query-Description": query.description,
        "X-SC-Worker-PID": str(os.getpid()),
        "X-SC-Cache": materialized.cache_status,
        "X-SC-Spill-Bytes": str(runtime.executor.temp_directory_size_bytes()),
        "Server-Timing": (
            f"materialize;dur={materialize_ms:.3f}, "
            f"duckdb;dur={prepared.query_duration_ms:.3f}"
        ),
    }
    _logger.info(
        "SC data query prepared description=%s scope=%s revision=%d "
        "cache=%s materialize_ms=%.3f duckdb_ms=%.3f",
        query.description,
        scope.public_name,
        revision,
        materialized.cache_status,
        materialize_ms,
        prepared.query_duration_ms,
    )
    return _ManagedStreamingResponse(
        body(),
        on_close=close_response,
        media_type=ARROW_STREAM_MEDIA_TYPE,
        headers=headers,
    )


async def _await_or_disconnect(request: Request, awaitable: Awaitable[_T]) -> _T:
    work = asyncio.ensure_future(awaitable)
    disconnected = asyncio.create_task(
        _wait_for_disconnect(request), name="sc-data-provider-client-disconnect"
    )
    try:
        done, _pending = await asyncio.wait(
            {work, disconnected}, return_when=asyncio.FIRST_COMPLETED
        )
        if work in done:
            return await work
        await disconnected
        work.cancel()
        try:
            await work
        except asyncio.CancelledError:
            pass
        raise _ScQueryClientDisconnected("SC data query client disconnected")
    finally:
        disconnected.cancel()
        try:
            await disconnected
        except asyncio.CancelledError:
            pass


async def _wait_for_disconnect(request: Request) -> None:
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return


def _events_response(request: Request, scope: ScDataScope) -> StreamingResponse:
    runtime = _runtime(request)
    return StreamingResponse(
        _event_stream(request, scope),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-SC-SSE-Max-Connection-Seconds": str(
                runtime.config.sse_max_connection_seconds
            ),
        },
    )


async def _event_stream(request: Request, scope: ScDataScope) -> AsyncIterator[str]:
    runtime = _runtime(request)
    deadline = time.monotonic() + runtime.config.sse_max_connection_seconds
    source_dataset_ids = frozenset(await runtime.materializer.source_dataset_ids(scope))
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
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=runtime.config.sse_heartbeat_seconds,
                    ),
                    timeout=remaining,
                )
            except TimeoutError:
                break
            if not message:
                yield ": keepalive\n\n"
                continue
            event = _invalidation_from_message(
                scope,
                message,
                source_dataset_ids=source_dataset_ids,
            )
            if event is not None:
                if scope.kind == "collection":
                    event = event.model_copy(
                        update={"revision": await runtime.revisions.increment(scope)}
                    )
                yield _sse_event(event)
    finally:
        await pubsub.unsubscribe(ANNOTATION_CHANNEL, PREDICTION_CHANNEL)
        await pubsub.aclose()


def _invalidation_from_message(
    scope: ScDataScope,
    message: dict[str, object],
    *,
    source_dataset_ids: frozenset[str] = frozenset(),
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
    if scope.kind == "collection" and data.get("dataset_id") not in source_dataset_ids:
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
