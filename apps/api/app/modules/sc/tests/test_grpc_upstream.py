from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import grpc
import pyarrow as pa
import pytest

from app.modules.sc.adapter.grpc_upstream import GrpcScUpstream
from app.modules.sc.domain.upstream_reader import ScInspectionPublicationCursor
from proto_stubs.sc.v1 import upstream_pb2 as pb


class _MissingInspectionStub:
    async def GetInspection(self, _request: object) -> object:
        raise grpc.aio.AioRpcError(
            grpc.StatusCode.NOT_FOUND,
            grpc.aio.Metadata(),
            grpc.aio.Metadata(),
            details="inspection not found",
        )


class _CurrentInspectionStub:
    async def GetInspection(self, _request: object) -> pb.GetInspectionResponse:
        return pb.GetInspectionResponse(
            inspection_time="2026-08-01T00:00:00+00:00",
            wafer_key=1,
            device="device-1",
            change_token=91,
        )


class _DiscoveryStub:
    def __init__(self) -> None:
        self.request: pb.ListDiscoveryInspectionsRequest | None = None

    async def ListDiscoveryInspections(
        self, request: pb.ListDiscoveryInspectionsRequest
    ) -> pb.ListInspectionsResponse:
        self.request = request
        return pb.ListInspectionsResponse(
            items=(
                pb.InspectionSummary(
                    inspection_time="2026-08-01T08:00:00+08:00",
                    wafer_key=3,
                    published_at="2026-08-30T01:00:00+00:00",
                ),
            )
        )


class _FlightReader:
    def __init__(self, defect_ids: list[int]) -> None:
        self._chunks = iter(
            [
                pa.RecordBatch.from_pylist(
                    [{"defect_id": defect_id} for defect_id in defect_ids]
                )
            ]
        )

    def read_chunk(self) -> object:
        return SimpleNamespace(data=next(self._chunks))

    def cancel(self) -> None:
        return None


class _FlightClient:
    def __init__(self) -> None:
        self.tickets: list[dict[str, object]] = []

    def do_get(self, ticket: Any) -> _FlightReader:
        payload = json.loads(ticket.ticket.decode())
        self.tickets.append(payload)
        return _FlightReader(payload["defect_ids"])


@pytest.mark.asyncio
async def test_get_inspection_maps_upstream_not_found_to_none(monkeypatch) -> None:
    upstream = GrpcScUpstream()
    monkeypatch.setattr(upstream, "_ensure_channel", lambda: _MissingInspectionStub())

    result = await upstream.get_inspection(
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        1,
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_inspection_preserves_authoritative_change_token(monkeypatch) -> None:
    upstream = GrpcScUpstream()
    monkeypatch.setattr(upstream, "_ensure_channel", lambda: _CurrentInspectionStub())

    result = await upstream.get_inspection(
        datetime(2026, 8, 1, tzinfo=timezone.utc),
        1,
    )

    assert result is not None
    assert result.change_token == 91


@pytest.mark.asyncio
async def test_publication_page_sends_complete_keyset_cursor(monkeypatch) -> None:
    upstream = GrpcScUpstream()
    stub = _DiscoveryStub()
    monkeypatch.setattr(upstream, "_ensure_channel", lambda: stub)

    page = await upstream.list_published_inspection_page(
        published_from=datetime(2026, 8, 30, tzinfo=timezone.utc),
        published_until=datetime(2026, 8, 30, 2, tzinfo=timezone.utc),
        after=ScInspectionPublicationCursor(
            published_at=datetime(2026, 8, 30, 0, 30, tzinfo=timezone.utc),
            inspection_time=datetime(2026, 8, 1, 7, tzinfo=timezone.utc),
            wafer_key=2,
        ),
        page_size=256,
    )

    assert stub.request is not None
    assert stub.request.order == pb.INSPECTION_DISCOVERY_ORDER_PUBLICATION
    assert stub.request.after_publication.wafer_key == 2
    assert page.row(0, named=True)["wafer_key"] == 3
    assert page.row(0, named=True)["published_at"].isoformat() == (
        "2026-08-30T01:00:00+00:00"
    )


@pytest.mark.asyncio
async def test_membership_sample_read_sends_one_bounded_flight_ticket(
    monkeypatch,
) -> None:
    upstream = GrpcScUpstream()
    client = _FlightClient()
    monkeypatch.setattr(upstream, "_ensure_flight_client", lambda: client)

    batches = [
        batch
        async for batch in upstream.stream_membership_sample_batches(
            datetime(2026, 8, 1, tzinfo=timezone.utc),
            9,
            defect_ids=[1, 2],
            batch_rows=2,
            projection=("defect_id",),
        )
    ]

    assert [batch.to_pylist() for batch in batches] == [
        [{"defect_id": 1}, {"defect_id": 2}],
    ]
    assert [ticket["defect_ids"] for ticket in client.tickets] == [[1, 2]]
    assert all(ticket["projection"] == ["defect_id"] for ticket in client.tickets)


@pytest.mark.asyncio
async def test_membership_sample_read_rejects_an_oversized_ticket(monkeypatch) -> None:
    upstream = GrpcScUpstream()
    client = _FlightClient()
    monkeypatch.setattr(upstream, "_ensure_flight_client", lambda: client)

    with pytest.raises(ValueError, match="must fit within batch_rows"):
        _ = [
            batch
            async for batch in upstream.stream_membership_sample_batches(
                datetime(2026, 8, 1, tzinfo=timezone.utc),
                9,
                defect_ids=[1, 2, 3],
                batch_rows=2,
                projection=("defect_id",),
            )
        ]

    assert client.tickets == []
