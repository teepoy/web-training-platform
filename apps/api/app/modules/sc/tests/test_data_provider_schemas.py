from __future__ import annotations

import pytest
import polars as pl
from pydantic import ValidationError

from app.modules.sc.data_provider.materializer import (
    _normalize_dataset_base_lazyframe,
)
from app.modules.sc.data_provider.sample_table_descriptor import (
    SC_SAMPLE_TABLE_DESCRIPTOR,
)
from app.modules.sc.data_provider.schemas import ScSqlQueryRequest


def test_query_parameters_accept_scalars_and_homogeneous_arrays() -> None:
    request = ScSqlQueryRequest.model_validate(
        {
            "description": "sc-workbench.selection.ids",
            "sql": "SELECT * FROM samples WHERE defect_id = ANY(?)",
            "parameters": [[1, 2, 3]],
        }
    )

    assert request.parameters == [[1, 2, 3]]


@pytest.mark.parametrize("parameter", [[], [1, "2"], [True, 1]])
def test_query_parameters_reject_untyped_or_mixed_arrays(parameter: list[object]) -> None:
    with pytest.raises(ValidationError):
        ScSqlQueryRequest.model_validate(
            {
                "description": "sc-workbench.table.rows",
                "sql": "SELECT * FROM samples",
                "parameters": [parameter],
            }
        )


@pytest.mark.parametrize(
    "description",
    ["", "Table rows", "table/rows", "x" * 121],
)
def test_query_description_requires_a_bounded_machine_readable_usage(
    description: str,
) -> None:
    with pytest.raises(ValidationError):
        ScSqlQueryRequest.model_validate(
            {
                "description": description,
                "sql": "SELECT * FROM samples",
                "parameters": [],
            }
        )


def test_sample_table_descriptor_is_versioned_and_has_unique_columns() -> None:
    descriptor = SC_SAMPLE_TABLE_DESCRIPTOR
    keys = [column.key for column in descriptor.columns]

    assert descriptor.version == "sc.sample-table.v1"
    assert len(keys) == len(set(keys))
    assert next(column for column in descriptor.columns if column.key == "final_class").visibility == (
        "filter_only"
    )
    assert next(column for column in descriptor.columns if column.key == "map_id").visibility == (
        "internal"
    )


def test_dataset_materializer_preserves_dynamic_metadata_columns() -> None:
    source = pl.DataFrame(
        {
            "sample_id": ["1"],
            "defect_id": [1],
            "inspection_time": ["2026-08-01T04:00:00+08:00"],
            "wafer_key": [1],
            "wafer_x": [100],
            "wafer_y": [200],
            "die_x": [3],
            "die_y": [4],
            "rough_bin": [5],
            "images": [7],
            "cluster": [8],
            "future_metric": [12.5],
            "upstream_payload": ["kept"],
        }
    ).lazy()
    review_images = pl.DataFrame(
        {
            "defect_id": pl.Series([], dtype=pl.Int32),
            "image_id": pl.Series([], dtype=pl.Int64),
        }
    )

    row = _normalize_dataset_base_lazyframe(source, review_images).collect().to_dicts()[0]

    assert row["upstream_images"] == 7
    assert row["images"] == 0
    assert row["cluster"] == 8
    assert row["cluster_id"] == 8
    assert row["future_metric"] == 12.5
    assert row["upstream_payload"] == "kept"


def test_collection_materializer_keeps_duplicate_defects_as_distinct_rows() -> None:
    source = pl.DataFrame(
        {
            "row_key": ["dataset-a::sample-1", "dataset-b::sample-9"],
            "sample_id": ["dataset-a::sample-1", "dataset-b::sample-9"],
            "source_dataset_id": ["dataset-a", "dataset-b"],
            "source_sample_id": ["sample-1", "sample-9"],
            "collection_member_id": ["member-a", "member-b"],
            "defect_id": [42, 42],
        }
    ).lazy()
    review_images = pl.DataFrame(
        {
            "source_dataset_id": ["dataset-a", "dataset-b"],
            "defect_id": [42, 42],
            "image_id": [100, 200],
        }
    )

    rows = _normalize_dataset_base_lazyframe(
        source,
        review_images,
        assign_map_ids=True,
    ).collect()

    assert rows["row_key"].to_list() == [
        "dataset-a::sample-1",
        "dataset-b::sample-9",
    ]
    assert rows["map_id"].to_list() == [0, 1]
    assert rows["defect_id"].to_list() == [42, 42]
    assert rows["review_image_ids_json"].to_list() == ["[100]", "[200]"]
