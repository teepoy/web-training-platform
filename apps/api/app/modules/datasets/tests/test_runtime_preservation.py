from __future__ import annotations

from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.context import (
    PredictionRuntimeContext,
    TrainingRuntimeContext,
)
from app.shared.api.schemas import Dataset, TaskSpec
from app.shared.application.compatibility import (
    validate_model_prediction,
)


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
    trainer_ids = set(runtime_catalog.list_trainer_ids())
    assert "resnet50-sc-v1" in trainer_ids
    assert "yolo-sc-v1" in trainer_ids


def test_runtime_contexts_only_carry_dispatch_context() -> None:
    assert not hasattr(TrainingRuntimeContext, "dataset_ref")
    assert not hasattr(PredictionRuntimeContext, "model_ref")




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
