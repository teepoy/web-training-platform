from __future__ import annotations

from app.modules.types.capabilities import (
    CapabilityBundle,
    ViewContractRef,
    ViewDefinition,
)

IMAGE_INPUT_V1 = ViewContractRef(
    view_id="image_input_v1",
    contract="image.input.v1",
    schema_version="1",
)
LABELED_IMAGE_V1 = ViewContractRef(
    view_id="labeled_image_v1",
    contract="image.labeled.v1",
    schema_version="1",
)
CORE_IMAGE_CAPABILITIES = CapabilityBundle(
    views=(
        ViewDefinition(
            ref=IMAGE_INPUT_V1,
            name="Image Input",
            is_annotation_view=False,
            row_type_path=(
                "app.modules.datasets.views.image_input.v1.schemas:ImageInputV1Row"
            ),
            arrow_schema_path=(
                "app.modules.storage.domain.data_plane.schemas:IMAGE_INPUT_V1_SCHEMA"
            ),
        ),
        ViewDefinition(
            ref=LABELED_IMAGE_V1,
            name="Labeled Image",
            is_annotation_view=True,
            row_type_path=(
                "app.modules.datasets.views.labeled_image.v1.schemas:LabeledImageV1Row"
            ),
            arrow_schema_path=(
                "app.modules.storage.domain.data_plane.schemas:LABELED_IMAGE_V1_SCHEMA"
            ),
        ),
    ),
)

__all__ = [
    "CORE_IMAGE_CAPABILITIES",
    "IMAGE_INPUT_V1",
    "LABELED_IMAGE_V1",
]
