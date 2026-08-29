from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import AsyncIterator, TypeVar


_T = TypeVar("_T")


class DirectMetadataCache:
    """Cache-shaped adapter that always delegates metadata reads to the source."""

    @asynccontextmanager
    async def fill_lock(self, *_parts: str) -> AsyncIterator[bool]:
        yield True

    async def wait_for_fill(
        self,
        getter: Callable[[], Awaitable[_T | None]],
        *,
        timeout_seconds: float = 30,
    ) -> _T | None:
        del timeout_seconds
        return await getter()

    async def get_inspection(self, inspection_time: str, wafer_key: int) -> dict | None:
        del inspection_time, wafer_key
        return None

    async def set_inspection(
        self, inspection_time: str, wafer_key: int, data: dict
    ) -> None:
        del inspection_time, wafer_key, data

    async def get_list_inspections(
        self,
        start_time: str,
        end_time: str,
        lot_id: str = "",
        wafer_id: str = "",
        layer_id: str = "",
        device: str = "",
    ) -> list[dict] | None:
        del start_time, end_time, lot_id, wafer_id, layer_id, device
        return None

    async def set_list_inspections(
        self,
        start_time: str,
        end_time: str,
        items: list[dict],
        lot_id: str = "",
        wafer_id: str = "",
        layer_id: str = "",
        device: str = "",
    ) -> None:
        del start_time, end_time, items, lot_id, wafer_id, layer_id, device

    async def get_patch_zips(
        self,
        inspection_time: str,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
    ) -> list[dict] | None:
        del inspection_time, lot_id, wafer_id, device, layer_id
        return None

    async def set_patch_zips(
        self,
        inspection_time: str,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
        zips: list[dict],
    ) -> None:
        del inspection_time, lot_id, wafer_id, device, layer_id, zips

    async def get_list_review_images(
        self, inspection_time: str, wafer_key: int
    ) -> list[dict] | None:
        del inspection_time, wafer_key
        return None

    async def set_list_review_images(
        self, inspection_time: str, wafer_key: int, items: list[dict]
    ) -> None:
        del inspection_time, wafer_key, items
