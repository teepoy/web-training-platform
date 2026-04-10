"""Prediction service for running models on datasets and storing results in Label Studio.

This module provides :class:`PredictionService` for:
- Running batch predictions on entire datasets
- Running single-sample predictions
- Storing prediction results in Label Studio

Uses CLIP zero-shot classification via the gRPC embedding service for real inference.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.services.embedding import EmbeddingClient
from app.services.label_studio import (
    LabelStudioClient,
    LabelStudioError,
    platform_prediction_to_ls,
)

if TYPE_CHECKING:
    from app.core.config import AppConfig
    from app.domain.models import Sample
    from app.repositories.sql_repository import SqlRepository
    from app.storage.interfaces import ArtifactStorage

logger = logging.getLogger(__name__)


class PredictionResult(BaseModel):
    """Result of a single prediction."""
    sample_id: str
    ls_task_id: int | None
    predicted_label: str
    confidence: float | None
    all_scores: dict[str, float] | None = None
    ls_prediction_id: int | None = None
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
    """Service for running model predictions and storing results in Label Studio.
    
    This service orchestrates:
    1. Fetching image data for samples
    2. Running real CLIP zero-shot classification via gRPC embedding service
    3. Storing predictions in Label Studio via the predictions API
    """

    def __init__(
        self,
        repository: SqlRepository,
        artifact_storage: ArtifactStorage,
        config: AppConfig,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_storage = artifact_storage
        self.config = config
        self._ls_client: LabelStudioClient | None = None
        self._embedding_client = embedding_client

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
        
        if dataset.ls_project_id is None:
            raise ValueError(f"Dataset {dataset_id} has no Label Studio project")
        
        # Get label space from dataset task spec
        label_space = dataset.task_spec.label_space
        if not label_space:
            raise ValueError(f"Dataset {dataset_id} has no label space defined")
        
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
        
        # Run predictions
        predictions: list[PredictionResult] = []
        successful = 0
        failed = 0
        
        ls_client = self._get_ls_client()
        embedding_client = self._get_embedding_client()
        
        for sample in samples:
            result = await self._predict_sample(
                sample=sample,
                label_space=label_space,
                model_version=version_tag,
                ls_client=ls_client,
                embedding_client=embedding_client,
            )
            predictions.append(result)
            if result.error:
                failed += 1
            else:
                successful += 1
        
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

    async def _predict_sample(
        self,
        sample: Sample,
        label_space: list[str],
        model_version: str,
        ls_client: LabelStudioClient,
        embedding_client: EmbeddingClient,
    ) -> PredictionResult:
        """Run prediction on a single sample and store in Label Studio.
        
        Uses CLIP zero-shot classification for real inference.
        """
        # Check if sample has Label Studio task ID
        if sample.ls_task_id is None:
            return PredictionResult(
                sample_id=sample.id,
                ls_task_id=None,
                predicted_label="",
                confidence=None,
                error="Sample has no Label Studio task ID",
            )
        
        # Get image bytes
        image_bytes = await self._get_image_bytes(sample)
        if image_bytes is None:
            return PredictionResult(
                sample_id=sample.id,
                ls_task_id=sample.ls_task_id,
                predicted_label="",
                confidence=None,
                error="Could not fetch image for sample",
            )
        
        # Run real inference via CLIP zero-shot classification
        try:
            predicted_label, confidence, all_scores = await embedding_client.classify_image(
                image_bytes=image_bytes,
                labels=label_space,
            )
        except Exception as e:
            logger.exception(f"Inference failed for sample {sample.id}")
            return PredictionResult(
                sample_id=sample.id,
                ls_task_id=sample.ls_task_id,
                predicted_label="",
                confidence=None,
                error=f"Inference failed: {e}",
            )
        
        # Convert to Label Studio format
        ls_result = platform_prediction_to_ls(predicted_label)
        
        # Store prediction in Label Studio
        try:
            ls_prediction = await ls_client.create_prediction(
                task_id=sample.ls_task_id,
                result=ls_result,
                model_version=model_version,
                score=confidence,
            )
            return PredictionResult(
                sample_id=sample.id,
                ls_task_id=sample.ls_task_id,
                predicted_label=predicted_label,
                confidence=confidence,
                all_scores=all_scores,
                ls_prediction_id=ls_prediction.get("id"),
            )
        except LabelStudioError as e:
            return PredictionResult(
                sample_id=sample.id,
                ls_task_id=sample.ls_task_id,
                predicted_label=predicted_label,
                confidence=confidence,
                all_scores=all_scores,
                error=f"Failed to store prediction in Label Studio: {e}",
            )

    async def predict_single(
        self,
        model_id: str,
        sample_id: str,
        org_id: str,
        model_version: str | None = None,
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
        
        label_space = dataset.task_spec.label_space
        if not label_space:
            raise ValueError(f"Dataset {sample.dataset_id} has no label space defined")
        
        version_tag = model_version or f"model-{model_id[:8]}"
        ls_client = self._get_ls_client()
        embedding_client = self._get_embedding_client()
        
        return await self._predict_sample(
            sample=sample,
            label_space=label_space,
            model_version=version_tag,
            ls_client=ls_client,
            embedding_client=embedding_client,
        )

    async def list_predictions_for_sample(
        self,
        sample_id: str,
        org_id: str,
    ) -> list[dict]:
        """List all predictions for a sample from Label Studio.
        
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
        
        if sample.ls_task_id is None:
            return []
        
        ls_client = self._get_ls_client()
        return await ls_client.list_predictions(sample.ls_task_id)
