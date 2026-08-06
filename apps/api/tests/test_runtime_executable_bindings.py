from __future__ import annotations

from app.modules.runtime.catalog import runtime_catalog


def test_runtime_catalog_is_the_single_trainer_predictor_source() -> None:
    assert set(runtime_catalog.list_trainer_ids()) == {
        "resnet50-sc-v1",
        "yolo-sc-v1",
    }
    assert set(runtime_catalog.list_predictor_ids()) == {
        "resnet50-sc-v1",
        "yolo-sc-v1",
    }


def test_registered_capabilities_include_metadata_callables_and_operations() -> None:
    for trainer_id in runtime_catalog.list_trainer_ids():
        trainer = runtime_catalog.get_trainer(trainer_id)
        predictor = runtime_catalog.get_predictor(trainer.metadata.predictor_id)
        assert callable(trainer.callable)
        assert callable(trainer.train_and_predict_callable)
        assert callable(predictor.callable)
        assert predictor.metadata.input_view == trainer.metadata.input_view
        assert predictor.metadata.input_model == trainer.metadata.output_model
        assert runtime_catalog.supports_train_and_predict(trainer_id)
