"""Ultralytics SC classifier with paired grayscale images."""

from __future__ import annotations

import asyncio
import hashlib
import io
import multiprocessing
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageChops
import torch
from torch import Tensor, nn

from ml_library.data_loading._parquet import ParquetPaths
from ml_library.data_loading.streaming import stream_parquet_dataset
from ml_library.device import select_torch_device, select_ultralytics_device
from ml_library.models import Prediction, TrainingOutput

YOLO_PRETRAINED_MODEL = "yolov8n-cls.pt"
YOLO_TRAIN_EPOCHS = 100
YOLO_TRAIN_PATIENCE = 20
YOLO_VALIDATION_FRACTION = 0.2
YOLO_TRAIN_BATCH_SIZE = 16
YOLO_PREDICTION_BATCH_SIZE = 256
YOLO_IMAGE_SIZE = 128
YOLO_DATALOADER_WORKERS = 4
YOLO_INPUT_CHANNELS = 3
YOLO_PREDICTION_PREPROCESS_TASK_SIZE = 64
YOLO_PREDICTION_PREFETCH_TASKS = 8

_TRAINING_COLUMNS = (
    "sample_id",
    "label",
    "patch_defective_bytes",
    "patch_template_bytes",
)


def _preprocess_grayscale_pair(row: dict[str, Any], image_size: int) -> Tensor:
    return cast(
        Tensor,
        _classification_transform(image_size)(_paired_rgb_image(row, image_size)),
    )


@lru_cache(maxsize=8)
def _classification_transform(image_size: int) -> Callable[[Image.Image], Tensor]:
    from ultralytics.data.augment import classify_transforms

    return cast(Callable[[Image.Image], Tensor], classify_transforms(size=image_size))


def _paired_rgb_image(row: dict[str, Any], image_size: int) -> Image.Image:
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
    difference = ImageChops.difference(defective, reference)
    return Image.merge("RGB", (defective, reference, difference))


def _decode_grayscale(value: object, *, role: str, image_size: int) -> Image.Image:
    image_bytes = _optional_bytes(value)
    if not image_bytes:
        raise ValueError(f"missing {role} image bytes")
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("L").resize(
            (image_size, image_size),
            Image.Resampling.BILINEAR,
        )
        return image.copy()


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


def _materialize_yolo_classification_dataset(
    parquet_paths: ParquetPaths,
    labels: Sequence[str],
    *,
    valid_samples: int,
    output_dir: Path,
    image_size: int,
    shuffle_seed: int,
    validation_fraction: float,
) -> Path:
    if output_dir.exists():
        raise FileExistsError(
            f"Ultralytics dataset directory already exists: {output_dir}"
        )

    label_to_index = {label: index for index, label in enumerate(labels)}
    prepared_dir = output_dir / "prepared"
    prepared_dir.mkdir(parents=True)
    samples_by_label: dict[str, list[tuple[str, Path]]] = {
        label: [] for label in labels
    }
    rows = stream_parquet_dataset(
        parquet_paths,
        columns=_TRAINING_COLUMNS,
        shuffle=False,
        seed=0,
        shuffle_buffer_rows=1,
    )
    materialized_samples = 0
    for row_number, row in enumerate(rows):
        label = str(row.get("label") or "").strip()
        class_index = label_to_index.get(label)
        if class_index is None:
            continue
        sample_id = str(row.get("sample_id") or "")
        sample_key = hashlib.sha256(
            f"{shuffle_seed}:{sample_id}:{row_number}".encode()
        ).hexdigest()
        class_dir = prepared_dir / f"class_{class_index:06d}"
        class_dir.mkdir(exist_ok=True)
        image_path = class_dir / f"{sample_key}.png"
        _paired_rgb_image(row, image_size).save(image_path, format="PNG")
        samples_by_label[label].append((sample_key, image_path))
        materialized_samples += 1

    if materialized_samples != valid_samples:
        raise RuntimeError(
            "SC training sample count changed between inspection and Ultralytics "
            "dataset materialization: "
            f"inspected={valid_samples} materialized={materialized_samples}"
        )

    insufficient = [
        label for label, samples in samples_by_label.items() if len(samples) < 2
    ]
    if insufficient:
        raise ValueError(
            "Ultralytics validation requires at least two readable samples per "
            f"class; insufficient classes: {insufficient}"
        )

    for label, samples in samples_by_label.items():
        class_index = label_to_index[label]
        class_name = f"class_{class_index:06d}"
        ordered = sorted(samples)
        validation_samples = min(
            len(ordered) - 1,
            max(1, int(len(ordered) * validation_fraction)),
        )
        for split in ("train", "val"):
            (output_dir / split / class_name).mkdir(parents=True, exist_ok=True)
        for position, (_, source_path) in enumerate(ordered):
            split = "val" if position < validation_samples else "train"
            source_path.replace(output_dir / split / class_name / source_path.name)

    for class_dir in prepared_dir.iterdir():
        class_dir.rmdir()
    prepared_dir.rmdir()
    return output_dir


def _load_pretrained_yolo() -> Any:
    from ultralytics import YOLO

    return YOLO(YOLO_PRETRAINED_MODEL, task="classify")


def _scalar_metric(value: object, *, name: str) -> float:
    if isinstance(value, Tensor):
        if value.numel() != 1:
            raise ValueError(f"Ultralytics {name} must contain one value")
        return float(value.detach().cpu().item())
    if isinstance(value, int | float):
        return float(value)
    raise TypeError(f"Ultralytics {name} must be numeric")


def _mapping_metric(metrics: object, name: str) -> float:
    if not isinstance(metrics, dict) or name not in metrics:
        raise RuntimeError(f"Ultralytics trainer did not report {name}")
    return _scalar_metric(metrics[name], name=name)


async def train_yolo(
    parquet_paths: ParquetPaths,
    label_space: Sequence[str],
    *,
    valid_samples: int,
    work_dir: Path,
    shuffle_seed: int,
    epochs: int = YOLO_TRAIN_EPOCHS,
    patience: int = YOLO_TRAIN_PATIENCE,
    validation_fraction: float = YOLO_VALIDATION_FRACTION,
    batch_size: int = YOLO_TRAIN_BATCH_SIZE,
    image_size: int = YOLO_IMAGE_SIZE,
    workers: int = YOLO_DATALOADER_WORKERS,
    on_epoch: Callable[[int, int, float, float, float], Awaitable[None]] | None = None,
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
    if epochs <= 0:
        raise ValueError("epochs must be greater than zero")
    if patience <= 0:
        raise ValueError("patience must be greater than zero")
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be between zero and one")

    work_dir.mkdir(parents=True, exist_ok=True)
    label_to_index = {label: index for index, label in enumerate(labels)}
    dataset_root = _materialize_yolo_classification_dataset(
        parquet_paths,
        labels,
        valid_samples=valid_samples,
        output_dir=work_dir / "dataset",
        image_size=image_size,
        shuffle_seed=shuffle_seed,
        validation_fraction=validation_fraction,
    )
    model = _load_pretrained_yolo()
    event_loop = asyncio.get_running_loop()
    observed_epochs: list[dict[str, float]] = []

    def report_epoch(trainer: Any) -> None:
        train_loss = _scalar_metric(trainer.tloss, name="train/loss")
        val_loss = _mapping_metric(trainer.metrics, "val/loss")
        val_accuracy = _mapping_metric(
            trainer.metrics,
            "metrics/accuracy_top1",
        )
        epoch_metrics = {
            "epoch": float(trainer.epoch + 1),
            "train_loss": train_loss,
            "val_loss": val_loss,
            "val_accuracy": val_accuracy,
        }
        observed_epochs.append(epoch_metrics)
        if on_epoch is not None:
            future = asyncio.run_coroutine_threadsafe(
                on_epoch(
                    trainer.epoch + 1,
                    trainer.epochs,
                    train_loss,
                    val_loss,
                    val_accuracy,
                ),
                event_loop,
            )
            future.result()

    model.add_callback("on_fit_epoch_end", report_epoch)

    def run_training() -> None:
        model.train(
            data=str(dataset_root),
            epochs=epochs,
            patience=patience,
            batch=batch_size,
            imgsz=image_size,
            workers=workers,
            project=str(work_dir / "runs"),
            name="train",
            exist_ok=True,
            device=select_ultralytics_device(torch),
            pretrained=True,
            seed=shuffle_seed,
            deterministic=True,
            val=True,
            plots=False,
            verbose=False,
            scale=0.0,
            fliplr=0.0,
            flipud=0.0,
            auto_augment=None,
            erasing=0.0,
            hsv_h=0.0,
            hsv_s=0.0,
            hsv_v=0.0,
        )

    await asyncio.to_thread(run_training)
    trainer = model.trainer
    checkpoint_path = trainer.best if trainer.best.is_file() else trainer.last
    if not checkpoint_path.is_file():
        raise FileNotFoundError(
            "Ultralytics training completed without a best.pt or last.pt checkpoint"
        )
    if not observed_epochs:
        raise RuntimeError("Ultralytics trainer did not report epoch metrics")
    final_epoch = observed_epochs[-1]
    best_epoch = max(
        observed_epochs,
        key=lambda item: (item["val_accuracy"], item["epoch"]),
    )
    completed_epochs = int(final_epoch["epoch"])

    metrics: dict[str, object] = {
        "num_samples": valid_samples,
        "num_classes": len(labels),
        "epochs": completed_epochs,
        "best_epoch": int(best_epoch["epoch"]),
        "max_epochs": epochs,
        "patience": patience,
        "batch_size": batch_size,
        "image_size": image_size,
        "train_loss": best_epoch["train_loss"],
        "val_loss": best_epoch["val_loss"],
        "val_accuracy": best_epoch["val_accuracy"],
        "architecture": "yolov8n-cls",
        "framework": "ultralytics",
        "pretrained_model": YOLO_PRETRAINED_MODEL,
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
            "channel_layout": [
                "patch_defective",
                "patch_template",
                "absolute_difference",
            ],
            "image_size": image_size,
            "training_seed": shuffle_seed,
            "pretrained_model": YOLO_PRETRAINED_MODEL,
        },
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
    model, checkpoint = _load_native_yolo_checkpoint(checkpoint_path, device)
    if getattr(model, "task", None) != "classify":
        raise ValueError("Ultralytics checkpoint task must be classify")
    names = getattr(model, "names", None)
    if not isinstance(names, dict) or len(names) != len(labels):
        raise ValueError(
            "Ultralytics checkpoint class count does not match model metadata "
            f"label_space: checkpoint={len(names) if isinstance(names, dict) else 'unknown'} "
            f"labels={len(labels)}"
        )
    train_args = checkpoint.get("train_args")
    if not isinstance(train_args, dict):
        raise ValueError("Ultralytics checkpoint is missing train_args")
    if train_args.get("imgsz") != image_size:
        raise ValueError(
            "YOLO checkpoint image size does not match prediction image size: "
            f"checkpoint={train_args.get('imgsz')} prediction={image_size}"
        )
    first_conv = next(
        (module for module in model.modules() if isinstance(module, nn.Conv2d)),
        None,
    )
    if first_conv is None or first_conv.in_channels != YOLO_INPUT_CHANNELS:
        raise ValueError(
            f"Ultralytics checkpoint must accept {YOLO_INPUT_CHANNELS} input channels"
        )
    return model


def _load_native_yolo_checkpoint(
    checkpoint_path: Path,
    device: Any,
) -> tuple[nn.Module, dict[str, object]]:
    from ultralytics.nn.tasks import load_checkpoint

    model, checkpoint = load_checkpoint(
        checkpoint_path,
        device=device,
        fuse=False,
    )
    if not isinstance(model, nn.Module) or not isinstance(checkpoint, dict):
        raise ValueError("Ultralytics checkpoint did not contain a PyTorch model")
    return model, cast(dict[str, object], checkpoint)


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
    "YOLO_PRETRAINED_MODEL",
    "YOLO_PREDICTION_BATCH_SIZE",
    "YOLO_TRAIN_BATCH_SIZE",
    "YOLO_TRAIN_EPOCHS",
    "YOLO_TRAIN_PATIENCE",
    "YOLO_VALIDATION_FRACTION",
    "inspect_yolo_training_samples",
    "predict_yolo_stream",
    "train_yolo",
]
