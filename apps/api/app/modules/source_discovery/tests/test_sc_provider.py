from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from app.modules.source_discovery.adapter.sc_provider import ScSourceRecordProvider
from app.modules.source_discovery.domain.models import (
    FilterCombinator,
    FilterGroup,
    FilterOperator,
    FilterPredicate,
    SourceConnector,
)


class _Upstream:
    def __init__(self) -> None:
        self.range: tuple[datetime, datetime] | None = None

    async def list_inspections(
        self,
        start_time: datetime,
        end_time: datetime,
        lot_id: str | None = None,
        wafer_id: str | None = None,
        layer_id: str | None = None,
        device: str | None = None,
    ) -> pl.LazyFrame:
        del lot_id, wafer_id, layer_id, device
        self.range = (start_time, end_time)
        rows = [
            {"inspection_time": datetime(2026, 8, 15, 7, 59), "wafer_key": 1, "layer_id": "M1"},
            {"inspection_time": datetime(2026, 8, 15, 8, 0), "wafer_key": 2, "layer_id": "M1"},
            {"inspection_time": datetime(2026, 8, 15, 8, 59), "wafer_key": 3, "layer_id": "M1"},
            {"inspection_time": datetime(2026, 8, 15, 9, 0), "wafer_key": 4, "layer_id": "M1"},
        ]
        return (
            pl.DataFrame(rows)
            .lazy()
            .filter(pl.col("inspection_time") >= start_time.replace(tzinfo=None))
            .filter(pl.col("inspection_time") < end_time.replace(tzinfo=None))
        )


class _Importer:
    async def submit_import(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("Import is not used by this test")


@pytest.mark.asyncio
async def test_sc_discovery_uses_local_wall_clock_and_utc_half_open_range() -> None:
    upstream = _Upstream()
    provider = ScSourceRecordProvider(upstream, _Importer())  # type: ignore[arg-type]
    connector = SourceConnector(
        id="connector",
        org_id="org",
        provider_id="sc",
        name="SC",
        config={},
        enabled=True,
        created_by="user",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    condition = FilterGroup(
        combinator=FilterCombinator.ALL,
        children=(
            FilterPredicate(
                field="inspection_time",
                operator=FilterOperator.GTE,
                value="2026-08-15T00:30:00+00:00",
            ),
        ),
    )
    batch = await provider.discover(
        connector=connector,
        condition=condition,
        start_utc=datetime(2026, 8, 15, 0, 0, tzinfo=UTC),
        end_utc=datetime(2026, 8, 15, 1, 0, tzinfo=UTC),
        max_records=10,
    )

    assert upstream.range is not None
    assert upstream.range[0].isoformat() == "2026-08-15T08:00:00+08:00"
    assert upstream.range[1].isoformat() == "2026-08-15T09:00:00+08:00"
    assert [record.record_key for record in batch.records] == [
        "2026-08-15T08:59:00+08:00::3"
    ]
