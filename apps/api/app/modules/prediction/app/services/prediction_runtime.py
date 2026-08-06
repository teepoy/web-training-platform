from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from injector import inject

from app.core.prefect_runner import PrefectFlowRunError, submit_flow_run_and_wait
from app.modules.datasets.port.dataset_reader import DatasetReader
from app.modules.datasets.port.local import validate_predictor_for_dataset
from app.modules.models.port.local import ModelCatalogPort
from app.modules.prediction.domain.results import (
    BatchPredictionResult,
    PredictionResult,
)
from app.modules.prediction.domain.submission import PredictionJobCommand
from app.modules.prediction.app.services.submission_parameters import (
    prediction_workflow_parameters,
)
from app.modules.runtime.app.services.deployment_seed import (
    PREDICTION_RUNTIME_DEPLOYMENT,
)
from app.modules.runtime.catalog import runtime_catalog
from app.shared.application.compatibility import validate_model_prediction


class PredictionRuntimeService:
    """Run the synchronous compatibility surface through a routed Prefect flow."""

    @inject
    def __init__(
        self,
        dataset_reader: DatasetReader,
        model_catalog: ModelCatalogPort,
    ) -> None:
        self._dataset_reader = dataset_reader
        self._model_catalog = model_catalog

    async def run_prediction(
        self,
        model_id: str,
        dataset_id: str,
        org_id: str,
        sample_ids: list[str] | None = None,
        model_version: str | None = None,
        target: str = "image_classification",
        prompt: str | None = None,
        predictor_id: str | None = None,
    ) -> BatchPredictionResult:
        started_at = datetime.now(UTC)
        flow_result, version_tag = await self._run_prediction_flow(
            model_id=model_id,
            dataset_id=dataset_id,
            org_id=org_id,
            sample_ids=sample_ids,
            model_version=model_version,
            target=target,
            prompt=prompt,
            predictor_id=predictor_id,
        )
        predictions = self._parse_predictions(flow_result)
        return BatchPredictionResult(
            model_id=model_id,
            dataset_id=dataset_id,
            total_samples=int(flow_result.get("total_samples", 0)),
            successful=int(flow_result.get("successful", 0)),
            failed=int(flow_result.get("failed", 0)),
            predictions=predictions,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            model_version=version_tag,
        )

    async def predict_single(
        self,
        *,
        model_id: str,
        dataset_id: str,
        sample_id: str,
        org_id: str,
        model_version: str | None = None,
        target: str = "image_classification",
        prompt: str | None = None,
        predictor_id: str | None = None,
    ) -> PredictionResult:
        flow_result, _version_tag = await self._run_prediction_flow(
            model_id=model_id,
            dataset_id=dataset_id,
            org_id=org_id,
            sample_ids=[sample_id],
            model_version=model_version,
            target=target,
            prompt=prompt,
            predictor_id=predictor_id,
        )
        predictions = self._parse_predictions(flow_result)
        if not predictions:
            raise ValueError(
                f"Prediction flow returned no result for sample {sample_id}"
            )
        return predictions[0]

    @staticmethod
    def _parse_predictions(flow_result: dict[str, Any]) -> list[PredictionResult]:
        predictions_raw = flow_result.get("predictions")
        if not isinstance(predictions_raw, list):
            raise ValueError("Prediction flow returned an invalid predictions payload")
        if any(not isinstance(item, dict) for item in predictions_raw):
            raise ValueError("Prediction flow returned a non-object prediction item")
        return [PredictionResult.model_validate(item) for item in predictions_raw]

    async def _run_prediction_flow(
        self,
        *,
        model_id: str,
        dataset_id: str,
        org_id: str,
        sample_ids: list[str] | None,
        model_version: str | None,
        target: str,
        prompt: str | None,
        predictor_id: str | None,
    ) -> tuple[dict[str, Any], str]:
        model = await self._model_catalog.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        dataset = await self._dataset_reader.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        validate_model_prediction(
            dataset,
            model.metadata if isinstance(model.metadata, dict) else {},
            target,
        )
        trainer_id = model.trainer_id or model.trainer_name or ""
        if not trainer_id:
            raise ValueError(f"Model '{model_id}' has no associated predictor")
        predictor_id = runtime_catalog.resolve_predictor_id(
            trainer_id,
            requested_predictor_id=predictor_id,
        )
        model_metadata = model.metadata if isinstance(model.metadata, dict) else {}
        runtime_catalog.validate_predictor_model_contract(
            predictor_id,
            model_contract=model_metadata.get("model_contract"),
            model_schema_version=model_metadata.get("model_schema_version"),
        )
        validate_predictor_for_dataset(
            predictor_id=predictor_id,
            view_types=dataset.view_types,
        )
        version_tag = model_version or f"model-{model_id[:8]}"
        command = PredictionJobCommand(
            dataset_id=dataset_id,
            model_id=model_id,
            org_id=org_id,
            created_by="system",
            target=target,
            model_version=version_tag,
            sample_ids=tuple(sample_ids) if sample_ids is not None else None,
            prompt=prompt,
            predictor_id=predictor_id,
        )
        try:
            flow_result = await submit_flow_run_and_wait(
                deployment_name=PREDICTION_RUNTIME_DEPLOYMENT.deployment_name,
                parameters=prediction_workflow_parameters(
                    command,
                    job_id=str(uuid4()),
                    predictor_id=predictor_id,
                ),
                timeout_seconds=300.0,
            )
        except PrefectFlowRunError as exc:
            raise ValueError(f"Prediction flow failed: {exc}") from exc
        if not isinstance(flow_result, dict):
            raise ValueError("Prediction flow returned an invalid result payload")
        return flow_result, version_tag
