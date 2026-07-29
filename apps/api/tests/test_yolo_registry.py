"""YOLO SC registry and API tests — T34.

Verifies that YOLO SC metadata IDs and executable IDs are aligned,
dependency-guard behavior is correct, and catalog entries are consistent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.shared.domain.runtime import DatasetRef, ModelRef, PredictContext, TrainContext

from app.core.registry import get_predictor_by_id, get_trainer_by_id
from app.modules.types import catalog

import app.runtime_compat.ml.trainers.sc  # noqa: F401  @trainer(resnet50-sc-v1)
import app.runtime_compat.ml.trainers.yolo_sc  # noqa: F401  @trainer(yolo-sc-v1)
import app.runtime_compat.ml.predictors.sc  # noqa: F401  @predictor(resnet50-sc-v1)
import app.runtime_compat.ml.predictors.yolo_sc  # noqa: F401  @predictor(yolo-sc-v1)


# ═══════════════════════════════════════════════════════════════════════
# 1.  ID alignment — catalog metadata ↔ executable registrations
# ═══════════════════════════════════════════════════════════════════════


def test_yolo_trainer_metadata_id_matches() -> None:
    """Catalog metadata ID 'yolo-sc-v1' matches executable trainer ID."""
    meta = catalog.get_trainer_meta("yolo-sc-v1")
    assert meta.id == "yolo-sc-v1"
    assert meta.name == "YOLO SC Detection Trainer"
    assert meta.view_id == "patch_image_v1"
    assert meta.predictor_id == "yolo-sc-v1"


def test_yolo_predictor_metadata_id_matches() -> None:
    """Catalog metadata ID 'yolo-sc-v1' matches executable predictor ID."""
    meta = catalog.get_predictor_meta("yolo-sc-v1")
    assert meta.id == "yolo-sc-v1"
    assert meta.name == "YOLO SC Detection Predictor"
    assert meta.view_id == "patch_image_v1"


def test_yolo_trainer_id_in_catalog_listing() -> None:
    """yolo-sc-v1 is in the trainer catalog listing."""
    trainer_ids = catalog.list_trainer_ids()
    assert "yolo-sc-v1" in trainer_ids


def test_yolo_predictor_id_in_catalog_listing() -> None:
    """yolo-sc-v1 is in the predictor catalog listing."""
    predictor_ids = catalog.list_predictor_ids()
    assert "yolo-sc-v1" in predictor_ids


# ═══════════════════════════════════════════════════════════════════════
# 2.  Registry resolution — get_trainer_by_id / get_predictor_by_id
# ═══════════════════════════════════════════════════════════════════════


def test_get_trainer_by_id_yolo_resolves() -> None:
    """get_trainer_by_id('yolo-sc-v1') returns a Trainer with correct metadata."""
    trainer = get_trainer_by_id("yolo-sc-v1")
    assert trainer is not None, "yolo-sc-v1 trainer must resolve"
    assert trainer.trainer_id == "yolo-sc-v1"
    # Name matches catalog metadata ("YOLO SC Detection") or executable
    # registration ("YOLO SC Detection Trainer") depending on whether the
    # executable module was loaded by an earlier test.
    assert trainer.name in {"YOLO SC Detection", "YOLO SC Detection Trainer"}, (
        f"Unexpected trainer name: {trainer.name!r}"
    )
    assert trainer.view_id == "patch_image_v1"


def test_get_predictor_by_id_yolo_resolves() -> None:
    """get_predictor_by_id('yolo-sc-v1') returns a Predictor with correct metadata."""
    predictor = get_predictor_by_id("yolo-sc-v1")
    assert predictor is not None, "yolo-sc-v1 predictor must resolve"
    assert predictor.predictor_id == "yolo-sc-v1"
    assert predictor.name in {"YOLO SC Detection", "YOLO SC Detection Predictor"}, (
        f"Unexpected predictor name: {predictor.name!r}"
    )
    assert predictor.view_id == "patch_image_v1"


# ═══════════════════════════════════════════════════════════════════════
# 3.  Missing dependency behavior — trainer
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.skip(reason="Requires Prefect flow/task run context for get_run_logger()")
@pytest.mark.asyncio
async def test_yolo_trainer_raises_on_missing_lazyframe() -> None:
    """Calling the YOLO trainer without a lazyframe raises ValueError."""
    trainer = get_trainer_by_id("yolo-sc-v1")
    assert trainer is not None
    ctx = TrainContext(job_id="test-yolo-trainer")
    with pytest.raises(ValueError, match="lazyframe"):
        await trainer(
            ctx,
            artifact_storage="mock",  # bypass artifact_storage guard
            lazyframe=None,
        )


@pytest.mark.skip(reason="Requires Prefect flow/task run context for get_run_logger()")
@pytest.mark.asyncio
async def test_yolo_trainer_error_message_mentions_lazyframe() -> None:
    """The YOLO trainer error message tells users about lazyframe requirement."""
    trainer = get_trainer_by_id("yolo-sc-v1")
    assert trainer is not None
    ctx = TrainContext(job_id="test-yolo-msg")
    with pytest.raises(Exception) as exc_info:
        await trainer(
            ctx,
            artifact_storage="mock",  # bypass artifact_storage guard
            lazyframe=None,
        )
    msg = str(exc_info.value).lower()
    assert "lazyframe" in msg, (
        f"Expected error mentioning 'lazyframe', got: {exc_info.value!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 4.  Flow runtime predictor registry
# ═══════════════════════════════════════════════════════════════════════


def test_yolo_predictor_resolves_in_flow_registry() -> None:
    """yolo-sc-v1 is registered in the flow runtime predictor registry."""
    from app.runtime_compat.ml.predictors import (
        get_predictor as flow_get_predictor,
    )

    fn = flow_get_predictor("yolo-sc-v1")
    assert callable(fn), "yolo-sc-v1 must be a callable in flow registry"


def test_yolo_predictor_is_generator() -> None:
    """yolo-sc-v1 predictor is a generator function, not a class."""
    import inspect

    from app.runtime_compat.ml.predictors import (
        get_predictor as flow_get_predictor,
    )

    fn = flow_get_predictor("yolo-sc-v1")
    assert callable(fn), "yolo-sc-v1 must be callable"
    assert inspect.isgeneratorfunction(fn), (
        "yolo-sc-v1 must be a generator function"
    )


def test_yolo_predictor_loads_native_ultralytics_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.runtime_compat.ml.predictors import yolo_sc

    checkpoint_bytes = b"native-ultralytics-checkpoint"
    loaded_bytes: list[bytes] = []

    class ArtifactStorage:
        async def get_bytes(self, uri: str) -> bytes:
            assert uri == "memory://model.pt"
            return checkpoint_bytes

    class FakeModel:
        names = {0: "defect", 1: "clean"}

        def to(self, device: object) -> None:
            assert device == "cpu"

    def fake_yolo(path: str) -> FakeModel:
        loaded_bytes.append(Path(path).read_bytes())
        return FakeModel()

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        mps=SimpleNamespace(is_available=lambda: False),
        device=lambda value: value,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules,
        "ultralytics",
        SimpleNamespace(YOLO=fake_yolo),
    )
    monkeypatch.setattr(
        yolo_sc,
        "get_run_logger",
        lambda: SimpleNamespace(info=lambda *args: None),
    )

    model_ref = ModelRef(
        uri="memory://model.pt",
        metadata={"label_space": ["defect", "clean"]},
    )
    ctx = PredictContext(
        job_id="test-yolo-native-checkpoint",
        dataset_ref=DatasetRef(dataset_id="d1", label_space=["fallback"]),
        model_ref=model_ref,
    )

    predictions = list(
        yolo_sc.yolo_sc_predictor.func(
                artifact_storage=ArtifactStorage(),
                ctx=ctx,
                model_ref=model_ref,
                materialized_dataset=[],
            )
    )

    assert predictions == []
    assert loaded_bytes == [checkpoint_bytes]


def test_yolo_active_labels_are_compacted_from_training_rows() -> None:
    from app.runtime_compat.ml.trainers import yolo_sc

    rows = [
        {"label": "a", "images": [{"role": "patch_defective"}, {"role": "patch_template"}]},
        {"label": "c", "images": [{"role": "patch_defective"}, {"role": "patch_template"}]},
    ]

    assert yolo_sc._ordered_active_labels(rows, ["a", "b", "c"]) == ["a", "c"]


def test_yolo_predictor_requires_model_metadata_label_space() -> None:
    from app.runtime_compat.ml.predictors import yolo_sc

    model_ref = ModelRef(metadata={})

    with pytest.raises(ValueError, match="compact label_space"):
        yolo_sc._resolve_labels(model_ref)


def test_trained_model_metadata_preserves_trainer_label_space() -> None:
    from app.modules.training.flows.train_job import build_trained_model_metadata

    metadata = build_trained_model_metadata(
        {"id": "dataset-1", "dataset_meta": {"label_space": ["a", "b", "c"]}},
        "yolo-sc-v1",
        {"label_space": ["a", "c"], "label_to_idx": {"a": 0, "c": 1}},
    )

    assert metadata["label_space"] == ["a", "c"]
    assert metadata["label_to_idx"] == {"a": 0, "c": 1}


@pytest.mark.skip(reason="Requires Prefect flow/task run context for get_run_logger()")
def test_yolo_predictor_raises_on_missing_storage() -> None:
    """yolo-sc-v1 predictor raises ValueError when artifact_storage is None."""
    from app.shared.domain.runtime import ModelRef, PredictContext, DatasetRef

    from app.runtime_compat.ml.predictors import (
        get_predictor as flow_get_predictor,
    )

    fn = flow_get_predictor("yolo-sc-v1")
    ctx = PredictContext(
        job_id="test-yolo-pred",
        dataset_ref=DatasetRef(dataset_id="d1"),
        model_ref=ModelRef(uri="test.pt"),
    )
    with pytest.raises(ValueError, match="artifact_storage"):
        gen = fn(artifact_storage=None, ctx=ctx, lazyframe=[], model_ref=ModelRef(uri="test.pt"))
        next(gen)
