from __future__ import annotations

import pytest

import app.registrations  # noqa: F401
from app.core.registry import get_view
from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.executables import (
    RuntimeCapabilityCatalog,
    RuntimeOperation,
    RuntimeRouteDefinition,
    RuntimeRouter,
)
from app.modules.storage.domain.data_plane import DataPlaneSchemaRegistry
from app.modules.types import catalog
from app.modules.types.capabilities import (
    ModelContractRef,
    ViewContractRef,
)

VIEW = ViewContractRef("example_v1", "example.view.v1", "1")
MODEL = ModelContractRef("example.model.v1", "1")


def _route(operation: RuntimeOperation) -> RuntimeRouteDefinition:
    return RuntimeRouteDefinition(
        operation=operation,
        deployment=f"{operation.value}-deployment",
        resource_profile="gpu",
        owner="local_compat",
        missing_image_policy="fail",
        output_contract=(
            "trainer_model"
            if operation is RuntimeOperation.TRAIN
            else "predictions.v1"
        ),
    )


def test_type_catalog_only_aggregates_views() -> None:
    assert {view.id for view in catalog.list_views()} == {
        "image_input_v1",
        "labeled_image_v1",
        "patch_image_v1",
        "review_image_v1",
    }
    assert not hasattr(catalog, "list_trainers")
    assert not hasattr(catalog, "get_predictor_meta")


def test_runtime_router_unifies_metadata_callable_and_routes() -> None:
    router = RuntimeRouter()

    @router.trainer(
        id="trainer",
        name="Trainer",
        input_view=VIEW,
        output_model=MODEL,
        predictor_ids=("predictor",),
        algo_id="algo",
        algo_version="1",
        routes=(_route(RuntimeOperation.TRAIN),),
    )
    async def trainer(_ctx: object) -> None:
        return None

    @router.predictor(
        id="predictor",
        name="Predictor",
        input_view=VIEW,
        input_model=MODEL,
        algo_id="algo",
        algo_version="1",
        routes=(_route(RuntimeOperation.PREDICT),),
    )
    async def predictor(_ctx: object) -> None:
        return None

    runtime = RuntimeCapabilityCatalog((router,), known_views={VIEW.view_id: VIEW})
    registration = runtime.get_trainer("trainer")
    assert registration.callable is trainer
    assert registration.metadata.name == "Trainer"
    assert runtime.get_predictor("predictor").callable is predictor


def test_runtime_catalog_validates_pair_model_contract() -> None:
    router = RuntimeRouter()

    @router.trainer(
        id="trainer",
        name="Trainer",
        input_view=VIEW,
        output_model=MODEL,
        predictor_ids=("predictor",),
        algo_id="algo",
        algo_version="1",
        routes=(_route(RuntimeOperation.TRAIN),),
    )
    async def _trainer(_ctx: object) -> None:
        return None

    @router.predictor(
        id="predictor",
        name="Predictor",
        input_view=VIEW,
        input_model=ModelContractRef("other.model", "1"),
        algo_id="algo",
        algo_version="1",
        routes=(_route(RuntimeOperation.PREDICT),),
    )
    async def _predictor(_ctx: object) -> None:
        return None

    with pytest.raises(RuntimeError, match="same model contract"):
        RuntimeCapabilityCatalog((router,), known_views={VIEW.view_id: VIEW})


def test_multiple_predictors_require_explicit_selection() -> None:
    router = RuntimeRouter()

    @router.trainer(
        id="trainer",
        name="Trainer",
        input_view=VIEW,
        output_model=MODEL,
        predictor_ids=("predictor-a", "predictor-b"),
        algo_id="algo",
        algo_version="1",
        routes=(_route(RuntimeOperation.TRAIN),),
    )
    async def _trainer(_ctx: object) -> None:
        return None

    for predictor_id in ("predictor-a", "predictor-b"):

        async def _predictor(_ctx: object) -> None:
            return None

        router.predictor(
            id=predictor_id,
            name=predictor_id,
            input_view=VIEW,
            input_model=MODEL,
            algo_id="algo",
            algo_version="1",
            routes=(_route(RuntimeOperation.PREDICT),),
        )(_predictor)

    runtime = RuntimeCapabilityCatalog((router,), known_views={VIEW.view_id: VIEW})
    with pytest.raises(ValueError, match="select predictor_id explicitly"):
        runtime.resolve_predictor_id("trainer")
    assert (
        runtime.resolve_predictor_id(
            "trainer", requested_predictor_id="predictor-b"
        )
        == "predictor-b"
    )


def test_registered_view_rows_are_canonical_and_catalog_backed() -> None:
    for metadata in catalog.list_views():
        row_type = get_view(metadata.id)
        assert row_type is not None
        assert row_type.view_id == metadata.id
        assert row_type.view_name == metadata.name


def test_data_plane_schema_registry_covers_every_view_contract() -> None:
    registry = DataPlaneSchemaRegistry.default()
    for metadata in catalog.list_views():
        assert registry.get(*metadata.ref.key).names


def test_sc_runtime_catalog_is_validated_at_import() -> None:
    assert runtime_catalog.get_trainer("resnet50-sc-v1").metadata.view_id == (
        "patch_image_v1"
    )
