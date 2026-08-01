from __future__ import annotations

# pyright: reportPrivateImportUsage=false

import csv
import io
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image
import torch
from ultralytics import YOLO

from ml_library.models import (
    Prediction,
    PredictionSample,
    TrainingOutput,
    TrainingSample,
)
from ml_library.device import select_torch_device, select_ultralytics_device


def _active_labels(
    samples: Sequence[TrainingSample],
    label_space: Sequence[str],
) -> list[str]:
    active = {sample.label for sample in samples if sample.label}
    ordered = [label for label in label_space if label in active]
    return ordered + sorted(active - set(ordered))


def _combined_image(sample: TrainingSample | PredictionSample) -> Image.Image:
    defective = Image.open(io.BytesIO(sample.defective_image or b"")).convert("RGB")
    reference = Image.open(io.BytesIO(sample.reference_image or b"")).convert("RGB")
    combined = Image.new("RGB", (defective.width, defective.height * 2))
    combined.paste(defective, (0, 0))
    combined.paste(reference, (0, defective.height))
    return combined.resize((224, 224), Image.Resampling.LANCZOS)


def train_yolo(
    samples: Sequence[TrainingSample],
    label_space: Sequence[str],
    *,
    epochs: int = 3,
) -> TrainingOutput:
    labels = _active_labels(samples, label_space)
    if len(labels) < 2:
        raise ValueError(f"need at least 2 active labels for training, got: {labels}")
    label_to_index = {label: index for index, label in enumerate(labels)}

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        train_root = root / "train"
        for label in labels:
            (train_root / str(label_to_index[label])).mkdir(parents=True)
        for sample in samples:
            if sample.label not in label_to_index:
                continue
            image_path = (
                train_root
                / str(label_to_index[sample.label])
                / f"{sample.sample_id}.jpg"
            )
            _combined_image(sample).save(image_path, "JPEG")
        if not samples:
            raise ValueError("no valid defective images with labels found")

        run_root = root / "runs"
        model = YOLO("yolov8n-cls.pt")
        model.train(
            data=str(root),
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
        metrics: dict[str, object] = {
            "num_samples": len(samples),
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
            checkpoint=checkpoint_path.read_bytes(),
            metrics=metrics,
            metadata={
                "runtime": "yolo-sc-v1",
                "framework": "ultralytics",
                "architecture": "yolov8n-cls",
                "trained_samples": len(samples),
                "label_space": labels,
                "label_to_idx": label_to_index,
            },
        )


def predict_yolo(
    checkpoint_bytes: bytes,
    label_space: Sequence[str],
    samples: Iterable[PredictionSample],
    *,
    batch_size: int = 16,
) -> Iterable[Prediction]:
    labels = [str(label) for label in label_space]
    if not labels:
        raise ValueError("YOLO model metadata must include compact label_space")
    with tempfile.TemporaryDirectory() as temporary_directory:
        checkpoint_path = Path(temporary_directory) / "model.pt"
        checkpoint_path.write_bytes(checkpoint_bytes)
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
