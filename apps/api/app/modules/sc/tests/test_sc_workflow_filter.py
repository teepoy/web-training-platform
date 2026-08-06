from __future__ import annotations

import polars as pl
import pytest

from app.modules.sc.app.services.sample_filter import (
    parse_and_apply_workflow_sample_filter,
)


def _samples() -> pl.LazyFrame:
    return pl.DataFrame(
        {
            "sample_id": ["s1", "s2", "s3", "s4"],
            "defect_id": [1, 2, None, 4],
            "test_id": [1, 2, 2, 3],
            "label": ["Scratch", None, "0", None],
            "predicted_label": ["Particle", "Scratch", "Particle", None],
            "confidence": [0.4, 0.8, 0.9, None],
        }
    ).lazy()


def _filter(*items: tuple[str, dict[str, object]]) -> dict[str, object]:
    return {
        "combinator": "and",
        "items": [
            {"kind": "condition", "field": field, "condition": condition}
            for field, condition in items
        ],
    }


@pytest.mark.asyncio
async def test_workflow_filter_applies_final_class_and_confidence() -> None:
    filtered = parse_and_apply_workflow_sample_filter(
        _samples(),
        _filter(
            ("final_class", {"filterType": "set", "values": ["Scratch"]}),
            (
                "prediction_confidence",
                {
                    "filterType": "number",
                    "type": "inRange",
                    "filter": 0.5,
                    "filterTo": 1.0,
                },
            ),
        ),
    )

    result = await filtered.collect_async()

    assert result["sample_id"].to_list() == ["s2"]


@pytest.mark.asyncio
async def test_workflow_filter_supports_missing_and_concrete_label_values() -> None:
    filtered = parse_and_apply_workflow_sample_filter(
        _samples(),
        _filter(
            (
                "final_class",
                {
                    "filterType": "set",
                    "values": ["Scratch", "__unclassified__"],
                },
            ),
        ),
    )

    result = await filtered.collect_async()

    assert result["sample_id"].to_list() == ["s1", "s2", "s4"]


@pytest.mark.asyncio
async def test_workflow_filter_excludes_values_and_preserves_unlisted_missing_rows() -> (
    None
):
    filtered = parse_and_apply_workflow_sample_filter(
        _samples(),
        _filter(
            (
                "final_class",
                {
                    "filterType": "set",
                    "values": ["Scratch"],
                    "exclude": True,
                },
            ),
        ),
    )

    result = await filtered.collect_async()

    assert result["sample_id"].to_list() == ["s3", "s4"]


@pytest.mark.asyncio
async def test_workflow_filter_empty_included_set_matches_no_rows() -> None:
    filtered = parse_and_apply_workflow_sample_filter(
        _samples(),
        _filter(("test_id", {"filterType": "set", "values": []})),
    )

    result = await filtered.collect_async()

    assert result.is_empty()


@pytest.mark.asyncio
async def test_workflow_filter_matches_integer_defect_ids_after_request_parsing() -> (
    None
):
    included = parse_and_apply_workflow_sample_filter(
        _samples(),
        _filter(("defect_id", {"filterType": "set", "values": [1]})),
    )
    excluded = parse_and_apply_workflow_sample_filter(
        _samples(),
        _filter(("defect_id", {"filterType": "set", "values": [1], "exclude": True})),
    )

    included_result = await included.collect_async()
    excluded_result = await excluded.collect_async()

    assert included_result["sample_id"].to_list() == ["s1"]
    assert excluded_result["sample_id"].to_list() == ["s2", "s3", "s4"]


def test_workflow_filter_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Unsupported sample_filter field"):
        parse_and_apply_workflow_sample_filter(
            _samples(),
            _filter(("unknown", {"filterType": "set", "values": [1]})),
        )


def test_workflow_filter_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="requires missing column"):
        parse_and_apply_workflow_sample_filter(
            _samples(),
            _filter(("rough_bin", {"filterType": "set", "values": [1]})),
        )


@pytest.mark.asyncio
async def test_workflow_filter_preserves_repeated_property_items() -> None:
    filtered = parse_and_apply_workflow_sample_filter(
        _samples(),
        _filter(
            ("defect_id", {"filterType": "set", "values": [1, 2, 4]}),
            (
                "defect_id",
                {"filterType": "set", "values": [2], "exclude": True},
            ),
        ),
    )

    result = await filtered.collect_async()

    assert result["sample_id"].to_list() == ["s1", "s4"]


@pytest.mark.asyncio
async def test_workflow_filter_supports_nested_and_or_groups() -> None:
    filtered = parse_and_apply_workflow_sample_filter(
        _samples(),
        {
            "combinator": "and",
            "items": [
                {
                    "kind": "group",
                    "combinator": "or",
                    "items": [
                        {
                            "kind": "condition",
                            "field": "test_id",
                            "condition": {"filterType": "set", "values": [1]},
                        },
                        {
                            "kind": "condition",
                            "field": "test_id",
                            "condition": {"filterType": "set", "values": [3]},
                        },
                    ],
                },
                {
                    "kind": "condition",
                    "field": "defect_id",
                    "condition": {
                        "filterType": "set",
                        "values": [4],
                        "exclude": True,
                    },
                },
            ],
        },
    )

    result = await filtered.collect_async()

    assert result["sample_id"].to_list() == ["s1"]
