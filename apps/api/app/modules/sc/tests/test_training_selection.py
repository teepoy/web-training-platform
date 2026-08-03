from __future__ import annotations

import polars as pl
import pytest

from app.modules.sc.app.services.training_selection import (
    limit_sc_training_rows_per_class,
)


def test_sc_training_selection_caps_each_class_deterministically() -> None:
    rows = [
        {"id": f"sample-{index:04d}", "label": label}
        for label in ("Scratch", "Particle")
        for index in range(1_005, -1, -1)
    ]

    selected = (
        limit_sc_training_rows_per_class(
            pl.DataFrame(rows).lazy(),
            max_samples_per_class=1_000,
        )
        .collect()
        .sort(["label", "id"])
    )

    counts = {
        str(row["label"]): int(row["len"])
        for row in selected.group_by("label").len().iter_rows(named=True)
    }
    assert counts == {"Particle": 1_000, "Scratch": 1_000}
    assert selected.filter(pl.col("label") == "Scratch")["id"].to_list() == [
        f"sample-{index:04d}" for index in range(1_000)
    ]


def test_sc_training_selection_excludes_unlabeled_rows() -> None:
    selected = limit_sc_training_rows_per_class(
        pl.DataFrame(
            {
                "sample_id": ["1", "2", "3", "4"],
                "latest_label": ["Scratch", "", None, "Particle"],
            }
        ).lazy()
    ).collect()

    assert selected["sample_id"].to_list() == ["4", "1"]


def test_sc_training_selection_requires_stable_identity() -> None:
    with pytest.raises(ValueError, match="stable sample identity"):
        limit_sc_training_rows_per_class(
            pl.DataFrame({"label": ["Scratch"]}).lazy()
        )
