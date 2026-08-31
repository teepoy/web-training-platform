from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from typing import cast

import polars as pl
import pyarrow as pa
import pytest

from app.modules.sc.app.services.latest_source import open_latest_sc_source
from app.modules.sc.domain.upstream_reader import ScUpstreamReader


class _Upstream:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.membership_requests: list[tuple[list[int], Sequence[str]]] = []
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

    async def stream_membership_sample_batches(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        defect_ids: Sequence[int],
        batch_rows: int,
        projection: Sequence[str] | None,
    ) -> AsyncIterator[pa.RecordBatch]:
        del inspection_time, wafer_key, batch_rows
        requested_projection = projection or tuple(self.rows[0])
        self.membership_requests.append((list(defect_ids), requested_projection))
        requested = set(defect_ids)
        rows = [
            {column: row[column] for column in requested_projection if column in row}
            for row in self.rows
            if int(cast(int, row["defect_id"])) in requested
        ]
        yield pa.RecordBatch.from_pylist(rows)


class _OverReturningUpstream(_Upstream):
    async def stream_membership_sample_batches(
        self,
        inspection_time: datetime,
        wafer_key: int,
        *,
        defect_ids: Sequence[int],
        batch_rows: int,
        projection: Sequence[str] | None,
    ) -> AsyncIterator[pa.RecordBatch]:
        del inspection_time, wafer_key, batch_rows
        requested_projection = projection or tuple(self.rows[0])
        self.membership_requests.append((list(defect_ids), requested_projection))
        yield pa.RecordBatch.from_pylist(
            [
                {
                    column: row[column]
                    for column in requested_projection
                    if column in row
                }
                for row in self.rows
            ]
        )


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
            "future_source_field": ["stale-a", "stale-b"],
            "label": ["scratch", "particle"],
            "annotation_id": ["annotation-1", "annotation-2"],
            "predicted_label": ["clean", "scratch"],
            "confidence": [0.8, 0.7],
        }
    )

    resolved_context = open_latest_sc_source(
        upstream_reader=cast(ScUpstreamReader, upstream),
        membership=membership,
        inspection_time=datetime(2026, 8, 29),
        wafer_key=17,
        dataset_id="dataset-1",
        batch_rows=100,
        projection=("rough_bin",),
    )

    async with resolved_context as resolved:
        assert resolved.collect().to_dicts() == [
            {
                "sample_id": "stored-1",
                "label": "scratch",
                "annotation_id": "annotation-1",
                "predicted_label": "clean",
                "confidence": "0.8",
                "defect_id": "1",
                "rough_bin": 8,
            },
            {
                "sample_id": "stored-2",
                "label": "particle",
                "annotation_id": "annotation-2",
                "predicted_label": "scratch",
                "confidence": "0.7",
                "defect_id": "2",
                "rough_bin": 9,
            },
        ]
    with pytest.raises((FileNotFoundError, pl.exceptions.ComputeError)):
        resolved.collect()
    assert upstream.membership_requests == [([1, 2], ["defect_id", "rough_bin"])]
    assert upstream.projections == []


@pytest.mark.asyncio
async def test_resolver_fails_when_upstream_membership_is_missing() -> None:
    upstream = _Upstream([{"defect_id": "1", "rough_bin": 8}])

    with pytest.raises(RuntimeError, match="missing 1 Dataset identities"):
        async with open_latest_sc_source(
            upstream_reader=cast(ScUpstreamReader, upstream),
            membership=pl.LazyFrame({"sample_id": ["1", "2"], "defect_id": ["1", "2"]}),
            inspection_time=datetime(2026, 8, 29),
            wafer_key=17,
            dataset_id="dataset-1",
            batch_rows=100,
        ):
            pass


@pytest.mark.asyncio
async def test_resolver_never_submits_more_than_one_membership_batch() -> None:
    upstream = _Upstream(
        [
            {"defect_id": defect_id, "rough_bin": defect_id + 10}
            for defect_id in range(1, 6)
        ]
    )

    resolved_context = open_latest_sc_source(
        upstream_reader=cast(ScUpstreamReader, upstream),
        membership=pl.LazyFrame(
            {
                "sample_id": [f"sample-{defect_id}" for defect_id in range(1, 6)],
                "defect_id": [str(defect_id) for defect_id in range(1, 6)],
            }
        ),
        inspection_time=datetime(2026, 8, 29),
        wafer_key=17,
        dataset_id="dataset-1",
        batch_rows=2,
        projection=("rough_bin",),
    )

    async with resolved_context as resolved:
        assert resolved.collect().height == 5
    assert [request[0] for request in upstream.membership_requests] == [
        [1, 2],
        [3, 4],
        [5],
    ]


@pytest.mark.asyncio
async def test_resolver_rejects_duplicate_membership_across_batches() -> None:
    upstream = _Upstream(
        [
            {"defect_id": 1, "rough_bin": 11},
            {"defect_id": 2, "rough_bin": 12},
        ]
    )

    with pytest.raises(ValueError, match="duplicate defect_id"):
        async with open_latest_sc_source(
            upstream_reader=cast(ScUpstreamReader, upstream),
            membership=pl.LazyFrame(
                {
                    "sample_id": ["sample-1", "sample-2", "sample-3"],
                    "defect_id": ["1", "2", "1"],
                }
            ),
            inspection_time=datetime(2026, 8, 29),
            wafer_key=17,
            dataset_id="dataset-1",
            batch_rows=2,
        ):
            pass


@pytest.mark.asyncio
async def test_resolver_rejects_an_over_returning_upstream_adapter() -> None:
    upstream = _OverReturningUpstream(
        [
            {"defect_id": 1, "rough_bin": 11},
            {"defect_id": 2, "rough_bin": 12},
            {"defect_id": 3, "rough_bin": 13},
        ]
    )

    with pytest.raises(RuntimeError, match="returned more rows"):
        async with open_latest_sc_source(
            upstream_reader=cast(ScUpstreamReader, upstream),
            membership=pl.LazyFrame(
                {
                    "sample_id": ["sample-1", "sample-2"],
                    "defect_id": ["1", "2"],
                }
            ),
            inspection_time=datetime(2026, 8, 29),
            wafer_key=17,
            dataset_id="dataset-1",
            batch_rows=2,
        ):
            pass
