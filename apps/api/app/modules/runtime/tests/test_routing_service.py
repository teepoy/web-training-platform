from __future__ import annotations

import pytest
from omegaconf import OmegaConf

from app.core.config import AppConfig, RuntimeDeploymentOverride, load_config
from app.modules.runtime.app.services.deployment_seed import (
    runtime_prefect_deployment_specs,
)
from app.modules.runtime.app.services.routing_service import (
    ConfigRuntimeRoutingService,
)


def _config() -> AppConfig:
    return load_config(skip_runtime_validation=True)


def test_module_owned_sc_routes_derive_catalog_contracts() -> None:
    service = ConfigRuntimeRoutingService(_config())

    train = service.training_route("resnet50-sc-v1")
    workflow = service.train_and_predict_route("resnet50-sc-v1")
    prediction = service.prediction_route("resnet50-sc-v1")

    assert train.deployment == "train-job-deployment"
    assert train.input_contract == "sc.patch_image.v1"
    assert train.output_contract == "sc.resnet50.model.v1"
    assert train.algo_id == "resnet50-sc"
    assert train.missing_image_policy == "fail"
    assert workflow.output_contract == "sample.predictions.v1"
    assert workflow.missing_image_policy == "skip"
    assert prediction.output_contract == "sample.predictions.v1"


def test_environment_can_override_deployment_fields_only() -> None:
    cfg = _config()
    cfg.runtime_routing.training_routes["resnet50-sc-v1"] = (
        RuntimeDeploymentOverride(
            deployment="prod-resnet-train",
            owner="external",
            resource_profile="gpu",
            code_version="sha256:runtime",
        )
    )

    route = ConfigRuntimeRoutingService(cfg).training_route("resnet50-sc-v1")

    assert route.deployment == "prod-resnet-train"
    assert route.owner == "external"
    assert route.code_version == "sha256:runtime"
    assert route.input_contract == "sc.patch_image.v1"
    assert route.output_contract == "sc.resnet50.model.v1"


def test_omegaconf_override_is_supported() -> None:
    cfg = OmegaConf.create(
        {
            "runtime_routing": {
                "prediction_routes": {
                    "yolo-sc-v1": {
                        "deployment": "prod-yolo-predict",
                    }
                }
            }
        }
    )

    route = ConfigRuntimeRoutingService(cfg).prediction_route("yolo-sc-v1")

    assert route.deployment == "prod-yolo-predict"
    assert route.algo_id == "yolo-sc"


def test_environment_cannot_override_capability_contracts() -> None:
    cfg = OmegaConf.create(
        {
            "runtime_routing": {
                "prediction_routes": {
                    "resnet50-sc-v1": {
                        "input_contract": "drifted.contract",
                    }
                }
            }
        }
    )

    with pytest.raises(RuntimeError, match="may override only"):
        ConfigRuntimeRoutingService(cfg).prediction_route("resnet50-sc-v1")


def test_unknown_runtime_capability_fails() -> None:
    with pytest.raises(KeyError, match="Unknown runtime capability"):
        ConfigRuntimeRoutingService(_config()).training_route("missing")


def test_runtime_catalog_validation_uses_single_descriptor_source() -> None:
    ConfigRuntimeRoutingService(_config()).validate_catalog_routes()


def test_prefect_deployment_specs_deduplicate_algorithms() -> None:
    assert runtime_prefect_deployment_specs(_config()) == [
        {
            "deployment_name": "train-job-deployment",
            "flow_name": "training-train-job",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.training.flows.train_job:train_job_flow",
            "path": "",
        },
        {
            "deployment_name": "train-and-predict-deployment",
            "flow_name": "training-train-and-predict",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.workflows.train_predict:train_and_predict_flow",
            "path": "",
        },
        {
            "deployment_name": "predict-job-batch-deployment",
            "flow_name": "prediction-predict-job",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.prediction.flows.predict_job:predict_job_flow",
            "path": "",
        },
    ]


def test_prefect_deployment_specs_do_not_seed_external_route() -> None:
    cfg = _config()
    for catalog_id in ("resnet50-sc-v1", "yolo-sc-v1"):
        cfg.runtime_routing.training_routes[catalog_id] = RuntimeDeploymentOverride(
            owner="external"
        )

    specs = runtime_prefect_deployment_specs(cfg)

    assert all(spec["deployment_name"] != "train-job-deployment" for spec in specs)
