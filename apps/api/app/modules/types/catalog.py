from __future__ import annotations

from collections.abc import Iterable, Mapping


def _extract_meta(
    entries: Mapping[str, object],
    fallback: Iterable[dict[str, str]],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {
        row["id"]: {
            "id": row["id"],
            "name": row["name"],
            "view_id": row["view_id"],
        }
        for row in fallback
    }
    for tid, obj in entries.items():
        if tid in result:
            continue
        name = getattr(obj, "name", tid)
        view_id = getattr(obj, "view_id", "")
        result[tid] = {"id": tid, "name": str(name), "view_id": str(view_id)}
    return result


def _trainer_meta_index() -> dict[str, dict[str, str]]:
    from app.core.registry import _registry

    return _extract_meta(_registry._trainers, _TRAINER_FALLBACK)


def _predictor_meta_index() -> dict[str, dict[str, str]]:
    from app.core.registry import _registry

    return _extract_meta(_registry._predictors, _PREDICTOR_FALLBACK)


def list_trainer_ids() -> list[str]:
    return list(_trainer_meta_index().keys())


def list_predictor_ids() -> list[str]:
    return list(_predictor_meta_index().keys())


def get_trainer_meta(trainer_id: str) -> dict[str, str]:
    try:
        return _trainer_meta_index()[trainer_id]
    except KeyError as exc:
        raise KeyError(trainer_id) from exc


def get_predictor_meta(predictor_id: str) -> dict[str, str]:
    try:
        return _predictor_meta_index()[predictor_id]
    except KeyError as exc:
        raise KeyError(predictor_id) from exc


# ── Fallback entries for trainers/predictors not yet registered ──
#     via @trainer/@predictor decorators (planned / non-executable).

_TRAINER_FALLBACK: tuple[dict[str, str], ...] = (
    {
        "id": "resnet50-sc-v1",
        "name": "ResNet-50 SC Defect Classifier",
        "view_id": "patch_image_v1",
    },
    {
        "id": "yolo-sc-v1",
        "name": "YOLO SC Detection Trainer",
        "view_id": "patch_image_v1",
    },
)

_PREDICTOR_FALLBACK: tuple[dict[str, str], ...] = (
    {
        "id": "resnet50-cls-v1",
        "name": "ResNet-50 Classification",
        "view_id": "image_input_v1",
    },
    {"id": "dspy-vqa-v1", "name": "DSPy VQA", "view_id": "qa_input_v1"},
    {"id": "clip-zero-shot-v1", "name": "CLIP Zero-Shot", "view_id": "image_input_v1"},
    {"id": "detection-v1", "name": "Detection V1", "view_id": "box_detection_v1"},
    {
        "id": "resnet50-sc-v1",
        "name": "ResNet-50 SC Defect Classifier",
        "view_id": "image_input_v1",
    },
    {"id": "yolo-sc-v1", "name": "YOLO SC Detection", "view_id": "patch_image_v1"},
)

__all__ = [
    "get_predictor_meta",
    "get_trainer_meta",
    "list_predictor_ids",
    "list_trainer_ids",
]
