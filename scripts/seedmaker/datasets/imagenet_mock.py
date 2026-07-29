from __future__ import annotations

import io
import json
from typing import Any

from seedmaker import SeedConfig, SeedRunner, IMAGENET_LABELS, registry
from seedmaker.images import generate_synthetic_image
from seedmaker.utils import (
    api_request,
    create_model_via_training_job,
)

DATASET_NAME = "ImageNet-1K Mock"
LEGACY_DATASET_NAME = "ImageNet-1K"
TRAINER_ID = "resnet50-cls-v1"
TRAINER_NAME = "ResNet50 Classification (v1)"
PLACEHOLDER_MODEL_NAME = "imagenet-mock-placeholder"
SEED_MODE = "mock"

config = SeedConfig(
    name="imagenet-mock",
    dataset_name=DATASET_NAME,
    description="ImageNet-1K mock dataset with 1000 synthetic coloured-square samples",
    label_space=IMAGENET_LABELS,
    dataset_type="image_classification",
    task_type="classification",
)


def _upload_placeholder_model(
    client: Any,
    job_id: str,
    label_space: list[str],
) -> str | None:
    dim = 64
    label_prototypes: dict[str, list[float]] = {}
    for idx, label in enumerate(label_space):
        vec = [0.0] * dim
        vec[idx % dim] = 1.0
        label_prototypes[label] = vec
    metadata = {
        "name": PLACEHOLDER_MODEL_NAME,
        "seed_mode": SEED_MODE,
        "format": "pytorch",
        "job_id": job_id,
        "template_id": "image-classifier",
        "profile_id": "resnet50-cls-v1",
        "model_spec": {
            "framework": "pytorch",
            "architecture": "resnet50",
            "base_model": "torchvision/resnet50",
        },
        "compatibility": {
            "dataset_types": ["image_classification"],
            "task_types": ["classification"],
            "prediction_targets": ["image_classification"],
            "label_space": label_space,
        },
    }
    payload = {
        "framework": "pytorch",
        "architecture": "resnet50",
        "label_space": label_space,
        "label_prototypes": label_prototypes,
        "source": "seed-imagenet-mock-placeholder",
    }
    files = {
        "file": (
            f"{PLACEHOLDER_MODEL_NAME}.pt",
            io.BytesIO(json.dumps(payload).encode("utf-8")),
            "application/octet-stream",
        ),
    }
    data = {"metadata": json.dumps(metadata)}
    r = client.post("/api/v1/models/upload", data=data, files=files)
    if r.status_code != 200:
        print(f"  ERROR: placeholder model upload failed: {r.status_code} {r.text}")
        return None
    model_id = r.json().get("id")
    print(f"  Uploaded placeholder image-classifier model: {model_id}")
    return model_id


def build_sample_item(idx: int) -> dict:
    """Build a single ImageNet mock sample item.

    Returns a dict with ``image_uris`` (single synthetic coloured square)
    and ``metadata`` (source, label_index, label_name).
    """
    label = IMAGENET_LABELS[idx]
    data_uri = generate_synthetic_image(idx)
    return {
        "image_uris": [data_uri],
        "metadata": {
            "source": "synthetic",
            "label_index": idx,
            "label_name": label,
        },
    }


def _resolve_trainer(client: Any) -> str:
    r = api_request(client, "get", "/api/v1/trainers")
    trainers = r.json() if r.status_code == 200 else []
    for item in trainers:
        if item.get("id") == TRAINER_ID or item.get("name") == TRAINER_NAME:
            return item["id"]
    raise RuntimeError(
        f"Required trainer '{TRAINER_ID}' not available. "
        "Trainers are catalog-backed; make sure the API started with the bundled catalog."
    )


def run(args: Any, runner: SeedRunner) -> int:
    client = runner.client
    dataset_id = runner.dataset_id

    if not dataset_id:
        print("ERROR: dataset_id not set")
        return 1

    trainer_id: str | None = None
    job_id: str | None = None
    model_id: str | None = None

    if not args.no_model:
        print("\n[6/7] Resolving trainer ...")
        trainer_id = _resolve_trainer(client)

        print("\n[7/7] Creating training job ...")
        job_id, trained_model_id = create_model_via_training_job(
            client, dataset_id, trainer_id, job_timeout=120
        )
        if job_id is None:
            print(
                "  WARNING: training job creation failed; uploading placeholder model instead."
            )
            model_id = _upload_placeholder_model(
                client, job_id or "", runner.config.label_space
            )
        elif trained_model_id is not None:
            model_id = trained_model_id
            print(f"  Model ID:   {model_id}")
        else:
            print(
                "  Training completed but no model artifact found; uploading placeholder."
            )
            model_id = _upload_placeholder_model(
                client, job_id, runner.config.label_space
            )
    else:
        print("\n  Skipping trainer/model creation (--no-model).")

    print(f"{'=' * 50}")
    print(f"  Trainer:     {TRAINER_NAME}")
    print(f"  Trainer ID:  {trainer_id}")
    if job_id:
        print(f"  Job ID:     {job_id}")
    if model_id:
        print(f"  Model ID:   {model_id}")
    print(f"{'=' * 50}")

    return 0


# Auto-register with registry
registry.register(config, run)
