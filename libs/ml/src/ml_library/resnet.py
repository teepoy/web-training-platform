from __future__ import annotations

# pyright: reportPrivateImportUsage=false

import io
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from PIL import Image
import torch
import torch.nn.functional as functional
from torch import nn, optim
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

from ml_library.models import (
    Prediction,
    PredictionSample,
    TrainingOutput,
    TrainingSample,
)
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


class _TrainingDataset(Dataset[tuple[Any, Any, int]]):
    def __init__(
        self,
        samples: Sequence[TrainingSample],
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

    def __getitem__(self, index: int) -> tuple[Any, Any, int]:
        sample = self._samples[index]
        defective = Image.open(io.BytesIO(sample.defective_image)).convert("RGB")
        reference = Image.open(io.BytesIO(sample.reference_image)).convert("RGB")
        return (
            self._transform(defective),
            self._transform(reference),
            self._label_to_index[sample.label],
        )


def _active_labels(
    samples: Sequence[TrainingSample],
    label_space: Sequence[str],
) -> list[str]:
    active = {sample.label for sample in samples if sample.label}
    ordered = [label for label in label_space if label in active]
    return ordered + sorted(active - set(ordered))


def train_resnet(
    samples: Sequence[TrainingSample],
    label_space: Sequence[str],
    *,
    epochs: int = 3,
    batch_size: int = 4,
) -> TrainingOutput:
    labels = _active_labels(samples, label_space)
    if len(labels) < 2:
        raise ValueError(f"need at least 2 active labels for training, got: {labels}")
    if not samples:
        raise ValueError("No annotated samples available for training")

    label_to_index = {label: index for index, label in enumerate(labels)}
    dataset = _TrainingDataset(samples, label_to_index=label_to_index)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    device = select_torch_device(torch)
    model = DualResNetClassifier(num_classes=len(labels)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    epoch_losses: list[float] = []
    model.train()
    for _ in range(epochs):
        running_loss = 0.0
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
        epoch_losses.append(running_loss / max(len(dataloader), 1))

    model.eval()
    correct = 0
    total = 0
    predictions: list[int] = []
    targets_seen: list[int] = []
    with torch.no_grad():
        for defective, reference, targets in dataloader:
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
    checkpoint_buffer = io.BytesIO()
    torch.save(checkpoint, checkpoint_buffer)
    final_loss = epoch_losses[-1] if epoch_losses else 0.0
    metrics: dict[str, object] = {
        "num_samples": len(dataset),
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
        checkpoint=checkpoint_buffer.getvalue(),
        metrics=metrics,
        metadata={
            "runtime": "resnet50-sc-v1",
            "framework": "pytorch",
            "architecture": "dual-resnet50",
            "trained_samples": len(dataset),
            "label_space": labels,
            "label_to_idx": label_to_index,
        },
    )


def predict_resnet(
    checkpoint_bytes: bytes,
    samples: Iterable[PredictionSample],
    *,
    batch_size: int = 16,
) -> Iterable[Prediction]:
    device = select_torch_device(torch)
    checkpoint = torch.load(
        io.BytesIO(checkpoint_bytes),
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
