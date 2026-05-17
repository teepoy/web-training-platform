from __future__ import annotations

import io
import json
from typing import Any

from seedmaker import SeedConfig, SeedRunner, IMAGENET_LABELS, registry
from seedmaker.images import generate_synthetic_image
from seedmaker.utils import (
    api_request,
    delete_model,
    is_image_classification_compatible,
    create_model_via_training_job,
)

DATASET_NAME = "ImageNet-1K Mock"
LEGACY_DATASET_NAME = "ImageNet-1K"
PRESET_ID = "resnet50-cls-v1"
PRESET_NAME = "ResNet50 Classification (v1)"
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


def _resolve_preset(client: Any) -> str:
    r = api_request(client, "get", "/api/v1/training-presets")
    presets = r.json() if r.status_code == 200 else []
    for item in presets:
        if item.get("id") == PRESET_ID or item.get("name") == PRESET_NAME:
            return item["id"]
    raise RuntimeError(
        f"Required preset '{PRESET_ID}' not available. "
        "Presets are file-backed and read-only; make sure the API started with the bundled preset registry."
    )


def run(args: Any, runner: SeedRunner) -> int:
    client = runner.client
    dataset_id = runner.dataset_id
    max_samples = getattr(args, "max_samples", None) or 1000

    if not dataset_id:
        print("ERROR: dataset_id not set")
        return 1

    # Resolve preset
    print("\n[6/7] Resolving training preset ...")
    preset_id = _resolve_preset(client)
    print(f"  Using preset: {preset_id}")

    # Create samples
    sample_count = 0
    if getattr(args, "no_samples", False):
        print("\n  Skipping sample creation (--no-samples).")
    else:
        print("\n[7/7] Creating samples ...")
        count = min(max_samples, len(IMAGENET_LABELS))

        def _item_builder(idx: int) -> dict:
            label = IMAGENET_LABELS[idx]
            data_uri = generate_synthetic_image(idx)
            metadata = {
                "source": "synthetic",
                "label_index": idx,
                "label_name": label,
            }
            return {"image_uris": [data_uri], "metadata": metadata}

        sample_count = runner.upload_samples(
            count, _item_builder, batch_size=5000, skip_existing=True
        )

    # Create model
    job_id: str | None = None
    model_id: str | None = None

    if getattr(args, "no_model", False):
        print("\n  Skipping model creation (--no-model).")
    else:
        print("\n[model] Creating training job + model artifact ...")

        # Delete existing mock models
        r = api_request(client, "get", f"/api/v1/models?dataset_id={dataset_id}")
        if r.status_code == 200:
            compatible_models = [
                m for m in r.json() if is_image_classification_compatible(m)
            ]
        else:
            compatible_models = []
        for existing_model in compatible_models:
            print(
                f"  Deleting existing mock model: {existing_model['id']} "
                f"({existing_model.get('name', 'n/a')})"
            )
            delete_model(client, existing_model["id"])

        job_timeout = getattr(args, "job_timeout", None) or 60
        job_id, model_id = create_model_via_training_job(
            client, dataset_id, preset_id, job_timeout
        )
        if model_id is None and job_id is not None:
            print(
                "  Training job failed in dev mode; "
                "uploading placeholder image-classifier model instead ..."
            )
            model_id = _upload_placeholder_model(client, job_id, IMAGENET_LABELS)

    # Summary
    print(f"\n{'=' * 50}")
    print("  Seed Summary (mock mode)")
    print(f"{'=' * 50}")
    print(f"  Dataset:    {DATASET_NAME}")
    print(f"  Dataset ID: {dataset_id}")
    print(f"  Labels:     {len(IMAGENET_LABELS)} ImageNet-1K classes")
    print(f"  Samples:    {sample_count}")
    print(f"  Preset:     {PRESET_NAME}")
    print(f"  Preset ID:  {preset_id}")
    if job_id:
        print(f"  Job ID:     {job_id}")
    if model_id:
        print(f"  Model ID:   {model_id}")
    print(f"{'=' * 50}")

    return 0


# Auto-register with registry
registry.register(config, run)
