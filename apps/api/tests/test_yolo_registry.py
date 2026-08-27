from __future__ import annotations

import inspect

from app.modules.runtime.catalog import runtime_catalog
from app.modules.sc.runtime import ultralytics


def test_yolo_registration_contains_metadata_and_protocol_callables() -> None:
    trainer = runtime_catalog.get_trainer("yolo-sc-v1")
    predictor = runtime_catalog.get_predictor("yolo-sc-v1")
    assert trainer.metadata.name == "YOLO SC Defect Classifier"
    assert trainer.callable is ultralytics.yolo_sc_train
    assert predictor.metadata.name == "YOLO SC Defect Prediction"
    assert predictor.callable is ultralytics.yolo_sc_predictor
    assert runtime_catalog.supports_train_and_predict(trainer.id)


def test_algorithm_runtime_modules_keep_train_and_predict_together() -> None:
    yolo_trainer = runtime_catalog.get_trainer("yolo-sc-v1")
    yolo_predictor = runtime_catalog.get_predictor("yolo-sc-v1")
    assert yolo_trainer.callable.__module__ == yolo_predictor.callable.__module__


def test_registered_yolo_model_contract() -> None:
    assert (
        runtime_catalog.get_trainer_meta("yolo-sc-v1").output_model.contract
        == "sc.yolo.model.v1"
    )


def test_yolo_prediction_stays_streaming_without_image_materialization() -> None:
    source = inspect.getsource(ultralytics._yolo_sc_predictor)

    assert "predict_yolo_stream" in source
    assert "stream_sc_prediction_image_pairs" in source
    assert "ScInspectionMaterializerPort" not in source
    assert ".materialize(" not in source
    assert ".collect(" not in source
    assert "prediction_max_materialized_bytes" not in source
    assert '"total_samples": None' not in source
    assert "_count_prediction_rows(rows)" in source
