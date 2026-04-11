from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.models import Dataset
from app.domain.types import DatasetType, TaskType
from app.presets.schema import PresetSpec


@dataclass(frozen=True)
class UploadTemplateDefinition:
    id: str
    name: str
    dataset_types: tuple[str, ...]
    task_types: tuple[str, ...]
    label_space_mode: str
    requires_embedding_metadata: bool = False
    profiles: tuple[dict[str, Any], ...] = ()


ALLOWED_DATASET_TASK_PAIRS: dict[DatasetType, TaskType] = {
    DatasetType.IMAGE_CLASSIFICATION: TaskType.CLASSIFICATION,
    DatasetType.IMAGE_VQA: TaskType.VQA,
}


UPLOAD_TEMPLATE_DEFINITIONS: tuple[UploadTemplateDefinition, ...] = (
    UploadTemplateDefinition(
        id="image-classifier",
        name="Image Classifier",
        dataset_types=(DatasetType.IMAGE_CLASSIFICATION.value,),
        task_types=(TaskType.CLASSIFICATION.value,),
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
        dataset_types=(DatasetType.IMAGE_CLASSIFICATION.value, DatasetType.IMAGE_VQA.value),
        task_types=(TaskType.CLASSIFICATION.value, TaskType.VQA.value),
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
    UploadTemplateDefinition(
        id="vqa",
        name="VQA",
        dataset_types=(DatasetType.IMAGE_VQA.value,),
        task_types=(TaskType.VQA.value,),
        label_space_mode="forbidden",
        profiles=(
            {
                "id": "dspy-vqa-v1",
                "name": "DSPy VQA",
                "model_spec": {
                    "framework": "dspy",
                    "architecture": "vqa-program",
                    "base_model": "gpt-4o-mini",
                },
                "default_prediction_targets": ["vqa"],
            },
            {
                "id": "custom",
                "name": "Custom",
                "model_spec": {},
                "default_prediction_targets": ["vqa"],
            },
        ),
    ),
)


def validate_dataset_contract(dataset_type: DatasetType, task_type: TaskType, label_space: list[str]) -> None:
    expected_task = ALLOWED_DATASET_TASK_PAIRS.get(dataset_type)
    if expected_task is None or expected_task != task_type:
        raise ValueError(
            f"dataset_type '{dataset_type.value}' is incompatible with task_type '{task_type.value}'"
        )
    if task_type == TaskType.CLASSIFICATION and not label_space:
        raise ValueError("classification datasets require a non-empty label space")
    if task_type == TaskType.VQA and label_space:
        raise ValueError("vqa datasets must not define a label space")


def validate_dataset_preset_training(dataset: Dataset, preset: PresetSpec) -> None:
    dataset_type = dataset.dataset_type.value
    task_type = dataset.task_spec.task_type.value
    if dataset_type not in preset.compatibility.dataset_types:
        raise ValueError(
            f"preset '{preset.id}' does not support dataset_type '{dataset_type}'"
        )
    if task_type not in preset.compatibility.task_types:
        raise ValueError(
            f"preset '{preset.id}' does not support task_type '{task_type}'"
        )
    validate_dataset_contract(dataset.dataset_type, dataset.task_spec.task_type, dataset.task_spec.label_space)


def validate_model_prediction(dataset: Dataset, model_metadata: dict[str, Any], target: str) -> None:
    supported_dataset_types = _as_str_list(model_metadata.get("dataset_types"))
    supported_task_types = _as_str_list(model_metadata.get("task_types"))
    supported_targets = _as_str_list(model_metadata.get("prediction_targets"))

    validate_dataset_contract(dataset.dataset_type, dataset.task_spec.task_type, dataset.task_spec.label_space)

    if target == "vqa" and dataset.task_spec.task_type != TaskType.VQA:
        raise ValueError("target 'vqa' requires dataset task_type 'vqa'")
    if target != "vqa" and dataset.task_spec.task_type == TaskType.VQA:
        raise ValueError("dataset task_type 'vqa' requires target 'vqa'")

    if target not in supported_targets:
        raise ValueError(f"model does not support prediction target '{target}'")
    if dataset.dataset_type.value not in supported_dataset_types:
        raise ValueError(
            f"model does not support dataset_type '{dataset.dataset_type.value}'"
        )
    if dataset.task_spec.task_type.value not in supported_task_types:
        raise ValueError(
            f"model does not support task_type '{dataset.task_spec.task_type.value}'"
        )

    if target == "image_classification":
        model_labels = set(_as_str_list(model_metadata.get("label_space")))
        dataset_labels = set(dataset.task_spec.label_space)
        if not model_labels:
            raise ValueError("classification model metadata must include a label space")
        if not model_labels.issubset(dataset_labels):
            raise ValueError("model label_space must be a subset of dataset label_space")

    if target == "embedding":
        if bool(model_metadata.get("requires_embedding_metadata")):
            dimension = model_metadata.get("embedding_dimension")
            if not isinstance(dimension, int) or dimension <= 0:
                raise ValueError("embedding models must declare a positive embedding_dimension")


def validate_model_review(dataset: Dataset, model_metadata: dict[str, Any]) -> None:
    supported_targets = _as_str_list(model_metadata.get("prediction_targets"))
    preferred_target = "vqa" if "vqa" in supported_targets else "image_classification"
    validate_model_prediction(dataset, model_metadata, preferred_target)


def get_upload_template(template_id: str) -> UploadTemplateDefinition:
    for template in UPLOAD_TEMPLATE_DEFINITIONS:
        if template.id == template_id:
            return template
    raise ValueError(f"unknown upload template '{template_id}'")


def validate_upload_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
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
            raise ValueError(f"template '{template.id}' requires a positive embedding_dimension")
        if normalized_output is None:
            raise ValueError(f"template '{template.id}' requires normalized_output")

    if template.id == "image-classifier" and prediction_targets != ["image_classification"]:
        raise ValueError("image-classifier uploads only support prediction target 'image_classification'")
    if template.id == "image-embedder" and prediction_targets != ["embedding"]:
        raise ValueError("image-embedder uploads only support prediction target 'embedding'")
    if template.id == "vqa" and prediction_targets != ["vqa"]:
        raise ValueError("vqa uploads only support prediction target 'vqa'")

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


def build_trained_model_metadata(dataset: Dataset, preset: PresetSpec, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    runtime_metadata = metadata.copy() if isinstance(metadata, dict) else {}
    merged = {
        **runtime_metadata,
        "preset_id": preset.id,
        "dataset_types": list(preset.compatibility.dataset_types),
        "task_types": list(preset.compatibility.task_types),
        "prediction_targets": list(preset.compatibility.prediction_targets),
        "adapter": preset.io.adapter,
        "label_space": list(dataset.task_spec.label_space),
        "source_dataset_id": dataset.id,
        "model_spec": {
            "framework": preset.model.framework,
            "architecture": preset.model.architecture,
            "base_model": preset.model.base_model,
        },
    }
    return merged


def _profile_prediction_targets(template: UploadTemplateDefinition, profile_id: str) -> list[str]:
    for profile in template.profiles:
        if str(profile.get("id", "")) == profile_id:
            return _as_str_list(profile.get("default_prediction_targets"))
    return []


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
