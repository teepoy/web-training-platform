from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, cast
from unittest.mock import AsyncMock

import grpc
import pytest

from proto_stubs.sc.v1 import upstream_pb2 as pb
from sc_upstream.service import ScUpstreamService


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
