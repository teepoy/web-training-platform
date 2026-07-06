from __future__ import annotations

# pyright: reportPrivateImportUsage=false
# pyright: reportMissingImports=false

import asyncio
import concurrent.futures
import io
import time
import tempfile
from pathlib import Path
from typing import Any, Generator, Sequence, cast

from PIL import Image
from prefect import get_run_logger

from app.modules.sc.schema import find_images_by_role
from platform_runtime.contracts import (
    ModelRef,
    PredictContext,
)
from app.modules.prediction.flows._predictors import predictor


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
    image_fetcher: Any = None,
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

    df = cast(Any, lazyframe).collect()
    rows = list(df.iter_rows(named=True))
    total = len(rows)
    batch_size = 16
    total_batches = (total + batch_size - 1) // batch_size
    t_start = time.monotonic()

    _cache: dict[tuple[str, int, str, str, int | None], bytes] = {}
    _insp_time = str(rows[0].get("inspection_time", "")) if rows else ""
    _wafer_key = int(rows[0].get("wafer_key", 0) or 0) if rows else 0

    if image_fetcher is not None:
        try:
            import asyncio as _asyncio_yp_warm

            _asyncio_yp_warm.run(
                image_fetcher.warm_cache(
                    inspection_time=_insp_time, wafer_key=_wafer_key
                )
            )
        except Exception:
            logger.warning("Warm-cache failed, continuing without warm")

    def _cache_key(
        defect_id: str, image_type: str, review_image_id: int | None
    ) -> tuple[str, int, str, str, int | None]:
        return (_insp_time, _wafer_key, defect_id, image_type, review_image_id)

    try:
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)

            _pending_fetches: list[Any] = []
            _pending_imgs: list[dict[str, object]] = []

            for i in range(start, end):
                row = rows[i]
                sample_id = str(row["sample_id"])
                images_list: list[dict[str, object]] = row["images"]
                defective_imgs = find_images_by_role(images_list, "patch_defective")
                template_imgs = find_images_by_role(images_list, "patch_template")
                if not defective_imgs or not template_imgs:
                    yield {
                        "sample_id": sample_id,
                        "label": "",
                        "confidence": None,
                        "error": "missing image bytes",
                    }
                    continue

                def_bytes: object | None = defective_imgs[0].get("bytes")
                ref_bytes: object | None = template_imgs[0].get("bytes")

                if def_bytes is not None and ref_bytes is not None:
                    _pending_imgs.append(
                        {
                            "_def_bytes": def_bytes,
                            "_ref_bytes": ref_bytes,
                            "_sid": sample_id,
                        }
                    )
                    continue

                if image_fetcher is None:
                    yield {
                        "sample_id": sample_id,
                        "label": "",
                        "confidence": None,
                        "error": "image bytes not available (no fetcher)",
                    }
                    continue

                d_type = str(defective_imgs[0].get("image_type", ""))
                r_type = str(template_imgs[0].get("image_type", ""))
                d_rid = cast(int | None, defective_imgs[0].get("review_image_id"))
                r_rid = cast(int | None, template_imgs[0].get("review_image_id"))
                defect_id = str(row.get("defect_id", ""))

                d_key = _cache_key(defect_id, d_type, d_rid)
                r_key = _cache_key(defect_id, r_type, r_rid)
                d_cached = _cache.get(d_key)
                r_cached = _cache.get(r_key)

                if d_cached is not None and r_cached is not None:
                    _pending_imgs.append(
                        {
                            "_def_bytes": d_cached,
                            "_ref_bytes": r_cached,
                            "_sid": sample_id,
                        }
                    )
                    continue

                async def _resolve_via_batch() -> tuple[str, bytes, bytes]:
                    imgs_for_batch: list[dict[str, object]] = []
                    if d_cached is None:
                        imgs_for_batch.append(
                            {
                                "defect_id": defect_id,
                                "image_type": d_type,
                                "review_image_id": d_rid,
                            }
                        )
                    if r_cached is None:
                        imgs_for_batch.append(
                            {
                                "defect_id": defect_id,
                                "image_type": r_type,
                                "review_image_id": r_rid,
                            }
                        )
                    results = await image_fetcher.get_image_bytes_batch(
                        inspection_time=_insp_time,
                        wafer_key=_wafer_key,
                        images=imgs_for_batch,
                    )
                    d_res = d_cached
                    r_res = r_cached
                    for r in results:
                        img_bytes = cast(bytes, r.get("image_data"))
                        if r.get("defect_id") == defect_id:
                            if r.get("image_type") == d_type and d_res is None:
                                _cache[d_key] = img_bytes
                                d_res = img_bytes
                            elif r.get("image_type") == r_type and r_res is None:
                                _cache[r_key] = img_bytes
                                r_res = img_bytes
                    if d_res is None or r_res is None:
                        raise RuntimeError(f"Batch fetch failed for sample {sample_id}")
                    return sample_id, d_res, r_res

                _pending_fetches.append(_resolve_via_batch())

            if _pending_fetches:
                import asyncio as _asyncio_yp_b

                async def _gather_all() -> list[Any]:
                    return await _asyncio_yp_b.gather(*_pending_fetches)

                _all_resolved = _asyncio_yp_b.run(_gather_all())
                for _sid, _d, _r in _all_resolved:
                    _pending_imgs.append(
                        {"_def_bytes": _d, "_ref_bytes": _r, "_sid": _sid}
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
