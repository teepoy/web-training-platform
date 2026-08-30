from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import polars as pl

from sc_upstream.upstream_db import (
    InspectionDiscoveryOrder,
    InspectionDiscoveryQuery,
    SampleBatchStream,
)


_SAMPLE_SCHEMA: Mapping[str, pl.DataType | type[pl.DataType]] = {
    "wafer_key": pl.Int64,
    "inspection_time": pl.Datetime("us", "UTC"),
    "defect_id": pl.Int64,
    "test_id": pl.Int32,
    "class_number": pl.Int32,
    "rough_bin": pl.Int32,
    "wafer_x": pl.Int32,
    "wafer_y": pl.Int32,
    "index_x": pl.Int32,
    "index_y": pl.Int32,
    "adder": pl.Int32,
    "cluster": pl.Int32,
    "images": pl.Int32,
    "size_x": pl.Int32,
    "size_y": pl.Int32,
    "size_d": pl.Int32,
    "area": pl.Int32,
    "final_bin": pl.Int32,
    "manual_bin": pl.Int32,
    "kill_ratio": pl.Float64,
    "lot_id": pl.String,
    "wafer_id": pl.String,
    "layer_id": pl.String,
    "inspect_equip_id": pl.String,
    "device": pl.String,
    "origin_x": pl.Int32,
    "origin_y": pl.Int32,
    "die_size_x": pl.Int32,
    "die_size_y": pl.Int32,
    "recipe_id": pl.String,
    "die_x": pl.Int32,
    "die_y": pl.Int32,
}


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _sample_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    for row in rows:
        value = datetime.fromisoformat(row["inspection_time"])
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        row["inspection_time"] = value
    return pl.DataFrame(rows, schema=_SAMPLE_SCHEMA, strict=False)


def _inspection_frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    for row in rows:
        for field in ("inspection_time", "published_at"):
            if row.get(field):
                row[field] = datetime.fromisoformat(row[field])
    return pl.DataFrame(rows)


class HttpUpstreamAdapter:
    """Read the standalone upstream mock over its HTTP source boundary."""

    def __init__(self, *, base_url: str, token: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds

    def _get(self, path: str, params: Mapping[str, object]) -> Any:
        query = urlencode(
            {name: value for name, value in params.items() if value not in (None, "")}
        )
        request = Request(
            f"{self._base_url}{path}?{query}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"upstream mock returned {exc.code}: {detail}") from exc

    def _post(self, path: str, body: Mapping[str, object]) -> Any:
        request = Request(
            f"{self._base_url}{path}",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return json.load(response)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"upstream mock returned {exc.code}: {detail}") from exc

    async def get_inspection(
        self, inspection_time: datetime, wafer_key: int
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            self._get,
            f"/upstream/v1/inspections/{wafer_key}",
            {"inspection_time": _isoformat(inspection_time)},
        )

    async def list_inspections(
        self,
        start_time: datetime,
        end_time: datetime,
        lot_id: str = "",
        wafer_id: str = "",
        layer_id: str = "",
        device: str = "",
    ) -> pl.LazyFrame:
        rows = await asyncio.to_thread(
            self._get,
            "/upstream/v1/inspections",
            {
                "start_time": _isoformat(start_time),
                "end_time": _isoformat(end_time),
                "lot_id": lot_id,
                "wafer_id": wafer_id,
                "layer_id": layer_id,
                "device": device,
            },
        )
        return pl.DataFrame(rows or []).lazy()

    async def list_discovery_inspections(
        self, query: InspectionDiscoveryQuery
    ) -> pl.DataFrame:
        params: dict[str, object] = {
            "order": query.order.value,
            "page_size": query.page_size,
            "start_time": _isoformat(query.start_time) if query.start_time else None,
            "end_time": _isoformat(query.end_time) if query.end_time else None,
            "published_from": (
                _isoformat(query.published_from) if query.published_from else None
            ),
            "published_until": (
                _isoformat(query.published_until) if query.published_until else None
            ),
        }
        if query.order is InspectionDiscoveryOrder.PRIMARY_KEY:
            after = query.after_primary_key
            if after is not None:
                params["after_inspection_time"] = _isoformat(after.inspection_time)
                params["after_wafer_key"] = after.wafer_key
        else:
            after = query.after_publication
            if after is not None:
                params["after_published_at"] = _isoformat(after.published_at)
                params["after_inspection_time"] = _isoformat(after.inspection_time)
                params["after_wafer_key"] = after.wafer_key
        rows = await asyncio.to_thread(
            self._get,
            "/upstream/v1/discovery-inspections",
            params,
        )
        return _inspection_frame(rows or [])

    async def list_samples(
        self, inspection_time: datetime, wafer_key: int
    ) -> pl.LazyFrame:
        count = await self.get_sample_count(inspection_time, wafer_key)
        batches = await asyncio.to_thread(
            lambda: list(
                self._sample_batches(
                    inspection_time,
                    wafer_key,
                    batch_size=65536,
                    offset=0,
                    count=count,
                )
            )
        )
        frame = pl.concat(batches) if batches else pl.DataFrame(schema=_SAMPLE_SCHEMA)
        return frame.lazy()

    async def get_sample_count(self, inspection_time: datetime, wafer_key: int) -> int:
        result = await asyncio.to_thread(
            self._get,
            f"/upstream/v1/inspections/{wafer_key}/sample-count",
            {"inspection_time": _isoformat(inspection_time)},
        )
        return int(result["count"])

    def open_list_samples_stream(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        batch_size: int = 65536,
        offset: int = 0,
        count: int | None = None,
    ) -> SampleBatchStream:
        if batch_size <= 0 or batch_size > 65536:
            raise ValueError("batch_size must be between 1 and 65536")
        if offset < 0:
            raise ValueError("offset must not be negative")
        if count is not None and count < 0:
            raise ValueError("count must not be negative")
        return SampleBatchStream(
            schema=pl.DataFrame(schema=_SAMPLE_SCHEMA).to_arrow().schema,
            batches=self._sample_batches(
                inspection_time,
                wafer_key,
                batch_size=batch_size,
                offset=offset,
                count=count,
            ),
        )

    def open_membership_samples_stream(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        defect_ids: Sequence[int],
        projection: Sequence[str] | None,
        batch_size: int,
    ) -> SampleBatchStream:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if not defect_ids:
            raise ValueError("defect_ids must not be empty")
        selected = list(projection) if projection is not None else list(_SAMPLE_SCHEMA)
        unknown = set(selected).difference(_SAMPLE_SCHEMA)
        if unknown:
            raise ValueError(f"unsupported sample projection: {sorted(unknown)}")
        result = self._post(
            "/upstream/v1/inspection-samples/query",
            {
                "inspection_time": _isoformat(inspection_time),
                "wafer_key": wafer_key,
                "defect_ids": list(defect_ids),
                "projection": selected,
            },
        )
        rows = result["rows"]
        for row in rows:
            if "inspection_time" in row:
                value = datetime.fromisoformat(row["inspection_time"])
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                row["inspection_time"] = value
        frame = pl.DataFrame(
            rows,
            schema={column: _SAMPLE_SCHEMA[column] for column in selected},
            strict=False,
        )
        return SampleBatchStream(
            schema=frame.to_arrow().schema,
            batches=iter(frame.iter_slices(n_rows=batch_size)),
        )

    def _sample_batches(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        batch_size: int,
        offset: int,
        count: int | None,
    ) -> Iterator[pl.DataFrame]:
        consumed = 0
        while count is None or consumed < count:
            requested = (
                batch_size if count is None else min(batch_size, count - consumed)
            )
            result = self._get(
                f"/upstream/v1/inspections/{wafer_key}/samples",
                {
                    "inspection_time": _isoformat(inspection_time),
                    "offset": offset + consumed,
                    "count": requested,
                },
            )
            rows = result["rows"]
            if not rows:
                break
            yield _sample_frame(rows)
            consumed += len(rows)
            if len(rows) < requested:
                break

    async def list_review_images(
        self, inspection_time: datetime, wafer_key: int
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._get,
            f"/upstream/v1/inspections/{wafer_key}/review-images",
            {"inspection_time": _isoformat(inspection_time)},
        )

    async def get_inspection_patch_zips(
        self,
        inspection_time: datetime,
        lot_id: str,
        wafer_id: str,
        device: str,
        layer_id: str,
    ) -> list[dict[str, str]]:
        return await asyncio.to_thread(
            self._get,
            "/upstream/v1/patch-zips",
            {
                "inspection_time": _isoformat(inspection_time),
                "lot_id": lot_id,
                "wafer_id": wafer_id,
                "device": device,
                "layer_id": layer_id,
            },
        )


def factory() -> tuple[HttpUpstreamAdapter, HttpUpstreamAdapter]:
    base_url = os.environ["UPSTREAM_MOCK_URL"]
    token = os.environ["UPSTREAM_MOCK_TOKEN"]
    timeout_seconds = float(os.environ["UPSTREAM_MOCK_TIMEOUT_SECONDS"])
    if timeout_seconds <= 0:
        raise RuntimeError("UPSTREAM_MOCK_TIMEOUT_SECONDS must be positive")
    adapter = HttpUpstreamAdapter(
        base_url=base_url,
        token=token,
        timeout_seconds=timeout_seconds,
    )
    return adapter, adapter
