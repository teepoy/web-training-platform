from __future__ import annotations

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
from app.modules.types.registrations.core_image import (
    BOX_DETECTION_V1,
    CORE_IMAGE_CAPABILITIES,
    IMAGE_INPUT_V1,
    LABELED_IMAGE_V1,
    QA_INPUT_V1,
)
from app.modules.types.registrations.sc import (
    SC_CAPABILITIES,
    SC_PATCH_IMAGE_V1,
    SC_REVIEW_IMAGE_V1,
)

capabilities = CapabilityCatalog((CORE_IMAGE_CAPABILITIES, SC_CAPABILITIES))


def list_views() -> tuple[ViewDefinition, ...]:
    return capabilities.list_views()


def list_materializers() -> tuple[MaterializerMetadata, ...]:
    return capabilities.list_materializers()


def list_trainers() -> tuple[TrainerMetadata, ...]:
    return capabilities.list_trainers()


def list_predictors() -> tuple[PredictorMetadata, ...]:
    return capabilities.list_predictors()


def list_trainer_ids() -> list[str]:
    return [trainer.id for trainer in list_trainers()]


def list_predictor_ids() -> list[str]:
    return [predictor.id for predictor in list_predictors()]


def get_view_meta(view_id: str) -> ViewDefinition:
    return capabilities.get_view(view_id)


def get_materializer_meta(materializer_id: str) -> MaterializerMetadata:
    return capabilities.get_materializer(materializer_id)


def get_trainer_meta(trainer_id: str) -> TrainerMetadata:
    return capabilities.get_trainer(trainer_id)


def get_predictor_meta(predictor_id: str) -> PredictorMetadata:
    return capabilities.get_predictor(predictor_id)


def resolve_predictor_id(
    trainer_id: str,
    *,
    requested_predictor_id: str | None = None,
) -> str:
    return capabilities.resolve_predictor_id(
        trainer_id,
        requested_predictor_id=requested_predictor_id,
    )


def validate_predictor_model_contract(
    predictor_id: str,
    *,
    model_contract: object,
    model_schema_version: object,
) -> PredictorMetadata:
    return capabilities.validate_predictor_model_contract(
        predictor_id,
        model_contract=model_contract,
        model_schema_version=model_schema_version,
    )


__all__ = [
    "BOX_DETECTION_V1",
    "CORE_IMAGE_CAPABILITIES",
    "CapabilityBundle",
    "IMAGE_INPUT_V1",
    "LABELED_IMAGE_V1",
    "MaterializerMetadata",
    "ModelContractRef",
    "PredictorMetadata",
    "QA_INPUT_V1",
    "SC_CAPABILITIES",
    "SC_PATCH_IMAGE_V1",
    "SC_REVIEW_IMAGE_V1",
    "TrainerMetadata",
    "ViewContractRef",
    "ViewDefinition",
    "capabilities",
    "get_materializer_meta",
    "get_predictor_meta",
    "get_trainer_meta",
    "get_view_meta",
    "list_materializers",
    "list_predictor_ids",
    "list_predictors",
    "list_trainer_ids",
    "list_trainers",
    "list_views",
    "resolve_predictor_id",
    "validate_predictor_model_contract",
]
