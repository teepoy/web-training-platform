from __future__ import annotations

from dataclasses import dataclass
from app.shared.api.schemas import Dataset
from app.core.registry import resolve_task_type


@dataclass(frozen=True)
class UploadTemplateDefinition:
    id: str
    name: str
    dataset_types: tuple[str, ...]
    task_types: tuple[str, ...]
    label_space_mode: str
    requires_embedding_metadata: bool = False
    profiles: tuple[dict[str, object], ...] = ()


UPLOAD_TEMPLATE_DEFINITIONS: tuple[UploadTemplateDefinition, ...] = (
    UploadTemplateDefinition(
        id="image-classifier",
        name="Image Classifier",
        dataset_types=("image_classification",),
        task_types=("classification",),
        label_space_mode="required",
        profiles=(
            {
                "id": "resnet50-cls-v1",
                "name": "ResNet50",
                "model_spec": {
                    "framework": "pytorch",
                    "architecture": "resnet50",
                    "base_model": "torchvision/resnet50",
                },
                "default_prediction_targets": ["image_classification"],
            },
            {
                "id": "clip-zero-shot-v1",
                "name": "CLIP Zero-Shot",
                "model_spec": {
                    "framework": "pytorch",
                    "architecture": "clip-vit-base-patch32",
                    "base_model": "openai/clip-vit-base-patch32",
                },
                "default_prediction_targets": ["image_classification"],
            },
            {
                "id": "custom",
                "name": "Custom",
                "model_spec": {},
                "default_prediction_targets": ["image_classification"],
            },
        ),
    ),
    UploadTemplateDefinition(
        id="image-embedder",
        name="Image Embedder",
        dataset_types=("image_classification",),
        task_types=("classification",),
        label_space_mode="forbidden",
        requires_embedding_metadata=True,
        profiles=(
            {
                "id": "clip-zero-shot-v1",
                "name": "CLIP Zero-Shot",
                "model_spec": {
                    "framework": "pytorch",
                    "architecture": "clip-vit-base-patch32",
                    "base_model": "openai/clip-vit-base-patch32",
                },
                "default_prediction_targets": ["embedding"],
            },
            {
                "id": "custom",
                "name": "Custom",
                "model_spec": {},
                "default_prediction_targets": ["embedding"],
            },
        ),
    ),
)


def validate_dataset_contract(
    dataset_type: str, task_type: str, label_space: list[str]
) -> None:
    expected_task = resolve_task_type(dataset_type)
    if expected_task is None or expected_task != task_type:
        raise ValueError(
            f"dataset_type '{dataset_type}' is incompatible with task_type '{task_type}'"
        )
    if task_type == "classification" and not label_space:
        raise ValueError("classification datasets require a non-empty label space")


def validate_model_prediction(
    dataset: Dataset, model_metadata: dict[str, object], target: str
) -> None:
    supported_dataset_types = _as_str_list(model_metadata.get("dataset_types"))
    supported_task_types = _as_str_list(model_metadata.get("task_types"))
    supported_targets = _as_str_list(model_metadata.get("prediction_targets"))

    validate_dataset_contract(
        dataset.dataset_type, dataset.task_spec.task_type, dataset.task_spec.label_space
    )

    if target not in supported_targets:
        raise ValueError(f"model does not support prediction target '{target}'")
    if dataset.dataset_type not in supported_dataset_types:
        raise ValueError(
            f"model does not support dataset_type '{dataset.dataset_type}'"
        )
    if dataset.task_spec.task_type not in supported_task_types:
        raise ValueError(
            f"model does not support task_type '{dataset.task_spec.task_type}'"
        )

    if target == "image_classification":
        model_labels = set(_as_str_list(model_metadata.get("label_space")))
        dataset_labels = set(dataset.task_spec.label_space)
        if not model_labels:
            raise ValueError("classification model metadata must include a label space")
        if not model_labels.issubset(dataset_labels):
            raise ValueError(
                "model label_space must be a subset of dataset label_space"
            )

    if target == "embedding":
        if bool(model_metadata.get("requires_embedding_metadata")):
            dimension = model_metadata.get("embedding_dimension")
            if not isinstance(dimension, int) or dimension <= 0:
                raise ValueError(
                    "embedding models must declare a positive embedding_dimension"
                )


def validate_model_review(dataset: Dataset, model_metadata: dict[str, object]) -> None:
    validate_model_prediction(dataset, model_metadata, "image_classification")


def get_upload_template(template_id: str) -> UploadTemplateDefinition:
    for template in UPLOAD_TEMPLATE_DEFINITIONS:
        if template.id == template_id:
            return template
    raise ValueError(f"unknown upload template '{template_id}'")


def validate_upload_metadata(metadata: dict[str, object]) -> dict[str, object]:
    template_id = str(metadata.get("template_id", ""))
    template = get_upload_template(template_id)

    compatibility = metadata.get("compatibility")
    if not isinstance(compatibility, dict):
        raise ValueError("upload compatibility metadata is required")

    dataset_types = _as_str_list(compatibility.get("dataset_types"))
    task_types = _as_str_list(compatibility.get("task_types"))
    prediction_targets = _as_str_list(compatibility.get("prediction_targets"))
    label_space = _as_str_list(compatibility.get("label_space"))
    embedding_dimension = compatibility.get("embedding_dimension")
    normalized_output = compatibility.get("normalized_output")

    if not dataset_types:
        dataset_types = list(template.dataset_types)
    if not task_types:
        task_types = list(template.task_types)
    if not prediction_targets:
        profile_id = str(metadata.get("profile_id", "custom"))
        prediction_targets = _profile_prediction_targets(template, profile_id)

    for dataset_type in dataset_types:
        if dataset_type not in template.dataset_types:
            raise ValueError(
                f"template '{template.id}' does not support dataset_type '{dataset_type}'"
            )
    for task_type in task_types:
        if task_type not in template.task_types:
            raise ValueError(
                f"template '{template.id}' does not support task_type '{task_type}'"
            )

    if template.label_space_mode == "required" and not label_space:
        raise ValueError(f"template '{template.id}' requires a non-empty label_space")
    if template.label_space_mode == "forbidden" and label_space:
        raise ValueError(f"template '{template.id}' does not allow label_space")
    if template.requires_embedding_metadata:
        if not isinstance(embedding_dimension, int) or embedding_dimension <= 0:
            raise ValueError(
                f"template '{template.id}' requires a positive embedding_dimension"
            )
        if normalized_output is None:
            raise ValueError(f"template '{template.id}' requires normalized_output")

    if template.id == "image-classifier" and prediction_targets != [
        "image_classification"
    ]:
        raise ValueError(
            "image-classifier uploads only support prediction target 'image_classification'"
        )
    if template.id == "image-embedder" and prediction_targets != ["embedding"]:
        raise ValueError(
            "image-embedder uploads only support prediction target 'embedding'"
        )
    return {
        **metadata,
        "compatibility": {
            **compatibility,
            "dataset_types": dataset_types,
            "task_types": task_types,
            "prediction_targets": prediction_targets,
            "label_space": label_space,
            "embedding_dimension": embedding_dimension,
            "normalized_output": normalized_output,
        },
    }


def build_trained_model_metadata(
    dataset: Dataset, trainer_id: str, metadata: dict[str, object] | None = None
) -> dict[str, object]:
    runtime_metadata = metadata.copy() if isinstance(metadata, dict) else {}
    return {
        **runtime_metadata,
        "trainer_id": trainer_id,
        "label_space": list(
            getattr(dataset, "dataset_meta", {}).get("label_space", [])
        ),
        "source_dataset_id": dataset.id,
    }


def _profile_prediction_targets(
    template: UploadTemplateDefinition, profile_id: str
) -> list[str]:
    for profile in template.profiles:
        if str(profile.get("id", "")) == profile_id:
            return _as_str_list(profile.get("default_prediction_targets"))
    return []


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
