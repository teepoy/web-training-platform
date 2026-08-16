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
                "conditional": {
                    "enabled": True,
                    "field": "rough_bin",
                    "value": "4",
                    "limit": 2,
                },
                "group": {
                    "enabled": True,
                    "field": "class_number",
                    "unit": "ratio",
                    "targets": [{"value": "1", "amount": 50}],
                    "othersAmount": 25,
                    "rounding": "nearest",
                },
                "total": {"enabled": True, "limit": 3},
            },
        }
    )
    compiled, parameters = compile_sc_sampling_query(
        validate_sc_sql(
            "SELECT map_id, rough_bin, class_number FROM samples WHERE images > ?"
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
                "images": [1, 1, 1, 1, 1, 1],
            }
        ),
    )

    result = connection.execute(compiled.sql, parameters).to_arrow_table()

    assert result.column_names == ["defect_id"]
    assert result.num_rows <= 3
    assert "__sampling_group_ranked" in compiled.sql


def test_maps_the_sc_missing_group_sentinel_to_sql_null() -> None:
    request = ScSamplingSelectionRequest.model_validate(
        {
            "seed": 42,
            "program": {
                "conditional": {
                    "enabled": False,
                    "field": "annotation_label",
                    "value": "",
                    "limit": 5,
                },
                "group": {
                    "enabled": True,
                    "field": "annotation_label",
                    "unit": "count",
                    "targets": [{"value": "__unlabeled__", "amount": 1}],
                    "othersAmount": 0,
                    "rounding": "nearest",
                },
                "total": {"enabled": False, "limit": 200},
            },
        }
    )

    _compiled, parameters = compile_sc_sampling_query(
        validate_sc_sql("SELECT map_id, annotation_label FROM samples"),
        [],
        request,
    )

    assert None in parameters
