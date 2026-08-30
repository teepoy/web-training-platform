from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import polars as pl
import pytest

from app.modules.source_discovery.adapter.sc_provider import ScSourceRecordProvider
from app.modules.source_discovery.domain.models import (
    FilterCombinator,
    FilterGroup,
    FilterOperator,
    FilterPredicate,
    ImportProfileVersion,
    SourceConnector,
    SourceRecord,
)
from app.modules.sc.domain.entities.sc_import import ScImportStatus
from app.modules.sc.domain.upstream_reader import (
    ScInspectionKey,
    ScInspectionPublicationCursor,
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

    async def list_inspection_page(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        after: ScInspectionKey | None,
        page_size: int,
    ) -> pl.DataFrame:
        frame = await self.list_inspections(start_time, end_time)
        if after is not None:
            frame = frame.filter(
                (pl.col("inspection_time") > after.inspection_time.replace(tzinfo=None))
                | (
                    (pl.col("inspection_time") == after.inspection_time.replace(tzinfo=None))
                    & (pl.col("wafer_key") > after.wafer_key)
                )
            )
        return await frame.sort(["inspection_time", "wafer_key"]).limit(page_size).collect_async()

    async def list_published_inspection_page(
        self,
        *,
        published_from: datetime,
        published_until: datetime,
        after: ScInspectionPublicationCursor | None,
        page_size: int,
    ) -> pl.DataFrame:
        del published_from, published_until, after, page_size
        return pl.DataFrame()


class _Importer:
    async def submit_import(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("Import is not used by this test")


class _ManyUpstream:
    async def list_inspections(
        self,
        start_time: datetime,
        end_time: datetime,
        **_filters: object,
    ) -> pl.LazyFrame:
        del end_time
        start = start_time.replace(tzinfo=None)
        return pl.DataFrame(
            {
                "inspection_time": [
                    start + timedelta(seconds=index) for index in range(600)
                ],
                "wafer_key": list(range(600)),
                "layer_id": ["M1"] * 600,
            }
        ).lazy()

    async def list_inspection_page(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        after: ScInspectionKey | None,
        page_size: int,
    ) -> pl.DataFrame:
        frame = await self.list_inspections(start_time, end_time)
        if after is not None:
            frame = frame.filter(
                (pl.col("inspection_time") > after.inspection_time.replace(tzinfo=None))
                | (
                    (pl.col("inspection_time") == after.inspection_time.replace(tzinfo=None))
                    & (pl.col("wafer_key") > after.wafer_key)
                )
            )
        return await frame.sort(["inspection_time", "wafer_key"]).limit(page_size).collect_async()

    async def list_published_inspection_page(
        self,
        *,
        published_from: datetime,
        published_until: datetime,
        after: ScInspectionPublicationCursor | None,
        page_size: int,
    ) -> pl.DataFrame:
        del published_from, published_until, after, page_size
        return pl.DataFrame()


class _PublishedUpstream:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.after: list[ScInspectionPublicationCursor | None] = []

    async def list_published_inspection_page(
        self,
        *,
        published_from: datetime,
        published_until: datetime,
        after: ScInspectionPublicationCursor | None,
        page_size: int,
    ) -> pl.DataFrame:
        self.after.append(after)
        rows = [
            row
            for row in self.rows
            if published_from
            <= cast(datetime, row["published_at"])
            < published_until
            and (
                after is None
                or (
                    row["published_at"],
                    row["inspection_time"],
                    row["wafer_key"],
                )
                > (after.published_at, after.inspection_time, after.wafer_key)
            )
        ]
        rows.sort(
            key=lambda row: (
                row["published_at"],
                row["inspection_time"],
                row["wafer_key"],
            )
        )
        return pl.DataFrame(rows[:page_size])

    async def list_inspection_page(self, **_kwargs: object) -> pl.DataFrame:
        return pl.DataFrame()

    async def list_inspections(self, *_args: object, **_kwargs: object) -> pl.LazyFrame:
        return pl.DataFrame(self.rows).lazy()


class _CapturingImporter:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def submit_import(self, **kwargs: object) -> ScImportStatus:
        self.kwargs = kwargs
        return ScImportStatus(
            status="completed",
            dataset_id="dataset-1",
            dataset_name="Imported wafer",
            imported_count=10,
        )


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
    records = [
        record
        async for batch in provider.discover_backfill(
            connector=connector,
            condition=condition,
            start_utc=datetime(2026, 8, 15, 0, 0, tzinfo=UTC),
            end_utc=datetime(2026, 8, 15, 1, 0, tzinfo=UTC),
        )
        for record in batch.records
    ]

    assert upstream.range is not None
    assert upstream.range[0].isoformat() == "2026-08-15T08:00:00+08:00"
    assert upstream.range[1].isoformat() == "2026-08-15T09:00:00+08:00"
    assert [record.record_key for record in records] == [
        "2026-08-15T08:59:00+08:00::3"
    ]


@pytest.mark.asyncio
async def test_sc_discovery_import_leaves_parser_selection_to_service() -> None:
    importer = _CapturingImporter()
    provider = ScSourceRecordProvider(_Upstream(), importer)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    connector = SourceConnector(
        id="connector",
        org_id="org",
        provider_id="sc",
        name="SC",
        config={},
        enabled=True,
        created_by="user",
        created_at=now,
        updated_at=now,
    )
    profile = ImportProfileVersion(
        id="profile-v1",
        profile_key="profile",
        version=1,
        org_id="org",
        connector_id="connector",
        name="SC import",
        settings={"label_space": ["Scratch"]},
        created_by="user",
        created_at=now,
    )
    record = SourceRecord(
        record_key="record",
        observed_at=now,
        display_name="Imported wafer",
        attributes={
            "inspection_time": "2026-08-15T08:59:00+08:00",
            "wafer_key": 3,
        },
    )

    result = await provider.import_record(
        connector=connector,
        profile=profile,
        record=record,
        org_id="org",
        actor_id="user",
    )

    assert result.dataset_id == "dataset-1"
    assert "image_source_format" not in importer.kwargs


@pytest.mark.asyncio
async def test_sc_discovery_pages_all_matches_without_one_eager_batch() -> None:
    provider = ScSourceRecordProvider(_ManyUpstream(), _Importer())  # type: ignore[arg-type]
    now = datetime.now(UTC)
    connector = SourceConnector(
        id="connector",
        org_id="org",
        provider_id="sc",
        name="SC",
        config={},
        enabled=True,
        created_by="user",
        created_at=now,
        updated_at=now,
    )
    batches = [
        batch
        async for batch in provider.discover_backfill(
            connector=connector,
            condition=FilterGroup(
                combinator=FilterCombinator.ALL,
                children=(
                    FilterPredicate("layer_id", FilterOperator.EQ, "M1"),
                ),
            ),
            start_utc=datetime(2026, 8, 15, 0, 0, tzinfo=UTC),
            end_utc=datetime(2026, 8, 15, 1, 0, tzinfo=UTC),
        )
    ]

    assert len(batches) > 1
    assert max(len(batch.records) for batch in batches) < 600
    assert sum(len(batch.records) for batch in batches) == 600


@pytest.mark.asyncio
async def test_sc_live_discovery_keysets_publication_with_inspection_identity_ties() -> None:
    published_at = datetime(2026, 8, 30, 1, tzinfo=UTC)
    rows = [
        {
            "published_at": published_at,
            "inspection_time": datetime(
                2026, 8, 1, 8, tzinfo=timezone(timedelta(hours=8))
            ),
            "wafer_key": wafer_key,
            "layer_id": "M1",
        }
        for wafer_key in range(1, 301)
    ]
    upstream = _PublishedUpstream(rows)
    provider = ScSourceRecordProvider(upstream, _Importer())  # type: ignore[arg-type]
    now = datetime.now(UTC)
    connector = SourceConnector(
        id="connector",
        org_id="org",
        provider_id="sc",
        name="SC",
        config={},
        enabled=True,
        created_by="user",
        created_at=now,
        updated_at=now,
    )

    batches = [
        batch
        async for batch in provider.discover_live(
            connector=connector,
            condition=FilterGroup(
                FilterCombinator.ALL,
                (FilterPredicate("layer_id", FilterOperator.EQ, "M1"),),
            ),
            publication_start_utc=published_at - timedelta(minutes=1),
            publication_end_utc=published_at + timedelta(minutes=1),
            after_cursor=None,
        )
    ]

    record_keys = [record.record_key for batch in batches for record in batch.records]
    assert len(record_keys) == len(set(record_keys)) == 300
    assert record_keys[0] == "2026-08-01T08:00:00+08:00::1"
    assert record_keys[-1] == "2026-08-01T08:00:00+08:00::300"
    assert batches[-1].checkpoint == {
        "published_at": published_at.isoformat(),
        "inspection_time": "2026-08-01T08:00:00+08:00",
        "wafer_key": 300,
    }
    assert len(upstream.after) > 1


@pytest.mark.asyncio
async def test_sc_live_discovery_replays_five_minute_publication_overlap() -> None:
    stored_published_at = datetime(2026, 8, 30, 1, tzinfo=UTC)
    inspection_time = datetime(
        2026, 8, 1, 8, tzinfo=timezone(timedelta(hours=8))
    )
    delayed = {
        "published_at": stored_published_at - timedelta(minutes=1),
        "inspection_time": inspection_time,
        "wafer_key": 1,
        "layer_id": "M1",
    }
    upstream = _PublishedUpstream([delayed])
    provider = ScSourceRecordProvider(upstream, _Importer())  # type: ignore[arg-type]
    now = datetime.now(UTC)
    connector = SourceConnector(
        id="connector",
        org_id="org",
        provider_id="sc",
        name="SC",
        config={},
        enabled=True,
        created_by="user",
        created_at=now,
        updated_at=now,
    )
    stored_cursor = {
        "published_at": stored_published_at.isoformat(),
        "inspection_time": inspection_time.isoformat(),
        "wafer_key": 2,
    }

    batches = [
        batch
        async for batch in provider.discover_live(
            connector=connector,
            condition=FilterGroup(
                FilterCombinator.ALL,
                (FilterPredicate("layer_id", FilterOperator.EQ, "M1"),),
            ),
            publication_start_utc=stored_published_at - timedelta(hours=1),
            publication_end_utc=stored_published_at + timedelta(minutes=1),
            after_cursor=stored_cursor,
        )
    ]

    assert upstream.after == [None]
    assert [record.record_key for record in batches[0].records] == [
        "2026-08-01T08:00:00+08:00::1"
    ]
    assert batches[0].checkpoint == stored_cursor
