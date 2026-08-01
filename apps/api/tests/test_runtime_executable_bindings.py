from __future__ import annotations

from app.modules.runtime.app.services.executable_loader import (
    list_local_executable_bindings,
    validate_local_executable_bindings,
)
from app.modules.runtime.domain.executables import (
    ExecutableKind,
)
from app.runtime_compat.materializers import (
    list_local_materializer_bindings,
    validate_local_materializer_bindings,
)
from app.modules.types import catalog


def test_worker_local_bindings_are_separate_from_catalog_metadata() -> None:
    validate_local_executable_bindings()

    binding_keys = {
        (binding.kind, binding.catalog_id)
        for binding in list_local_executable_bindings()
    }
    assert binding_keys == {
        (ExecutableKind.TRAINER, "resnet50-sc-v1"),
        (ExecutableKind.TRAINER, "yolo-sc-v1"),
        (ExecutableKind.PREDICTOR, "resnet50-sc-v1"),
        (ExecutableKind.PREDICTOR, "yolo-sc-v1"),
    }
    assert set(catalog.list_predictor_ids()) == {
        binding.catalog_id
        for binding in list_local_executable_bindings()
        if binding.kind is ExecutableKind.PREDICTOR
    }


def test_trainers_declare_explicit_predictor_pairing() -> None:
    for trainer in catalog.list_trainers():
        predictor = catalog.get_predictor_meta(trainer.predictor_id)
        assert predictor.view_id == trainer.view_id
        assert predictor.input_model == trainer.output_model


def test_local_materializer_bindings_reference_catalog_metadata() -> None:
    validate_local_materializer_bindings()

    assert {
        binding.catalog_id for binding in list_local_materializer_bindings()
    } == {"sc-inspection-patch-image-v1"}
