from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import polars as pl

from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import (
    ScDiscoveryUpstreamReader,
    ScInspectionKey,
    ScInspectionPublicationCursor,
)
from app.modules.sc.port.local import ScImportPort
from app.modules.source_discovery.domain.models import (
    FilterCombinator,
    FilterGroup,
    FilterNode,
    FilterOperator,
    FilterPredicate,
    ImportProfileVersion,
    SourceConnector,
    SourceDiscoveryBatch,
    SourceEstimate,
    SourceFieldType,
    SourceFilterField,
    SourceImportResult,
    SourceProviderDescriptor,
    SourceRecord,
)


_FIELD_COLUMNS = {
    "inspection_time": "inspection_time",
    "wafer_key": "wafer_key",
    "lot_id": "lot_id",
    "wafer_id": "wafer_id",
    "layer_id": "layer_id",
    "device": "device",
    "eqp_id": "inspect_equip_id",
    "recipe_id": "recipe_id",
    "defects": "defects",
    "images": "images",
}
_SC_TIMEZONE = ZoneInfo("Asia/Shanghai")
_SOURCE_DISCOVERY_BATCH_ROWS = 256
_PUBLICATION_REPLAY_OVERLAP = timedelta(minutes=5)

_TEXT_OPERATORS = (
    FilterOperator.EQ,
    FilterOperator.NE,
    FilterOperator.IN,
    FilterOperator.NOT_IN,
    FilterOperator.CONTAINS,
    FilterOperator.STARTS_WITH,
    FilterOperator.IS_NULL,
)
_ORDER_OPERATORS = (
    FilterOperator.EQ,
    FilterOperator.NE,
    FilterOperator.IN,
    FilterOperator.NOT_IN,
    FilterOperator.GT,
    FilterOperator.GTE,
    FilterOperator.LT,
    FilterOperator.LTE,
    FilterOperator.IS_NULL,
)


SC_SOURCE_PROVIDER_DESCRIPTOR = SourceProviderDescriptor(
    provider_id="sc",
    display_name="SC inspection source",
    fields=(
        SourceFilterField(
            "inspection_time",
            "Inspection time",
            SourceFieldType.DATETIME,
            _ORDER_OPERATORS,
        ),
        SourceFilterField(
            "wafer_key", "Wafer key", SourceFieldType.INTEGER, _ORDER_OPERATORS
        ),
        SourceFilterField("lot_id", "Lot", SourceFieldType.STRING, _TEXT_OPERATORS),
        SourceFilterField("wafer_id", "Wafer", SourceFieldType.STRING, _TEXT_OPERATORS),
        SourceFilterField("layer_id", "Layer", SourceFieldType.STRING, _TEXT_OPERATORS),
        SourceFilterField("device", "Device", SourceFieldType.STRING, _TEXT_OPERATORS),
        SourceFilterField(
            "eqp_id", "Equipment", SourceFieldType.STRING, _TEXT_OPERATORS
        ),
        SourceFilterField(
            "recipe_id", "Recipe", SourceFieldType.STRING, _TEXT_OPERATORS
        ),
        SourceFilterField(
            "defects", "Defects", SourceFieldType.INTEGER, _ORDER_OPERATORS
        ),
        SourceFilterField(
            "images", "Images", SourceFieldType.INTEGER, _ORDER_OPERATORS
        ),
    ),
    backfill_time_field="inspection_time",
    max_condition_depth=4,
    max_condition_nodes=40,
)


class ScSourceRecordProvider:
    def __init__(
        self, upstream: ScDiscoveryUpstreamReader, importer: ScImportPort
    ) -> None:
        self._upstream = upstream
        self._importer = importer

    @property
    def descriptor(self) -> SourceProviderDescriptor:
        return SC_SOURCE_PROVIDER_DESCRIPTOR

    async def discover_live(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        publication_start_utc: datetime,
        publication_end_utc: datetime,
        after_cursor: dict[str, object] | None,
    ) -> AsyncIterator[SourceDiscoveryBatch]:
        del connector
        stored_cursor = _publication_cursor(after_cursor)
        published_from = publication_start_utc
        if stored_cursor is not None:
            published_from = max(
                publication_start_utc,
                stored_cursor.published_at - _PUBLICATION_REPLAY_OVERLAP,
            )
        page_after: ScInspectionPublicationCursor | None = None
        while True:
            page = await self._upstream.list_published_inspection_page(
                published_from=published_from,
                published_until=publication_end_utc,
                after=page_after,
                page_size=_SOURCE_DISCOVERY_BATCH_ROWS,
            )
            if page.is_empty():
                return
            page_after = _publication_cursor_from_row(page.row(-1, named=True))
            checkpoint = (
                page_after
                if stored_cursor is None
                or _cursor_key(page_after) > _cursor_key(stored_cursor)
                else stored_cursor
            )
            matched = (
                await page.lazy().filter(_condition_expr(condition)).collect_async()
            )
            yield SourceDiscoveryBatch(
                records=tuple(
                    self._record(row) for row in matched.iter_rows(named=True)
                ),
                checkpoint=_publication_checkpoint(checkpoint),
            )
            if page.height < _SOURCE_DISCOVERY_BATCH_ROWS:
                return

    async def discover_backfill(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
    ) -> AsyncIterator[SourceDiscoveryBatch]:
        del connector
        after: ScInspectionKey | None = None
        while True:
            page = await self._upstream.list_inspection_page(
                start_time=start_utc.astimezone(_SC_TIMEZONE),
                end_time=end_utc.astimezone(_SC_TIMEZONE),
                after=after,
                page_size=_SOURCE_DISCOVERY_BATCH_ROWS,
            )
            if page.is_empty():
                return
            after = _inspection_key_from_row(page.row(-1, named=True))
            matched = (
                await page.lazy().filter(_condition_expr(condition)).collect_async()
            )
            yield SourceDiscoveryBatch(
                records=tuple(
                    self._record(row) for row in matched.iter_rows(named=True)
                ),
                checkpoint=None,
            )
            if page.height < _SOURCE_DISCOVERY_BATCH_ROWS:
                return

    async def estimate(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
        representative_limit: int,
    ) -> SourceEstimate:
        records: list[SourceRecord] = []
        matched_count = 0
        async for batch in self.discover_backfill(
            connector=connector,
            condition=condition,
            start_utc=start_utc,
            end_utc=end_utc,
        ):
            matched_count += len(batch.records)
            remaining = representative_limit - len(records)
            if remaining > 0:
                records.extend(batch.records[:remaining])
        return SourceEstimate(
            as_of_utc=datetime.now(UTC),
            matched_count=matched_count,
            representative_records=tuple(records),
        )

    async def import_record(
        self,
        *,
        connector: SourceConnector,
        profile: ImportProfileVersion,
        record: SourceRecord,
        org_id: str,
        actor_id: str,
    ) -> SourceImportResult:
        del connector
        inspection_time = record.attributes.get("inspection_time")
        wafer_key = record.attributes.get("wafer_key")
        if not isinstance(inspection_time, str) or not isinstance(wafer_key, int):
            raise ValueError("SC Source record is missing inspection identity")
        label_space_value = profile.settings.get("label_space")
        if label_space_value is None:
            label_space = None
        elif isinstance(label_space_value, list) and all(
            isinstance(item, str) for item in label_space_value
        ):
            label_space = cast(list[str], label_space_value)
        else:
            raise ValueError("SC Import profile label_space must be a list of strings")
        result = await self._importer.submit_import(
            source_inspection_time=inspection_time,
            source_wafer_key=wafer_key,
            dataset_name=record.display_name,
            org_id=org_id,
            created_by=actor_id,
            label_space=label_space,
        )
        if result.status != "completed" or not result.dataset_id:
            raise RuntimeError(result.error or "SC import did not create a Dataset")
        return SourceImportResult(
            dataset_id=result.dataset_id,
            dataset_name=result.dataset_name,
            imported_count=result.imported_count,
        )

    @staticmethod
    def _record(row: dict[str, object]) -> SourceRecord:
        raw_time = row.get("inspection_time")
        if isinstance(raw_time, datetime):
            source_time = _coerce_naive_to_upstream_tz(raw_time).astimezone(
                _SC_TIMEZONE
            )
        elif isinstance(raw_time, str):
            source_time = _coerce_naive_to_upstream_tz(
                datetime.fromisoformat(raw_time)
            ).astimezone(_SC_TIMEZONE)
        else:
            raise ValueError("SC Source record has no inspection_time")
        wafer_key = row.get("wafer_key")
        if not isinstance(wafer_key, int) or isinstance(wafer_key, bool):
            raise ValueError("SC Source record has no wafer_key")
        inspection_time = source_time.isoformat()
        attributes = {
            key: _json_value(row.get(column)) for key, column in _FIELD_COLUMNS.items()
        }
        attributes["inspection_time"] = inspection_time
        attributes["wafer_key"] = wafer_key
        lot = attributes.get("lot_id") or "SC"
        wafer = attributes.get("wafer_id") or wafer_key
        layer = attributes.get("layer_id") or "unlayered"
        return SourceRecord(
            record_key=f"{inspection_time}::{wafer_key}",
            observed_at=source_time.astimezone(UTC),
            display_name=f"{lot}-{wafer}-{layer}-{source_time:%Y%m%d-%H%M%S}",
            attributes=attributes,
        )


def _inspection_time(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        return _coerce_naive_to_upstream_tz(value).astimezone(_SC_TIMEZONE)
    if isinstance(value, str):
        return _coerce_naive_to_upstream_tz(datetime.fromisoformat(value)).astimezone(
            _SC_TIMEZONE
        )
    raise ValueError(f"SC inspection page is missing {field}")


def _inspection_key_from_row(row: dict[str, object]) -> ScInspectionKey:
    wafer_key = row.get("wafer_key")
    if not isinstance(wafer_key, int) or isinstance(wafer_key, bool):
        raise ValueError("SC inspection page is missing wafer_key")
    return ScInspectionKey(
        inspection_time=_inspection_time(row.get("inspection_time"), "inspection_time"),
        wafer_key=wafer_key,
    )


def _publication_cursor_from_row(
    row: dict[str, object],
) -> ScInspectionPublicationCursor:
    key = _inspection_key_from_row(row)
    published_at = row.get("published_at")
    if isinstance(published_at, str):
        published_at = datetime.fromisoformat(published_at)
    if not isinstance(published_at, datetime) or published_at.tzinfo is None:
        raise ValueError("SC inspection page is missing timezone-aware published_at")
    return ScInspectionPublicationCursor(
        published_at=published_at.astimezone(UTC),
        inspection_time=key.inspection_time,
        wafer_key=key.wafer_key,
    )


def _publication_cursor(
    value: dict[str, object] | None,
) -> ScInspectionPublicationCursor | None:
    if value is None:
        return None
    try:
        published_at = datetime.fromisoformat(cast(str, value["published_at"]))
        inspection_time = datetime.fromisoformat(cast(str, value["inspection_time"]))
        wafer_key = value["wafer_key"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Stored SC publication cursor is invalid") from exc
    if (
        published_at.tzinfo is None
        or inspection_time.tzinfo is None
        or not isinstance(wafer_key, int)
        or isinstance(wafer_key, bool)
    ):
        raise ValueError("Stored SC publication cursor is invalid")
    return ScInspectionPublicationCursor(
        published_at=published_at.astimezone(UTC),
        inspection_time=inspection_time.astimezone(_SC_TIMEZONE),
        wafer_key=wafer_key,
    )


def _publication_checkpoint(
    cursor: ScInspectionPublicationCursor,
) -> dict[str, object]:
    return {
        "published_at": cursor.published_at.isoformat(),
        "inspection_time": cursor.inspection_time.isoformat(),
        "wafer_key": cursor.wafer_key,
    }


def _cursor_key(
    cursor: ScInspectionPublicationCursor,
) -> tuple[datetime, datetime, int]:
    return cursor.published_at, cursor.inspection_time, cursor.wafer_key


def _condition_expr(node: FilterNode) -> pl.Expr:
    if isinstance(node, FilterGroup):
        expressions = [_condition_expr(child) for child in node.children]
        expression = expressions[0]
        for child in expressions[1:]:
            expression = (
                expression & child
                if node.combinator is FilterCombinator.ALL
                else expression | child
            )
        return expression

    column = pl.col(_FIELD_COLUMNS[node.field])
    value = node.value
    if node.field == "inspection_time":
        column = column.cast(pl.Datetime, strict=False)
        if isinstance(value, list):
            value = [
                datetime.fromisoformat(cast(str, item))
                .astimezone(_SC_TIMEZONE)
                .replace(tzinfo=None)
                for item in value
            ]
        elif isinstance(value, str):
            value = (
                datetime.fromisoformat(value)
                .astimezone(_SC_TIMEZONE)
                .replace(tzinfo=None)
            )
    return _predicate_expr(column, node, value)


def _predicate_expr(
    column: pl.Expr, predicate: FilterPredicate, value: object
) -> pl.Expr:
    operator = predicate.operator
    literal = pl.lit(value)
    if operator is FilterOperator.EQ:
        return column == literal
    if operator is FilterOperator.NE:
        return column != literal
    if operator is FilterOperator.IN:
        return column.is_in(cast(list[object], value))
    if operator is FilterOperator.NOT_IN:
        return ~column.is_in(cast(list[object], value))
    if operator is FilterOperator.GT:
        return column > literal
    if operator is FilterOperator.GTE:
        return column >= literal
    if operator is FilterOperator.LT:
        return column < literal
    if operator is FilterOperator.LTE:
        return column <= literal
    if operator is FilterOperator.CONTAINS:
        return column.cast(pl.String).str.contains(re.escape(cast(str, value)))
    if operator is FilterOperator.STARTS_WITH:
        return column.cast(pl.String).str.starts_with(cast(str, value))
    if operator is FilterOperator.IS_NULL:
        return column.is_null() if value is True else column.is_not_null()
    raise ValueError(f"Unsupported SC filter operator: {operator}")


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return _coerce_naive_to_upstream_tz(value).isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
