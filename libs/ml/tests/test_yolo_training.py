from __future__ import annotations

import asyncio
import io
from pathlib import Path

from PIL import Image
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from torch import Tensor, nn

from ml_library import ultralytics


def _image_bytes(value: int) -> bytes:
    output = io.BytesIO()
    Image.new("L", (4, 4), color=value).save(output, "PNG")
    return output.getvalue()


class _TinyClassifier(nn.Module):
    def __init__(self, observed_batches: list[tuple[int, ...]] | None = None) -> None:
        super().__init__()
        self.linear = nn.Linear(2, 2)
        self._observed_batches = observed_batches

    def forward(self, images: Tensor) -> Tensor:
        if self._observed_batches is not None:
            self._observed_batches.append(tuple(images.shape))
        features = images.mean(dim=(2, 3))
        return self.linear(features)


def test_yolo_runtime_defaults() -> None:
    assert ultralytics.YOLO_TRAIN_EPOCHS == 50
    assert ultralytics.YOLO_PREDICTION_BATCH_SIZE == 256
    assert ultralytics.YOLO_IMAGE_SIZE == 128
    assert ultralytics.YOLO_DATALOADER_WORKERS == 4
    assert ultralytics.YOLO_INPUT_CHANNELS == 2


def test_yolo_dataset_stacks_grayscale_images_by_channel(tmp_path: Path) -> None:
    parquet_path = tmp_path / "channel-stack.parquet"
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-a"],
                "patch_defective_bytes": [_image_bytes(0)],
                "patch_template_bytes": [_image_bytes(255)],
            }
        ),
        parquet_path,
    )

    dataset = ultralytics._ScYoloPredictionDataset(
        parquet_path,
        image_size=128,
    )
    sample = next(iter(dataset))
    image = sample["image"]

    assert isinstance(image, Tensor)
    assert tuple(image.shape) == (2, 128, 128)
    assert torch.all(image[0] == -1)
    assert torch.all(image[1] == 1)


def _write_training_parquet(path: Path) -> None:
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-a", "sample-c"],
                "label": ["a", "c"],
                "patch_defective_bytes": [_image_bytes(0), _image_bytes(255)],
                "patch_template_bytes": [_image_bytes(255), _image_bytes(0)],
            }
        ),
        path,
        row_group_size=1,
    )


def test_yolo_training_uses_two_channel_grayscale_dataset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parquet_path = tmp_path / "training.parquet"
    _write_training_parquet(parquet_path)
    observed_batches: list[tuple[int, ...]] = []
    monkeypatch.setattr(
        ultralytics,
        "_build_yolo_classifier",
        lambda _classes: _TinyClassifier(observed_batches),
    )
    monkeypatch.setattr(
        ultralytics,
        "select_torch_device",
        lambda _torch: torch.device("cpu"),
    )

    labels, valid_samples, skipped = ultralytics.inspect_yolo_training_samples(
        parquet_path,
        ["a", "b", "c"],
    )
    progress: list[tuple[int, int, float, float]] = []

    async def on_epoch(epoch: int, total: int, loss: float, accuracy: float) -> None:
        progress.append((epoch, total, loss, accuracy))

    output = asyncio.run(
        ultralytics.train_yolo(
            parquet_path,
            labels,
            valid_samples=valid_samples,
            work_dir=tmp_path,
            shuffle_seed=0,
            shuffle_buffer_rows=2,
            epochs=1,
            batch_size=2,
            image_size=128,
            workers=0,
            on_epoch=on_epoch,
        )
    )

    assert labels == ("a", "c")
    assert skipped == 0
    assert observed_batches == [(2, 2, 128, 128)]
    assert output.metadata["input_channels"] == 2
    assert output.metadata["image_roles"] == [
        "patch_defective",
        "patch_template",
    ]
    assert output.metadata["image_size"] == 128
    assert output.metadata["training_seed"] == 0
    assert output.metrics["epochs"] == 1
    assert output.checkpoint_path.is_file()
    assert len(progress) == 1
    assert progress[0][:2] == (1, 1)


def test_yolo_prediction_defaults_to_256_and_preprocesses_in_dataset_workers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    row_count = 257
    parquet_path = tmp_path / "prediction.parquet"
    defective = _image_bytes(0)
    reference = _image_bytes(255)
    pq.write_table(
        pa.table(
            {
                "sample_id": [f"sample-{index}" for index in range(row_count)],
                "patch_defective_bytes": [defective] * row_count,
                "patch_template_bytes": [reference] * row_count,
            }
        ),
        parquet_path,
        row_group_size=64,
    )
    observed_batches: list[tuple[int, ...]] = []
    checkpoint_model = _TinyClassifier()
    checkpoint_path = tmp_path / "checkpoint.pt"
    torch.save(
        {
            "model_state_dict": checkpoint_model.state_dict(),
            "architecture": "yolov8n-cls",
            "label_space": ["a", "c"],
            "num_classes": 2,
            "input_channels": 2,
            "image_size": 128,
        },
        checkpoint_path,
    )
    monkeypatch.setattr(
        ultralytics,
        "_build_yolo_classifier",
        lambda _classes: _TinyClassifier(observed_batches),
    )
    monkeypatch.setattr(
        ultralytics,
        "select_torch_device",
        lambda _torch: torch.device("cpu"),
    )

    predictions = list(
        ultralytics.predict_yolo(
            checkpoint_path,
            ["a", "c"],
            parquet_path,
            workers=2,
        )
    )

    assert len(predictions) == row_count
    assert observed_batches == [(256, 2, 128, 128), (1, 2, 128, 128)]
    assert {prediction.label for prediction in predictions} <= {"a", "c"}


def test_yolo_prediction_reports_image_preprocess_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parquet_path = tmp_path / "prediction-errors.parquet"
    pq.write_table(
        pa.table(
            {
                "sample_id": ["valid", "missing"],
                "patch_defective_bytes": [_image_bytes(0), None],
                "patch_template_bytes": [_image_bytes(255), _image_bytes(255)],
            }
        ),
        parquet_path,
    )
    model = _TinyClassifier()
    checkpoint_path = tmp_path / "checkpoint.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "architecture": "yolov8n-cls",
            "label_space": ["a", "c"],
            "num_classes": 2,
            "input_channels": 2,
            "image_size": 128,
        },
        checkpoint_path,
    )
    monkeypatch.setattr(
        ultralytics,
        "_build_yolo_classifier",
        lambda _classes: _TinyClassifier(),
    )
    monkeypatch.setattr(
        ultralytics,
        "select_torch_device",
        lambda _torch: torch.device("cpu"),
    )

    predictions = list(
        ultralytics.predict_yolo(
            checkpoint_path,
            ["a", "c"],
            parquet_path,
            workers=0,
        )
    )

    assert predictions[0].error is None
    assert predictions[1].sample_id == "missing"
    assert "missing patch_defective" in (predictions[1].error or "")
