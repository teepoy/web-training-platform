from __future__ import annotations

from app.modules.runtime.domain.executables import (
    RuntimeCapabilityBundle,
    RuntimeExecutableDefinition,
    RuntimeOperation,
    RuntimeRouteDefinition,
)


def _routes() -> tuple[RuntimeRouteDefinition, ...]:
    return (
        RuntimeRouteDefinition(
            operation=RuntimeOperation.TRAIN,
            deployment="train-job-deployment",
            resource_profile="gpu",
            owner="local_compat",
            missing_image_policy="fail",
            output_contract="trainer_model",
        ),
        RuntimeRouteDefinition(
            operation=RuntimeOperation.TRAIN_AND_PREDICT,
            deployment="train-and-predict-deployment",
            resource_profile="gpu",
            owner="local_compat",
            missing_image_policy="skip",
            output_contract="sample.predictions.v1",
        ),
        RuntimeRouteDefinition(
            operation=RuntimeOperation.PREDICT,
            deployment="predict-job-batch-deployment",
            resource_profile="gpu",
            owner="local_compat",
            missing_image_policy="skip",
            output_contract="sample.predictions.v1",
        ),
    )


SC_RUNTIME_CAPABILITIES = RuntimeCapabilityBundle(
    executables=(
        RuntimeExecutableDefinition(
            catalog_id="resnet50-sc-v1",
            algo_id="resnet50-sc",
            algo_version="1",
            trainer_module="app.modules.sc.runtime.trainers",
            predictor_module="app.modules.sc.runtime.predictors",
            routes=_routes(),
        ),
        RuntimeExecutableDefinition(
            catalog_id="yolo-sc-v1",
            algo_id="yolo-sc",
            algo_version="1",
            trainer_module="app.modules.sc.runtime.trainers",
            predictor_module="app.modules.sc.runtime.predictors",
            routes=_routes(),
        ),
    )
)

__all__ = ["SC_RUNTIME_CAPABILITIES"]
