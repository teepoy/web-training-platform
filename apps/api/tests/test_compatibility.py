"""Behavioral tests for dataset view compatibility.

Storage mode is intentionally absent from these checks.  It selects a data
backend; it does not change the semantic views a dataset exposes.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.modules.datasets.domain.compatibility import (
    DatasetCompatibilityError,
    validate_predictor_for_dataset,
    validate_trainer_for_dataset,
    validate_view_for_dataset,
)
from app.shared.api.schemas import Dataset, DatasetStorageMode


@pytest.mark.parametrize("storage_mode", list(DatasetStorageMode))
@pytest.mark.parametrize(
    ("dataset_type", "view_types"),
    [
        ("image_classification", ["image_input_v1", "labeled_image_v1"]),
    ],
)
def test_storage_mode_is_orthogonal_to_dataset_views(
    storage_mode: DatasetStorageMode,
    dataset_type: str,
    view_types: list[str],
) -> None:
    dataset = Dataset(
        id=f"{dataset_type}-{storage_mode.value}",
        name="compatibility",
        dataset_type=dataset_type,
        storage_mode=storage_mode,
        view_types=view_types,
    )

    assert dataset.view_types == view_types
    assert dataset.storage_mode == storage_mode


def test_validate_view_accepts_enabled_view() -> None:
    validate_view_for_dataset(
        "labeled_image_v1",
        ["image_input_v1", "labeled_image_v1"],
    )


def test_validate_view_rejects_disabled_view() -> None:
    with pytest.raises(DatasetCompatibilityError, match="not enabled"):
        validate_view_for_dataset(
            "review_image_v1",
            ["image_input_v1", "labeled_image_v1"],
        )

def test_validate_trainer_uses_catalog_view_contract() -> None:
    from app.modules.types import catalog
    from app.modules.types.catalog import ModelContractRef, TrainerMetadata

    with patch(
        "app.modules.datasets.domain.compatibility.catalog.get_trainer_meta",
        return_value=TrainerMetadata(
            id="trainer",
            name="Trainer",
            input_view=catalog.LABELED_IMAGE_V1,
            output_model=ModelContractRef("test.model.v1", "1"),
            predictor_ids=("predictor",),
        ),
    ):
        validate_trainer_for_dataset(
            "trainer",
            ["image_input_v1", "labeled_image_v1"],
        )

        with pytest.raises(DatasetCompatibilityError, match="not compatible"):
            validate_trainer_for_dataset(
                "trainer",
                ["image_input_v1", "review_image_v1"],
            )


def test_validate_predictor_uses_catalog_view_contract() -> None:
    from app.modules.types import catalog
    from app.modules.types.catalog import ModelContractRef, PredictorMetadata

    with patch(
        "app.modules.datasets.domain.compatibility.catalog.get_predictor_meta",
        return_value=PredictorMetadata(
            id="predictor",
            name="Predictor",
            input_view=catalog.IMAGE_INPUT_V1,
            input_model=ModelContractRef("test.model.v1", "1"),
        ),
    ):
        validate_predictor_for_dataset(
            "predictor",
            ["image_input_v1", "review_image_v1"],
        )


@pytest.mark.parametrize(
    ("validator", "catalog_method", "kind"),
    [
        (validate_trainer_for_dataset, "get_trainer_meta", "Trainer"),
        (validate_predictor_for_dataset, "get_predictor_meta", "Predictor"),
    ],
)
def test_unknown_runtime_type_is_rejected(
    validator,
    catalog_method: str,
    kind: str,
) -> None:
    with (
        patch(
            f"app.modules.datasets.domain.compatibility.catalog.{catalog_method}",
            side_effect=KeyError("missing"),
        ),
        pytest.raises(
            DatasetCompatibilityError,
            match=f"{kind} 'missing' is not registered",
        ),
    ):
        validator("missing", ["image_input_v1"])
