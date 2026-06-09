"""Prediction service for running models on datasets and storing results in the platform DB.

This module provides :class:`PredictionService` for:
- Running batch predictions on entire datasets
- Running single-sample predictions
- Storing prediction results in the platform DB
- Creating prediction review actions and saving reviewed annotations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from omegaconf import DictConfig
from pydantic import BaseModel

from app.core.prefect_runner import PrefectFlowRunError, submit_flow_run_and_wait
from app.shared.api.schemas import (
    Annotation,
    AnnotationVersion,
    DatasetStorageMode,
    PlatformPrediction,
    PredictionCollection,
    PredictionCollectionItem,
    PredictionReviewAction,
)
from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.port.local import SampleRow
from app.modules.prediction.domain.repository import PredictionRepository
from app.shared.application.compatibility import (
    validate_model_prediction,
    validate_model_review,
)
from app.shared.domain.protocols import (
    LabelStudioClient,
    LlmClient,
)
from app.shared.infrastructure.label_studio.client import (
    LabelStudioClient as RealLabelStudioClient,
)
from app.shared.infrastructure.label_studio.client import (
    LabelStudioError,
    platform_annotation_to_ls,
    platform_prediction_to_ls,
    platform_text_prediction_to_ls,
)


from app.shared.domain.protocols import ArtifactStorage

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
        repository: PredictionRepository,
        artifact_storage: ArtifactStorage,
        config: DictConfig,
        dataset_storage_factory: DatasetStorageFactory,
        llm_client: LlmClient | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_storage = artifact_storage
        self.config = config
        self._ls_client: LabelStudioClient | None = None
        self._llm_client = llm_client
        self._dataset_storage_factory = dataset_storage_factory

    def _get_ls_client(self) -> LabelStudioClient:
        """Lazy initialization of Label Studio client."""
        if self._ls_client is None:
            ls_cfg = self.config.label_studio
            if not ls_cfg.url:
                raise ValueError("Label Studio URL not configured")
            self._ls_client = RealLabelStudioClient(
                url=ls_cfg.url,
                api_key=ls_cfg.api_key,
            )
        return self._ls_client

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

        Submits a ``prediction-predict-job`` Prefect flow run and waits for
        completion.  The flow handles sample loading, inference dispatch, and
        result persistence for all storage modes (``db_full`` and
        ``file_shard_sparse``).

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

        # ── Validation (fast local checks before submitting the flow) ──
        model = await self.repository.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")

        dataset = await self.repository.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")

        validate_model_prediction(
            dataset, model.metadata if isinstance(model.metadata, dict) else {}, target
        )

        version_tag = model_version or f"model-{model_id[:8]}"

        # ── Submit Prefect flow run ────────────────────────────────────
        job_id = str(uuid4())

        try:
            flow_result = await submit_flow_run_and_wait(
                deployment_name="prediction-predict-job",
                parameters={
                    "job_id": job_id,
                    "dataset_id": dataset_id,
                    "model_id": model_id,
                    "org_id": org_id,
                    "created_by": "system",
                    "target": target,
                    "model_version": version_tag,
                    "sample_ids": sample_ids,
                    "prompt": prompt,
                },
                timeout_seconds=300.0,
            )
        except PrefectFlowRunError as exc:
            raise ValueError(f"Prediction flow failed: {exc}") from exc

        completed_at = datetime.now(UTC)

        # ── Map flow result to BatchPredictionResult ───────────────────
        predictions_raw = flow_result.get("predictions", [])
        predictions: list[PredictionResult] = []
        if isinstance(predictions_raw, list):
            for p in predictions_raw:
                if isinstance(p, dict):
                    predictions.append(PredictionResult(**p))

        return BatchPredictionResult(
            model_id=model_id,
            dataset_id=dataset_id,
            total_samples=int(flow_result.get("total_samples", 0)),
            successful=int(flow_result.get("successful", 0)),
            failed=int(flow_result.get("failed", 0)),
            predictions=predictions,
            started_at=started_at,
            completed_at=completed_at,
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
    ) -> PredictionResult:
        """Run prediction on a single sample.

        Submits a ``prediction-predict-job`` Prefect flow run scoped to a
        single sample and returns the result.

        Parameters
        ----------
        model_id:
            ID of the model artifact to use.
        dataset_id:
            ID of the dataset containing the sample.
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
        model = await self.repository.get_model(model_id, org_id)
        if model is None:
            raise ValueError(f"Model not found: {model_id}")

        dataset = await self.repository.get_dataset(dataset_id, org_id)
        if dataset is None:
            raise ValueError(f"Dataset not found: {dataset_id}")

        validate_model_prediction(
            dataset, model.metadata if isinstance(model.metadata, dict) else {}, target
        )

        version_tag = model_version or f"model-{model_id[:8]}"
        job_id = str(uuid4())

        try:
            flow_result = await submit_flow_run_and_wait(
                deployment_name="prediction-predict-job",
                parameters={
                    "job_id": job_id,
                    "dataset_id": dataset_id,
                    "model_id": model_id,
                    "org_id": org_id,
                    "created_by": "system",
                    "target": target,
                    "model_version": version_tag,
                    "sample_ids": [sample_id],
                    "prompt": prompt,
                },
                timeout_seconds=300.0,
            )
        except PrefectFlowRunError as exc:
            raise ValueError(f"Prediction flow failed: {exc}") from exc

        predictions_raw = flow_result.get("predictions", [])
        if isinstance(predictions_raw, list) and predictions_raw:
            first = predictions_raw[0]
            if isinstance(first, dict):
                return PredictionResult(**first)

        raise ValueError(f"Prediction flow returned no result for sample {sample_id}")

    async def list_predictions_for_sample(
        self,
        *,
        sample_id: str,
        org_id: str,
        dataset_id: str | None = None,
        model_version: str | None = None,
    ) -> list[PredictionResult]:
        """List all predictions for a sample from the platform DB.

        Parameters
        ----------
        sample_id:
            Platform sample ID.
        org_id:
            Organization ID for access control.
        dataset_id:
            Dataset ID (optional; when provided, validates dataset existence).
        """
        if dataset_id is not None:
            dataset = await self.repository.get_dataset(dataset_id, org_id)
            if dataset is None:
                raise ValueError(f"Dataset not found: {dataset_id}")

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
        offset: int = 0,
        limit: int = 1000,
    ) -> list[PredictionResult]:
        job = await self.repository.get_prediction_job(job_id, org_id)
        if job is not None:
            dataset = await self.repository.get_dataset(job.dataset_id, org_id)
            if (
                dataset is not None
                and dataset.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE
            ):
                sparse_results = await self._list_sparse_predictions_for_job(
                    job_id=job_id,
                    org_id=org_id,
                    dataset_id=job.dataset_id,
                    offset=offset,
                    limit=limit,
                )
                if sparse_results:
                    return sparse_results
                # Fallback: parquet shards missing, query SQL platform_predictions
        predictions = await self.repository.list_platform_predictions_for_job(
            job_id, org_id, offset=offset, limit=limit
        )
        return [self._result_from_prediction(prediction) for prediction in predictions]

    async def _list_sparse_predictions_for_job(
        self,
        *,
        job_id: str,
        org_id: str,
        dataset_id: str,
        offset: int,
        limit: int,
    ) -> list[PredictionResult]:
        import io as _io
        import json as _json

        import pyarrow.parquet as _pq

        prefix = f"datasets/{org_id}/{dataset_id}/predictions/{job_id}"
        try:
            manifest_uri = await self._resolve_job_result_uri(prefix)
            manifest_bytes = await self.artifact_storage.get_bytes(manifest_uri)
        except (FileNotFoundError, ValueError, OSError):
            return []

        manifest = _json.loads(manifest_bytes)
        total = manifest.get("total_processed", 0)
        shards_meta = sorted(manifest.get("shards", []), key=lambda s: s["shard_index"])

        if not shards_meta or total == 0:
            return []

        sample_id_by_locator = await self._build_reverse_locator_index(
            dataset_id, org_id
        )

        results: list[PredictionResult] = []
        cumulative = 0
        remaining = limit

        for shard_meta in shards_meta:
            shard_row_count = shard_meta["row_count"]
            shard_end = cumulative + shard_row_count

            if offset >= shard_end:
                cumulative = shard_end
                continue

            local_offset = max(0, offset - cumulative)
            local_limit = min(remaining, shard_row_count - local_offset)

            parquet_bytes = await self.artifact_storage.get_bytes(
                shard_meta["shard_uri"]
            )
            table = _pq.read_table(_io.BytesIO(parquet_bytes))
            sliced = table.slice(local_offset, local_limit)

            shard_index = shard_meta["shard_index"]
            col = sliced.column
            row_indices = (
                col("row_index").to_pylist()
                if "row_index" in sliced.column_names
                else list(range(local_offset, local_offset + sliced.num_rows))
            )
            pred_labels = col("predicted_label").to_pylist()
            confidences = col("confidence").to_pylist()
            errors = (
                col("error").to_pylist()
                if "error" in sliced.column_names
                else [None] * sliced.num_rows
            )
            all_scores_raw = (
                col("all_scores").to_pylist()
                if "all_scores" in sliced.column_names
                else [None] * sliced.num_rows
            )

            for i in range(sliced.num_rows):
                row_idx = row_indices[i]
                sample_id = (
                    sample_id_by_locator.get((shard_index, row_idx))
                    or f"{shard_index}:{row_idx}"
                )

                scores_raw = all_scores_raw[i]
                scores: dict[str, float] | None = None
                if isinstance(scores_raw, str) and scores_raw:
                    try:
                        scores = _json.loads(scores_raw)
                    except (_json.JSONDecodeError, TypeError):
                        pass

                results.append(
                    PredictionResult(
                        sample_id=str(sample_id),
                        predicted_label=str(pred_labels[i] or ""),
                        confidence=(
                            float(confidences[i])
                            if confidences[i] is not None
                            else None
                        ),
                        all_scores=scores,
                        error=errors[i],
                    )
                )

            remaining -= local_limit
            cumulative = shard_end

            if remaining <= 0:
                break

        return results

    async def _resolve_job_result_uri(self, prefix: str) -> str:
        tmp_key = f"{prefix}/job_result.json.__tmp_discovery__"
        tmp_uri = await self.artifact_storage.put_bytes(
            object_name=tmp_key, data=b"", content_type="application/json"
        )
        await self.artifact_storage.delete(tmp_uri)
        return tmp_uri.replace(".__tmp_discovery__", "")

    async def _build_reverse_locator_index(
        self, dataset_id: str, org_id: str
    ) -> dict[tuple[int, int], str]:
        try:
            from platform_runtime.sparse import DatasetPayloadStore

            store = DatasetPayloadStore(self.artifact_storage)
            manifest = await store.get_manifest(dataset_id, org_id)
        except (FileNotFoundError, ValueError, OSError):
            return {}

        reverse: dict[tuple[int, int], str] = {}
        for sample_id, locator in manifest.sample_index.items():
            reverse[(locator.shard_index, locator.row_index)] = sample_id
        return reverse

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
            prediction = await self.repository.get_platform_prediction(
                prediction_id, org_id=org_id
            )
            if prediction is None:
                raise ValueError(f"Prediction not found: {prediction_id}")
            if prediction.dataset_id != dataset_id:
                raise ValueError(
                    f"Prediction {prediction_id} does not belong to dataset {dataset_id}"
                )
            items.append(
                PredictionCollectionItem(
                    collection_id=collection.id, prediction_id=prediction_id
                )
            )
        await self.repository.add_prediction_collection_items(items)
        return collection

    async def list_prediction_collections(
        self, dataset_id: str, org_id: str
    ) -> list[PredictionCollection]:
        return await self.repository.list_prediction_collections(dataset_id, org_id)

    async def sync_prediction_collection_to_label_studio(
        self,
        collection_id: str,
        org_id: str,
        sync_tag: str | None = None,
    ) -> tuple[PredictionCollection, int, int, list[str]]:
        collection = await self.repository.get_prediction_collection(
            collection_id, org_id=org_id
        )
        if collection is None:
            raise ValueError(f"Prediction collection not found: {collection_id}")
        dataset = await self.repository.get_dataset(collection.dataset_id, org_id)
        if dataset is None or dataset.ls_project_id is None:
            raise ValueError(
                f"Dataset not found or missing Label Studio project: {collection.dataset_id}"
            )
        predictions = await self.repository.list_prediction_collection_predictions(
            collection_id, org_id
        )
        ls_client = self._get_ls_client()
        sync_tag_value = (
            sync_tag
            or collection.sync_tag
            or f"sync-{collection.id[:8]}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        )
        successful = 0
        failed = 0
        errors: list[str] = []

        sample_ids = [p.sample_id for p in predictions]
        sample_map: dict[str, SampleRow | None] = {}
        storage = await self._dataset_storage_factory.open(
            dataset_id=collection.dataset_id, org_id=org_id
        )
        rows = await storage.get_samples_batch(sample_ids)
        for i, sid in enumerate(sample_ids):
            sample_map[sid] = rows[i]

        for prediction in predictions:
            sid = prediction.sample_id
            ls_task_id: int | None = None
            sample_row = sample_map.get(sid)
            if sample_row is not None:
                ls_task_id = sample_row.ls_task_id
            else:
                sample_row = await storage.get_sample(sid)
                if sample_row is not None and sample_row.ls_task_id is not None:
                    ls_task_id = sample_row.ls_task_id

            if ls_task_id is None:
                failed += 1
                errors.append(f"sample {prediction.sample_id} has no Label Studio task")
                continue
            if prediction.error:
                failed += 1
                errors.append(f"prediction {prediction.id} has runtime error")
                continue
            try:
                if prediction.target == "vqa":
                    ls_result = platform_text_prediction_to_ls(
                        prediction.predicted_label
                    )
                else:
                    ls_result = platform_prediction_to_ls(prediction.predicted_label)
                await ls_client.create_prediction(
                    task_id=ls_task_id,
                    result=ls_result,
                    model_version=sync_tag_value,
                    score=prediction.confidence,
                )
                successful += 1
            except LabelStudioError as exc:
                failed += 1
                errors.append(f"prediction {prediction.id}: {exc}")
        return (
            collection.model_copy(update={"sync_tag": sync_tag_value}),
            successful,
            failed,
            errors,
        )

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
        validate_model_review(
            dataset, model.metadata if isinstance(model.metadata, dict) else {}
        )

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

        sample_ids = [str(item["sample_id"]) for item in items]
        sample_map: dict[str, SampleRow | None] = {}
        storage = await self._dataset_storage_factory.open(
            dataset_id=action.dataset_id, org_id=None
        )
        rows = await storage.get_samples_batch(sample_ids)
        for i, sid in enumerate(sample_ids):
            sample_map[sid] = rows[i]

        for item in items:
            sample_id: str = item["sample_id"]
            final_label: str = item["final_label"]
            predicted_label: str = item["predicted_label"]
            confidence: float | None = item.get("confidence")
            prediction_id: str | None = item.get("prediction_id")

            sample_row = sample_map.get(sample_id)
            ls_task_id: int | None = None
            if sample_row is not None:
                ls_task_id = sample_row.ls_task_id
            else:
                sample_row = await storage.get_sample(sample_id)
                if sample_row is not None:
                    ls_task_id = sample_row.ls_task_id
            if ls_task_id is None:
                logger.warning(
                    f"No LS task found for sample during review save: {sample_id}"
                )
                continue

            if ls_task_id:
                try:
                    ls_result = platform_annotation_to_ls(final_label)
                    await ls_client.create_annotation(ls_task_id, ls_result)
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
