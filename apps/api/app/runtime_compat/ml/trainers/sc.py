from __future__ import annotations

# pyright: reportMissingImports=false

import io
import importlib
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast

from PIL import Image
from prefect import get_run_logger
from torch.utils.data import Dataset

from app.modules.sc.schema import find_images_by_role
from app.modules.sc.app.services.training_images import image_bytes_are_readable
from app.shared.domain.data_plane import DataPlaneManifest
from app.shared.domain.runtime import TrainContext, TrainResult
from app.runtime_compat.ml.trainers import trainer
from app.runtime_compat.ml.trainers.materialized_input import (
    sc_materialized_lazyframe,
)

logger = logging.getLogger(__name__)


def _get_training_logger() -> logging.Logger | Any:
    try:
        return get_run_logger()
    except Exception:
        return logger


def _normalize_training_label(value: object) -> str | None:
    if value is None:
        return None
    label = str(value)
    return label or None


def _ordered_active_labels(
    rows: list[dict[str, Any]], label_space: list[str]
) -> list[str]:
    active: set[str] = set()
    for row in rows:
        label = _normalize_training_label(row.get("label"))
        if not label:
            continue
        images_list: list[dict[str, Any]] = row.get("images") or []
        if not find_images_by_role(images_list, "patch_defective"):
            continue
        if not find_images_by_role(images_list, "patch_template"):
            continue
        active.add(label)
    ordered = [label for label in label_space if label in active]
    extras = sorted(active - set(ordered))
    return ordered + extras


def _collate_sc_tensor_batch(
    batch: list[dict[str, Any]],
    *,
    shape: tuple[int, int, int],
) -> tuple[Any, Any, Any]:
    torch: Any = importlib.import_module("torch")

    defective = torch.stack([item["defective"].reshape(shape) for item in batch])
    reference = torch.stack([item["reference"].reshape(shape) for item in batch])
    labels_tensor = torch.tensor([item["label"] for item in batch], dtype=torch.long)
    return defective, reference, labels_tensor


class ScTrainingDataset(Dataset[tuple[Any, Any, int]]):
    """PyTorch Dataset backed by a Polars LazyFrame of SC patch image samples.

    Collects the LazyFrame once in ``__init__``, filters to valid samples
    (must have defective + reference images and a label), and caches the
    filtered rows.  Image decoding and transforms are deferred to
    ``__getitem__`` so DataLoader ``num_workers>0`` can parallelise
    I/O and transformation.
    """

    def __init__(
        self,
        lf: Any,
        transform: Any,
        *,
        label_order: list[str],
    ) -> None:
        self._transform = transform

        df = lf.collect()

        valid_rows: list[dict[str, Any]] = []
        for row in df.iter_rows(named=True):
            images_list: list[dict[str, Any]] = row.get("images") or []
            defective_imgs = find_images_by_role(images_list, "patch_defective")
            reference_imgs = find_images_by_role(images_list, "patch_template")
            if not defective_imgs or not reference_imgs:
                continue

            label: str | None = row.get("label")
            if not label:
                continue

            valid_rows.append(row)

        self._rows = valid_rows

        self.labels = _ordered_active_labels(valid_rows, label_order)
        if len(self.labels) < 2:
            raise ValueError(
                f"need at least 2 active labels for training, got: {self.labels}"
            )
        self.label_to_idx: dict[str, int] = {
            label: idx for idx, label in enumerate(self.labels)
        }
        self._label_to_idx = self.label_to_idx
        self.num_classes: int = len(self.label_to_idx)

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, idx: int) -> tuple[Any, Any, int]:
        row = self._rows[idx]
        sample_id: str = row.get("sample_id", "unknown")
        images_list: list[dict[str, Any]] = row["images"]

        defective_imgs = find_images_by_role(images_list, "patch_defective")
        reference_imgs = find_images_by_role(images_list, "patch_template")

        if not defective_imgs or not reference_imgs:
            raise RuntimeError(f"Sample {sample_id}: missing image bytes")

        defective_bytes: bytes | None = cast(
            bytes | None, defective_imgs[0].get("bytes")
        )
        reference_bytes: bytes | None = cast(
            bytes | None, reference_imgs[0].get("bytes")
        )

        if not defective_bytes or not reference_bytes:
            raise RuntimeError(f"Sample {sample_id}: image bytes not available")

        def_img = Image.open(io.BytesIO(defective_bytes)).convert("RGB")
        ref_img = Image.open(io.BytesIO(reference_bytes)).convert("RGB")

        label: str | None = row.get("label")
        label_idx = self._label_to_idx.get(label, 0) if label else 0

        return (self._transform(def_img), self._transform(ref_img), label_idx)


@trainer(id="resnet50-sc-v1")
async def resnet_sc_train(
    ctx: TrainContext,
    *,
    artifact_storage: Any = None,
    materialized_dataset: Any,
    materialization_manifest: DataPlaneManifest,
    **kwargs: Any,
) -> TrainResult:
    logger = _get_training_logger()

    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader
    from torchvision import transforms
    import polars as pl

    torch: Any = importlib.import_module("torch")

    if artifact_storage is None:
        raise ValueError("artifact_storage is required for resnet50-sc-v1 training")

    missing_image_policy = str(kwargs.get("missing_image_policy") or "fail")
    skip_missing_images = missing_image_policy == "skip"

    lazyframe = sc_materialized_lazyframe(
        materialized_dataset,
        materialization_manifest,
    )
    rows = [dict(row) for row in lazyframe.collect().iter_rows(named=True)]
    for row in rows:
        row["label"] = _normalize_training_label(row.get("label"))

    skipped_sample_ids: set[str] = set()

    for row in rows:
        if not row.get("label"):
            continue
        images_list = row.get("images") or []
        missing_roles = [
            role
            for role in ("patch_template", "patch_defective")
            if not (
                (refs := find_images_by_role(images_list, role))
                and image_bytes_are_readable(refs[0].get("bytes"))
            )
        ]
        if not missing_roles:
            continue
        sample_id = str(row.get("sample_id", ""))
        if skip_missing_images:
            skipped_sample_ids.add(sample_id)
            continue
        raise ValueError(
            "SC training image validation failed for "
            f"sample_id={sample_id!r}: missing or unreadable roles={missing_roles}"
        )

    if skipped_sample_ids:
        logger.warning(
            "Skipping %d SC training samples with missing image bytes",
            len(skipped_sample_ids),
        )
        rows = [
            row
            for row in rows
            if str(row.get("sample_id", "")) not in skipped_sample_ids
        ]

    lazyframe = pl.DataFrame(rows, infer_schema_length=None).lazy()

    train_transform: Any = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )

    dataset = ScTrainingDataset(
        lf=lazyframe,
        transform=train_transform,
        label_order=list(ctx.dataset_ref.label_space),
    )

    if len(dataset) == 0:
        raise ValueError(
            "No annotated samples available for training — "
            "dataset has samples but none with valid labels. "
            "Annotate samples before training."
        )

    labels: list[str] = dataset.labels
    label_to_idx: dict[str, int] = dataset.label_to_idx
    num_classes: int = dataset.num_classes

    # ── Local materialization to parquet ──────────────────────────────
    import datasets as hf_datasets

    materialized_rows: list[dict[str, Any]] = []
    _tensor_shape: tuple[int, int, int] | None = None
    for i in range(len(dataset)):
        def_t, ref_t, lbl = dataset[i]
        if _tensor_shape is None and hasattr(def_t, "shape"):
            _tensor_shape = tuple(def_t.shape)  # pyright: ignore[reportUnknownMemberType]
        materialized_rows.append(
            {
                "defective": def_t.flatten().tolist(),
                "reference": ref_t.flatten().tolist(),
                "label": lbl,
            }
        )

    parquet_file = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    try:
        pl_df = pl.DataFrame(
            materialized_rows,
            schema={
                "defective": pl.List(pl.Float32),
                "reference": pl.List(pl.Float32),
                "label": pl.Int64,
            },
        )
        pl_df.write_parquet(parquet_file.name)
        parquet_file.close()

        hf_dataset = hf_datasets.load_dataset(
            "parquet", data_files=parquet_file.name, split="train"
        )
        hf_dataset = hf_dataset.with_format("torch")
    finally:
        try:
            os.unlink(parquet_file.name)
        except OSError:
            pass

    _shape = _tensor_shape or (3, 224, 224)

    dataloader = DataLoader(
        hf_dataset,  # type: ignore[arg-type]
        batch_size=4,
        shuffle=True,
        collate_fn=partial(_collate_sc_tensor_batch, shape=_shape),
        num_workers=2,
    )

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    class DualResNetClassifier(nn.Module):
        def __init__(self, num_classes: int) -> None:
            super().__init__()
            from torchvision import models

            backbone = models.resnet50(weights=None)
            self.backbone = nn.Sequential(*list(backbone.children())[:-1])
            self.classifier = nn.Sequential(
                nn.Linear(2048 * 3, 512),
                nn.ReLU(),
                nn.Dropout(0.3),
                nn.Linear(512, num_classes),
            )

        def forward(self, defective: Any, reference: Any) -> Any:
            feat_d = self.backbone(defective).flatten(1)
            feat_r = self.backbone(reference).flatten(1)
            diff = torch.abs(feat_d - feat_r)
            combined = torch.cat([feat_d, feat_r, diff], dim=1)
            return self.classifier(combined)

    model = DualResNetClassifier(num_classes=num_classes).to(device)

    criterion: nn.Module = nn.CrossEntropyLoss()
    optimizer: optim.Optimizer = optim.Adam(model.parameters(), lr=0.001)

    num_epochs = 3
    model.train()
    epoch_losses: list[float] = []
    for _epoch in range(num_epochs):
        running_loss = 0.0
        logger.info(
            "Training epoch %d/%d started — batches=%d",
            _epoch + 1,
            num_epochs,
            len(dataloader),
        )
        for batch_idx, (defective_images, reference_images, targets) in enumerate(
            dataloader
        ):
            defective_images = defective_images.to(device)
            reference_images = reference_images.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            outputs = model(defective_images, reference_images)
            loss = criterion(outputs, targets)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
            if batch_idx > 0 and batch_idx % 10 == 0:
                logger.info(
                    "Epoch %d batch %d/%d loss=%.4f",
                    _epoch + 1,
                    batch_idx,
                    len(dataloader),
                    loss.item(),
                )
        epoch_loss = running_loss / max(len(dataloader), 1)
        epoch_losses.append(epoch_loss)
        logger.info(
            "Epoch %d/%d completed loss=%.4f",
            _epoch + 1,
            num_epochs,
            epoch_loss,
        )

    final_loss = epoch_losses[-1] if epoch_losses else 0.0

    model.eval()
    correct = 0
    total = 0
    all_preds: list[int] = []
    all_targets: list[int] = []
    with torch.no_grad():
        for defective_images, reference_images, targets in dataloader:
            defective_images = defective_images.to(device)
            reference_images = reference_images.to(device)
            targets_device = targets.to(device)
            outputs = model(defective_images, reference_images)
            _, predicted = torch.max(outputs, 1)
            total += targets_device.size(0)
            correct += (predicted == targets_device).sum().item()
            all_preds.extend(predicted.cpu().tolist())
            all_targets.extend(targets.cpu().tolist())

    val_acc = correct / max(total, 1)

    per_class: dict[int, dict[str, int]] = {
        i: {"tp": 0, "fp": 0, "fn": 0} for i in range(num_classes)
    }
    for pred, target in zip(all_preds, all_targets):
        for c in range(num_classes):
            if pred == c and target == c:
                per_class[c]["tp"] += 1
            elif pred == c:
                per_class[c]["fp"] += 1
            elif target == c:
                per_class[c]["fn"] += 1
    f1_scores: list[float] = []
    for c in range(num_classes):
        tp = per_class[c]["tp"]
        if per_class[c]["fp"] > 0 or per_class[c]["fn"] > 0 or tp > 0:
            precision = (
                tp / (tp + per_class[c]["fp"]) if (tp + per_class[c]["fp"]) > 0 else 0.0
            )
            recall = (
                tp / (tp + per_class[c]["fn"]) if (tp + per_class[c]["fn"]) > 0 else 0.0
            )
            if precision + recall > 0:
                f1_scores.append(2 * precision * recall / (precision + recall))
    val_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

    checkpoint: dict[str, Any] = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "num_classes": num_classes,
        "labels": labels,
        "label_to_idx": label_to_idx,
        "architecture": "dual-resnet50",
        "framework": "pytorch",
        "created_at": datetime.now(UTC).isoformat(),
    }
    buf = io.BytesIO()
    torch.save(checkpoint, buf)
    buf.seek(0)

    checkpoint_object = f"models/{ctx.job_id}/checkpoint.pt"
    metrics_object = f"models/{ctx.job_id}/metrics.json"
    model_uri = await artifact_storage.put_bytes(
        object_name=checkpoint_object,
        data=buf.read(),
        content_type="application/octet-stream",
    )

    metrics_payload: dict[str, Any] = {
        "num_samples": len(dataset),
        "num_classes": num_classes,
        "epochs": num_epochs,
        "epoch_losses": epoch_losses,
        "final_loss": final_loss,
        "val/loss": final_loss,
        "val/acc": val_acc,
        "val/f1": val_f1,
        "architecture": "dual-resnet50",
    }
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
            "runtime": "resnet50-sc-cpu",
            "framework": "pytorch",
            "architecture": "dual-resnet50",
            "trained_samples": len(dataset),
            "label_space": labels,
            "label_to_idx": label_to_idx,
        },
    )
