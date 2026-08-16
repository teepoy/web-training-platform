"""Ultralytics SC classifier with paired grayscale images."""

from __future__ import annotations

import io
import asyncio
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path
from typing import Any, cast

from PIL import Image
import torch
from torch import Tensor, nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, IterableDataset

from ml_library.data_loading._parquet import ParquetPaths
from ml_library.data_loading.streaming import stream_parquet_dataset
from ml_library.device import select_torch_device
from ml_library.models import Prediction, TrainingOutput

YOLO_TRAIN_EPOCHS = 50
YOLO_TRAIN_BATCH_SIZE = 16
YOLO_PREDICTION_BATCH_SIZE = 256
YOLO_IMAGE_SIZE = 128
YOLO_DATALOADER_WORKERS = 4
YOLO_INPUT_CHANNELS = 2
YOLO_PREDICTION_PREPROCESS_TASK_SIZE = 64
YOLO_PREDICTION_PREFETCH_TASKS = 8

_TRAINING_COLUMNS = (
    "sample_id",
    "label",
    "patch_defective_bytes",
    "patch_template_bytes",
)
_PREDICTION_COLUMNS = (
    "sample_id",
    "patch_defective_bytes",
    "patch_template_bytes",
)


class _ScYoloTrainingDataset(IterableDataset[dict[str, Tensor]]):
    def __init__(
        self,
        parquet_paths: ParquetPaths,
        label_to_index: dict[str, int],
        *,
        image_size: int,
        shuffle_seed: int,
        shuffle_buffer_rows: int,
    ) -> None:
        super().__init__()
        self._rows = stream_parquet_dataset(
            parquet_paths,
            columns=_TRAINING_COLUMNS,
            shuffle=True,
            seed=shuffle_seed,
            shuffle_buffer_rows=shuffle_buffer_rows,
        )
        self._label_to_index = label_to_index
        self._image_size = image_size

    def __len__(self) -> int:
        return len(self._rows)

    def set_epoch(self, epoch: int) -> None:
        self._rows.set_epoch(epoch)

    def __iter__(self) -> Iterator[dict[str, Tensor]]:
        for row in self._rows:
            label = str(row.get("label") or "").strip()
            class_index = self._label_to_index.get(label)
            if class_index is None:
                continue
            yield {
                "img": _preprocess_grayscale_pair(row, self._image_size),
                "cls": torch.tensor(class_index, dtype=torch.long),
            }


class _ScYoloPredictionDataset(IterableDataset[dict[str, object]]):
    def __init__(
        self,
        parquet_paths: ParquetPaths,
        *,
        image_size: int,
    ) -> None:
        super().__init__()
        self._rows = stream_parquet_dataset(
            parquet_paths,
            columns=_PREDICTION_COLUMNS,
            shuffle=False,
            seed=0,
            shuffle_buffer_rows=1,
        )
        self._image_size = image_size

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[dict[str, object]]:
        for row in self._rows:
            sample_id = str(row.get("sample_id") or "")
            try:
                image = _preprocess_grayscale_pair(row, self._image_size)
            except (OSError, TypeError, ValueError) as exc:
                yield {
                    "sample_id": sample_id,
                    "image": None,
                    "error": f"image preprocessing failed: {exc}",
                }
                continue
            yield {"sample_id": sample_id, "image": image, "error": None}


def _preprocess_grayscale_pair(row: dict[str, Any], image_size: int) -> Tensor:
    defective = _decode_grayscale(
        row.get("patch_defective_bytes"),
        role="patch_defective",
        image_size=image_size,
    )
    reference = _decode_grayscale(
        row.get("patch_template_bytes"),
        role="patch_template",
        image_size=image_size,
    )
    return torch.cat((defective, reference), dim=0)


def _decode_grayscale(value: object, *, role: str, image_size: int) -> Tensor:
    image_bytes = _optional_bytes(value)
    if not image_bytes:
        raise ValueError(f"missing {role} image bytes")
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("L").resize(
            (image_size, image_size),
            Image.Resampling.BILINEAR,
        )
        pixels = torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8)
    tensor = pixels.reshape(1, image_size, image_size).to(dtype=torch.float32)
    return tensor.div_(255.0).sub_(0.5).div_(0.5)


def _optional_bytes(value: object) -> bytes | None:
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, bytearray):
        return bytes(value)
    return value if isinstance(value, bytes) else None


def inspect_yolo_training_samples(
    parquet_paths: ParquetPaths,
    label_space: Sequence[str],
) -> tuple[tuple[str, ...], int, int]:
    """Return active labels, valid sample count, and unreadable sample count."""

    rows = stream_parquet_dataset(
        parquet_paths,
        columns=_TRAINING_COLUMNS,
        shuffle=False,
        seed=0,
        shuffle_buffer_rows=1,
    )
    active: set[str] = set()
    valid_samples = 0
    unreadable_samples = 0
    for row in rows:
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        try:
            _verify_image(row.get("patch_defective_bytes"))
            _verify_image(row.get("patch_template_bytes"))
        except (OSError, TypeError, ValueError):
            unreadable_samples += 1
            continue
        active.add(label)
        valid_samples += 1
    declared = [label for label in label_space if label in active]
    labels = tuple(declared + sorted(active - set(declared)))
    return labels, valid_samples, unreadable_samples


def _verify_image(value: object) -> None:
    image_bytes = _optional_bytes(value)
    if not image_bytes:
        raise ValueError("missing image bytes")
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.verify()


def _build_yolo_classifier(num_classes: int) -> nn.Module:
    from ultralytics.nn.tasks import ClassificationModel

    return ClassificationModel(
        "yolov8n-cls.yaml",
        ch=YOLO_INPUT_CHANNELS,
        nc=num_classes,
        verbose=False,
    )


async def train_yolo(
    parquet_paths: ParquetPaths,
    label_space: Sequence[str],
    *,
    valid_samples: int,
    work_dir: Path,
    shuffle_seed: int,
    shuffle_buffer_rows: int,
    epochs: int = YOLO_TRAIN_EPOCHS,
    batch_size: int = YOLO_TRAIN_BATCH_SIZE,
    image_size: int = YOLO_IMAGE_SIZE,
    workers: int = YOLO_DATALOADER_WORKERS,
    on_epoch: Callable[[int, int, float, float], Awaitable[None]] | None = None,
) -> TrainingOutput:
    labels = list(label_space)
    if len(labels) < 2:
        raise ValueError(f"need at least 2 active labels for training, got: {labels}")
    if valid_samples == 0:
        raise ValueError("no valid paired images with labels found")
    _validate_loader_options(
        batch_size=batch_size,
        image_size=image_size,
        workers=workers,
    )

    work_dir.mkdir(parents=True, exist_ok=True)
    label_to_index = {label: index for index, label in enumerate(labels)}
    dataset = _ScYoloTrainingDataset(
        parquet_paths,
        label_to_index,
        image_size=image_size,
        shuffle_seed=shuffle_seed,
        shuffle_buffer_rows=shuffle_buffer_rows,
    )
    device = select_torch_device(torch)
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
        persistent_workers=False,
        prefetch_factor=2 if workers else None,
        pin_memory=device.type == "cuda",
    )
    torch.manual_seed(shuffle_seed)
    model = _build_yolo_classifier(len(labels)).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=1e-3,
        weight_decay=5e-4,
    )

    final_loss = 0.0
    final_accuracy = 0.0
    for epoch in range(epochs):
        dataset.set_epoch(epoch)
        model.train()
        total_loss = 0.0
        correct = 0
        seen = 0
        for raw_batch in loader:
            batch = cast(dict[str, Tensor], raw_batch)
            images = batch["img"].to(device, non_blocking=device.type == "cuda")
            targets = batch["cls"].to(device, non_blocking=device.type == "cuda")
            optimizer.zero_grad(set_to_none=True)
            logits = _classification_logits(model(images))
            loss = F.cross_entropy(logits, targets)
            loss.backward()
            optimizer.step()
            sample_count = int(targets.shape[0])
            total_loss += float(loss.detach().item()) * sample_count
            correct += int((logits.argmax(dim=1) == targets).sum().item())
            seen += sample_count
        if seen != valid_samples:
            raise RuntimeError(
                "SC training sample count changed between inspection and DataLoader: "
                f"inspected={valid_samples} loaded={seen} epoch={epoch}"
            )
        final_loss = total_loss / seen
        final_accuracy = correct / seen
        if on_epoch is not None:
            await on_epoch(epoch + 1, epochs, final_loss, final_accuracy)

    checkpoint_path = work_dir / "checkpoint.pt"
    torch.save(
        {
            "model_state_dict": {
                name: parameter.detach().cpu()
                for name, parameter in model.state_dict().items()
            },
            "architecture": "yolov8n-cls",
            "label_space": labels,
            "num_classes": len(labels),
            "input_channels": YOLO_INPUT_CHANNELS,
            "image_size": image_size,
            "training_seed": shuffle_seed,
        },
        checkpoint_path,
    )
    metrics: dict[str, object] = {
        "num_samples": valid_samples,
        "num_classes": len(labels),
        "epochs": epochs,
        "batch_size": batch_size,
        "image_size": image_size,
        "loss": final_loss,
        "accuracy": final_accuracy,
        "architecture": "yolov8n-cls",
        "framework": "ultralytics",
    }
    return TrainingOutput(
        checkpoint_path=checkpoint_path,
        metrics=metrics,
        metadata={
            "runtime": "yolo-sc-v1",
            "framework": "ultralytics",
            "architecture": "yolov8n-cls",
            "trained_samples": valid_samples,
            "label_space": labels,
            "label_to_idx": label_to_index,
            "input_channels": YOLO_INPUT_CHANNELS,
            "image_roles": ["patch_defective", "patch_template"],
            "image_size": image_size,
            "training_seed": shuffle_seed,
        },
    )


def predict_yolo(
    checkpoint_path: Path,
    label_space: Sequence[str],
    parquet_paths: ParquetPaths,
    *,
    batch_size: int = YOLO_PREDICTION_BATCH_SIZE,
    image_size: int = YOLO_IMAGE_SIZE,
    workers: int = YOLO_DATALOADER_WORKERS,
) -> Iterator[Prediction]:
    labels = [str(label) for label in label_space]
    if not labels:
        raise ValueError("YOLO model metadata must include compact label_space")
    _validate_loader_options(
        batch_size=batch_size,
        image_size=image_size,
        workers=workers,
    )
    device = select_torch_device(torch)
    model = _load_yolo_classifier(
        checkpoint_path,
        labels,
        image_size=image_size,
        device=device,
    )
    dataset = _ScYoloPredictionDataset(parquet_paths, image_size=image_size)
    loader = DataLoader(
        dataset,
        batch_size=None,
        shuffle=False,
        num_workers=workers,
        persistent_workers=False,
        prefetch_factor=2 if workers else None,
        pin_memory=device.type == "cuda",
    )

    model.eval()
    with torch.inference_mode():
        pending: list[dict[str, object]] = []
        for raw_sample in loader:
            pending.append(cast(dict[str, object], raw_sample))
            if len(pending) == batch_size:
                yield from _predict_preprocessed_batch(
                    model,
                    labels,
                    pending,
                    device=device,
                )
                pending = []
        if pending:
            yield from _predict_preprocessed_batch(
                model,
                labels,
                pending,
                device=device,
            )


async def predict_yolo_stream(
    checkpoint_path: Path,
    label_space: Sequence[str],
    samples: AsyncIterator[dict[str, object]],
    *,
    batch_size: int = YOLO_PREDICTION_BATCH_SIZE,
    image_size: int = YOLO_IMAGE_SIZE,
    workers: int = YOLO_DATALOADER_WORKERS,
    preprocess_task_size: int = YOLO_PREDICTION_PREPROCESS_TASK_SIZE,
    prefetch_tasks: int = YOLO_PREDICTION_PREFETCH_TASKS,
) -> AsyncIterator[Prediction]:
    """Predict a bounded async stream without materializing image Parquet.

    At most ``prefetch_tasks`` process-pool tasks, each containing at most
    ``preprocess_task_size`` samples, are in flight.  The pool always uses the
    ``spawn`` context so Torch state is not inherited through ``fork``.
    """

    labels = [str(label) for label in label_space]
    if not labels:
        raise ValueError("YOLO model metadata must include compact label_space")
    _validate_loader_options(
        batch_size=batch_size,
        image_size=image_size,
        workers=workers,
    )
    if preprocess_task_size <= 0:
        raise ValueError("preprocess_task_size must be greater than zero")
    if prefetch_tasks <= 0:
        raise ValueError("prefetch_tasks must be greater than zero")

    device = select_torch_device(torch)
    model = _load_yolo_classifier(
        checkpoint_path,
        labels,
        image_size=image_size,
        device=device,
    )
    model.eval()
    pending_batch: list[dict[str, object]] = []
    with torch.inference_mode():
        async for sample in _preprocess_prediction_stream(
            samples,
            image_size=image_size,
            workers=workers,
            task_size=preprocess_task_size,
            prefetch_tasks=prefetch_tasks,
        ):
            pending_batch.append(sample)
            if len(pending_batch) == batch_size:
                for prediction in _predict_preprocessed_batch(
                    model,
                    labels,
                    pending_batch,
                    device=device,
                ):
                    yield prediction
                pending_batch = []
        if pending_batch:
            for prediction in _predict_preprocessed_batch(
                model,
                labels,
                pending_batch,
                device=device,
            ):
                yield prediction


async def _preprocess_prediction_stream(
    samples: AsyncIterator[dict[str, object]],
    *,
    image_size: int,
    workers: int,
    task_size: int,
    prefetch_tasks: int,
) -> AsyncIterator[dict[str, object]]:
    if workers == 0:
        task: list[dict[str, object]] = []
        async for sample in samples:
            task.append(sample)
            if len(task) == task_size:
                for item in _preprocess_prediction_task(task, image_size):
                    yield item
                task = []
        if task:
            for item in _preprocess_prediction_task(task, image_size):
                yield item
        return

    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
    )
    pending: deque[asyncio.Future[list[dict[str, object]]]] = deque()

    async def drain_one() -> AsyncIterator[dict[str, object]]:
        completed = await pending.popleft()
        for item in completed:
            yield item

    try:
        task = []
        async for sample in samples:
            task.append(sample)
            if len(task) < task_size:
                continue
            pending.append(
                loop.run_in_executor(
                    executor,
                    _preprocess_prediction_task,
                    task,
                    image_size,
                )
            )
            task = []
            if len(pending) >= prefetch_tasks:
                async for item in drain_one():
                    yield item
        if task:
            pending.append(
                loop.run_in_executor(
                    executor,
                    _preprocess_prediction_task,
                    task,
                    image_size,
                )
            )
        while pending:
            async for item in drain_one():
                yield item
    finally:
        for future in pending:
            future.cancel()
        await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)


def _preprocess_prediction_task(
    rows: list[dict[str, object]],
    image_size: int,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        sample_id = str(row.get("sample_id") or "")
        source_error = row.get("error")
        if isinstance(source_error, str) and source_error:
            output.append(
                {"sample_id": sample_id, "image": None, "error": source_error}
            )
            continue
        try:
            image = _preprocess_grayscale_pair(row, image_size)
        except (OSError, TypeError, ValueError) as exc:
            output.append(
                {
                    "sample_id": sample_id,
                    "image": None,
                    "error": f"image preprocessing failed: {exc}",
                }
            )
            continue
        output.append({"sample_id": sample_id, "image": image, "error": None})
    return output


def _load_yolo_classifier(
    checkpoint_path: Path,
    labels: Sequence[str],
    *,
    image_size: int,
    device: Any,
) -> nn.Module:
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if not isinstance(checkpoint, dict):
        raise ValueError("YOLO checkpoint must contain a mapping")
    if checkpoint.get("architecture") != "yolov8n-cls":
        raise ValueError("YOLO checkpoint architecture must be yolov8n-cls")
    if checkpoint.get("input_channels") != YOLO_INPUT_CHANNELS:
        raise ValueError(
            f"YOLO checkpoint must use {YOLO_INPUT_CHANNELS} grayscale channels"
        )
    if checkpoint.get("image_size") != image_size:
        raise ValueError(
            "YOLO checkpoint image size does not match prediction image size: "
            f"checkpoint={checkpoint.get('image_size')} prediction={image_size}"
        )
    checkpoint_labels = checkpoint.get("label_space")
    if checkpoint_labels != list(labels):
        raise ValueError("YOLO checkpoint label_space does not match model metadata")
    state_dict = checkpoint.get("model_state_dict")
    if not isinstance(state_dict, dict):
        raise ValueError("YOLO checkpoint is missing model_state_dict")
    model = _build_yolo_classifier(len(labels))
    model.load_state_dict(state_dict)
    return model.to(device)


def _classification_logits(output: object) -> Tensor:
    if isinstance(output, tuple):
        output = output[-1]
    if not isinstance(output, Tensor):
        raise TypeError("YOLO classifier must return a tensor or tensor tuple")
    return output


def _predict_preprocessed_batch(
    model: nn.Module,
    labels: Sequence[str],
    samples: list[dict[str, object]],
    *,
    device: Any,
) -> Iterator[Prediction]:
    batch = _collate_prediction_samples(samples)
    sample_ids = cast(list[str], batch["sample_ids"])
    errors = cast(list[str | None], batch["errors"])
    valid_positions = cast(list[int], batch["valid_positions"])
    images = cast(Tensor, batch["images"])
    predictions: dict[int, Prediction] = {}
    if valid_positions:
        probabilities = _classification_logits(
            model(
                images.to(
                    device,
                    non_blocking=device.type == "cuda",
                )
            )
        ).softmax(dim=1)
        if int(probabilities.shape[1]) != len(labels):
            raise ValueError(
                "YOLO prediction output class count does not match model metadata "
                "label_space: "
                f"output={probabilities.shape[1]} labels={len(labels)}"
            )
        for output_index, sample_position in enumerate(valid_positions):
            scores = {
                label: float(probabilities[output_index, label_index].item())
                for label_index, label in enumerate(labels)
            }
            confidence, best_index = probabilities[output_index].max(dim=0)
            predictions[sample_position] = Prediction(
                sample_id=sample_ids[sample_position],
                label=labels[int(best_index.item())],
                confidence=float(confidence.item()),
                scores=scores,
            )
    for position, sample_id in enumerate(sample_ids):
        error = errors[position]
        if error is not None:
            yield Prediction(
                sample_id=sample_id,
                label="",
                confidence=None,
                error=error,
            )
        else:
            yield predictions[position]


def _collate_prediction_samples(
    samples: list[dict[str, object]],
) -> dict[str, object]:
    sample_ids: list[str] = []
    errors: list[str | None] = []
    valid_positions: list[int] = []
    images: list[Tensor] = []
    for position, sample in enumerate(samples):
        sample_ids.append(cast(str, sample["sample_id"]))
        error = cast(str | None, sample["error"])
        errors.append(error)
        if error is None:
            valid_positions.append(position)
            images.append(cast(Tensor, sample["image"]))
    return {
        "sample_ids": sample_ids,
        "errors": errors,
        "valid_positions": valid_positions,
        "images": (
            torch.stack(images)
            if images
            else torch.empty((0, YOLO_INPUT_CHANNELS, 0, 0))
        ),
    }


def _validate_loader_options(
    *,
    batch_size: int,
    image_size: int,
    workers: int,
) -> None:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    if image_size <= 0:
        raise ValueError("image_size must be greater than zero")
    if workers < 0:
        raise ValueError("workers must be non-negative")


__all__ = [
    "YOLO_DATALOADER_WORKERS",
    "YOLO_IMAGE_SIZE",
    "YOLO_INPUT_CHANNELS",
    "YOLO_PREDICTION_BATCH_SIZE",
    "YOLO_TRAIN_BATCH_SIZE",
    "YOLO_TRAIN_EPOCHS",
    "inspect_yolo_training_samples",
    "predict_yolo",
    "train_yolo",
]
