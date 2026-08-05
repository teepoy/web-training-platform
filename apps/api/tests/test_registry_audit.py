from __future__ import annotations

import inspect

import app.core.registry as view_registry
from app.modules.prediction.flows import predict_job
from app.modules.runtime.catalog import runtime_catalog
from app.modules.training.flows import train_job


def test_core_registry_no_longer_owns_executable_registrations() -> None:
    for name in (
        "trainer",
        "predictor",
        "get_trainer",
        "get_predictor",
        "get_trainer_by_id",
        "get_predictor_by_id",
    ):
        assert not hasattr(view_registry, name)


def test_runtime_catalog_owns_registered_callable_and_metadata() -> None:
    trainer = runtime_catalog.get_trainer("resnet50-sc-v1")
    predictor = runtime_catalog.get_predictor("resnet50-sc-v1")
    assert trainer.metadata.id == trainer.id
    assert predictor.metadata.id == predictor.id
    assert callable(trainer.callable)
    assert callable(predictor.callable)


def test_generic_flows_do_not_materialize_or_chunk_algorithm_data() -> None:
    source = inspect.getsource(train_job) + inspect.getsource(predict_job)
    assert "materializers_for" not in source
    assert "materialization_manifest" not in source
    assert "predict-chunk" not in source
    assert "persist-chunk" not in source
