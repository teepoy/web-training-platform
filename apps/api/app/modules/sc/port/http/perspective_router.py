from __future__ import annotations

from typing import Any

import polars as pl
import starlette.websockets
from fastapi import APIRouter, Query, WebSocket

from app.modules.auth.port.http.deps import get_current_org, get_current_user
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


@router.websocket("/inspections/{inspection_time}/{wafer_key}/ws")
async def inspection_ws(
    websocket: WebSocket,
    inspection_time: str,
    wafer_key: int,
    reticle_x_die_count: int = Query(default=10, alias="reticleXDieCount", ge=1),
    reticle_y_die_count: int = Query(default=10, alias="reticleYDieCount", ge=1),
    reticle_x_die_shift: int = Query(default=0, alias="reticleXDieShift"),
    reticle_y_die_shift: int = Query(default=0, alias="reticleYDieShift"),
) -> None:
    upstream_reader = websocket.app.state.app_context.sc.upstream_reader

    async def samples_df_factory() -> pl.DataFrame:
        return await _build_inspection_df(
            upstream_reader=upstream_reader,
            inspection_time=inspection_time,
            wafer_key=wafer_key,
            reticle_x_die_count=reticle_x_die_count,
            reticle_y_die_count=reticle_y_die_count,
            reticle_x_die_shift=reticle_x_die_shift,
            reticle_y_die_shift=reticle_y_die_shift,
        )

    await run_sc_perspective_ws(
        websocket=websocket,
        dataset_id=None,
        samples_df_factory=samples_df_factory,
        redis_client=_redis_client(websocket),
    )


@router.websocket("/datasets/{dataset_id}/ws")
async def dataset_ws(
    websocket: WebSocket,
    dataset_id: str,
    reticle_x_die_count: int = Query(default=3, alias="reticleXDieCount", ge=1),
    reticle_y_die_count: int = Query(default=5, alias="reticleYDieCount", ge=1),
    reticle_x_die_shift: int = Query(default=0, alias="reticleXDieShift"),
    reticle_y_die_shift: int = Query(default=0, alias="reticleYDieShift"),
) -> None:
    app_context = websocket.app.state.app_context
    current_user = await get_current_user(websocket)  # type: ignore[arg-type]
    org = await get_current_org(websocket, current_user)  # type: ignore[arg-type]
    upstream_reader = app_context.sc.upstream_reader
    storage_factory = app_context.datasets.dataset_storage_factory

    async def build_dataset_df() -> pl.DataFrame:
        return await _build_dataset_df(
            dataset_id=dataset_id,
            org_id=org.id,
            storage_factory=storage_factory,
            upstream_reader=upstream_reader,
            reticle_x_die_count=reticle_x_die_count,
            reticle_y_die_count=reticle_y_die_count,
            reticle_x_die_shift=reticle_x_die_shift,
            reticle_y_die_shift=reticle_y_die_shift,
        )

    try:
        await run_sc_perspective_ws(
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
