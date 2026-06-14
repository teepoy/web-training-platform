from __future__ import annotations

import io
import os

from diskcache import Cache
from polars import LazyFrame

CACHE_TTL = 3600


class QueryCache:
    def __init__(self, cache_dir: str | None = None) -> None:
        self._dir = cache_dir or os.environ.get("CACHE_DIR", "/tmp/sc-upstream")
        self._cache = Cache(self._dir)

    def _key(self, *parts: str) -> str:
        return ":".join(parts)

    def get_inspection(self, inspection_time: str, wafer_key: int) -> dict | None:
        return self._cache.get(self._key("inspect", inspection_time, str(wafer_key)))

    def set_inspection(self, inspection_time: str, wafer_key: int, data: dict) -> None:
        self._cache.set(
            self._key("inspect", inspection_time, str(wafer_key)),
            data,
            expire=CACHE_TTL,
        )

    def get_list_inspections(self, start_time: str, end_time: str) -> list[dict] | None:
        return self._cache.get(self._key("insps", start_time, end_time))

    def set_list_inspections(
        self, start_time: str, end_time: str, items: list[dict]
    ) -> None:
        self._cache.set(
            self._key("insps", start_time, end_time),
            items,
            expire=CACHE_TTL,
        )

    def get_list_review_images(
        self, inspection_time: str, wafer_key: int
    ) -> list[dict] | None:
        return self._cache.get(self._key("review", inspection_time, str(wafer_key)))

    def set_list_review_images(
        self, inspection_time: str, wafer_key: int, items: list[dict]
    ) -> None:
        self._cache.set(
            self._key("review", inspection_time, str(wafer_key)),
            items,
            expire=CACHE_TTL,
        )

    def get_list_samples(
        self, inspection_time: str, wafer_key: int
    ) -> LazyFrame | None:
        key = self._key("samples", inspection_time, str(wafer_key))
        ipc_bytes = self._cache.get(key)
        if ipc_bytes is not None:
            from polars import read_ipc

            return read_ipc(io.BytesIO(ipc_bytes)).lazy()
        return None

    def set_list_samples(
        self, inspection_time: str, wafer_key: int, lf: LazyFrame
    ) -> None:
        key = self._key("samples", inspection_time, str(wafer_key))
        buf = io.BytesIO()
        lf.collect().write_ipc(buf)
        self._cache.set(key, buf.getvalue(), expire=CACHE_TTL)

    def get_patch_zips(
        self,
        inspection_time: str,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
    ) -> list[dict] | None:
        return self._cache.get(
            self._key("zips", inspection_time, lot_id, wafer_id, device, layer_id)
        )

    def set_patch_zips(
        self,
        inspection_time: str,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
        items: list[dict],
    ) -> None:
        self._cache.set(
            self._key("zips", inspection_time, lot_id, wafer_id, device, layer_id),
            items,
            expire=CACHE_TTL,
        )
