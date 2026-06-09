from __future__ import annotations

import base64
import io
import random
import sys
import time

from PIL import Image, ImageChops

from seedmaker import SeedConfig, SeedRunner, IMAGENET_LABELS, registry

"""ImageNet-100 R-Channel seed dataset: 10K samples with 5 derived R-channel grayscale images."""

DATASET_DISPLAY_NAME = "ImageNet-100 R-Channel (10K)"
DATASET_DESCRIPTION = (
    "10K samples with 5 R-channel grayscale images each: "
    "noisy 32×32 (salt & pepper), clean 32×32, diff 32×32, "
    "full 224×224, random crop 224×224."
)

NUM_CLASSES = 100
MAX_SAMPLES_DEFAULT = 10_000
SALT_PEPPER_AMOUNT = 0.05

_RESAMPLE = Image.Resampling.LANCZOS

metadata_schema: dict = {
    "label_name": {"type": "string", "description": "ImageNet class name."},
    "label_idx": {"type": "integer", "description": "ImageNet class index (0-99)."},
    "image_count": {"type": "integer", "description": "Number of images (always 5)."},
    "primary_image_index": {
        "type": "integer",
        "description": "Default preview image index (0 = noisy 32x32).",
    },
    "crop_box_32": {
        "type": "list",
        "description": "[x, y, w, h] crop region for 32x32 images.",
    },
    "crop_box_224": {
        "type": "list",
        "description": "[x, y, w, h] crop region for 224x224 crop image.",
    },
    "noise_type": {
        "type": "string",
        "description": "Noise type applied to image 1 (salt_pepper).",
    },
    "noise_amount": {
        "type": "float",
        "description": "Proportion of pixels affected by noise.",
    },
    "view_mode": {
        "type": "string",
        "description": "Marks dataset as R-channel denoising.",
    },
}

config = SeedConfig(
    name="imagenet-100-rchannel",
    dataset_name=DATASET_DISPLAY_NAME,
    description=DATASET_DESCRIPTION,
    label_space=IMAGENET_LABELS[:NUM_CLASSES],
    metadata_schema=metadata_schema,
)


def _add_salt_pepper_noise(img: Image.Image, amount: float = 0.05) -> Image.Image:
    """Add salt & pepper noise to a single-channel (L mode) PIL Image."""
    w, h = img.size
    n_pixels = w * h
    n_noisy = max(1, int(n_pixels * amount))
    n_salt = n_noisy // 2

    noisy = img.copy()
    pixels = noisy.load()
    assert pixels is not None

    indices = random.sample(range(n_pixels), n_noisy)
    for i, idx in enumerate(indices):
        y, x = divmod(idx, w)
        pixels[x, y] = 255 if i < n_salt else 0

    return noisy


def _random_square_crop(
    img: Image.Image, min_ratio: float = 0.5
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Random square crop from a PIL Image.

    Returns (cropped_image, (x, y, w, h)).
    """
    w, h = img.size
    min_dim = min(w, h)
    crop_size = random.randint(max(1, int(min_dim * min_ratio)), min_dim)
    x = random.randint(0, max(1, w - crop_size))
    y = random.randint(0, max(1, h - crop_size))
    return img.crop((x, y, x + crop_size, y + crop_size)), (x, y, crop_size, crop_size)


def _img_to_data_uri(img: Image.Image, fmt: str = "PNG", quality: int = 85) -> str:
    """Convert a PIL Image to a data URI (PNG or JPEG)."""
    buf = io.BytesIO()
    save_kwargs: dict = {"format": fmt}
    if fmt == "JPEG":
        save_kwargs["quality"] = quality
    img.save(buf, **save_kwargs)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/{fmt.lower()};base64,{b64}"


def run(args, runner: SeedRunner) -> int:
    max_samples: int = (
        args.max_samples if args.max_samples is not None else MAX_SAMPLES_DEFAULT
    )

    # Check for existing samples before attempting HF download
    existing = runner._existing_sample_count()
    if existing > 0:
        print(f"  Dataset already has {existing} samples, skipping HF download.")
        runner._sample_count = existing
        runner.summary()
        return 0

    print("[6/6] Streaming ImageNet-1K train split (first 100 classes) ...")
    try:
        from datasets import load_dataset  # pyright: ignore[reportMissingImports]
    except ImportError:
        print(
            "  ERROR: 'datasets' package not found. "
            "Install: uv pip install datasets Pillow"
        )
        sys.exit(1)

    import os

    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    load_kwargs: dict = {"split": "train", "streaming": True}
    if hf_token:
        load_kwargs["token"] = hf_token

    try:
        t0 = time.time()
        hf = load_dataset("ILSVRC/imagenet-1k", **load_kwargs)
    except Exception as exc:
        msg = str(exc)
        if "gated" in msg.lower() or "authenticated" in msg.lower():
            print(
                "  SKIPPING: ILSVRC/imagenet-1k is a gated dataset on HuggingFace Hub.\n"
                "  Set HF_TOKEN env var and accept the license at: "
                "https://huggingface.co/datasets/ILSVRC/imagenet-1k\n"
                "  Then re-run this command."
            )
            runner.summary()
            return 0
        raise

    r_channels: list[Image.Image] = []
    labels: list[int] = []
    for example in hf:
        if len(r_channels) >= max_samples:
            break
        label_idx: int = example["label"]
        if 0 <= label_idx < NUM_CLASSES:
            image: Image.Image = example["image"]
            if image.mode != "RGB":
                image = image.convert("RGB")
            r_channels.append(image.getchannel("R"))
            labels.append(label_idx)
        if len(r_channels) % 1000 == 0 and len(r_channels) > 0:
            elapsed = time.time() - t0
            print(f"    ... {len(r_channels)}/{max_samples} images ({elapsed:.1f}s)")

    elapsed = time.time() - t0
    print(f"  Collected {len(r_channels)} images in {elapsed:.1f}s")

    if len(r_channels) < max_samples:
        print(
            f"  WARNING: Only collected {len(r_channels)}/{max_samples} images "
            f"from first {NUM_CLASSES} classes."
        )

    total = len(r_channels)
    print(f"  Generating {total} samples with 5 R-channel images each ...")
    t0 = time.time()

    def _build_item(idx: int) -> dict:
        r_img = r_channels[idx]
        label_idx = labels[idx]
        label_name = IMAGENET_LABELS[label_idx]

        # Images 1 & 2: same random square crop → 32×32
        crop_32, crop_box_32 = _random_square_crop(r_img)
        img_32_clean = crop_32.resize((32, 32), _RESAMPLE)
        img_32_noisy = _add_salt_pepper_noise(img_32_clean, SALT_PEPPER_AMOUNT)

        # Image 3: absolute difference (isolates noise pattern)
        img_diff = ImageChops.difference(img_32_noisy, img_32_clean)

        # Image 4: full R channel → 224×224
        img_224_full = r_img.resize((224, 224), _RESAMPLE)

        # Image 5: different random square crop → 224×224
        crop_224, crop_box_224 = _random_square_crop(r_img)
        img_224_crop = crop_224.resize((224, 224), _RESAMPLE)

        image_uris = [
            _img_to_data_uri(img_32_noisy, "PNG"),  # 0: noisy 32×32
            _img_to_data_uri(img_32_clean, "PNG"),  # 1: clean 32×32
            _img_to_data_uri(img_diff, "PNG"),  # 2: diff 32×32
            _img_to_data_uri(img_224_full, "JPEG"),  # 3: full 224×224
            _img_to_data_uri(img_224_crop, "JPEG"),  # 4: crop 224×224
        ]

        return {
            "image_uris": image_uris,
            "metadata": {
                "label_name": label_name,
                "label_idx": label_idx,
                "image_count": len(image_uris),
                "primary_image_index": 0,
                "crop_box_32": list(crop_box_32),
                "crop_box_224": list(crop_box_224),
                "noise_type": "salt_pepper",
                "noise_amount": SALT_PEPPER_AMOUNT,
                "view_mode": "rchannel-denoise",
            },
            "label": label_name,
        }

    runner.upload_samples(
        total=total,
        item_builder=_build_item,
    )
    runner.summary()
    return 0


registry.register(config, run)
