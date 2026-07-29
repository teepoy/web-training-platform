"""Demo utilities for prototype classification trainer/predictor."""

from __future__ import annotations

import base64
import logging
import math
from io import BytesIO
from typing import Callable

from PIL import Image


def _decode_data_uri(uri: str) -> bytes:
    _, encoded = uri.split(",", 1)
    return base64.b64decode(encoded)


def _image_embedding_from_bytes(
    image_bytes: bytes,
    dim: int = 64,
    embed_fn: Callable[[bytes], list[float]] | None = None,
) -> list[float]:
    if embed_fn is not None:
        result = embed_fn(image_bytes)
        # Pad/truncate result to dim dimensions, then normalize
        if len(result) < dim:
            result = list(result) + [0.0] * (dim - len(result))
        vec = list(result)[:dim]
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    with Image.open(BytesIO(image_bytes)) as img:
        gray = img.convert("L").resize((8, 8))
        pixels = list(gray.tobytes())
    vals = [float(p) / 255.0 for p in pixels]
    if len(vals) < dim:
        vals.extend([0.0] * (dim - len(vals)))
    vec = vals[:dim]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _logger() -> logging.Logger:
    return logging.getLogger(__name__)
