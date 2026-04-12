"""Prediction service for running models on datasets and storing results in the platform DB.

This module provides :class:`PredictionService` for:
- Running batch predictions on entire datasets
- Running single-sample predictions
- Storing prediction results in the platform DB
- Creating prediction review actions and saving reviewed annotations
"""
from __future__ import annotations

import base64
import importlib
import inspect
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel

from app.domain.models import (
    Annotation,
    AnnotationVersion,
    PlatformPrediction,
    PredictionCollection,
    PredictionCollectionItem,
    PredictionReviewAction,
)
from app.domain.types import TaskType
from app.presets.registry import PresetRegistry
from app.presets.runtime import DatasetRef, ModelRef, PredictContext, PredictResult as RuntimePredictResult
from app.services.compatibility import validate_model_prediction, validate_model_review
from app.services.embedding import EmbeddingClient
from app.services.inference_worker import InferenceWorkerClient
from app.services.llm import OpenAICompatibleLlmClient
from app.services.label_studio import (
    LabelStudioClient,
    LabelStudioError,
    platform_annotation_to_ls,
    platform_prediction_to_ls,
    platform_text_prediction_to_ls,
)

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.domain.models import Sample
    from app.repositories.sql_repository import SqlRepository
    from app.storage.interfaces import ArtifactStorage

logger = logging.getLogger(__name__)


class PredictionResult(BaseModel):
    """Result of a single prediction."""
    id: str | None = None
    sample_id: str
    predicted_label: str
    confidence: float | None
    all_scores: dict[str, float] | None = None
    model_id: str | None = None
    target: str | None = None
    model_version: str | None = None
    job_id: str | None = None
    created_at: datetime | None = None
    error: str | None = None


class BatchPredictionResult(BaseModel):
    """Result of running predictions on a batch of samples."""
    model_id: str
    dataset_id: str
    total_samples: int
    successful: int
    failed: int
    predictions: list[PredictionResult]
    started_at: datetime
    completed_at: datetime
    model_version: str | None = None


@dataclass
class PredictionRequest:
    """Request parameters for running predictions."""
    model_id: str
    dataset_id: str
    sample_ids: list[str] | None = None  # None = all samples in dataset
    model_version: str | None = None  # Tag for Label Studio filtering


class PredictionService:
    """Service for running model predictions and storing results in the platform DB.
    
    This service orchestrates:
    1. Fetching image data for samples
    2. Running real CLIP zero-shot classification via gRPC embedding service
    3. Storing predictions in the platform database
    """

    @staticmethod
    def _result_from_prediction(prediction: PlatformPrediction) -> PredictionResult:
        return PredictionResult(
            id=prediction.id,
            sample_id=prediction.sample_id,
            predicted_label=prediction.predicted_label,
            confidence=prediction.confidence,
            all_scores=prediction.all_scores,
            model_id=prediction.model_id,
            target=prediction.target,
            model_version=prediction.model_version,
            job_id=prediction.job_id,
            created_at=prediction.created_at,
            error=prediction.error,
        )

    def __init__(
        self,
        repository: SqlRepository,
        artifact_storage: ArtifactStorage,
        config: AppConfig,
        embedding_client: EmbeddingClient | None = None,
        llm_client: OpenAICompatibleLlmClient | None = None,
        inference_worker: InferenceWorkerClient | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_storage = artifact_storage
        self.config = config
        self._ls_client: LabelStudioClient | None = None
        self._embedding_client = embedding_client
        self._llm_client = llm_client
        self._inference_worker = inference_worker

    def _get_ls_client(self) -> LabelStudioClient:
        """Lazy initialization of Label Studio client."""
        if self._ls_client is None:
            ls_cfg = self.config.label_studio
            if not ls_cfg.url:
                raise ValueError("Label Studio URL not configured")
            self._ls_client = LabelStudioClient(
                url=ls_cfg.url,
                api_key=ls_cfg.api_key,
            )
        return self._ls_client

    def _get_embedding_client(self) -> EmbeddingClient:
        """Get the embedding client for inference."""
        if self._embedding_client is None:
            # Create a default client - in production this should be injected
            grpc_target = getattr(self.config, 'embedding_grpc_target', 'localhost:50051')
            self._embedding_client = EmbeddingClient(grpc_target=grpc_target)
        return self._embedding_client

    def _load_preset_registry(self) -> PresetRegistry:
        try:
            presets_dir = str(self.config.presets.dir)
        except Exception:
            presets_dir = "presets"
        root = Path(presets_dir)
        if not root.is_absolute():
            root = (Path(__file__).resolve().parents[2] / presets_dir).resolve()
        registry = PresetRegistry(str(root), strict=True)
        registry.load()
        return registry

    @staticmethod
    def _load_entrypoint(ref: str) -> Any:
        module_name, sep, attr_name = ref.partition(":")
        if sep != ":" or not module_name or not attr_name:
            raise ValueError(f"Invalid predict entrypoint reference: {ref}")
        module = importlib.import_module(module_name)
        return getattr(module, attr_name)

    async def _resolve_predictor(self, model, org_id: str, target: str = "image_classification") -> tuple[Any, PredictContext]:
        registry = self._load_preset_registry()
        preset_id = model.preset_id or model.preset_name or ""
        preset = registry.get_preset(preset_id)
        if preset is None and model.job_id:
            job = await self.repository.get_job(model.job_id, org_id=org_id)
            if job is not None:
                preset_id = job.preset_id
                preset = registry.get_preset(preset_id)
        if preset is None:
            raise ValueError(f"Preset not found for model/job: {model.id}")

        target_cfg = preset.predict.targets.get(target)
        entrypoint_ref = target_cfg.entrypoint if target_cfg is not None else preset.predict.entrypoint
        if not entrypoint_ref:
            raise ValueError(f"No predict entrypoint configured for preset: {preset.id}")

        entrypoint = self._load_entrypoint(entrypoint_ref)
        predictor = None
        if inspect.isclass(entrypoint):
            try:
                ctor = inspect.signature(entrypoint)
                ctor_kwargs = {
                    "embedding_client": self._get_embedding_client(),
                    "llm_client": self._llm_client,
                    "artifact_storage": self.artifact_storage,
                }
                accepts_kwargs = any(
                    param.kind == inspect.Parameter.VAR_KEYWORD
                    for param in ctor.parameters.values()
                )
                filtered_kwargs = {
                    key: value
                    for key, value in ctor_kwargs.items()
                    if accepts_kwargs or key in ctor.parameters
                }
                predictor = entrypoint(**filtered_kwargs)
            except (TypeError, ValueError):
                predictor = entrypoint()
        else:
            maybe_predictor = entrypoint
            if hasattr(maybe_predictor, "predict_single") and callable(getattr(maybe_predictor, "predict_single")):
                predictor = maybe_predictor

        if predictor is None:
            raise ValueError(
                f"Predict entrypoint must resolve to a Predictor class/instance with predict_single: {entrypoint_ref}"
            )

        dataset_ref = DatasetRef(dataset_id=model.dataset_id or "")
        model_ref = ModelRef(
            uri=model.uri,
            framework=str(model.metadata.get("framework", "")) if isinstance(model.metadata, dict) else "",
            architecture=str(model.metadata.get("architecture", "")) if isinstance(model.metadata, dict) else "",
            base_model=str(model.metadata.get("base_model", "")) if isinstance(model.metadata, dict) else "",
            format=model.format,
            metadata=model.metadata,
        )

        ctx = PredictContext(
            job_id=model.job_id,
            preset=preset,
            model_ref=model_ref,
            dataset_ref=dataset_ref,
            target=target,
        )
        return predictor, ctx

    async def _get_image_bytes(self, sample: Sample) -> bytes | None:
        """Fetch image bytes for a sample.
        
        Supports data URIs, s3://, and memory:// schemes.
        """
        if not sample.image_uris:
            return None
        
        uri = sample.image_uris[0]
        
        if uri.startswith("data:"):
            try:
                _, encoded = uri.split(",", 1)
                return base64.b64decode(encoded)
            except Exception as e:
                logger.warning(f"Failed to decode data URI for sample {sample.id}: {e}")
                return None
        elif uri.startswith("s3://") or uri.startswith("memory://"):
            try:
                return await self.artifact_storage.get_bytes(uri)
            except (FileNotFoundError, KeyError) as e:
                logger.warning(f"Failed to fetch image for sample {sample.id}: {e}")
                return None
        else:
            logger.warning(f"Unsupported URI scheme for sample {sample.id}: {uri[:20]}...")
            return None

    async def run_prediction(
        self,
        model_id: str,
        dataset_id: str,
        org_id: str,
        sample_ids: list[str] | None = None,
        model_version: str | None = None,
        target: str = "image_classification",
        prompt: str | None = None,
    ) -> BatchPredictionResult:
        """Run predictions on a dataset using a trained model.
        
        Parameters
        ----------
        model_id:
            ID of the model artifact to use for predictions.
        dataset_id:
            ID of the dataset to run predictions on.
        org_id:
            Organization ID for access control.
        sample_ids:
            Optional list of specific sample IDs. If None, runs on all samples.
        model_version:
            Optional version tag for Label Studio (for filtering predictions).
            
        Returns
        -------
        BatchPredictionResult
            Summary of prediction results including per-sample outcomes.
        """
        started_at = datetime.now(UTC)
        
        # Get model info
        model = await self.repository.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        
        # Get dataset info
        dataset = await self.repository.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        
        validate_model_prediction(dataset, model.metadata if isinstance(model.metadata, dict) else {}, target)
        label_space = dataset.task_spec.label_space
        
        # Get samples
        if sample_ids:
            samples = []
            for sid in sample_ids:
                sample = await self.repository.get_sample(sid)
                if sample and sample.dataset_id == dataset_id:
                    samples.append(sample)
        else:
            # Get all samples (paginated fetch)
            samples = []
            offset = 0
            batch_size = 100
            while True:
                batch, total = await self.repository.list_samples(
                    dataset_id, offset=offset, limit=batch_size
                )
                samples.extend(batch)
                offset += batch_size
                if offset >= total:
                    break
        
        # Generate model version tag
        version_tag = model_version or f"model-{model_id[:8]}"

        predictions: list[PredictionResult] = []
        successful = 0
        failed = 0
        
        if self._should_use_inference_worker():
            worker_results = await self._predict_via_worker(
                model=model,
                samples=samples,
                label_space=list(label_space),
                target=target,
                prompt=prompt,
            )
            worker_by_sample = {str(item.get("sample_id", "")): item for item in worker_results}
            for sample in samples:
                result = await self._prediction_result_from_worker(
                    sample=sample,
                    worker_result=worker_by_sample.get(sample.id, {"sample_id": sample.id, "error": "missing worker result"}),
                    model_id=model.id,
                    org_id=org_id,
                    model_version=version_tag,
                    target=target,
                )
                predictions.append(result)
                if result.error:
                    failed += 1
                else:
                    successful += 1
        else:
            predictor, predict_ctx = await self._resolve_predictor(model, org_id=org_id, target=target)
            predict_ctx.dataset_ref.label_space = list(label_space)
            if prompt:
                predict_ctx.dataset_ref.metadata["prompt"] = prompt
            await predictor.load_model(predict_ctx.model_ref)
            for sample in samples:
                result = await self._predict_sample(
                    sample=sample,
                    predictor=predictor,
                    predict_ctx=predict_ctx,
                    model_id=model.id,
                    org_id=org_id,
                    model_version=version_tag,
                    target=target,
                    prompt=prompt,
                )
                predictions.append(result)
                if result.error:
                    failed += 1
                else:
                    successful += 1
            await predictor.unload_model()

        completed_at = datetime.now(UTC)

        return BatchPredictionResult(
            model_id=model_id,
            dataset_id=dataset_id,
            total_samples=len(samples),
            successful=successful,
            failed=failed,
            predictions=predictions,
            started_at=started_at,
            completed_at=completed_at,
            model_version=version_tag,
        )

    def _should_use_inference_worker(self) -> bool:
        try:
            return str(self.config.app.env) != "test" and self._inference_worker is not None
        except Exception:
            return self._inference_worker is not None

    async def _predict_via_worker(
        self,
        *,
        model: Any,
        samples: list[Sample],
        label_space: list[str],
        target: str,
        prompt: str | None,
    ) -> list[dict[str, Any]]:
        if self._inference_worker is None:
            raise ValueError("Inference worker is not configured")
        model_bytes = await self.artifact_storage.get_bytes(model.uri)
        payload_samples: list[dict[str, Any]] = []
        for sample in samples:
            text_input = sample.metadata.get("text") if isinstance(sample.metadata, dict) else None
            question_input = prompt or (str(sample.metadata.get("question", "")) if isinstance(sample.metadata, dict) else "")
            image_bytes = await self._get_image_bytes(sample) if sample.image_uris else None
            payload_samples.append(
                {
                    "sample_id": sample.id,
                    "image_bytes": image_bytes,
                    "metadata": sample.metadata,
                    "image_uris": sample.image_uris,
                    "question": question_input,
                    "text": text_input,
                }
            )
        metadata = model.metadata if isinstance(model.metadata, dict) else {}
        return await self._inference_worker.predict_batch(
            model_id=model.id,
            model_uri=model.uri,
            model_format=model.format,
            model_metadata=metadata,
            model_bytes=model_bytes,
            target=target,
            label_space=label_space,
            samples=payload_samples,
        )

    async def _prediction_result_from_worker(
        self,
        *,
        sample: Sample,
        worker_result: dict[str, Any],
        model_id: str,
        org_id: str,
        model_version: str,
        target: str,
    ) -> PredictionResult:
        predicted_label = str(worker_result.get("label", ""))
        confidence_raw = worker_result.get("confidence")
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else None
        all_scores = worker_result.get("scores") if isinstance(worker_result.get("scores"), dict) else None
        runtime_error = worker_result.get("error")
        return await self._finalize_prediction(
            sample=sample,
            model_id=model_id,
            org_id=org_id,
            predicted_label=predicted_label,
            confidence=confidence,
            all_scores=all_scores,
            runtime_error=str(runtime_error) if runtime_error else None,
            model_version=model_version,
            target=target,
        )

    async def _finalize_prediction(
        self,
        *,
        sample: Sample,
        model_id: str,
        org_id: str,
        predicted_label: str,
        confidence: float | None,
        all_scores: dict[str, float] | None,
        runtime_error: str | None,
        model_version: str,
        target: str,
    ) -> PredictionResult:
        stored = await self.repository.create_platform_prediction(
            PlatformPrediction(
                org_id=org_id,
                dataset_id=sample.dataset_id,
                sample_id=sample.id,
                model_id=model_id,
                target=target,
                model_version=model_version,
                predicted_label=(predicted_label or "embedding") if target == "embedding" else predicted_label,
                confidence=confidence,
                all_scores=all_scores,
                error=str(runtime_error) if runtime_error else None,
                created_by="system",
            )
        )
        return self._result_from_prediction(stored)

    async def _predict_sample(
        self,
        sample: Sample,
        predictor: Any,
        predict_ctx: PredictContext,
        model_id: str,
        org_id: str,
        model_version: str,
        target: str,
        prompt: str | None = None,
    ) -> PredictionResult:
        """Run prediction on a single sample and store in the platform DB.
        
        Uses preset-runtime predictor dispatch.
        """
        text_input = sample.metadata.get("text") if isinstance(sample.metadata, dict) else None
        question_input = ""
        if prompt:
            question_input = prompt
        elif isinstance(sample.metadata, dict):
            question_input = str(sample.metadata.get("question", ""))
        image_bytes = await self._get_image_bytes(sample) if sample.image_uris else None
        if target == "vqa":
            if image_bytes is None:
                return PredictionResult(
                    id=None,
                    sample_id=sample.id,
                    predicted_label="",
                    confidence=None,
                    error="No image available for VQA prediction",
                )
            if not question_input:
                return PredictionResult(
                    id=None,
                    sample_id=sample.id,
                    predicted_label="",
                    confidence=None,
                    error="No prompt/question provided for VQA prediction",
                )
        elif image_bytes is None and text_input is None:
            return PredictionResult(
                id=None,
                sample_id=sample.id,
                predicted_label="",
                confidence=None,
                error="No usable prediction input (image or text)",
            )
        
        runtime_input: dict[str, Any] = {
            "sample_id": sample.id,
            "image_bytes": image_bytes,
            "metadata": sample.metadata,
            "image_uris": sample.image_uris,
            "question": question_input,
        }
        if text_input is not None:
            runtime_input["text"] = text_input

        # Run inference via runtime predictor
        try:
            runtime_pred: RuntimePredictResult = await predictor.predict_single(
                predict_ctx,
                runtime_input,
            )
            predicted_label = runtime_pred.label
            confidence = runtime_pred.confidence
            all_scores = runtime_pred.scores
            runtime_error = runtime_pred.metadata.get("error") if runtime_pred.metadata else None
            return await self._finalize_prediction(
                sample=sample,
                model_id=model_id,
                org_id=org_id,
                predicted_label=predicted_label,
                confidence=confidence,
                all_scores=all_scores,
                runtime_error=str(runtime_error) if runtime_error else None,
                model_version=model_version,
                target=target,
            )
        except Exception as e:
            logger.exception(f"Inference failed for sample {sample.id}")
            return PredictionResult(
                id=None,
                sample_id=sample.id,
                predicted_label="",
                confidence=None,
                error=f"Inference failed: {e}",
            )
        

    async def predict_single(
        self,
        model_id: str,
        sample_id: str,
        org_id: str,
        model_version: str | None = None,
        target: str = "image_classification",
        prompt: str | None = None,
    ) -> PredictionResult:
        """Run prediction on a single sample.
        
        Parameters
        ----------
        model_id:
            ID of the model artifact to use.
        sample_id:
            ID of the sample to predict.
        org_id:
            Organization ID for access control.
        model_version:
            Optional version tag for Label Studio.
            
        Returns
        -------
        PredictionResult
            Single prediction result.
        """
        # Get model info
        model = await self.repository.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        
        # Get sample
        sample = await self.repository.get_sample(sample_id)
        if sample is None:
            raise ValueError(f"Sample not found: {sample_id}")
        
        # Get dataset for label space
        dataset = await self.repository.get_dataset(sample.dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {sample.dataset_id}")
        validate_model_prediction(dataset, model.metadata if isinstance(model.metadata, dict) else {}, target)
        label_space = dataset.task_spec.label_space
        
        version_tag = model_version or f"model-{model_id[:8]}"
        if self._should_use_inference_worker():
            worker_results = await self._predict_via_worker(
                model=model,
                samples=[sample],
                label_space=list(label_space),
                target=target,
                prompt=prompt,
            )
            worker_result = worker_results[0] if worker_results else {"sample_id": sample.id, "error": "missing worker result"}
            return await self._prediction_result_from_worker(
                sample=sample,
                worker_result=worker_result,
                model_id=model.id,
                org_id=org_id,
                model_version=version_tag,
                target=target,
            )

        predictor, predict_ctx = await self._resolve_predictor(model, org_id=org_id, target=target)
        predict_ctx.dataset_ref.label_space = list(label_space)
        if prompt:
            predict_ctx.dataset_ref.metadata["prompt"] = prompt
        await predictor.load_model(predict_ctx.model_ref)
        result = await self._predict_sample(
            sample=sample,
            predictor=predictor,
            predict_ctx=predict_ctx,
            model_id=model.id,
            org_id=org_id,
            model_version=version_tag,
            target=target,
            prompt=prompt,
        )
        await predictor.unload_model()
        return result

    async def list_predictions_for_sample(
        self,
        sample_id: str,
        org_id: str,
        model_version: str | None = None,
    ) -> list[PredictionResult]:
        """List all predictions for a sample from the platform DB.
        
        Parameters
        ----------
        sample_id:
            Platform sample ID.
        org_id:
            Organization ID for access control.
            
        Returns
        -------
        list[dict]
            List of prediction objects from Label Studio.
        """
        sample = await self.repository.get_sample(sample_id)
        if sample is None:
            raise ValueError(f"Sample not found: {sample_id}")
        
        predictions = await self.repository.list_platform_predictions_for_sample(
            sample_id=sample_id,
            org_id=org_id,
            model_version=model_version,
        )
        return [self._result_from_prediction(prediction) for prediction in predictions]

    async def list_predictions_for_job(
        self,
        job_id: str,
        org_id: str,
    ) -> list[PredictionResult]:
        predictions = await self.repository.list_platform_predictions_for_job(job_id, org_id)
        return [self._result_from_prediction(prediction) for prediction in predictions]

    async def create_prediction_collection(
        self,
        dataset_id: str,
        model_id: str,
        org_id: str,
        created_by: str,
        prediction_ids: list[str],
        name: str,
        model_version: str | None = None,
        target: str = "image_classification",
        source_job_id: str | None = None,
    ) -> PredictionCollection:
        dataset = await self.repository.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")
        model = await self.repository.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        collection = await self.repository.create_prediction_collection(
            PredictionCollection(
                org_id=org_id,
                dataset_id=dataset_id,
                model_id=model_id,
                name=name,
                model_version=model_version,
                target=target,
                source_job_id=source_job_id,
                created_by=created_by,
            )
        )
        items: list[PredictionCollectionItem] = []
        for prediction_id in prediction_ids:
            prediction = await self.repository.get_platform_prediction(prediction_id, org_id=org_id)
            if prediction is None:
                raise ValueError(f"Prediction not found: {prediction_id}")
            if prediction.dataset_id != dataset_id:
                raise ValueError(f"Prediction {prediction_id} does not belong to dataset {dataset_id}")
            items.append(PredictionCollectionItem(collection_id=collection.id, prediction_id=prediction_id))
        await self.repository.add_prediction_collection_items(items)
        return collection

    async def list_prediction_collections(self, dataset_id: str, org_id: str) -> list[PredictionCollection]:
        return await self.repository.list_prediction_collections(dataset_id, org_id)

    async def sync_prediction_collection_to_label_studio(
        self,
        collection_id: str,
        org_id: str,
        sync_tag: str | None = None,
    ) -> tuple[PredictionCollection, int, int, list[str]]:
        collection = await self.repository.get_prediction_collection(collection_id, org_id=org_id)
        if collection is None:
            raise ValueError(f"Prediction collection not found: {collection_id}")
        dataset = await self.repository.get_dataset(collection.dataset_id, org_id)
        if dataset is None or dataset.ls_project_id is None:
            raise ValueError(f"Dataset not found or missing Label Studio project: {collection.dataset_id}")
        predictions = await self.repository.list_prediction_collection_predictions(collection_id, org_id)
        ls_client = self._get_ls_client()
        sync_tag_value = sync_tag or collection.sync_tag or f"sync-{collection.id[:8]}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        successful = 0
        failed = 0
        errors: list[str] = []
        for prediction in predictions:
            sample = await self.repository.get_sample(prediction.sample_id)
            if sample is None or sample.ls_task_id is None:
                failed += 1
                errors.append(f"sample {prediction.sample_id} has no Label Studio task")
                continue
            if prediction.error:
                failed += 1
                errors.append(f"prediction {prediction.id} has runtime error")
                continue
            try:
                if prediction.target == "vqa":
                    ls_result = platform_text_prediction_to_ls(prediction.predicted_label)
                else:
                    ls_result = platform_prediction_to_ls(prediction.predicted_label)
                await ls_client.create_prediction(
                    task_id=sample.ls_task_id,
                    result=ls_result,
                    model_version=sync_tag_value,
                    score=prediction.confidence,
                )
                successful += 1
            except LabelStudioError as exc:
                failed += 1
                errors.append(f"prediction {prediction.id}: {exc}")
        return collection.model_copy(update={"sync_tag": sync_tag_value}), successful, failed, errors

    # ------------------------------------------------------------------
    # Prediction review actions
    # ------------------------------------------------------------------

    async def create_review_action(
        self,
        dataset_id: str,
        model_id: str,
        org_id: str,
        created_by: str,
        model_version: str | None = None,
        collection_id: str | None = None,
        sync_tag: str | None = None,
    ) -> PredictionReviewAction:
        """Create a new prediction review action (a review session).

        Validates that the dataset and model exist before creating.
        """
        dataset = await self.repository.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")

        model = await self.repository.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")
        validate_model_review(dataset, model.metadata if isinstance(model.metadata, dict) else {})

        action = PredictionReviewAction(
            dataset_id=dataset_id,
            model_id=model_id,
            model_version=model_version,
            collection_id=collection_id,
            sync_tag=sync_tag,
            created_by=created_by,
        )
        return await self.repository.create_review_action(action)

    async def save_review_annotations(
        self,
        review_action_id: str,
        items: list[dict],
        created_by: str,
    ) -> tuple[list[Annotation], list[AnnotationVersion]]:
        """Save reviewed predictions as annotations.

        For each item in ``items`` (with keys: sample_id, predicted_label,
        final_label, confidence, prediction_id):
        1. Create LS annotation first (LS-first pattern).
        2. Create local Annotation.
        3. Create AnnotationVersion linking to the review action.

        Returns (annotations, annotation_versions).
        """
        action = await self.repository.get_review_action(review_action_id)
        if action is None:
            raise ValueError(f"Review action not found: {review_action_id}")

        ls_client = self._get_ls_client()

        annotations: list[Annotation] = []
        versions: list[AnnotationVersion] = []

        for item in items:
            sample_id: str = item["sample_id"]
            final_label: str = item["final_label"]
            predicted_label: str = item["predicted_label"]
            confidence: float | None = item.get("confidence")
            prediction_id: str | None = item.get("prediction_id")

            sample = await self.repository.get_sample(sample_id)
            if sample is None:
                logger.warning(f"Sample not found during review save: {sample_id}")
                continue

            # LS-first: create annotation in Label Studio
            if sample.ls_task_id:
                try:
                    ls_result = platform_annotation_to_ls(final_label)
                    await ls_client.create_annotation(sample.ls_task_id, ls_result)
                except LabelStudioError as e:
                    logger.warning(f"LS annotation failed for sample {sample_id}: {e}")
                    # Continue anyway — local annotation still valuable

            # Create local annotation
            ann = Annotation(
                sample_id=sample_id,
                label=final_label,
                created_by=created_by,
            )
            ann = await self.repository.create_annotation(ann)
            annotations.append(ann)

            # Create annotation version
            version = AnnotationVersion(
                review_action_id=review_action_id,
                annotation_id=ann.id,
                prediction_id=prediction_id,
                predicted_label=predicted_label,
                final_label=final_label,
                confidence=confidence,
            )
            versions.append(version)

        # Bulk-insert annotation versions
        if versions:
            versions = await self.repository.create_annotation_versions_bulk(versions)

        return annotations, versions
