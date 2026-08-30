from __future__ import annotations

from datetime import datetime, timezone

import grpc
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
