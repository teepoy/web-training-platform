from __future__ import annotations

import asyncio
from concurrent.futures import Executor, Future, ThreadPoolExecutor
import io
from pathlib import Path
import threading

from PIL import Image
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
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
        self.stem = nn.Conv2d(3, 3, kernel_size=1)
        self.linear = nn.Linear(3, 2)
        self._observed_batches = observed_batches
        self.task = "classify"
        self.names = {0: "class_000000", 1: "class_000001"}

    def forward(self, images: Tensor) -> Tensor:
        if self._observed_batches is not None:
            self._observed_batches.append(tuple(images.shape))
        features = self.stem(images).mean(dim=(2, 3))
        return self.linear(features)


def test_yolo_runtime_defaults() -> None:
    assert ultralytics.YOLO_TRAIN_EPOCHS == 100
    assert ultralytics.YOLO_TRAIN_PATIENCE == 20
    assert ultralytics.YOLO_VALIDATION_FRACTION == 0.2
    assert ultralytics.YOLO_PRETRAINED_MODEL == "yolov8n-cls.pt"
    assert ultralytics.YOLO_PREDICTION_BATCH_SIZE == 256
    assert ultralytics.YOLO_IMAGE_SIZE == 128
    assert ultralytics.YOLO_DATALOADER_WORKERS == 4
    assert ultralytics.YOLO_PREDICTION_PREPROCESS_TASK_SIZE == 64
    assert ultralytics.YOLO_PREDICTION_PREFETCH_TASKS == 8
    assert ultralytics.YOLO_INPUT_CHANNELS == 3


def test_yolo_dataset_builds_defective_template_difference_channels(
    tmp_path: Path,
) -> None:
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
    assert tuple(image.shape) == (3, 128, 128)
    assert torch.all(image[0] == 0)
    assert torch.all(image[1] == 1)
    assert torch.all(image[2] == 1)


def _write_training_parquet(path: Path) -> None:
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-a-1", "sample-a-2", "sample-c-1", "sample-c-2"],
                "label": ["a", "a", "c", "c"],
                "patch_defective_bytes": [
                    _image_bytes(0),
                    _image_bytes(32),
                    _image_bytes(255),
                    _image_bytes(224),
                ],
                "patch_template_bytes": [
                    _image_bytes(255),
                    _image_bytes(224),
                    _image_bytes(0),
                    _image_bytes(32),
                ],
            }
        ),
        path,
        row_group_size=1,
    )


def test_yolo_training_uses_native_trainer_pretrained_weights_and_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parquet_path = tmp_path / "training.parquet"
    _write_training_parquet(parquet_path)
    observed_train_args: dict[str, object] = {}
    callbacks: dict[str, object] = {}

    class FakeTrainer:
        def __init__(self) -> None:
            self.epoch = 99
            self.epochs = 100
            self.tloss = torch.tensor(0.25)
            self.metrics = {
                "val/loss": 0.2,
                "metrics/accuracy_top1": 0.75,
            }
            self.best = tmp_path / "native-run" / "weights" / "best.pt"
            self.last = tmp_path / "native-run" / "weights" / "last.pt"

    class FakeYolo:
        def __init__(self) -> None:
            self.trainer = FakeTrainer()

        def add_callback(self, event: str, callback: object) -> None:
            callbacks[event] = callback

        def train(self, **kwargs: object) -> None:
            observed_train_args.update(kwargs)
            self.trainer.best.parent.mkdir(parents=True)
            self.trainer.best.write_bytes(b"native ultralytics checkpoint")
            callback = callbacks["on_fit_epoch_end"]
            assert callable(callback)
            callback(self.trainer)

    fake_yolo = FakeYolo()
    monkeypatch.setattr(ultralytics, "_load_pretrained_yolo", lambda: fake_yolo)
    monkeypatch.setattr(ultralytics, "select_ultralytics_device", lambda _torch: "cpu")

    labels, valid_samples, skipped = ultralytics.inspect_yolo_training_samples(
        parquet_path,
        ["a", "b", "c"],
    )
    progress: list[tuple[int, int, float, float, float]] = []

    async def on_epoch(
        epoch: int,
        total: int,
        train_loss: float,
        val_loss: float,
        val_accuracy: float,
    ) -> None:
        progress.append((epoch, total, train_loss, val_loss, val_accuracy))

    output = asyncio.run(
        ultralytics.train_yolo(
            parquet_path,
            labels,
            valid_samples=valid_samples,
            work_dir=tmp_path,
            shuffle_seed=0,
            batch_size=2,
            image_size=128,
            workers=0,
            on_epoch=on_epoch,
        )
    )

    assert labels == ("a", "c")
    assert skipped == 0
    assert observed_train_args["pretrained"] is True
    assert observed_train_args["val"] is True
    assert observed_train_args["epochs"] == 100
    assert observed_train_args["patience"] == 20
    assert output.metadata["input_channels"] == 3
    assert output.metadata["channel_layout"] == [
        "patch_defective",
        "patch_template",
        "absolute_difference",
    ]
    assert output.metadata["image_roles"] == [
        "patch_defective",
        "patch_template",
    ]
    assert output.metadata["image_size"] == 128
    assert output.metadata["training_seed"] == 0
    assert output.metrics["epochs"] == 100
    assert output.metrics["best_epoch"] == 100
    assert output.metrics["train_loss"] == 0.25
    assert output.metrics["val_loss"] == 0.2
    assert output.metrics["val_accuracy"] == 0.75
    assert output.checkpoint_path.is_file()
    assert len(progress) == 1
    assert progress[0] == (100, 100, 0.25, 0.2, 0.75)

    dataset_root = Path(str(observed_train_args["data"]))
    assert len(list((dataset_root / "train").rglob("*.png"))) == 2
    assert len(list((dataset_root / "val").rglob("*.png"))) == 2
    with Image.open(next((dataset_root / "train").rglob("*.png"))) as image:
        assert image.mode == "RGB"


def test_yolo_training_requires_validation_sample_for_every_class(
    tmp_path: Path,
) -> None:
    parquet_path = tmp_path / "insufficient-validation.parquet"
    pq.write_table(
        pa.table(
            {
                "sample_id": ["sample-a", "sample-c"],
                "label": ["a", "c"],
                "patch_defective_bytes": [_image_bytes(0), _image_bytes(255)],
                "patch_template_bytes": [_image_bytes(255), _image_bytes(0)],
            }
        ),
        parquet_path,
    )

    with pytest.raises(
        ValueError,
        match="validation requires at least two readable samples per class",
    ):
        asyncio.run(
            ultralytics.train_yolo(
                parquet_path,
                ("a", "c"),
                valid_samples=2,
                work_dir=tmp_path / "work",
                shuffle_seed=0,
                workers=0,
            )
        )


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
    checkpoint_path = tmp_path / "checkpoint.pt"
    checkpoint_path.write_bytes(b"native checkpoint")
    monkeypatch.setattr(
        ultralytics,
        "_load_native_yolo_checkpoint",
        lambda _path, _device: (
            _TinyClassifier(observed_batches),
            {"train_args": {"imgsz": 128}},
        ),
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
    assert observed_batches == [(256, 3, 128, 128), (1, 3, 128, 128)]
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
    checkpoint_path = tmp_path / "checkpoint.pt"
    checkpoint_path.write_bytes(b"native checkpoint")
    monkeypatch.setattr(
        ultralytics,
        "_load_native_yolo_checkpoint",
        lambda _path, _device: (
            _TinyClassifier(),
            {"train_args": {"imgsz": 128}},
        ),
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


def test_yolo_stream_prediction_processes_every_sample_and_final_partial_batch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    row_count = 257
    observed_batches: list[tuple[int, ...]] = []
    checkpoint_path = _write_checkpoint(tmp_path)
    monkeypatch.setattr(
        ultralytics,
        "_load_native_yolo_checkpoint",
        lambda _path, _device: (
            _TinyClassifier(observed_batches),
            {"train_args": {"imgsz": 128}},
        ),
    )
    monkeypatch.setattr(
        ultralytics,
        "select_torch_device",
        lambda _torch: torch.device("cpu"),
    )

    async def samples():
        defective = _image_bytes(0)
        template = _image_bytes(255)
        for index in range(row_count):
            yield {
                "sample_id": f"sample-{index}",
                "patch_defective_bytes": defective,
                "patch_template_bytes": template,
            }

    async def collect_predictions():
        return [
            prediction
            async for prediction in ultralytics.predict_yolo_stream(
                checkpoint_path,
                ["a", "c"],
                samples(),
                workers=0,
            )
        ]

    predictions = asyncio.run(collect_predictions())

    assert [prediction.sample_id for prediction in predictions] == [
        f"sample-{index}" for index in range(row_count)
    ]
    assert observed_batches == [(256, 3, 128, 128), (1, 3, 128, 128)]


def test_yolo_stream_prediction_preserves_source_item_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkpoint_path = _write_checkpoint(tmp_path)
    monkeypatch.setattr(
        ultralytics,
        "_load_native_yolo_checkpoint",
        lambda _path, _device: (
            _TinyClassifier(),
            {"train_args": {"imgsz": 128}},
        ),
    )
    monkeypatch.setattr(
        ultralytics,
        "select_torch_device",
        lambda _torch: torch.device("cpu"),
    )

    async def samples():
        yield {"sample_id": "missing", "error": "archive missing"}
        yield {
            "sample_id": "valid",
            "patch_defective_bytes": _image_bytes(0),
            "patch_template_bytes": _image_bytes(255),
        }

    async def collect_predictions():
        return [
            prediction
            async for prediction in ultralytics.predict_yolo_stream(
                checkpoint_path,
                ["a", "c"],
                samples(),
                workers=0,
            )
        ]

    predictions = asyncio.run(collect_predictions())
    assert [prediction.sample_id for prediction in predictions] == ["missing", "valid"]
    assert predictions[0].error == "archive missing"
    assert predictions[1].error is None


def test_preprocess_stream_bounds_prefetch_and_cleans_up_worker_failure(
    monkeypatch,
) -> None:
    executors: list[_TrackingExecutor] = []

    def executor_factory(*, max_workers: int, mp_context: object):
        del mp_context
        executor = _TrackingExecutor(max_workers=max_workers)
        executors.append(executor)
        return executor

    def fail_task(_rows: list[dict[str, object]], _image_size: int):
        raise RuntimeError("worker failed")

    monkeypatch.setattr(ultralytics, "ProcessPoolExecutor", executor_factory)
    monkeypatch.setattr(ultralytics, "_preprocess_prediction_task", fail_task)

    async def samples():
        for index in range(20):
            yield {"sample_id": str(index)}

    async def consume() -> None:
        async for _ in ultralytics._preprocess_prediction_stream(
            samples(),
            image_size=128,
            workers=2,
            task_size=2,
            prefetch_tasks=3,
        ):
            pass

    with pytest.raises(RuntimeError, match="worker failed"):
        asyncio.run(consume())
    assert len(executors) == 1
    assert executors[0].submitted <= 3
    assert executors[0].shutdown_called


def test_preprocess_stream_cancellation_cancels_pending_and_does_not_block_loop(
    monkeypatch,
) -> None:
    executor = _ManualShutdownExecutor()
    monkeypatch.setattr(
        ultralytics,
        "ProcessPoolExecutor",
        lambda **_kwargs: executor,
    )
    monkeypatch.setattr(
        ultralytics,
        "_preprocess_prediction_task",
        lambda rows, _image_size: rows,
    )

    async def samples():
        yield {"sample_id": "first"}
        yield {"sample_id": "pending"}

    async def exercise() -> None:
        stream = ultralytics._preprocess_prediction_stream(
            samples(),
            image_size=128,
            workers=1,
            task_size=1,
            prefetch_tasks=2,
        )
        assert (await anext(stream))["sample_id"] == "first"

        close_task = asyncio.create_task(stream.aclose())
        while not executor.shutdown_entered.is_set():
            await asyncio.sleep(0)

        loop_was_responsive = False

        def mark_responsive() -> None:
            nonlocal loop_was_responsive
            loop_was_responsive = True

        asyncio.get_running_loop().call_soon(mark_responsive)
        await asyncio.sleep(0)
        assert loop_was_responsive

        executor.allow_shutdown.set()
        await asyncio.wait_for(close_task, timeout=1)

    asyncio.run(exercise())
    assert executor.shutdown_called
    assert len(executor.futures) == 2
    assert executor.futures[1].cancelled()


class _TrackingExecutor(ThreadPoolExecutor):
    def __init__(self, *, max_workers: int) -> None:
        super().__init__(max_workers=max_workers)
        self.submitted = 0
        self.shutdown_called = False

    def submit(self, fn, /, *args, **kwargs):
        self.submitted += 1
        return super().submit(fn, *args, **kwargs)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        self.shutdown_called = True
        super().shutdown(wait=wait, cancel_futures=cancel_futures)


class _ManualShutdownExecutor(Executor):
    def __init__(self) -> None:
        self.futures: list[Future[list[dict[str, object]]]] = []
        self.shutdown_called = False
        self.shutdown_entered = threading.Event()
        self.allow_shutdown = threading.Event()

    def submit(self, fn, /, *args, **kwargs):
        future: Future[list[dict[str, object]]] = Future()
        if not self.futures:
            future.set_result(fn(*args, **kwargs))
        self.futures.append(future)
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        del wait, cancel_futures
        self.shutdown_called = True
        self.shutdown_entered.set()
        if not self.allow_shutdown.wait(timeout=1):
            raise TimeoutError("test did not release executor shutdown")


def _write_checkpoint(tmp_path: Path) -> Path:
    checkpoint_path = tmp_path / "stream-checkpoint.pt"
    checkpoint_path.write_bytes(b"native checkpoint")
    return checkpoint_path
