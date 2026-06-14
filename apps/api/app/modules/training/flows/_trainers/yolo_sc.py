"""YOLO SC classification trainer.

Trains a YOLOv8-cls model on SC patch defective images using ultralytics.
Follows the ResNet-50 ``sc.py`` trainer pattern but replaces the dual-stream
PyTorch training loop with ultralytics YOLO classification.
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportPrivateImportUsage=false

from prefect import get_run_logger
from typing import Any, cast

from app.modules.sc.schema import find_images_by_role
from platform_runtime.contracts import TrainContext, TrainResult
from app.core.registry import trainer


@trainer(
    id="yolo-sc-v1",
    name="YOLO SC Detection Trainer",
    view_id="patch_image_v1",
)
async def yolo_sc_train(
    ctx: TrainContext,
    *,
    artifact_storage: Any = None,
    lazyframe: Any | None = None,
    image_fetcher: Any = None,
    **kwargs: Any,
) -> TrainResult:
    import io
    import json
    import os
    import tempfile
    from datetime import UTC, datetime

    logger = get_run_logger()

    import torch
    from PIL import Image
    from ultralytics import YOLO

    if artifact_storage is None:
        raise ValueError("artifact_storage is required for yolo-sc-v1 training")

    if lazyframe is None:
        raise ValueError("no lazyframe provided for training")

    # ── Pre-resolve image bytes concurrently ─────────────────────────
    if image_fetcher is not None and lazyframe is not None:
        import asyncio as _asyncio_yolo

        _lf: Any = lazyframe
        df = _lf.collect()
        _fetches: list[Any] = []
        _targets: list[dict[str, Any]] = []
        for row in df.iter_rows(named=True):
            images_list: list[dict[str, Any]] = row.get("images") or []
            for img in images_list:
                role = img.get("role", "")
                if role not in ("patch_template", "patch_defective"):
                    continue
                if img.get("bytes") is not None:
                    continue
                _fetches.append(
                    image_fetcher.get_image_bytes(
                        inspection_time=str(row.get("inspection_time", "")),
                        wafer_key=int(row.get("wafer_key", 0) or 0),
                        defect_id=str(row.get("defect_id", "")),
                        image_type=str(img.get("image_type", "")),
                        review_image_id=cast(
                            int | None,
                            img.get("review_image_id")
                            if img.get("review_image_id") is not None
                            else None,
                        ),
                    )
                )
                _targets.append(img)
        if _fetches:
            _resolved = await _asyncio_yolo.gather(*_fetches)
            for img, _bytes in zip(_targets, _resolved):
                img["bytes"] = _bytes
        lazyframe = df.lazy()

    label_space: list[str] = list(ctx.dataset_ref.label_space)
    label_map: dict[str, int] = {label: idx for idx, label in enumerate(label_space)}

    # ── Device selection ──────────────────────────────────────────────
    if torch.cuda.is_available():
        device_str: int | str = 0
    elif torch.mps.is_available():
        device_str = "mps"
    else:
        device_str = "cpu"

    tmpdir_obj = tempfile.TemporaryDirectory()
    tmpdir = tmpdir_obj.name

    try:
        # ── Collect LazyFrame and build YOLO dataset on disk ──────────
        df = lazyframe.collect()

        images_dir = os.path.join(tmpdir, "images")
        labels_dir = os.path.join(tmpdir, "labels")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(labels_dir, exist_ok=True)

        sample_count = 0

        logger.info("YOLO SC training — building dataset from LazyFrame")
        for row in df.iter_rows(named=True):
            sample_id: str = row.get("sample_id", "unknown")
            images_list: list[dict[str, Any]] = row.get("images") or []

            defective_imgs = find_images_by_role(images_list, "patch_defective")
            template_imgs = find_images_by_role(images_list, "patch_template")
            if not defective_imgs or not template_imgs:
                continue

            label: str | None = row.get("label")
            if not label or label not in label_map:
                continue

            defective_bytes: bytes | None = cast(
                bytes | None, defective_imgs[0].get("bytes")
            )
            template_bytes: bytes | None = cast(
                bytes | None, template_imgs[0].get("bytes")
            )
            if not defective_bytes or not template_bytes:
                continue

            defective_img = Image.open(io.BytesIO(defective_bytes)).convert("RGB")
            template_img = Image.open(io.BytesIO(template_bytes)).convert("RGB")

            stacked = Image.new("RGB", (defective_img.width, defective_img.height * 2))
            stacked.paste(defective_img, (0, 0))
            stacked.paste(template_img, (0, defective_img.height))

            pil_img = stacked.resize((224, 224), Image.Resampling.LANCZOS)
            img_path = os.path.join(images_dir, f"{sample_id}.jpg")
            pil_img.save(img_path, "JPEG")

            class_idx = label_map[label]
            label_path = os.path.join(labels_dir, f"{sample_id}.txt")
            with open(label_path, "w") as lf:
                lf.write(f"{class_idx} 0.5 0.5 1.0 1.0\n")

            sample_count += 1
            if sample_count % 500 == 0:
                logger.info("YOLO SC dataset build: %d samples prepared", sample_count)

        if sample_count == 0:
            raise ValueError("no valid defective images with labels found in LazyFrame")

        # ── Label mapping ─────────────────────────────────────────────
        labels = list(label_space)
        label_to_idx: dict[str, int] = dict(label_map)
        num_classes: int = len(labels)

        # ── Train YOLOv8 classification model ─────────────────────────
        logger.info(
            "YOLO SC training started — %d samples, %d classes, device=%s",
            sample_count,
            num_classes,
            device_str,
        )
        model = YOLO("yolov8n-cls.pt")
        model.train(
            data=tmpdir,
            epochs=3,
            imgsz=224,
            device=device_str,
            project=tmpdir,
            name="train_run",
            exist_ok=True,
        )

        # ── Find best checkpoint ──────────────────────────────────────
        best_pt_path = os.path.join(tmpdir, "train_run", "weights", "best.pt")
        if not os.path.exists(best_pt_path):
            best_pt_path = os.path.join(tmpdir, "train_run", "weights", "last.pt")

        with open(best_pt_path, "rb") as fh:
            checkpoint_bytes = fh.read()

        checkpoint_object = f"models/{ctx.job_id}/checkpoint.pt"
        metrics_object = f"models/{ctx.job_id}/metrics.json"

        model_uri = await artifact_storage.put_bytes(
            object_name=checkpoint_object,
            data=checkpoint_bytes,
            content_type="application/octet-stream",
        )

        # ── Collect metrics ───────────────────────────────────────────
        metrics_payload: dict[str, Any] = {
            "num_samples": sample_count,
            "num_classes": num_classes,
            "epochs": 3,
            "architecture": "yolov8n-cls",
            "framework": "ultralytics",
        }

        # Try to read YOLO results CSV for per-epoch metrics
        results_csv = os.path.join(tmpdir, "train_run", "results.csv")
        if os.path.exists(results_csv):
            import csv

            with open(results_csv) as cf:
                reader = csv.DictReader(cf)
                rows = list(reader)
                if rows:
                    last_row = rows[-1]
                    for k, v in last_row.items():
                        key = k.strip()
                        try:
                            metrics_payload[key] = float(v)
                        except (ValueError, TypeError):
                            metrics_payload[key] = v

        metrics_uri = await artifact_storage.put_bytes(
            object_name=metrics_object,
            data=json.dumps(metrics_payload, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )

        return TrainResult(
            model_uri=model_uri,
            metrics=metrics_payload,
            artifact_uris=[model_uri, metrics_uri],
            metadata={
                "runtime": "yolo-sc-v1",
                "framework": "ultralytics",
                "architecture": "yolov8n-cls",
                "trained_samples": sample_count,
                "label_space": labels,
                "label_to_idx": label_to_idx,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    finally:
        tmpdir_obj.cleanup()
