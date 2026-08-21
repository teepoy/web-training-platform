from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.sc.data_provider.schemas import ScSamplingProgramRequest
from app.modules.sc.domain.prediction_export import (
    ScKlarfVersion,
    ScPredictionExportFormat,
    ScPredictionExportResultSource,
)
from app.modules.sc.schemas import ScWorkflowSampleFilter


class ScPredictionExportSamplingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    program: ScSamplingProgramRequest
    seed: int = Field(ge=0)
    extra_filter: ScWorkflowSampleFilter | None = None


class ScPredictionExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: ScPredictionExportFormat
    result_source: ScPredictionExportResultSource = (
        ScPredictionExportResultSource.FINAL_CLASS
    )
    klarf_version: ScKlarfVersion | None = None
    include_images: bool = False
    sampling: ScPredictionExportSamplingRequest | None = None

    @model_validator(mode="after")
    def validate_klarf_version_scope(self) -> ScPredictionExportRequest:
        if (
            self.format is ScPredictionExportFormat.PARQUET
            and self.klarf_version is not None
        ):
            raise ValueError(
                "klarf_version is available only for KLARF and ZIP exports"
            )
        if self.format is ScPredictionExportFormat.PARQUET and self.include_images:
            raise ValueError(
                "include_images is available only for KLARF and ZIP exports"
            )
        return self


class ScCollectionPredictionExportRequest(ScPredictionExportRequest):
    member_ids: list[str] = Field(min_length=1)


class ScPredictionExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str
    format: ScPredictionExportFormat
    rows: int
    sampled: bool
    filename: str
    klarf_version: ScKlarfVersion | None
