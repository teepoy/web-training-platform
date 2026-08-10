from __future__ import annotations

from app.modules.types.capabilities import (
    CapabilityBundle,
    ModelContractRef,
    ViewContractRef,
    ViewDefinition,
)

SC_PATCH_IMAGE_V1 = ViewContractRef(
    view_id="patch_image_v1",
    contract="sc.patch_image.v1",
    schema_version="1",
)
SC_REVIEW_IMAGE_V1 = ViewContractRef(
    view_id="review_image_v1",
    contract="sc.review_image.v1",
    schema_version="1",
)
SC_YOLO_MODEL_V1 = ModelContractRef(
    contract="sc.yolo.model.v1",
    schema_version="1",
)

SC_CAPABILITIES = CapabilityBundle(
    views=(
        ViewDefinition(
            ref=SC_PATCH_IMAGE_V1,
            name="Patch Image",
            is_annotation_view=False,
            row_type_path=(
                "app.modules.sc.views.patch_image.v1.schemas:ScPatchImageV1Row"
            ),
            arrow_schema_path=(
                "app.modules.storage.domain.data_plane.schemas:SC_PATCH_IMAGE_V1_SCHEMA"
            ),
            image_roles=("patch_template", "patch_defective"),
            label_columns=("label",),
        ),
        ViewDefinition(
            ref=SC_REVIEW_IMAGE_V1,
            name="Review Image",
            is_annotation_view=False,
            row_type_path=(
                "app.modules.sc.views.review_image.v1.schemas:ScReviewImageV1Row"
            ),
            arrow_schema_path=(
                "app.modules.storage.domain.data_plane.schemas:"
                "SC_REVIEW_IMAGE_V1_SCHEMA"
            ),
        ),
    ),
)

__all__ = [
    "SC_CAPABILITIES",
    "SC_PATCH_IMAGE_V1",
    "SC_REVIEW_IMAGE_V1",
    "SC_YOLO_MODEL_V1",
]
