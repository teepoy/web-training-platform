from __future__ import annotations

import pytest
from pydantic import ValidationError

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
