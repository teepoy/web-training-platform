from __future__ import annotations

from app.modules.types.capabilities import (
    CapabilityBundle,
    MaterializerMetadata,
    ModelContractRef,
    PredictorMetadata,
    TrainerMetadata,
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
SC_RESNET_MODEL_V1 = ModelContractRef(
    contract="sc.resnet50.model.v1",
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
    materializers=(
        MaterializerMetadata(
            id="sc-inspection-patch-image-v1",
            output_view=SC_PATCH_IMAGE_V1,
            purposes=("train", "predict"),
            formats=("parquet",),
            storage_modes=("db_full", "file_shard_sparse"),
        ),
    ),
    trainers=(
        TrainerMetadata(
            id="resnet50-sc-v1",
            name="ResNet-50 SC Defect Classifier",
            input_view=SC_PATCH_IMAGE_V1,
            output_model=SC_RESNET_MODEL_V1,
            predictor_ids=("resnet50-sc-v1",),
        ),
        TrainerMetadata(
            id="yolo-sc-v1",
            name="YOLO SC Detection Trainer",
            input_view=SC_PATCH_IMAGE_V1,
            output_model=SC_YOLO_MODEL_V1,
            predictor_ids=("yolo-sc-v1",),
        ),
    ),
    predictors=(
        PredictorMetadata(
            id="resnet50-sc-v1",
            name="ResNet-50 SC Defect Prediction",
            input_view=SC_PATCH_IMAGE_V1,
            input_model=SC_RESNET_MODEL_V1,
        ),
        PredictorMetadata(
            id="yolo-sc-v1",
            name="YOLO SC Detection Predictor",
            input_view=SC_PATCH_IMAGE_V1,
            input_model=SC_YOLO_MODEL_V1,
        ),
    ),
)

__all__ = [
    "SC_CAPABILITIES",
    "SC_PATCH_IMAGE_V1",
    "SC_RESNET_MODEL_V1",
    "SC_REVIEW_IMAGE_V1",
    "SC_YOLO_MODEL_V1",
]
