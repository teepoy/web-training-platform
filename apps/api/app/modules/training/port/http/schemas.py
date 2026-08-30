from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.training.domain.submission import (
    TrainAndPredictCommand,
    TrainingJobCommand,
)
from app.shared.api.schemas import TrainingJob


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateTrainingJobRequest(_StrictRequest):
    dataset_id: str | None = Field(default=None, min_length=1)
    collection_id: str | None = Field(default=None, min_length=1)
    collection_revision_id: str | None = Field(default=None, min_length=1)
    trainer_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_data_source(self) -> CreateTrainingJobRequest:
        self._data_source()
        return self

    def _data_source(self) -> None:
        from app.shared.domain.data_source import RuntimeDataSourceRef

        RuntimeDataSourceRef.from_fields(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
        )

    def to_command(self, *, org_id: str, created_by: str) -> TrainingJobCommand:
        return TrainingJobCommand(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
            trainer_id=self.trainer_id,
            org_id=org_id,
            created_by=created_by,
        )


class SampleSetFilterCondition(_StrictRequest):
    filter_type: Literal["set"] = Field(alias="filterType")
    values: list[float | str]
    exclude: bool = False


class SampleRangeFilterCondition(_StrictRequest):
    filter_type: Literal["number"] = Field(alias="filterType")
    type: Literal["inRange"]
    filter: float
    filter_to: float = Field(alias="filterTo")


class SampleFilterItemRequest(_StrictRequest):
    kind: Literal["condition"]
    field: str = Field(min_length=1)
    condition: SampleSetFilterCondition | SampleRangeFilterCondition


class SampleFilterGroupRequest(_StrictRequest):
    kind: Literal["group"]
    combinator: Literal["and", "or"]
    items: list[SampleFilterItemRequest | SampleFilterGroupRequest] = Field(
        min_length=1
    )


class SampleFilterRequest(_StrictRequest):
    combinator: Literal["and", "or"]
    items: list[SampleFilterItemRequest | SampleFilterGroupRequest] = Field(
        min_length=1
    )


class TrainAndPredictRequest(_StrictRequest):
    dataset_id: str | None = Field(default=None, min_length=1)
    collection_id: str | None = Field(default=None, min_length=1)
    collection_revision_id: str | None = Field(default=None, min_length=1)
    trainer_id: str = Field(min_length=1)
    target: str = Field(default="image_classification", min_length=1)
    model_version: str | None = None
    sample_ids: list[str] | None = Field(default=None, min_length=1)
    collection_member_ids: list[str] | None = Field(default=None, min_length=1)
    sample_filter: SampleFilterRequest | None = None
    prompt: str | None = None
    predictor_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_sample_selection(self) -> TrainAndPredictRequest:
        from app.shared.domain.data_source import RuntimeDataSourceRef

        RuntimeDataSourceRef.from_fields(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
        )
        if self.sample_ids is not None and self.sample_filter is not None:
            raise ValueError("sample_ids and sample_filter are mutually exclusive")
        return self

    def to_command(self, *, org_id: str, created_by: str) -> TrainAndPredictCommand:
        return TrainAndPredictCommand(
            dataset_id=self.dataset_id,
            collection_id=self.collection_id,
            collection_revision_id=self.collection_revision_id,
            trainer_id=self.trainer_id,
            org_id=org_id,
            created_by=created_by,
            target=self.target,
            model_version=self.model_version,
            sample_ids=tuple(self.sample_ids) if self.sample_ids is not None else None,
            collection_member_ids=(
                tuple(self.collection_member_ids)
                if self.collection_member_ids is not None
                else None
            ),
            sample_filter=(
                self.sample_filter.model_dump(by_alias=True)
                if self.sample_filter is not None
                else None
            ),
            prompt=self.prompt,
            predictor_id=self.predictor_id,
        )


class TrainAndPredictResponse(BaseModel):
    train_job: TrainingJob
    workflow_run_id: str


class MarkLeftResponse(BaseModel):
    marked: bool
