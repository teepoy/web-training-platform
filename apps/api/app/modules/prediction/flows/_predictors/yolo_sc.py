from __future__ import annotations

# pyright: reportPrivateImportUsage=false
# pyright: reportMissingImports=false

import asyncio
import concurrent.futures
import io
import time
import tempfile
from pathlib import Path
from typing import Any, Generator, Mapping, Sequence, cast

from PIL import Image
from prefect import get_run_logger

from app.modules.sc.schema import find_images_by_role
from platform_runtime.contracts import (
    ModelRef,
    PredictContext,
)
from app.modules.prediction.flows._predictors import predictor


def _resolve_labels(
    model: Any,
    model_ref: ModelRef,
    ctx: PredictContext,
) -> list[str]:
    names = getattr(model, "names", None)
    if isinstance(names, Mapping):
        return [str(names[index]) for index in sorted(names)]
    if isinstance(names, Sequence) and not isinstance(names, (str, bytes)):
        return [str(name) for name in names]

    metadata_labels = model_ref.metadata.get("label_space", [])
    if isinstance(metadata_labels, Sequence) and not isinstance(
        metadata_labels, (str, bytes)
    ):
        labels = [str(label) for label in metadata_labels]
        if labels:
            return labels

    return list(ctx.dataset_ref.label_space)


@predictor(
    id="yolo-sc-v1",
    name="YOLO SC Detection Predictor",
    view_id="patch_image_v1",
)
def yolo_sc_predictor(
    *,
    artifact_storage: Any,
    ctx: PredictContext,
    lazyframe: Any,
    model_ref: ModelRef,
) -> Generator[dict[str, Any], None, None]:
    logger = get_run_logger()

    import torch
    from ultralytics import YOLO

    if artifact_storage is None:
        raise ValueError("artifact_storage is required for yolo-sc-v1 predictor")
    if not model_ref.uri:
        raise ValueError("model_ref.uri is required")

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    _storage = artifact_storage
    _uri = model_ref.uri

    async def _fetch_model() -> bytes:
        return await _storage.get_bytes(_uri)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
        raw_bytes = _pool.submit(
            lambda: asyncio.new_event_loop().run_until_complete(_fetch_model())
        ).result()

    _tmp_dir = tempfile.TemporaryDirectory()
    _tmp_path = Path(_tmp_dir.name) / "model.pt"
    _tmp_path.write_bytes(raw_bytes)

    try:
        model = YOLO(str(_tmp_path))
        model.to(device)
        labels = _resolve_labels(model, model_ref, ctx)
        if not labels:
            raise ValueError("YOLO model has no class names")
    except Exception:
        _tmp_dir.cleanup()
        raise

    df = cast(Any, lazyframe).collect()
    rows = list(df.iter_rows(named=True))
    total = len(rows)
    batch_size = 16
    total_batches = (total + batch_size - 1) // batch_size
    t_start = time.monotonic()

    try:
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_imgs: list[Image.Image] = []
            batch_ids: list[str] = []

            for i in range(start, end):
                row = rows[i]
                sample_id = str(row["sample_id"])
                images_list: list[dict[str, object]] = row["images"]
                defective_imgs = find_images_by_role(images_list, "patch_defective")
                if not defective_imgs:
                    yield {
                        "sample_id": sample_id,
                        "label": "",
                        "confidence": None,
                        "error": "missing image bytes",
                    }
                    continue

                def_bytes = defective_imgs[0]["bytes"]
                batch_imgs.append(
                    Image.open(io.BytesIO(cast(bytes, def_bytes))).convert("RGB")
                )
                batch_ids.append(sample_id)

            if not batch_imgs:
                continue

            results = model(batch_imgs)

            for i, sid in enumerate(batch_ids):
                probs = results[i].probs
                if probs is None:
                    yield {
                        "sample_id": sid,
                        "label": "",
                        "confidence": None,
                        "error": "no classification output",
                    }
                    continue

                scores: dict[str, float] = {
                    labels[j]: float(probs.data[j].item()) for j in range(len(labels))
                }
                best_idx = int(probs.top1)
                yield {
                    "sample_id": sid,
                    "label": labels[best_idx] if best_idx < len(labels) else "",
                    "confidence": float(probs.top1conf.item()),
                    "scores": scores,
                }
            elapsed = time.monotonic() - t_start
            processed = min(end, total)
            logger.info(
                "Prediction batch %d/%d — %d/%d samples (%.1f samples/s)",
                start // batch_size + 1,
                total_batches,
                processed,
                total,
                processed / elapsed if elapsed > 0 else 0,
            )
    finally:
        _tmp_dir.cleanup()
