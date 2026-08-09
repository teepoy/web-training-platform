from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from PIL import Image
import pyarrow as pa
import pyarrow.parquet as pq

from ml_library import ultralytics


def _image_bytes(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), color=color).save(output, "PNG")
    return output.getvalue()


def test_yolo_training_streams_samples_into_compact_local_class_folders(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image = _image_bytes("blue")
    parquet_path = tmp_path / "training.parquet"
    pq.write_table(
        pa.table(
            {
                "sample_id": ["../../unsafe", "sample-c"],
                "label": ["a", "c"],
                "patch_defective_bytes": [image, image],
                "patch_template_bytes": [image, image],
            }
        ),
        parquet_path,
    )

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
    monkeypatch.setattr(
        ultralytics,
        "select_ultralytics_device",
        lambda _torch: "cpu",
    )

    output = ultralytics.train_yolo(
        parquet_path,
        ["a", "c"],
        valid_samples=2,
        work_dir=tmp_path,
        shuffle_seed=0,
        shuffle_buffer_rows=2,
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
    monkeypatch.setattr(ultralytics, "select_torch_device", lambda _torch: "cpu")

    assert list(ultralytics.predict_yolo(checkpoint_path, ["a", "c"], [])) == []
    assert loaded_paths == [str(checkpoint_path)]
