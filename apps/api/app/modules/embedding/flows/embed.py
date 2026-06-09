from __future__ import annotations

import io
from typing import Any

from prefect import flow, get_run_logger

# Module-level model cache — models are expensive to load and
# Prefect flow worker processes persist across runs.
_model_cache: dict[str, tuple[Any, Any]] = {}


def _load_model(model_name: str) -> tuple[Any, Any]:
    if model_name not in _model_cache:
        from transformers import CLIPModel, CLIPProcessor  # ruff: TID253  # pyright: ignore[reportMissingImports]

        logger = get_run_logger()
        logger.info("Loading model %s", model_name)
        processor = CLIPProcessor.from_pretrained(model_name)
        model = CLIPModel.from_pretrained(model_name)
        model.eval()
        _model_cache[model_name] = (model, processor)
    return _model_cache[model_name]


def _embed_one(image_bytes: bytes, model_name: str) -> list[float]:
    import torch  # noqa: F811  # ruff: TID253

    model, processor = _load_model(model_name)
    image = __import__("PIL.Image").open(io.BytesIO(image_bytes)).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    with torch.no_grad():
        features = model.get_image_features(**inputs)
        features = features / features.norm(dim=-1, keepdim=True)
    return features[0].tolist()


def _classify_one(
    image_bytes: bytes, labels: list[str], model_name: str
) -> tuple[str, float, list[tuple[str, float]]]:
    import torch  # noqa: F811  # ruff: TID253

    model, processor = _load_model(model_name)
    image = __import__("PIL.Image").open(io.BytesIO(image_bytes)).convert("RGB")

    text_prompts = [f"a photo of {label}" for label in labels]
    inputs = processor(
        text=text_prompts,
        images=image,
        return_tensors="pt",
        padding=True,
    )

    with torch.no_grad():
        outputs = model(**inputs)
        logits_per_image = outputs.logits_per_image
        probs = logits_per_image.softmax(dim=1)[0]

    scores = [(labels[i], float(probs[i])) for i in range(len(labels))]
    best_idx = probs.argmax().item()
    predicted_label = labels[best_idx]
    confidence = float(probs[best_idx])

    return predicted_label, confidence, scores


@flow(name="embedding-embed")
async def embed_flow(
    image_bytes: bytes | None = None,
    image_path: str | None = None,
    model_name: str = "openai/clip-vit-base-patch32",
) -> dict[str, Any]:
    """Generate normalized CLIP image embeddings.

    Provide either ``image_bytes`` or ``image_path``.
    Returns ``{"embedding": [...], "dim": N}``.
    """
    logger = get_run_logger()
    logger.info("Embedding flow started: model=%s", model_name)

    if image_bytes is None and image_path is None:
        raise ValueError("One of image_bytes or image_path must be provided")

    if image_bytes is None:
        assert image_path is not None
        with open(image_path, "rb") as f:
            image_bytes = f.read()

    embedding = _embed_one(image_bytes, model_name)
    return {"embedding": embedding, "dim": len(embedding)}


@flow(name="embedding-classify")
async def classify_flow(
    image_bytes: bytes | None = None,
    image_path: str | None = None,
    labels: list[str] | None = None,
    model_name: str = "openai/clip-vit-base-patch32",
) -> dict[str, Any]:
    """Zero-shot CLIP classification.

    Provide either ``image_bytes`` or ``image_path``, plus a non-empty ``labels`` list.
    Returns ``{"predicted_label": ..., "confidence": ..., "scores": [...], "model_name": ...}``.
    """
    logger = get_run_logger()
    logger.info("Classify flow started: model=%s labels=%s", model_name, labels)

    if image_bytes is None and image_path is None:
        raise ValueError("One of image_bytes or image_path must be provided")
    if not labels:
        raise ValueError("At least one label must be provided")

    if image_bytes is None:
        assert image_path is not None
        with open(image_path, "rb") as f:
            image_bytes = f.read()

    predicted_label, confidence, scores = _classify_one(image_bytes, labels, model_name)
    return {
        "predicted_label": predicted_label,
        "confidence": confidence,
        "scores": [{"label": label, "score": score} for label, score in scores],
        "model_name": model_name,
    }
