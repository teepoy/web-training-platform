from __future__ import annotations

import pytest

import app.registrations  # noqa: F401
from app.core.registry import get_view
from app.modules.storage.domain.data_plane import DataPlaneSchemaRegistry
from app.modules.types import catalog
from app.modules.types.capabilities import (
    CapabilityBundle,
    CapabilityCatalog,
    MaterializerMetadata,
    ModelContractRef,
    PredictorMetadata,
    TrainerMetadata,
    ViewContractRef,
    ViewDefinition,
)

MODEL_V1 = ModelContractRef("example.model.v1", "1")


def _view(ref: ViewContractRef, name: str) -> ViewDefinition:
    return ViewDefinition(
        ref=ref,
        name=name,
        is_annotation_view=False,
        row_type_path=f"tests.example:{ref.view_id}",
        arrow_schema_path=f"tests.example:{ref.view_id}_schema",
    )


def test_catalog_aggregates_module_owned_capability_bundles() -> None:
    assert catalog.list_trainers() == catalog.SC_CAPABILITIES.trainers
    assert set(catalog.list_predictors()) == set(
        (
            *catalog.CORE_IMAGE_CAPABILITIES.predictors,
            *catalog.SC_CAPABILITIES.predictors,
        )
    )
    assert {view.id for view in catalog.list_views()} == {
        "image_input_v1",
        "labeled_image_v1",
        "box_detection_v1",
        "qa_input_v1",
        "patch_image_v1",
        "review_image_v1",
    }


def test_multiple_view_versions_can_coexist_and_pair_independently() -> None:
    view_v1 = ViewContractRef("example_v1", "example.view.v1", "1")
    view_v2 = ViewContractRef("example_v2", "example.view.v2", "2")
    capabilities = CapabilityCatalog(
        (
            CapabilityBundle(
                views=(
                    _view(view_v1, "Example v1"),
                    _view(view_v2, "Example v2"),
                ),
                trainers=(
                    TrainerMetadata(
                        "trainer-v1",
                        "Trainer v1",
                        view_v1,
                        MODEL_V1,
                        ("pred-v1",),
                    ),
                    TrainerMetadata(
                        "trainer-v2",
                        "Trainer v2",
                        view_v2,
                        MODEL_V1,
                        ("pred-v2",),
                    ),
                ),
                predictors=(
                    PredictorMetadata("pred-v1", "Predictor v1", view_v1, MODEL_V1),
                    PredictorMetadata("pred-v2", "Predictor v2", view_v2, MODEL_V1),
                ),
            ),
        )
    )

    assert capabilities.get_trainer("trainer-v1").input_view == view_v1
    assert capabilities.get_trainer("trainer-v2").input_view == view_v2


def test_trainer_predictor_pair_must_use_exact_view_version() -> None:
    view_v1 = ViewContractRef("example_v1", "example.view.v1", "1")
    view_v2 = ViewContractRef("example_v2", "example.view.v2", "2")

    with pytest.raises(ValueError, match="same versioned view contract"):
        CapabilityCatalog(
            (
                CapabilityBundle(
                    views=(
                        _view(view_v1, "Example v1"),
                        _view(view_v2, "Example v2"),
                    ),
                    trainers=(
                        TrainerMetadata(
                            "trainer-v1",
                            "Trainer v1",
                            view_v1,
                            MODEL_V1,
                            ("pred-v2",),
                        ),
                    ),
                    predictors=(
                        PredictorMetadata(
                            "pred-v2",
                            "Predictor v2",
                            view_v2,
                            MODEL_V1,
                        ),
                    ),
                ),
            )
        )


def test_trainer_predictor_pair_must_share_model_contract() -> None:
    view = ViewContractRef("example_v1", "example.view.v1", "1")
    other_model = ModelContractRef("example.other-model.v1", "1")

    with pytest.raises(ValueError, match="produces model contract"):
        CapabilityCatalog(
            (
                CapabilityBundle(
                    views=(_view(view, "Example"),),
                    trainers=(
                        TrainerMetadata(
                            "trainer",
                            "Trainer",
                            view,
                            MODEL_V1,
                            ("predictor",),
                        ),
                    ),
                    predictors=(
                        PredictorMetadata(
                            "predictor",
                            "Predictor",
                            view,
                            other_model,
                        ),
                    ),
                ),
            )
        )


def test_multiple_paired_predictors_require_explicit_selection() -> None:
    view = ViewContractRef("example_v1", "example.view.v1", "1")
    capabilities = CapabilityCatalog(
        (
            CapabilityBundle(
                views=(_view(view, "Example"),),
                trainers=(
                    TrainerMetadata(
                        "trainer",
                        "Trainer",
                        view,
                        MODEL_V1,
                        ("predictor-a", "predictor-b"),
                    ),
                ),
                predictors=(
                    PredictorMetadata(
                        "predictor-a", "Predictor A", view, MODEL_V1
                    ),
                    PredictorMetadata(
                        "predictor-b", "Predictor B", view, MODEL_V1
                    ),
                ),
            ),
        )
    )

    with pytest.raises(ValueError, match="must be selected explicitly"):
        capabilities.resolve_predictor_id("trainer")
    assert (
        capabilities.resolve_predictor_id(
            "trainer",
            requested_predictor_id="predictor-b",
        )
        == "predictor-b"
    )


def test_predictor_model_contract_validation_returns_metadata() -> None:
    predictor = catalog.validate_predictor_model_contract(
        "resnet50-sc-v1",
        model_contract="sc.resnet50.model.v1",
        model_schema_version="1",
    )

    assert predictor.id == "resnet50-sc-v1"


def test_predictor_model_contract_validation_rejects_mismatch() -> None:
    with pytest.raises(ValueError, match="is incompatible"):
        catalog.validate_predictor_model_contract(
            "resnet50-sc-v1",
            model_contract="sc.yolo.model.v1",
            model_schema_version="1",
        )


def test_materializer_selection_is_explicit_by_view_purpose_and_storage() -> None:
    matches = catalog.capabilities.materializers_for(
        "patch_image_v1",
        purpose="train",
        storage_mode="file_shard_sparse",
    )

    assert matches == (
        catalog.get_materializer_meta("sc-inspection-patch-image-v1"),
    )
    assert (
        catalog.capabilities.materializers_for(
            "review_image_v1",
            purpose="predict",
            storage_mode="file_shard_sparse",
        )
        == ()
    )


def test_materializer_must_reference_registered_view_version() -> None:
    registered = ViewContractRef("example_v1", "example.view.v1", "1")
    undeclared = ViewContractRef("example_v2", "example.view.v2", "2")

    with pytest.raises(KeyError, match="Unknown view capability"):
        CapabilityCatalog(
            (
                CapabilityBundle(
                    views=(_view(registered, "Example"),),
                    materializers=(
                        MaterializerMetadata(
                            id="materializer",
                            output_view=undeclared,
                            purposes=("train",),
                            formats=("parquet",),
                            storage_modes=("db_full",),
                        ),
                    ),
                ),
            )
        )


def test_registered_view_rows_are_canonical_and_catalog_backed() -> None:
    for metadata in catalog.list_views():
        row_type = get_view(metadata.id)
        assert row_type is not None
        assert row_type.view_id == metadata.id
        assert row_type.view_name == metadata.name
        assert row_type.is_annotation_view is metadata.is_annotation_view
        assert (
            f"{row_type.__module__}:{row_type.__name__}"
            == metadata.row_type_path
        )


def test_data_plane_schema_registry_covers_every_catalog_view_contract() -> None:
    registry = DataPlaneSchemaRegistry.default()

    for metadata in catalog.list_views():
        schema = registry.get(*metadata.ref.key)
        assert schema.names
