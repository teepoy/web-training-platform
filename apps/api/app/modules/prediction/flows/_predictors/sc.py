from __future__ import annotations

# pyright: reportPrivateImportUsage=false
# pyright: reportMissingImports=false

import asyncio
import concurrent.futures
import io
import time
from typing import Any, Generator, cast

from PIL import Image
from prefect import get_run_logger

from app.modules.sc.schema import find_images_by_role
from platform_runtime.contracts import (
    ModelRef,
    PredictContext,
)
from app.modules.prediction.flows._predictors import predictor


@predictor(
    id="resnet50-sc-v1",
    name="ResNet-50 SC Defect Prediction",
    view_id="patch_image_v1",
)
def resnet_sc_predictor(
    *,
    artifact_storage: Any,
    ctx: PredictContext,
    lazyframe: Any,
    model_ref: ModelRef,
    image_fetcher: Any = None,
) -> Generator[dict[str, Any], None, None]:
    logger = get_run_logger()

    import torch
    import torch.nn.functional as F
    from torchvision import models, transforms

    if artifact_storage is None:
        raise ValueError("artifact_storage is required for resnet50-sc-v1 predictor")
    if not model_ref.uri:
        raise ValueError("model_ref.uri is required")

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    _transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )

    _storage = artifact_storage
    _uri = model_ref.uri

    async def _load_checkpoint() -> Any:
        raw = await _storage.get_bytes(_uri)
        return torch.load(io.BytesIO(raw), map_location=device, weights_only=False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
        checkpoint = _pool.submit(
            lambda: asyncio.new_event_loop().run_until_complete(_load_checkpoint())
        ).result()

    labels = list(checkpoint.get("labels", []))
    num_classes = checkpoint.get("num_classes", len(labels))
    if not labels:
        raise ValueError("checkpoint has no labels — cannot create classifier")

    class DualResNetClassifier(torch.nn.Module):
        def __init__(self, num_classes: int) -> None:
            super().__init__()
            backbone = models.resnet50(weights=None)
            self.backbone = torch.nn.Sequential(*list(backbone.children())[:-1])
            self.classifier = torch.nn.Sequential(
                torch.nn.Linear(2048 * 3, 512),
                torch.nn.ReLU(),
                torch.nn.Dropout(0.3),
                torch.nn.Linear(512, num_classes),
            )

        def forward(
            self, defective: torch.Tensor, reference: torch.Tensor
        ) -> torch.Tensor:
            feat_d = self.backbone(defective).flatten(1)
            feat_r = self.backbone(reference).flatten(1)
            diff = torch.abs(feat_d - feat_r)
            combined = torch.cat([feat_d, feat_r, diff], dim=1)
            return self.classifier(combined)

    model = DualResNetClassifier(num_classes=int(num_classes))
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device)
    model.eval()

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
            import asyncio as _asyncio_pr_warm

            _asyncio_pr_warm.run(
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

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch_no = start // batch_size + 1

        _pending_fetches: list[Any] = []  # coroutines
        _pending_imgs: list[dict[str, object]] = []
        _pending_batch_sids: list[str] = []

        for i in range(start, end):
            row = rows[i]
            sample_id = str(row["sample_id"])
            images_list: list[dict[str, object]] = row["images"]
            defective_imgs = find_images_by_role(images_list, "patch_defective")
            reference_imgs = find_images_by_role(images_list, "patch_template")
            if not defective_imgs or not reference_imgs:
                yield {
                    "sample_id": sample_id,
                    "label": "",
                    "confidence": None,
                    "error": "missing image bytes",
                }
                continue

            def_bytes: object | None = defective_imgs[0].get("bytes")
            ref_bytes: object | None = reference_imgs[0].get("bytes")

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
            r_type = str(reference_imgs[0].get("image_type", ""))
            d_rid = cast(int | None, defective_imgs[0].get("review_image_id"))
            r_rid = cast(int | None, reference_imgs[0].get("review_image_id"))
            defect_id = str(row.get("defect_id", ""))

            d_key = _cache_key(defect_id, d_type, d_rid)
            r_key = _cache_key(defect_id, r_type, r_rid)
            d_cached = _cache.get(d_key)
            r_cached = _cache.get(r_key)

            if d_cached is not None and r_cached is not None:
                _pending_imgs.append(
                    {"_def_bytes": d_cached, "_ref_bytes": r_cached, "_sid": sample_id}
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
            _pending_batch_sids.append(sample_id)

        if _pending_fetches:
            import asyncio as _asyncio_pr_b

            async def _gather_all() -> list[Any]:
                return await _asyncio_pr_b.gather(*_pending_fetches)

            _all_resolved = _asyncio_pr_b.run(_gather_all())
            for _sid, _d, _r in _all_resolved:
                _pending_imgs.append({"_def_bytes": _d, "_ref_bytes": _r, "_sid": _sid})

        if not _pending_imgs:
            continue

        def_batch: list[torch.Tensor] = []
        ref_batch: list[torch.Tensor] = []
        batch_ids: list[str] = []

        for _img in _pending_imgs:
            def_img = Image.open(io.BytesIO(cast(bytes, _img["_def_bytes"]))).convert(
                "RGB"
            )
            ref_img = Image.open(io.BytesIO(cast(bytes, _img["_ref_bytes"]))).convert(
                "RGB"
            )
            def_batch.append(cast(Any, _transform(def_img)))
            ref_batch.append(cast(Any, _transform(ref_img)))
            batch_ids.append(str(_img["_sid"]))

        def_tensor = torch.stack(def_batch).to(device)
        ref_tensor = torch.stack(ref_batch).to(device)

        with torch.no_grad():
            outputs = model(def_tensor, ref_tensor)
            probs = F.softmax(outputs, dim=1)

        for i, sid in enumerate(batch_ids):
            scores: dict[str, float] = {
                labels[j]: float(probs[i][j].item()) for j in range(len(labels))
            }
            best_idx = int(torch.argmax(probs[i]).item())
            yield {
                "sample_id": sid,
                "label": labels[best_idx] if best_idx < len(labels) else "",
                "confidence": float(probs[i][best_idx].item()),
                "scores": scores,
            }
        elapsed = time.monotonic() - t_start
        processed = min(end, total)
        logger.info(
            "Prediction batch %d/%d — %d/%d samples (%.1f samples/s)",
            batch_no,
            total_batches,
            processed,
            total,
            processed / elapsed if elapsed > 0 else 0,
        )
