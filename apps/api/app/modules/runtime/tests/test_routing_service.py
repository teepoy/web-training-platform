from __future__ import annotations

import pytest
from omegaconf import OmegaConf

from app.core.config import AppConfig, RuntimeDeploymentConfig
from app.modules.runtime.app.services.routing_service import ConfigRuntimeRoutingService
from app.modules.runtime.app.services.deployment_seed import (
    runtime_prefect_deployment_specs,
)


def test_config_runtime_routing_service_resolves_routes() -> None:
    cfg = OmegaConf.create(
        {
            "runtime_routing": {
                "training_routes": {
                    "trainer-a": {
                        "deployment": "train.a.gpu",
                        "input_contract": "view.v1",
                        "output_contract": "model.v1",
                        "resource_profile": "gpu",
                        "owner": "local_compat",
                        "algo_id": "algo-a",
                        "algo_version": "1",
                    }
                },
                "prediction_routes": {
                    "predictor-a": {
                        "deployment": "predict.a.gpu",
                        "input_contract": "view.v1",
                        "output_contract": "predictions.v1",
                        "resource_profile": "gpu",
                        "owner": "local_compat",
                    }
                },
                "train_and_predict_routes": {
                    "trainer-a": {
                        "deployment": "train-predict.a.gpu",
                        "input_contract": "view.v1",
                        "output_contract": "predictions.v1",
                        "resource_profile": "gpu",
                        "owner": "local_compat",
                    }
                },
            }
        }
    )

    service = ConfigRuntimeRoutingService(cfg)

    train_route = service.training_route("trainer-a")
    predict_route = service.prediction_route("predictor-a")
    workflow_route = service.train_and_predict_route("trainer-a")

    assert train_route.deployment == "train.a.gpu"
    assert train_route.algo_id == "algo-a"
    assert predict_route.deployment == "predict.a.gpu"
    assert workflow_route.deployment == "train-predict.a.gpu"


def test_config_runtime_routing_service_resolves_pydantic_config() -> None:
    cfg = AppConfig()
    cfg.runtime_routing.train_and_predict_routes["trainer-a"] = (
        RuntimeDeploymentConfig(
            deployment="train-predict.a.gpu",
            input_contract="view.v1",
            output_contract="predictions.v1",
            resource_profile="gpu",
            owner="local_compat",
            algo_id="algo-a",
            algo_version="1",
        )
    )

    service = ConfigRuntimeRoutingService(cfg)

    route = service.train_and_predict_route("trainer-a")

    assert route.deployment == "train-predict.a.gpu"
    assert route.algo_id == "algo-a"
    assert route.algo_version == "1"


def test_base_runtime_routing_matches_typed_catalog() -> None:
    cfg = OmegaConf.load("config/base.yaml")

    ConfigRuntimeRoutingService(cfg).validate_catalog_routes()


def test_catalog_route_validation_rejects_contract_drift() -> None:
    cfg = OmegaConf.load("config/base.yaml")
    cfg.runtime_routing.prediction_routes[
        "resnet50-sc-v1"
    ].input_contract = "image_input_v1"

    with pytest.raises(
        RuntimeError,
        match="prediction_routes.resnet50-sc-v1.input_contract",
    ):
        ConfigRuntimeRoutingService(cfg).validate_catalog_routes()


def test_catalog_route_validation_requires_explicit_image_policy() -> None:
    cfg = OmegaConf.load("config/base.yaml")
    cfg.runtime_routing.training_routes[
        "resnet50-sc-v1"
    ].missing_image_policy = None

    with pytest.raises(
        RuntimeError,
        match="training_routes.resnet50-sc-v1.missing_image_policy",
    ):
        ConfigRuntimeRoutingService(cfg).validate_catalog_routes()


def test_config_runtime_routing_service_fails_for_missing_route() -> None:
    cfg = OmegaConf.create(
        {
            "runtime_routing": {
                "training_routes": {},
            }
        }
    )
    service = ConfigRuntimeRoutingService(cfg)

    with pytest.raises(RuntimeError, match="training_routes.missing"):
        service.training_route("missing")


def test_runtime_prefect_deployment_specs_deduplicate_routing_entries() -> None:
    cfg = OmegaConf.create(
        {
            "runtime_routing": {
                "training_routes": {
                    "trainer-a": {
                        "deployment": "train.shared.gpu",
                        "input_contract": "view.v1",
                        "output_contract": "model.v1",
                        "resource_profile": "gpu",
                        "owner": "local_compat",
                    },
                    "trainer-b": {
                        "deployment": "train.shared.gpu",
                        "input_contract": "view.v1",
                        "output_contract": "model.v1",
                        "resource_profile": "gpu",
                        "owner": "local_compat",
                    },
                },
                "prediction_routes": {},
                "train_and_predict_routes": {},
            }
        }
    )

    specs = runtime_prefect_deployment_specs(cfg)

    assert specs == [
        {
            "deployment_name": "train.shared.gpu",
            "flow_name": "training-train-job",
            "work_pool_name": "default-gpu",
            "entrypoint": "app.modules.training.flows.train_job:train_job_flow",
            "path": "",
        }
    ]


def test_runtime_prefect_deployment_specs_do_not_seed_external_routes() -> None:
    cfg = OmegaConf.create(
        {
            "runtime_routing": {
                "training_routes": {
                    "external-trainer": {
                        "deployment": "external.train.gpu",
                        "input_contract": "view.v1",
                        "output_contract": "model.v1",
                        "resource_profile": "gpu",
                        "owner": "external",
                    }
                },
                "prediction_routes": {},
                "train_and_predict_routes": {},
            }
        }
    )

    assert runtime_prefect_deployment_specs(cfg) == []
