from __future__ import annotations

# pyright: reportPrivateImportUsage=false
# pyright: reportMissingImports=false

import asyncio
import concurrent.futures
import io
import time
import tempfile
from itertools import batched
from pathlib import Path
from typing import Any, Generator, Sequence, cast

from PIL import Image
from prefect import get_run_logger

from app.shared.domain.runtime import (
    ModelRef,
    PredictContext,
)
from app.runtime_compat.ml.predictors import predictor


def _resolve_labels(
    model_ref: ModelRef,
) -> list[str]:
    metadata_labels = model_ref.metadata.get("label_space", [])
    if isinstance(metadata_labels, Sequence) and not isinstance(
        metadata_labels, (str, bytes)
    ):
        labels = [str(label) for label in metadata_labels]
        if labels:
            return labels

    raise ValueError("YOLO model metadata must include compact label_space")


@predictor(id="yolo-sc-v1")
def yolo_sc_predictor(
    *,
    artifact_storage: Any,
    ctx: PredictContext,
    model_ref: ModelRef,
    materialized_dataset: Any,
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
        labels = _resolve_labels(model_ref)
    except Exception:
        _tmp_dir.cleanup()
        raise

    total = len(materialized_dataset)
    batch_size = 16
    total_batches = (total + batch_size - 1) // batch_size
    t_start = time.monotonic()
    processed = 0

    try:
        for batch_no, rows in enumerate(
            batched(materialized_dataset, batch_size),
            start=1,
        ):
            _pending_imgs: list[dict[str, object]] = []

            for row in rows:
                sample_id = str(row["sample_id"])
                def_bytes = row.get("patch_defective_bytes")
                ref_bytes = row.get("patch_template_bytes")
                if def_bytes is None or ref_bytes is None:
                    yield {
                        "sample_id": sample_id,
                        "label": "",
                        "confidence": None,
                        "error": "missing materialized image bytes",
                    }
                    continue

                _pending_imgs.append(
                    {
                        "_def_bytes": def_bytes,
                        "_ref_bytes": ref_bytes,
                        "_sid": sample_id,
                    }
                )

            if not _pending_imgs:
                continue

            batch_imgs: list[Image.Image] = []
            batch_ids: list[str] = []

            for _img in _pending_imgs:
                defective_img = Image.open(
                    io.BytesIO(cast(bytes, _img["_def_bytes"]))
                ).convert("RGB")
                template_img = Image.open(
                    io.BytesIO(cast(bytes, _img["_ref_bytes"]))
                ).convert("RGB")

                stacked = Image.new(
                    "RGB", (defective_img.width, defective_img.height * 2)
                )
                stacked.paste(defective_img, (0, 0))
                stacked.paste(template_img, (0, defective_img.height))

                combined = stacked.resize((224, 224), Image.Resampling.LANCZOS)
                batch_imgs.append(combined)
                batch_ids.append(str(_img["_sid"]))

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

                output_classes = int(probs.data.shape[0])
                if output_classes != len(labels):
                    raise ValueError(
                        "YOLO prediction output class count does not match "
                        f"model metadata label_space: output={output_classes} "
                        f"labels={len(labels)}"
                    )
                scores: dict[str, float] = {
                    labels[j]: float(probs.data[j].item()) for j in range(len(labels))
                }
                best_idx = int(probs.top1)
                yield {
                    "sample_id": sid,
                    "label": labels[best_idx],
                    "confidence": float(probs.top1conf.item()),
                    "scores": scores,
                }
            elapsed = time.monotonic() - t_start
            processed += len(rows)
            logger.info(
                "Prediction batch %d/%d — %d/%d samples (%.1f samples/s)",
                batch_no,
                total_batches,
                processed,
                total,
                processed / elapsed if elapsed > 0 else 0,
            )
    finally:
        _tmp_dir.cleanup()
