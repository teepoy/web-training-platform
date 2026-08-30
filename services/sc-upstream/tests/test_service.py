from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, cast
from unittest.mock import AsyncMock

import grpc
import polars as pl
import pytest

from proto_stubs.sc.v1 import upstream_pb2 as pb
from sc_upstream.service import ScUpstreamService
from sc_upstream.upstream_db import (
    InspectionDiscoveryOrder,
    InspectionDiscoveryQuery,
)


@pytest.mark.parametrize(
    ("method_name", "rpc_request", "message"),
    [
        (
            "GetInspection",
            pb.GetInspectionRequest(inspection_time="invalid", wafer_key=1),
            "invalid inspection_time format",
        ),
        (
            "ListInspections",
            pb.ListInspectionsRequest(start_time="invalid", end_time="invalid"),
            "invalid time format",
        ),
        (
            "GetInspectionPatchZips",
            pb.GetInspectionPatchZipsRequest(inspection_time="invalid"),
            "invalid inspection_time format",
        ),
        (
            "GetReviewImageFileSpec",
            pb.GetReviewImageFileSpecRequest(inspection_time="invalid"),
            "invalid inspection_time format",
        ),
        (
            "ListReviewImages",
            pb.ListReviewImagesRequest(inspection_time="invalid"),
            "invalid inspection_time format",
        ),
    ],
)
def test_invalid_requests_await_grpc_abort(
    method_name: str, rpc_request: object, message: str
) -> None:
    service = ScUpstreamService(
        cast(Any, object()), cast(Any, object()), cast(Any, object())
    )
    context = AsyncMock()

    asyncio.run(getattr(service, method_name)(rpc_request, context))

    context.abort.assert_awaited_once_with(grpc.StatusCode.INVALID_ARGUMENT, message)


class _MissingInspectionCache:
    async def get_inspection(self, inspection_time: str, wafer_key: int) -> None:
        return None

    @asynccontextmanager
    async def fill_lock(self, *parts: str) -> AsyncIterator[bool]:
        yield True


class _MissingInspectionDB:
    async def get_inspection(self, inspection_time: object, wafer_key: int) -> None:
        return None


def test_missing_inspection_awaits_not_found_abort() -> None:
    service = ScUpstreamService(
        cast(Any, _MissingInspectionDB()),
        cast(Any, object()),
        cast(Any, _MissingInspectionCache()),
    )
    context = AsyncMock()

    asyncio.run(
        service.GetInspection(
            pb.GetInspectionRequest(inspection_time="2026-08-04T00:00:00", wafer_key=7),
            context,
        )
    )

    context.abort.assert_awaited_once_with(
        grpc.StatusCode.NOT_FOUND, "inspection not found"
    )


class _DiscoveryDB:
    def __init__(self) -> None:
        self.query: InspectionDiscoveryQuery | None = None

    async def list_discovery_inspections(
        self, query: InspectionDiscoveryQuery
    ) -> pl.DataFrame:
        self.query = query
        return pl.DataFrame(
            [
                {
                    "inspection_time": "2026-08-01T08:00:00+08:00",
                    "wafer_key": 3,
                    "published_at": "2026-08-30T01:00:00+00:00",
                    "layer_id": "M1",
                }
            ]
        )


@pytest.mark.asyncio
async def test_discovery_page_transports_publication_cursor_and_identity() -> None:
    database = _DiscoveryDB()
    service = ScUpstreamService(
        cast(Any, database), cast(Any, object()), cast(Any, object())
    )

    response = await service.ListDiscoveryInspections(
        pb.ListDiscoveryInspectionsRequest(
            order=pb.INSPECTION_DISCOVERY_ORDER_PUBLICATION,
            published_from="2026-08-30T00:00:00+00:00",
            published_until="2026-08-30T02:00:00+00:00",
            after_publication=pb.InspectionPublicationCursor(
                published_at="2026-08-30T00:30:00+00:00",
                inspection_time="2026-08-01T07:00:00+08:00",
                wafer_key=2,
            ),
            page_size=256,
        ),
        AsyncMock(),
    )

    assert database.query is not None
    assert database.query.order is InspectionDiscoveryOrder.PUBLICATION
    assert database.query.after_publication is not None
    assert database.query.after_publication.wafer_key == 2
    assert response.items[0].published_at == "2026-08-30T01:00:00+00:00"
    assert response.items[0].inspection_time == "2026-08-01T08:00:00+08:00"
