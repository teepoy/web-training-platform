from __future__ import annotations

import os
import random
import sys
import time

from seedmaker import SeedConfig, SeedRunner, CIFAR100_LABELS, registry

"""Multi-image mock dataset: 100K samples with CIFAR-100 + optional ImageNet images."""


DATASET_DISPLAY_NAME = "Multi-Image Mock (100K)"
DATASET_DESCRIPTION = (
    "100K samples: 3 required 32x32 CIFAR-100 images + "
    "~100 samples with 4 optional 680x680 ImageNet images. "
    "Scatter coordinates for interactive visualization."
)

REQUIRED_IMAGES = 3
OPTIONAL_IMAGES = 4
IMAGENET_SIZE = 680
IMAGENET_POOL_SIZE = 400

metadata_schema = {
    "scatter_x": {"type": "float", "description": "X coordinate for scatter plot."},
    "scatter_y": {"type": "float", "description": "Y coordinate for scatter plot."},
    "point_label": {"type": "string", "description": "Cluster/group label."},
    "sample_title": {"type": "string", "description": "Human-readable sample title."},
    "image_count": {"type": "integer", "description": "Number of images."},
    "primary_image_index": {
        "type": "integer",
        "description": "Default preview image index.",
    },
    "has_large_images": {
        "type": "boolean",
        "description": "Whether sample has 680x680 optional images.",
    },
    "view_mode": {
        "type": "string",
        "description": "Marks dataset as multi-image mock.",
    },
}

config = SeedConfig(
    name="mock-multi-image",
    dataset_name=DATASET_DISPLAY_NAME,
    description=DATASET_DESCRIPTION,
    label_space=CIFAR100_LABELS,
    metadata_schema=metadata_schema,
)


def _scatter_center(label_idx: int) -> tuple[float, float]:
    cols = 10
    col = label_idx % cols
    row = label_idx // cols
    return (col - 4.5) * 10.0, (4.5 - row) * 10.0


def _scatter_coords(label_idx: int) -> tuple[float, float]:
    cx, cy = _scatter_center(label_idx)
    return round(cx + random.gauss(0, 1.5), 3), round(cy + random.gauss(0, 1.5), 3)


def _build_cifar100_pool() -> list[str]:
    import torchvision  # type: ignore[import-untyped]
    import base64
    import io

    print("  Downloading CIFAR-100 dataset via torchvision ...")
    t0 = time.time()
    train_set = torchvision.datasets.CIFAR100(
        root=os.path.expanduser("~/.cache/torchvision"),
        train=True,
        download=True,
    )
    print(f"  Downloaded {len(train_set)} images in {time.time() - t0:.1f}s")

    print("  Encoding CIFAR-100 images as PNG data URIs ...")
    t0 = time.time()
    pool: list[str] = []
    for idx in range(len(train_set)):
        img, _label = train_set[idx]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        pool.append(f"data:image/png;base64,{b64}")
        if (idx + 1) % 10000 == 0:
            print(
                f"    ... {idx + 1}/{len(train_set)} images ({time.time() - t0:.1f}s)"
            )
    print(f"  Encoded {len(pool)} CIFAR-100 images in {time.time() - t0:.1f}s")
    return pool


def _build_imagenet_pool(size: int) -> list[str]:
    import base64
    import io
    from PIL import Image  # type: ignore[import-untyped]

    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token:
        print("=" * 60)
        print("  ERROR: HF_TOKEN environment variable is not set.")
        print(
            "  ImageNet-1K requires a HuggingFace access token with accepted license."
        )
        print("  1. Go to https://huggingface.co/settings/tokens")
        print("  2. Create a token with read access")
        print("  3. Visit https://huggingface.co/datasets/ILSVRC/imagenet-1k")
        print("     and accept the license terms")
        print("  4. Run: export HF_TOKEN=hf_your_token_here")
        print("=" * 60)
        sys.exit(1)

    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError:
        print(
            "  ERROR: 'datasets' package not found. Install: uv pip install datasets Pillow"
        )
        sys.exit(1)

    print(
        f"  Streaming up to {size} ImageNet-1K validation images from HuggingFace ..."
    )
    t0 = time.time()
    hf = load_dataset(
        "ILSVRC/imagenet-1k", split="validation", streaming=True, token=hf_token
    )

    pool: list[str] = []
    for example in hf:
        if len(pool) >= size:
            break
        image = example["image"]
        if image.mode != "RGB":
            image = image.convert("RGB")
            resized = image.resize(
                (IMAGENET_SIZE, IMAGENET_SIZE),
                Image.LANCZOS
                if hasattr(Image, "LANCZOS")
                else Image.Resampling.LANCZOS,
            )  # type: ignore[union-attr]
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode()
        pool.append(f"data:image/jpeg;base64,{b64}")
        if len(pool) % 100 == 0 and len(pool) > 0:
            print(f"    ... {len(pool)}/{size} images ({time.time() - t0:.1f}s)")

    print(f"  Streamed {len(pool)} ImageNet images in {time.time() - t0:.1f}s")
    return pool


def build_sample_item_factory(
    cifar_pool: list[str],
    imagenet_pool: list[str],
    large_indices: set[int],
    max_samples: int = 100_000,
):
    """Return an item builder for multi-image mock samples.

    The returned callable expects an index and produces a dict with
    ``image_uris`` (3 CIFAR-100 images + optional 4 ImageNet images),
    ``metadata`` (scatter coords, label, etc.), and ``label``.
    """
    if not imagenet_pool:
        large_indices = set()

    def build_sample_item(idx: int) -> dict:
        label_idx = idx % len(CIFAR100_LABELS)
        label = CIFAR100_LABELS[label_idx]
        required_uris = [random.choice(cifar_pool) for _ in range(REQUIRED_IMAGES)]
        optional_uris = (
            [random.choice(imagenet_pool) for _ in range(OPTIONAL_IMAGES)]
            if idx in large_indices
            else []
        )
        image_uris = required_uris + optional_uris
        sx, sy = _scatter_coords(label_idx)
        return {
            "image_uris": image_uris,
            "metadata": {
                "scatter_x": sx,
                "scatter_y": sy,
                "point_label": label,
                "sample_title": f"{label} sample {idx + 1}",
                "image_count": len(image_uris),
                "primary_image_index": 0,
                "has_large_images": idx in large_indices,
                "view_mode": "multi-image-mock",
            },
            "label": label,
        }

    return build_sample_item


def run(args, runner: SeedRunner) -> int:
    max_samples: int = args.max_samples if args.max_samples is not None else 100_000
    large_samples: int = args.large_samples if args.large_samples is not None else 100
    loader_name: str = getattr(args, "loader", "dataset")

    if large_samples > max_samples:
        print("ERROR: --large-samples cannot exceed --max-samples")
        return 1

    print("[6/6] Building image pools ...")
    print("  Building CIFAR-100 pool (32x32 required images) ...")
    try:
        cifar_pool = _build_cifar100_pool()
    except Exception as exc:
        print(f"  ERROR: Failed to build CIFAR-100 pool: {exc}")
        return 1
    print(f"  CIFAR-100 pool ready: {len(cifar_pool)} images")

    imagenet_pool: list[str] = []
    if large_samples > 0:
        print(
            f"\n  Building ImageNet pool ({IMAGENET_SIZE}x{IMAGENET_SIZE} optional images) ..."
        )
        try:
            imagenet_pool = _build_imagenet_pool(IMAGENET_POOL_SIZE)
        except Exception as exc:
            print(f"  ERROR: Failed to build ImageNet pool: {exc}")
            return 1
    else:
        print("  Skipping ImageNet pool (--large-samples=0)")

    step = (
        max(1, max_samples // large_samples)
        if large_samples > 0 and imagenet_pool
        else max_samples + 1
    )
    large_indices = (
        {min(k * step, max_samples - 1) for k in range(large_samples)}
        if large_samples > 0 and imagenet_pool
        else set()
    )

    if large_indices:
        print(
            f"  Large image samples: {len(large_indices)} (first: {min(large_indices)}, last: {max(large_indices)})"
        )

    build_sample_item = build_sample_item_factory(
        cifar_pool, imagenet_pool, large_indices, max_samples
    )

    loader = None
    if loader_name == "s3-zip":
        from seedmaker.loaders.s3_zip import S3ZipWriter

        s3_bucket: str = getattr(args, "s3_bucket", "finetune-preview")
        s3_prefix: str = getattr(args, "s3_prefix", f"seed/{config.name}")
        zip_samples: int = getattr(args, "zip_samples", 500)
        loader = S3ZipWriter(
            bucket=s3_bucket,
            prefix=s3_prefix,
            samples_per_zip=zip_samples,
        )

    runner.upload_samples(
        total=max_samples,
        item_builder=build_sample_item,
        loader=loader,
    )
    runner.summary()
    return 0


registry.register(config, run)
