from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import cast
from zoneinfo import ZoneInfo

import polars as pl

from app.modules.sc.domain.models import _coerce_naive_to_upstream_tz
from app.modules.sc.domain.upstream_reader import ScUpstreamReader
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
    def __init__(self, upstream: ScUpstreamReader, importer: ScImportPort) -> None:
        self._upstream = upstream
        self._importer = importer

    @property
    def descriptor(self) -> SourceProviderDescriptor:
        return SC_SOURCE_PROVIDER_DESCRIPTOR

    async def discover(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
        max_records: int,
    ) -> SourceDiscoveryBatch:
        del connector
        frame = await self._filtered_frame(
            condition=condition,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        limited = await frame.limit(max_records + 1).collect_async()
        has_more = limited.height > max_records
        if has_more:
            limited = limited.head(max_records)
        return SourceDiscoveryBatch(
            records=tuple(self._record(row) for row in limited.iter_rows(named=True)),
            has_more=has_more,
        )

    async def estimate(
        self,
        *,
        connector: SourceConnector,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
        representative_limit: int,
        max_records: int,
    ) -> SourceEstimate:
        del connector, max_records
        frame = await self._filtered_frame(
            condition=condition,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        count_frame, sample_frame = await _collect_estimate(frame, representative_limit)
        matched_count = int(count_frame.item()) if count_frame.height else 0
        return SourceEstimate(
            as_of_utc=datetime.now(UTC),
            matched_count=matched_count,
            representative_records=tuple(
                self._record(row) for row in sample_frame.iter_rows(named=True)
            ),
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
        image_source_profile = profile.settings.get("image_source_profile")
        if (
            not isinstance(image_source_profile, str)
            or not image_source_profile.strip()
        ):
            raise ValueError(
                "SC Import profile image_source_profile must be a non-empty string"
            )
        result = await self._importer.submit_import(
            source_inspection_time=inspection_time,
            source_wafer_key=wafer_key,
            image_source_profile=image_source_profile,
            dataset_name=record.display_name,
            org_id=org_id,
            created_by=actor_id,
            label_space=label_space,
            max_rows=profile.max_rows_per_dataset,
        )
        if result.status != "completed" or not result.dataset_id:
            raise RuntimeError(result.error or "SC import did not create a Dataset")
        return SourceImportResult(
            dataset_id=result.dataset_id,
            dataset_name=result.dataset_name,
            imported_count=result.imported_count,
        )

    async def _filtered_frame(
        self,
        *,
        condition: FilterGroup,
        start_utc: datetime,
        end_utc: datetime,
    ) -> pl.LazyFrame:
        source_start = start_utc.astimezone(_SC_TIMEZONE)
        source_end = end_utc.astimezone(_SC_TIMEZONE)
        frame = await self._upstream.list_inspections(source_start, source_end)
        return frame.filter(_condition_expr(condition)).sort(
            ["inspection_time", "wafer_key"]
        )

    @staticmethod
    def _record(row: dict[str, object]) -> SourceRecord:
        raw_time = row.get("inspection_time")
        if isinstance(raw_time, datetime):
            source_time = _coerce_naive_to_upstream_tz(raw_time)
        elif isinstance(raw_time, str):
            source_time = _coerce_naive_to_upstream_tz(datetime.fromisoformat(raw_time))
        else:
            raise ValueError("SC Source record has no inspection_time")
        wafer_key = row.get("wafer_key")
        if not isinstance(wafer_key, int) or isinstance(wafer_key, bool):
            raise ValueError("SC Source record has no wafer_key")
        inspection_time = source_time.isoformat()
        latest_update = row.get("latest_update")
        source_version = (
            str(latest_update)
            if isinstance(latest_update, int) and latest_update > 0
            else None
        )
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
            source_version=source_version,
            observed_at=source_time.astimezone(UTC),
            display_name=f"{lot}-{wafer}-{layer}-{source_time:%Y%m%d-%H%M%S}",
            attributes=attributes,
        )


async def _collect_estimate(
    frame: pl.LazyFrame, representative_limit: int
) -> tuple[pl.DataFrame, pl.DataFrame]:
    count = await frame.select(pl.len().alias("matched_count")).collect_async()
    sample = await frame.limit(representative_limit).collect_async()
    return count, sample


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
