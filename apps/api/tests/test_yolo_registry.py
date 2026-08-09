from __future__ import annotations

from app.modules.runtime.catalog import runtime_catalog
from app.modules.sc.runtime import resnet50, ultralytics


def test_yolo_registration_contains_metadata_and_protocol_callables() -> None:
    trainer = runtime_catalog.get_trainer("yolo-sc-v1")
    predictor = runtime_catalog.get_predictor("yolo-sc-v1")
    assert trainer.metadata.name == "YOLO SC Detection Trainer"
    assert trainer.callable is ultralytics.yolo_sc_train
    assert predictor.metadata.name == "YOLO SC Detection Prediction"
    assert predictor.callable is ultralytics.yolo_sc_predictor
    assert runtime_catalog.supports_train_and_predict(trainer.id)


def test_algorithm_runtime_modules_keep_train_and_predict_together() -> None:
    resnet_trainer = runtime_catalog.get_trainer("resnet50-sc-v1")
    resnet_predictor = runtime_catalog.get_predictor("resnet50-sc-v1")
    assert resnet_trainer.callable is resnet50.resnet_sc_train
    assert resnet_predictor.callable is resnet50.resnet_sc_predictor
    assert resnet_trainer.callable.__module__ == resnet_predictor.callable.__module__

    yolo_trainer = runtime_catalog.get_trainer("yolo-sc-v1")
    yolo_predictor = runtime_catalog.get_predictor("yolo-sc-v1")
    assert yolo_trainer.callable.__module__ == yolo_predictor.callable.__module__


def test_registered_model_contracts_differ_by_algorithm() -> None:
    assert (
        runtime_catalog.get_trainer_meta("resnet50-sc-v1").output_model.contract
        == "sc.resnet50.model.v1"
    )
    assert (
        runtime_catalog.get_trainer_meta("yolo-sc-v1").output_model.contract
        == "sc.yolo.model.v1"
    )
