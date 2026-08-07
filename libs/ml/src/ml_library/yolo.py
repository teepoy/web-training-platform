from __future__ import annotations

# pyright: reportPrivateImportUsage=false

import csv
import hashlib
import io
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image
import torch

from ml_library.models import (
    Prediction,
    PredictionSample,
    TrainingOutput,
    TrainingSample,
)
from ml_library.data_loading.sc import ScTrainingDataset
from ml_library.device import select_torch_device, select_ultralytics_device


def _combined_image(sample: TrainingSample | PredictionSample) -> Image.Image:
    defective = Image.open(io.BytesIO(sample.defective_image or b"")).convert("RGB")
    reference = Image.open(io.BytesIO(sample.reference_image or b"")).convert("RGB")
    combined = Image.new("RGB", (defective.width, defective.height * 2))
    combined.paste(defective, (0, 0))
    combined.paste(reference, (0, defective.height))
    return combined.resize((224, 224), Image.Resampling.LANCZOS)


def train_yolo(
    samples: ScTrainingDataset,
    label_space: Sequence[str],
    *,
    work_dir: Path,
    epochs: int = 3,
) -> TrainingOutput:
    from ultralytics import YOLO

    summary = samples.inspect(label_space)
    labels = list(summary.active_labels)
    if len(labels) < 2:
        raise ValueError(f"need at least 2 active labels for training, got: {labels}")

    work_dir.mkdir(parents=True, exist_ok=True)
    dataset_root = work_dir / "ultralytics-data"
    staging_root = dataset_root / "staging"
    staging_root.mkdir(parents=True)
    staged_by_label: dict[str, Path] = {}
    trained_samples = 0
    for index, sample in enumerate(samples):
        label_root = staged_by_label.get(sample.label)
        if label_root is None:
            label_token = hashlib.sha256(sample.label.encode("utf-8")).hexdigest()
            label_root = staging_root / label_token
            label_root.mkdir()
            staged_by_label[sample.label] = label_root
        sample_token = hashlib.sha256(sample.sample_id.encode("utf-8")).hexdigest()[:16]
        image_path = label_root / f"{index:012d}-{sample_token}.jpg"
        _combined_image(sample).save(image_path, "JPEG")
        trained_samples += 1
    if trained_samples == 0:
        raise ValueError("no valid defective images with labels found")

    train_root = dataset_root / "train"
    train_root.mkdir()
    label_to_index = {label: index for index, label in enumerate(labels)}
    for label, index in label_to_index.items():
        staged_by_label[label].rename(train_root / f"{index:06d}")
    staging_root.rmdir()

    run_root = work_dir / "runs"
    model = YOLO("yolov8n-cls.pt")
    model.train(
        data=str(dataset_root),
        epochs=epochs,
        imgsz=224,
        device=select_ultralytics_device(torch),
        project=str(run_root),
        name="train",
        exist_ok=True,
    )
    checkpoint_path = run_root / "train" / "weights" / "best.pt"
    if not checkpoint_path.exists():
        checkpoint_path = run_root / "train" / "weights" / "last.pt"
    if not checkpoint_path.exists():
        raise FileNotFoundError("Ultralytics training did not produce a checkpoint")
    metrics: dict[str, object] = {
        "num_samples": trained_samples,
        "num_classes": len(labels),
        "epochs": epochs,
        "architecture": "yolov8n-cls",
        "framework": "ultralytics",
    }
    results_csv = run_root / "train" / "results.csv"
    if results_csv.exists():
        with results_csv.open(newline="") as results_file:
            rows = list(csv.DictReader(results_file))
        if rows:
            for key, value in rows[-1].items():
                normalized_key = key.strip()
                try:
                    metrics[normalized_key] = float(value)
                except (TypeError, ValueError):
                    metrics[normalized_key] = value
    return TrainingOutput(
        checkpoint_path=checkpoint_path,
        metrics=metrics,
        metadata={
            "runtime": "yolo-sc-v1",
            "framework": "ultralytics",
            "architecture": "yolov8n-cls",
            "trained_samples": trained_samples,
            "label_space": labels,
            "label_to_idx": label_to_index,
        },
    )


def predict_yolo(
    checkpoint_path: Path,
    label_space: Sequence[str],
    samples: Iterable[PredictionSample],
    *,
    batch_size: int = 16,
) -> Iterable[Prediction]:
    from ultralytics import YOLO

    labels = [str(label) for label in label_space]
    if not labels:
        raise ValueError("YOLO model metadata must include compact label_space")
    model = YOLO(str(checkpoint_path))
    model.to(select_torch_device(torch))

    pending: list[PredictionSample] = []
    for sample in samples:
        if sample.defective_image is None or sample.reference_image is None:
            yield Prediction(
                sample_id=sample.sample_id,
                label="",
                confidence=None,
                error="missing materialized image bytes",
            )
            continue
        pending.append(sample)
        if len(pending) == batch_size:
            yield from _predict_yolo_batch(model, labels, pending)
            pending = []
    if pending:
        yield from _predict_yolo_batch(model, labels, pending)


def _predict_yolo_batch(
    model: Any,
    labels: Sequence[str],
    samples: Sequence[PredictionSample],
) -> Iterable[Prediction]:
    results = model([_combined_image(sample) for sample in samples])
    for index, sample in enumerate(samples):
        probabilities = results[index].probs
        if probabilities is None:
            yield Prediction(
                sample_id=sample.sample_id,
                label="",
                confidence=None,
                error="no classification output",
            )
            continue
        output_classes = int(probabilities.data.shape[0])
        if output_classes != len(labels):
            raise ValueError(
                "YOLO prediction output class count does not match model metadata "
                f"label_space: output={output_classes} labels={len(labels)}"
            )
        scores = {
            label: float(probabilities.data[label_index].item())
            for label_index, label in enumerate(labels)
        }
        best_index = int(probabilities.top1)
        yield Prediction(
            sample_id=sample.sample_id,
            label=labels[best_index],
            confidence=float(probabilities.top1conf.item()),
            scores=scores,
        )
