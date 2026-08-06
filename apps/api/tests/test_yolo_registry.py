from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace
from typing import cast

import pytest

from app.modules.runtime.catalog import runtime_catalog
from app.modules.sc.runtime import predictors, trainers
from app.shared.domain.data_plane import DataPlaneManifest


def test_yolo_registration_contains_metadata_and_protocol_callables() -> None:
    trainer = runtime_catalog.get_trainer("yolo-sc-v1")
    predictor = runtime_catalog.get_predictor("yolo-sc-v1")
    assert trainer.metadata.name == "YOLO SC Detection Trainer"
    assert trainer.callable is trainers.yolo_sc_train
    assert predictor.metadata.name == "YOLO SC Detection Prediction"
    assert predictor.callable is predictors.yolo_sc_predictor
    assert runtime_catalog.supports_train_and_predict(trainer.id)


def test_yolo_predict_rows_uses_model_label_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[tuple[bytes, list[str]]] = []

    def kernel(
        checkpoint: bytes,
        labels: list[str],
        samples: Iterable[object],
    ) -> list[object]:
        assert list(samples) == []
        loaded.append((checkpoint, labels))
        return []

    monkeypatch.setattr(predictors, "_checkpoint_bytes", lambda *_: b"checkpoint")
    monkeypatch.setattr(predictors, "_prediction_samples", lambda *_: iter(()))

    result = list(
        predictors._predict_rows(
            artifact_storage=object(),
            model_uri="memory://model.pt",
            materialization_manifest=cast(DataPlaneManifest, SimpleNamespace()),
            kernel=kernel,
            label_space=["defect", "clean"],
        )
    )

    assert result == []
    assert loaded == [(b"checkpoint", ["defect", "clean"])]


def test_registered_model_contracts_differ_by_algorithm() -> None:
    assert (
        runtime_catalog.get_trainer_meta("resnet50-sc-v1").output_model.contract
        == "sc.resnet50.model.v1"
    )
    assert (
        runtime_catalog.get_trainer_meta("yolo-sc-v1").output_model.contract
        == "sc.yolo.model.v1"
    )
