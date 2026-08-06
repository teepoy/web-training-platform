from __future__ import annotations

from app.modules.sc.capabilities import (
    SC_PATCH_IMAGE_V1,
    SC_RESNET_MODEL_V1,
    SC_YOLO_MODEL_V1,
)
from app.modules.sc.runtime.predictors import resnet_sc_predictor, yolo_sc_predictor
from app.modules.sc.runtime.router import SC_RUNTIME_ROUTER
from app.modules.sc.runtime.trainers import resnet_sc_train, yolo_sc_train
from app.modules.sc.runtime.workflows import run_sc_train_and_predict


@SC_RUNTIME_ROUTER.algorithm(
    id="resnet50-sc-v1",
    trainer_name="ResNet-50 SC Defect Classifier",
    predictor_name="ResNet-50 SC Defect Prediction",
    input_view=SC_PATCH_IMAGE_V1,
    model=SC_RESNET_MODEL_V1,
    algo_id="resnet50-sc",
    algo_version="1",
)
class ResNetScAlgorithm:
    train = staticmethod(resnet_sc_train)
    predict = staticmethod(resnet_sc_predictor)
    train_and_predict = staticmethod(run_sc_train_and_predict)


@SC_RUNTIME_ROUTER.algorithm(
    id="yolo-sc-v1",
    trainer_name="YOLO SC Detection Trainer",
    predictor_name="YOLO SC Detection Prediction",
    input_view=SC_PATCH_IMAGE_V1,
    model=SC_YOLO_MODEL_V1,
    algo_id="yolo-sc",
    algo_version="1",
)
class YoloScAlgorithm:
    train = staticmethod(yolo_sc_train)
    predict = staticmethod(yolo_sc_predictor)
    train_and_predict = staticmethod(run_sc_train_and_predict)


__all__ = ["ResNetScAlgorithm", "YoloScAlgorithm"]
