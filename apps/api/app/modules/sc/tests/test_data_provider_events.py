from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast

import pytest
from starlette.requests import ClientDisconnect, Request
from starlette.types import Message, Scope

from app.modules.sc.data_provider.router import (
    _ManagedStreamingResponse,
    _ScQueryClientDisconnected,
    _await_or_disconnect,
    _event_stream,
    _invalidation_from_message,
    _sse_event,
)
from app.modules.sc.data_provider import router as data_provider_router
from app.modules.sc.data_provider.schemas import ScDataInvalidationEvent
from app.modules.sc.data_provider.scope import ScDataScope
from app.shared.infrastructure.redis.event_publisher import PREDICTION_CHANNEL


@pytest.mark.asyncio
async def test_managed_stream_closes_resources_on_transport_disconnect() -> None:
    closed = False

    async def body() -> AsyncIterator[bytes]:
        yield b"arrow-header"

    async def close() -> None:
        nonlocal closed
        closed = True

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError("client disconnected")

    response = _ManagedStreamingResponse(
        body(),
        on_close=close,
        media_type="application/vnd.apache.arrow.stream",
        headers={},
    )
    scope = cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
        },
    )

    with pytest.raises(ClientDisconnect):
        await response(scope, receive, send)

    assert closed


@pytest.mark.asyncio
async def test_disconnect_cancels_query_before_the_first_arrow_chunk() -> None:
    cancelled = False

    async def query() -> None:
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    request = Request(
        cast(Scope, {"type": "http", "method": "POST", "path": "/query"}),
        receive,
    )

    with pytest.raises(_ScQueryClientDisconnected, match="client disconnected"):
        await _await_or_disconnect(request, query())

    assert cancelled


@pytest.mark.asyncio
async def test_event_stream_closes_pubsub_at_connection_deadline(monkeypatch) -> None:
    closed = False
    unsubscribed = False

    class PubSub:
        async def subscribe(self, *channels: str) -> None:
            pass

        async def get_message(
            self, *, ignore_subscribe_messages: bool, timeout: int
        ) -> dict[str, object] | None:
            await asyncio.Event().wait()
            return None

        async def unsubscribe(self, *channels: str) -> None:
            nonlocal unsubscribed
            unsubscribed = True

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    pubsub = PubSub()
    runtime = SimpleNamespace(
        config=SimpleNamespace(
            sse_max_connection_seconds=0.01,
            sse_heartbeat_seconds=30,
        ),
        materializer=SimpleNamespace(
            source_dataset_ids=lambda scope: asyncio.sleep(0, result=[])
        ),
        revisions=SimpleNamespace(current=lambda scope: asyncio.sleep(0, result=1)),
        redis=SimpleNamespace(pubsub=lambda: pubsub),
    )
    monkeypatch.setattr(data_provider_router, "_runtime", lambda request: runtime)
    request = SimpleNamespace(is_disconnected=lambda: asyncio.sleep(0, result=False))
    stream = _event_stream(
        cast(Request, request),
        ScDataScope.dataset(dataset_id="ds-1", org_id="org-1"),
    )

    assert "\"revision\":1" in await anext(stream)
    with pytest.raises(StopAsyncIteration):
        await anext(stream)

    assert unsubscribed
    assert closed


def test_dataset_event_maps_atomic_revision_and_changed_kind() -> None:
    scope = ScDataScope.dataset(dataset_id="ds-1", org_id="org-1")
    event = _invalidation_from_message(
        scope,
        {
            "channel": PREDICTION_CHANNEL.encode(),
            "data": json.dumps(
                {
                    "revision": 7,
                    "event": "prediction.refresh",
                    "data": {"dataset_id": "ds-1"},
                }
            ).encode(),
        },
    )

    assert event == ScDataInvalidationEvent(
        scope="dataset:ds-1",
        revision=7,
        changed_kinds=["prediction"],
    )
    assert event is not None
    assert _sse_event(event).startswith("event: invalidation\ndata: {")


def test_collection_event_accepts_only_revision_source_datasets() -> None:
    scope = ScDataScope.collection(
        collection_id="collection-1",
        revision_id="revision-1",
        org_id="org-1",
    )
    message: dict[str, object] = {
        "channel": PREDICTION_CHANNEL,
        "data": json.dumps(
            {
                "revision": 4,
                "data": {"dataset_id": "dataset-a"},
            }
        ),
    }

    event = _invalidation_from_message(
        scope,
        message,
        source_dataset_ids=frozenset({"dataset-a", "dataset-b"}),
    )

    assert event == ScDataInvalidationEvent(
        scope="collection:collection-1/revision-1",
        revision=4,
        changed_kinds=["prediction"],
    )
    assert (
        _invalidation_from_message(
            scope,
            {
                **message,
                "data": json.dumps(
                    {"revision": 4, "data": {"dataset_id": "dataset-c"}}
                ),
            },
            source_dataset_ids=frozenset({"dataset-a", "dataset-b"}),
        )
        is None
    )


@pytest.mark.parametrize("wafer_key", [None, "invalid", [], {}])
def test_malformed_inspection_event_is_ignored(wafer_key: object) -> None:
    scope = ScDataScope.inspection(
        inspection_time="2026-01-01T00:00:00",
        wafer_key=3,
        org_id="org-1",
    )

    assert (
        _invalidation_from_message(
            scope,
            {
                "channel": PREDICTION_CHANNEL,
                "data": json.dumps(
                    {
                        "revision": 1,
                        "data": {
                            "inspection_time": "2026-01-01T00:00:00",
                            "wafer_key": wafer_key,
                        },
                    }
                ),
            },
        )
        is None
    )
