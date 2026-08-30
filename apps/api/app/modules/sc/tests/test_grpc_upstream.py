from __future__ import annotations

from datetime import datetime, timezone

import grpc
import pytest

from app.modules.sc.adapter.grpc_upstream import GrpcScUpstream


class _MissingInspectionStub:
    async def GetInspection(self, _request: object) -> object:
        raise grpc.aio.AioRpcError(
            grpc.StatusCode.NOT_FOUND,
            grpc.aio.Metadata(),
            grpc.aio.Metadata(),
            details="inspection not found",
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
