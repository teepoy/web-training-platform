from __future__ import annotations

from app.modules.types.capabilities import (
    CapabilityBundle,
    CapabilityCatalog,
    ModelContractRef,
    ViewContractRef,
    ViewDefinition,
)
from app.modules.types.registrations.core_image import (
    CORE_IMAGE_CAPABILITIES,
    IMAGE_INPUT_V1,
    LABELED_IMAGE_V1,
)
from app.modules.sc.capabilities import (
    SC_CAPABILITIES,
    SC_PATCH_IMAGE_V1,
    SC_REVIEW_IMAGE_V1,
)

capabilities = CapabilityCatalog((CORE_IMAGE_CAPABILITIES, SC_CAPABILITIES))


def list_views() -> tuple[ViewDefinition, ...]:
    return capabilities.list_views()


def get_view_meta(view_id: str) -> ViewDefinition:
    return capabilities.get_view(view_id)


__all__ = [
    "CORE_IMAGE_CAPABILITIES",
    "CapabilityBundle",
    "IMAGE_INPUT_V1",
    "LABELED_IMAGE_V1",
    "ModelContractRef",
    "SC_CAPABILITIES",
    "SC_PATCH_IMAGE_V1",
    "SC_REVIEW_IMAGE_V1",
    "ViewContractRef",
    "ViewDefinition",
    "capabilities",
    "get_view_meta",
    "list_views",
]
