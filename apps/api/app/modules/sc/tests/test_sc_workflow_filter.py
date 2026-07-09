from __future__ import annotations

import polars as pl
import pytest

from app.modules.sc.app.services.sc_plot_points_service import (
    apply_sc_workflow_sample_filter,
)


def _samples() -> pl.LazyFrame:
    return pl.DataFrame(
        {
            "sample_id": ["s1", "s2", "s3"],
            "test_id": [1, 2, 2],
            "label": ["Scratch", None, "0"],
            "predicted_label": ["Particle", "Scratch", "Particle"],
            "confidence": [0.4, 0.8, 0.9],
        }
    ).lazy()


@pytest.mark.asyncio
async def test_workflow_filter_applies_final_class_and_confidence() -> None:
    filtered = apply_sc_workflow_sample_filter(
        _samples(),
        {
            "final_class": {"filterType": "set", "values": ["Scratch"]},
            "prediction_confidence": {
                "filterType": "number",
                "type": "inRange",
                "filter": 0.5,
                "filterTo": 1.0,
            },
        },
    )

    result = await filtered.collect_async()

    assert result["sample_id"].to_list() == ["s2"]


def test_workflow_filter_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Unsupported sample_filter field"):
        apply_sc_workflow_sample_filter(
            _samples(),
            {"unknown": {"filterType": "set", "values": [1]}},
        )


def test_workflow_filter_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="requires missing column"):
        apply_sc_workflow_sample_filter(
            _samples(),
            {"rough_bin": {"filterType": "set", "values": [1]}},
        )
