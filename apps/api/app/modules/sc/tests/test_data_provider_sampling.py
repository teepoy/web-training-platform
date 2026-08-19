from __future__ import annotations

import duckdb
import pyarrow as pa

from app.modules.sc.data_provider.sampling import compile_sc_sampling_query
from app.modules.sc.data_provider.schemas import ScSamplingSelectionRequest
from app.modules.sc.data_provider.sql_policy import validate_sc_sql


def test_compiles_and_executes_structured_sc_sampling_in_the_library() -> None:
    request = ScSamplingSelectionRequest.model_validate(
        {
            "seed": 42,
            "program": {
                "rules": [
                    {"type": "exclude_class_codes", "classCodes": [99]},
                    {"type": "cluster_count", "count": 3},
                    {
                        "type": "random_percentage",
                        "percentage": 50,
                        "rounding": "floor",
                    },
                    {"type": "per_die_limit", "limit": 2},
                ]
            },
        }
    )
    compiled, parameters = compile_sc_sampling_query(
        validate_sc_sql(
            "SELECT map_id, inspection_time, wafer_key, index_x, index_y, "
            "cluster_id, class_number FROM samples WHERE images > ?"
        ),
        [0],
        request,
    )
    connection = duckdb.connect(":memory:")
    connection.register(
        "samples",
        pa.table(
            {
                "map_id": [1, 2, 3, 4, 5, 6],
                "rough_bin": [4, 4, 4, 5, 5, 5],
                "class_number": [1, 1, 1, 2, 2, 2],
                "inspection_time": ["2026-08-19T10:00:00+08:00"] * 6,
                "wafer_key": [1] * 6,
                "index_x": [0, 0, 1, 1, 2, 2],
                "index_y": [0] * 6,
                "cluster_id": [1, 1, 2, 0, 0, 0],
                "images": [1, 1, 1, 1, 1, 1],
            }
        ),
    )

    result = connection.execute(compiled.sql, parameters).to_arrow_table()

    assert result.column_names == ["defect_id"]
    assert result.num_rows <= 5
    assert "__review_selector_ranked" in compiled.sql
    assert "__review_cap_ranked" in compiled.sql


def test_maps_the_sc_missing_group_sentinel_to_sql_null() -> None:
    request = ScSamplingSelectionRequest.model_validate(
        {
            "seed": 42,
            "program": {
                "rules": [
                    {
                        "type": "final_class_distribution",
                        "count": 2,
                        "targets": [
                            {"value": "__unclassified__", "percentage": 50},
                            {"value": "Scratch", "percentage": 50},
                        ],
                    }
                ]
            },
        }
    )

    _compiled, parameters = compile_sc_sampling_query(
        validate_sc_sql("SELECT map_id, final_class FROM samples"),
        [],
        request,
    )

    assert None in parameters
