from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from PIL import Image

from ml_library import TrainingSample
from ml_library.data_loading import ScTrainingDatasetSummary
from ml_library import yolo


def _image_bytes(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), color=color).save(output, "PNG")
    return output.getvalue()


def test_yolo_training_streams_samples_into_compact_local_class_folders(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image = _image_bytes("blue")
    samples = [
        TrainingSample("../../unsafe", image, image, "a"),
        TrainingSample("sample-c", image, image, "c"),
    ]

    class Dataset:
        def inspect(self, _label_space):
            return ScTrainingDatasetSummary(("a", "c"), 2, 0)

        def __iter__(self):
            return iter(samples)

    observed_class_dirs: list[str] = []

    class FakeYolo:
        def __init__(self, _model: str) -> None:
            pass

        def train(self, **kwargs: Any) -> None:
            data_root = Path(cast(str, kwargs["data"]))
            observed_class_dirs.extend(
                sorted(path.name for path in (data_root / "train").iterdir())
            )
            image_names = [path.name for path in (data_root / "train").rglob("*.jpg")]
            assert all(".." not in name and "/" not in name for name in image_names)
            checkpoint = (
                Path(cast(str, kwargs["project"]))
                / cast(str, kwargs["name"])
                / "weights"
                / "best.pt"
            )
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b"checkpoint")

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=FakeYolo))
    monkeypatch.setattr(yolo, "select_ultralytics_device", lambda _torch: "cpu")

    output = yolo.train_yolo(
        cast(Any, Dataset()),
        ["a", "b", "c"],
        work_dir=tmp_path,
        epochs=1,
    )

    assert observed_class_dirs == ["000000", "000001"]
    assert output.checkpoint_path.read_bytes() == b"checkpoint"
    assert output.metadata["label_space"] == ["a", "c"]
    assert output.metadata["label_to_idx"] == {"a": 0, "c": 1}


def test_yolo_prediction_loads_existing_checkpoint_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checkpoint_path = tmp_path / "model.pt"
    checkpoint_path.write_bytes(b"checkpoint")
    loaded_paths: list[str] = []

    class FakeYolo:
        def __init__(self, path: str) -> None:
            loaded_paths.append(path)

        def to(self, _device: object) -> None:
            pass

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=FakeYolo))
    monkeypatch.setattr(yolo, "select_torch_device", lambda _torch: "cpu")

    assert list(yolo.predict_yolo(checkpoint_path, ["a", "c"], [])) == []
    assert loaded_paths == [str(checkpoint_path)]
