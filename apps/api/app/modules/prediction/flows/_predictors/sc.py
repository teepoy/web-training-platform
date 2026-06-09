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

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch_no = start // batch_size + 1
        def_batch: list[torch.Tensor] = []
        ref_batch: list[torch.Tensor] = []
        batch_ids: list[str] = []

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

            def_bytes = defective_imgs[0]["bytes"]
            ref_bytes = reference_imgs[0]["bytes"]
            def_img = Image.open(io.BytesIO(cast(bytes, def_bytes))).convert("RGB")
            ref_img = Image.open(io.BytesIO(cast(bytes, ref_bytes))).convert("RGB")
            def_batch.append(cast(Any, _transform(def_img)))
            ref_batch.append(cast(Any, _transform(ref_img)))
            batch_ids.append(sample_id)

        if not def_batch:
            continue

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
