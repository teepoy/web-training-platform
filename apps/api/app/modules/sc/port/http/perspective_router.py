from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import polars as pl
import starlette.websockets
from fastapi import APIRouter, WebSocket
from perspective import Server

from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.storage.port.local import DatasetStorageFactoryPort
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
from app.modules.sc.port.http.perspective_ws import (
    _build_dataset_df,
    _build_inspection_df,
    overlay_df_from_samples,
    run_sc_perspective_ws,
)

router = APIRouter(prefix="/api/v1/sc/perspective", tags=["sc-perspective"])


def _redis_client(websocket: WebSocket) -> Any | None:
    publisher = websocket.app.state.app_context.shared.redis_event_publisher
    return getattr(publisher, "_redis", None)


def _perspective_server(websocket: WebSocket) -> Server:
    server = getattr(websocket.app.state, "perspective_server", None)
    if server is None:
        raise RuntimeError("Perspective Server was not initialized")
    return cast(Server, server)


@router.websocket("/inspections/{inspection_time}/{wafer_key}/ws")
async def inspection_ws(
    websocket: WebSocket,
    inspection_time: str,
    wafer_key: int,
    table_name: UUID,
) -> None:
    injector = websocket.app.state.app_context.injector
    if injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    upstream_reader = injector.get(ScUpstreamReader)

    async def samples_df_factory() -> pl.DataFrame:
        return await _build_inspection_df(
            upstream_reader=upstream_reader,
            inspection_time=inspection_time,
            wafer_key=wafer_key,
        )

    await run_sc_perspective_ws(
        server=_perspective_server(websocket),
        table_name=str(table_name),
        websocket=websocket,
        dataset_id=None,
        samples_df_factory=samples_df_factory,
        redis_client=_redis_client(websocket),
    )


@router.websocket("/datasets/{dataset_id}/ws")
async def dataset_ws(
    websocket: WebSocket,
    dataset_id: str,
    table_name: UUID,
) -> None:
    injector = websocket.app.state.app_context.injector
    if injector is None:
        raise RuntimeError("AppContext injector was not initialized")
    current_user = await get_current_user(websocket)  # type: ignore[arg-type]
    org = await get_current_org(websocket, current_user)  # type: ignore[arg-type]
    upstream_reader = injector.get(ScUpstreamReader)
    storage_factory = injector.get(DatasetStorageFactoryPort)

    async def build_dataset_df() -> pl.DataFrame:
        return await _build_dataset_df(
            dataset_id=dataset_id,
            org_id=org.id,
            storage_factory=storage_factory,
            upstream_reader=upstream_reader,
        )

    try:
        await run_sc_perspective_ws(
            server=_perspective_server(websocket),
            table_name=str(table_name),
            websocket=websocket,
            dataset_id=dataset_id,
            samples_df_factory=build_dataset_df,
            redis_client=_redis_client(websocket),
            refresh_overlay=lambda: _refresh_overlay(build_dataset_df),
        )
    except starlette.websockets.WebSocketDisconnect:
        pass


async def _refresh_overlay(build_dataset_df: Any) -> pl.DataFrame:
    return overlay_df_from_samples(await build_dataset_df())
