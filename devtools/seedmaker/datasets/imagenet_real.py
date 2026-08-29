from __future__ import annotations

import base64
import io
import sys
import time
from typing import Any

import httpx

from seedmaker import SeedConfig, SeedRunner, IMAGENET_LABELS, registry
from seedmaker.utils import (
    api_request,
)

DATASET_NAME = "ImageNet-1K Real"
LEGACY_DATASET_NAME = "ImageNet-1K"
TRAINER_ID = "resnet50-cls-v1"
TRAINER_NAME = "ResNet50 Classification (v1)"

config = SeedConfig(
    name="imagenet-real",
    dataset_name=DATASET_NAME,
    description="ImageNet-1K real dataset from S3/dev bucket with configurable sample count",
    label_space=IMAGENET_LABELS,
    dataset_type="image_classification",
    task_type="classification",
)


def _image_to_data_uri(img: Any) -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _resolve_trainer(client: httpx.Client) -> str:
    r = api_request(client, "get", "/api/v1/trainers")
    trainers = r.json() if r.status_code == 200 else []
    for item in trainers:
        if item.get("id") == TRAINER_ID or item.get("name") == TRAINER_NAME:
            return item["id"]
    raise RuntimeError(
        f"Required trainer '{TRAINER_ID}' not available. "
        "Trainers are catalog-backed; make sure the API started with the bundled catalog."
    )


def _upload_real_resnet50(
    client: httpx.Client,
    job_id: str,
) -> str | None:
    try:
        import torch
        from torchvision import models
    except ImportError:
        print(
            "  ERROR: torch/torchvision not found. Install: uv pip install torch torchvision"
        )
        return None

    print("  Downloading pretrained ResNet-50 weights ...")
    model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    model_bytes = buf.getvalue()
    print(f"  Model size: {len(model_bytes) / 1024 / 1024:.1f} MB")

    print("  Uploading to platform ...")
    r = client.post(
        "/api/v1/models/upload",
        params={
            "name": "resnet50-imagenet1k-v2",
            "format": "pytorch",
            "job_id": job_id,
        },
        files={
            "file": (
                "resnet50_imagenet1k_v2.pt",
                io.BytesIO(model_bytes),
                "application/octet-stream",
            )
        },
    )
    if r.status_code == 200:
        model_id = r.json()["id"]
        print(f"  Uploaded model: {model_id}")
        return model_id
    else:
        print(f"  ERROR: upload failed: {r.status_code} {r.text}")
        return None


def run(args: Any, runner: SeedRunner) -> int:
    dataset_id = runner.dataset_id

    if not dataset_id:
        print("ERROR: dataset_id not set")
        return 1

    print("\n[6/7] Resolving trainer ...")
    print(f"  Trainer:     {TRAINER_NAME}")

    return 0


def _create_real_samples(
    client: httpx.Client,
    dataset_id: str,
    max_samples: int,
    batch_report: int,
) -> int:
    """Stream real images from HuggingFace ``ILSVRC/imagenet-1k``."""
    try:
        from datasets import load_dataset  # pyright: ignore[reportMissingImports]
    except ImportError:
        print(
            "  ERROR: 'datasets' package not found. Install: uv pip install datasets Pillow"
        )
        sys.exit(1)

    print("  Loading ILSVRC/imagenet-1k from HuggingFace (streaming) ...")
    print("  (Requires HF_TOKEN env var with accepted license)")
    hf = load_dataset("ILSVRC/imagenet-1k", split="validation", streaming=True)

    created = 0
    skipped = 0
    batch_size = 5000
    batch: list[dict] = []
    t0 = time.time()
    limit = max_samples if max_samples > 0 else None
    seen = 0

    for example in hf:
        if limit is not None and seen >= limit:
            break
        seen += 1

        image = example["image"]
        label_idx = example["label"]
        data_uri = _image_to_data_uri(image)

        label_name = (
            IMAGENET_LABELS[label_idx]
            if label_idx < len(IMAGENET_LABELS)
            else f"class_{label_idx}"
        )
        metadata = {
            "source": "imagenet-1k",
            "split": "validation",
            "label_index": label_idx,
            "label_name": label_name,
        }

        batch.append({"image_uris": [data_uri], "metadata": metadata, "label": None})

        if len(batch) >= batch_size or (limit is not None and seen >= limit):
            r = api_request(
                client,
                "post",
                f"/api/v1/datasets/{dataset_id}/samples/import",
                json={"items": batch},
            )
            if r.status_code == 200:
                created += int(r.json().get("imported", 0))
            else:
                skipped += len(batch)
                if skipped <= batch_size * 3:
                    print(f"    WARN: {r.status_code} {r.text[:120]}")
            batch = []

        if created > 0 and created % batch_report == 0:
            elapsed = time.time() - t0
            rate = created / elapsed if elapsed > 0 else 0
            print(f"    ... {created} samples ({rate:.1f}/s)")

    elapsed = time.time() - t0
    print(f"  Created {created} real samples, skipped {skipped} in {elapsed:.1f}s")
    return created


# Auto-register with registry
registry.register(config, run)
