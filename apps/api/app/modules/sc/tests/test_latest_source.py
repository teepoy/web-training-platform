from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import cast

import polars as pl
import pyarrow as pa
import pytest

from app.modules.sc.app.services.latest_source import resolve_latest_sc_source
from app.modules.sc.domain.upstream_reader import ScUpstreamReader


class _Upstream:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.projections: list[Sequence[str] | None] = []

    async def get_sample_count(self, inspection_time: datetime, wafer_key: int) -> int:
        del inspection_time, wafer_key
        return len(self.rows)

    async def stream_sample_batches(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        projection: Sequence[str] | None = None,
        **_kwargs: object,
    ) -> AsyncIterator[pa.RecordBatch]:
        del inspection_time, wafer_key
        self.projections.append(projection)
        rows = self.rows
        if projection is not None:
            rows = [
                {column: row[column] for column in projection if column in row}
                for row in rows
            ]
        yield pa.RecordBatch.from_pylist(rows)


@pytest.mark.asyncio
async def test_resolver_uses_current_source_and_ignores_legacy_extras() -> None:
    upstream = _Upstream(
        [
            {"defect_id": 1, "rough_bin": 8, "unused": "not requested"},
            {"defect_id": 2, "rough_bin": 9, "unused": "not requested"},
            {"defect_id": 3, "rough_bin": 10, "unused": "outside membership"},
        ]
    )
    membership = pl.LazyFrame(
        {
            "sample_id": ["stored-1", "stored-2"],
            "defect_id": ["1", "2"],
            "rough_bin": [1, 1],
            "label": ["scratch", "particle"],
        }
    )

    resolved = await resolve_latest_sc_source(
        upstream_reader=cast(ScUpstreamReader, upstream),
        membership=membership,
        inspection_time=datetime(2026, 8, 29),
        wafer_key=17,
        dataset_id="dataset-1",
        batch_rows=100,
        projection=("rough_bin",),
    )

    assert resolved.collect().to_dicts() == [
        {
            "sample_id": "stored-1",
            "label": "scratch",
            "defect_id": "1",
            "rough_bin": 8,
        },
        {
            "sample_id": "stored-2",
            "label": "particle",
            "defect_id": "2",
            "rough_bin": 9,
        },
    ]
    assert upstream.projections == [["defect_id", "rough_bin"]]


@pytest.mark.asyncio
async def test_resolver_fails_when_upstream_membership_is_missing() -> None:
    upstream = _Upstream([{"defect_id": "1", "rough_bin": 8}])

    with pytest.raises(RuntimeError, match="missing 1 Dataset identities"):
        await resolve_latest_sc_source(
            upstream_reader=cast(ScUpstreamReader, upstream),
            membership=pl.LazyFrame({"sample_id": ["1", "2"], "defect_id": ["1", "2"]}),
            inspection_time=datetime(2026, 8, 29),
            wafer_key=17,
            dataset_id="dataset-1",
            batch_rows=100,
        )
