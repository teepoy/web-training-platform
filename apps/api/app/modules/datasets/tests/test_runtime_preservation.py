from __future__ import annotations

from dataclasses import fields

from app.modules.types import catalog
from app.shared.api.schemas import Dataset, TaskSpec
from app.shared.application.compatibility import (
    validate_model_prediction,
)
from app.shared.domain.runtime import DatasetRef, PredictContext, TrainContext


def _make_classification_dataset() -> Dataset:
    return Dataset(
        name="classification-dataset",
        dataset_type="image_classification",
        task_spec=TaskSpec(
            task_type="classification",
            label_space=["cat", "dog"],
        ),
    )




def test_trainers_register_and_import_without_error() -> None:
    import app.registrations  # noqa: F401

    trainer_ids = set(catalog.list_trainer_ids())
    assert "resnet50-sc-v1" in trainer_ids
    assert "resnet50-sc-v1" in trainer_ids


def test_runtime_context_field_signatures_are_unchanged() -> None:
    train_fields = [field.name for field in fields(TrainContext)]
    predict_fields = [field.name for field in fields(PredictContext)]

    assert "trainer_id" in train_fields
    assert "dataset_ref" in train_fields
    assert "model_ref" in train_fields
    assert "trainer_id" in predict_fields
    assert "dataset_ref" in predict_fields
    assert "model_ref" in predict_fields
    assert [field.name for field in fields(DatasetRef)] == [
        "dataset_id",
        "sample_ids",
        "label_space",
        "storage_uri_prefix",
        "metadata",
    ]




def test_validate_model_prediction_is_callable() -> None:
    dataset = _make_classification_dataset()

    validate_model_prediction(
        dataset,
        {
            "dataset_types": ["image_classification"],
            "task_types": ["classification"],
            "prediction_targets": ["image_classification"],
            "label_space": ["cat"],
        },
        "image_classification",
    )
