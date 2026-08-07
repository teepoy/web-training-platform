from __future__ import annotations

# pyright: reportPrivateImportUsage=false

import io
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image
import torch
import torch.nn.functional as functional
from torch import nn, optim
from torch.utils.data import DataLoader, IterableDataset
from torchvision import models, transforms

from ml_library.models import (
    Prediction,
    PredictionSample,
    TrainingOutput,
)
from ml_library.data_loading.sc import ScTrainingDataset
from ml_library.device import select_torch_device


class DualResNetClassifier(nn.Module):
    def __init__(self, num_classes: int) -> None:
        super().__init__()
        backbone = models.resnet50(weights=None)
        self.backbone = nn.Sequential(*list(backbone.children())[:-1])
        self.classifier = nn.Sequential(
            nn.Linear(2048 * 3, 512),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(512, num_classes),
        )

    def forward(self, defective: Any, reference: Any) -> Any:
        defective_features = self.backbone(defective).flatten(1)
        reference_features = self.backbone(reference).flatten(1)
        difference = torch.abs(defective_features - reference_features)
        combined = torch.cat(
            [defective_features, reference_features, difference],
            dim=1,
        )
        return self.classifier(combined)


class _TrainingDataset(IterableDataset[tuple[Any, Any, int]]):
    def __init__(
        self,
        samples: ScTrainingDataset,
        *,
        label_to_index: dict[str, int],
    ) -> None:
        self._samples = samples
        self._label_to_index = label_to_index
        self._transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    def __len__(self) -> int:
        return len(self._samples)

    def __iter__(self) -> Iterator[tuple[Any, Any, int]]:
        for sample in self._samples:
            defective = Image.open(io.BytesIO(sample.defective_image)).convert("RGB")
            reference = Image.open(io.BytesIO(sample.reference_image)).convert("RGB")
            yield (
                self._transform(defective),
                self._transform(reference),
                self._label_to_index[sample.label],
            )


def train_resnet(
    samples: ScTrainingDataset,
    label_space: Sequence[str],
    *,
    work_dir: Path,
    epochs: int = 3,
    batch_size: int = 4,
) -> TrainingOutput:
    summary = samples.inspect(label_space)
    labels = list(summary.active_labels)
    if len(labels) < 2:
        raise ValueError(f"need at least 2 active labels for training, got: {labels}")
    if summary.valid_samples == 0:
        raise ValueError("No annotated samples available for training")

    label_to_index = {label: index for index, label in enumerate(labels)}
    dataset = _TrainingDataset(samples, label_to_index=label_to_index)
    device = select_torch_device(torch)
    model = DualResNetClassifier(num_classes=len(labels)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    epoch_losses: list[float] = []
    model.train()
    for epoch in range(epochs):
        samples.set_epoch(epoch)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
        running_loss = 0.0
        batch_count = 0
        for defective, reference, targets in dataloader:
            defective = defective.to(device)
            reference = reference.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            output = model(defective, reference)
            loss = criterion(output, targets)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item())
            batch_count += 1
        epoch_losses.append(running_loss / max(batch_count, 1))

    model.eval()
    correct = 0
    total = 0
    predictions: list[int] = []
    targets_seen: list[int] = []
    samples.set_epoch(epochs)
    validation_loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    with torch.no_grad():
        for defective, reference, targets in validation_loader:
            output = model(defective.to(device), reference.to(device))
            predicted = torch.max(output, 1).indices
            targets_device = targets.to(device)
            total += int(targets_device.size(0))
            correct += int((predicted == targets_device).sum().item())
            predictions.extend(int(value) for value in predicted.cpu().tolist())
            targets_seen.extend(int(value) for value in targets.tolist())

    f1_scores: list[float] = []
    for class_index in range(len(labels)):
        true_positive = sum(
            prediction == class_index and target == class_index
            for prediction, target in zip(predictions, targets_seen)
        )
        false_positive = sum(
            prediction == class_index and target != class_index
            for prediction, target in zip(predictions, targets_seen)
        )
        false_negative = sum(
            prediction != class_index and target == class_index
            for prediction, target in zip(predictions, targets_seen)
        )
        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        precision = (
            true_positive / precision_denominator if precision_denominator else 0.0
        )
        recall = true_positive / recall_denominator if recall_denominator else 0.0
        if precision + recall:
            f1_scores.append(2 * precision * recall / (precision + recall))

    checkpoint = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "num_classes": len(labels),
        "labels": labels,
        "label_to_idx": label_to_index,
        "architecture": "dual-resnet50",
        "framework": "pytorch",
        "created_at": datetime.now(UTC).isoformat(),
    }
    work_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = work_dir / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)
    final_loss = epoch_losses[-1] if epoch_losses else 0.0
    metrics: dict[str, object] = {
        "num_samples": summary.valid_samples,
        "num_classes": len(labels),
        "epochs": epochs,
        "epoch_losses": epoch_losses,
        "final_loss": final_loss,
        "val/loss": final_loss,
        "val/acc": correct / max(total, 1),
        "val/f1": sum(f1_scores) / len(f1_scores) if f1_scores else 0.0,
        "architecture": "dual-resnet50",
    }
    return TrainingOutput(
        checkpoint_path=checkpoint_path,
        metrics=metrics,
        metadata={
            "runtime": "resnet50-sc-v1",
            "framework": "pytorch",
            "architecture": "dual-resnet50",
            "trained_samples": summary.valid_samples,
            "label_space": labels,
            "label_to_idx": label_to_index,
        },
    )


def predict_resnet(
    checkpoint_path: Path,
    samples: Iterable[PredictionSample],
    *,
    batch_size: int = 16,
) -> Iterable[Prediction]:
    device = select_torch_device(torch)
    checkpoint = torch.load(
        checkpoint_path,
        map_location=device,
        weights_only=False,
    )
    labels = [str(label) for label in checkpoint.get("labels", [])]
    if not labels:
        raise ValueError("checkpoint has no labels — cannot create classifier")
    model = DualResNetClassifier(int(checkpoint.get("num_classes", len(labels))))
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device)
    model.eval()
    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
    )

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
            yield from _predict_resnet_batch(model, transform, device, labels, pending)
            pending = []
    if pending:
        yield from _predict_resnet_batch(model, transform, device, labels, pending)


def _predict_resnet_batch(
    model: Any,
    transform: Any,
    device: Any,
    labels: Sequence[str],
    samples: Sequence[PredictionSample],
) -> Iterable[Prediction]:
    defective_tensors = []
    reference_tensors = []
    for sample in samples:
        defective = Image.open(io.BytesIO(sample.defective_image or b"")).convert("RGB")
        reference = Image.open(io.BytesIO(sample.reference_image or b"")).convert("RGB")
        defective_tensors.append(transform(defective))
        reference_tensors.append(transform(reference))
    with torch.no_grad():
        output = model(
            torch.stack(defective_tensors).to(device),
            torch.stack(reference_tensors).to(device),
        )
        probabilities = functional.softmax(output, dim=1)
    for index, sample in enumerate(samples):
        scores = {
            label: float(probabilities[index][label_index].item())
            for label_index, label in enumerate(labels)
        }
        best_index = int(torch.argmax(probabilities[index]).item())
        yield Prediction(
            sample_id=sample.sample_id,
            label=labels[best_index],
            confidence=float(probabilities[index][best_index].item()),
            scores=scores,
        )
