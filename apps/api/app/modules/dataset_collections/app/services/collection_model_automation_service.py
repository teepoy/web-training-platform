from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timezone
import logging
from uuid import uuid4

from injector import inject

from app.modules.dataset_collections.domain.errors import (
    DatasetCollectionNotFoundError,
    DatasetCollectionPermissionError,
    DatasetCollectionValidationError,
)
from app.modules.dataset_collections.domain.models import (
    CollectionPredictionBatch,
    CollectionPredictionBatchItem,
    CollectionPredictionCoverage,
    CollectionPredictionObservation,
    DatasetCollection,
    DatasetCollectionRevision,
    PredictionCoverageStatus,
)
from app.modules.dataset_collections.domain.repository import (
    DatasetCollectionRepository,
)
from app.modules.dataset_collections.port.local.protocols import (
    CollectionAutomationAdmissionPort,
    DatasetCollectionManagementPort,
)
from app.modules.models.port.local import ModelCatalogPort
from app.modules.datasets.port.local import DatasetRevisionReaderPort
from app.modules.prediction.domain.submission import (
    PredictionJobCommand,
    PredictionSubmissionOrigin,
)
from app.modules.prediction.port.local import PredictionExecutionPort
from app.modules.runtime.catalog import runtime_catalog
from app.shared.api.schemas import JobStatus, Model


_logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CollectionModelAutomationService:
    @inject
    def __init__(
        self,
        repository: DatasetCollectionRepository,
        model_catalog: ModelCatalogPort,
        prediction_execution: PredictionExecutionPort,
        dataset_revisions: DatasetRevisionReaderPort,
    ) -> None:
        self._repository = repository
        self._model_catalog = model_catalog
        self._prediction_execution = prediction_execution
        self._dataset_revisions = dataset_revisions

    async def set_default_model(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_binding_version: int,
        model_id: str | None,
    ) -> DatasetCollection:
        collection = await self._require_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        normalized_model_id = model_id.strip() if model_id is not None else None
        if normalized_model_id == "":
            raise DatasetCollectionValidationError(
                "invalid_default_model", "Default model ID must not be empty"
            )
        if normalized_model_id is not None:
            model = await self._model_catalog.get_org_model(normalized_model_id, org_id)
            if model is None:
                raise DatasetCollectionValidationError(
                    "default_model_not_owned",
                    "Default model must belong to the same organization as the Collection",
                )
            self._validate_model_compatibility(collection, model)
        return await self._repository.set_default_model(
            collection_id,
            org_id,
            expected_binding_version=expected_binding_version,
            model_id=normalized_model_id,
        )

    async def list_coverage(
        self,
        collection_id: str,
        org_id: str,
        *,
        revision_id: str | None = None,
    ) -> list[CollectionPredictionCoverage]:
        collection = await self._require_collection(collection_id, org_id)
        revision = await self._resolve_revision(
            collection_id, org_id, revision_id=revision_id
        )
        entries = await self._revision_entries(revision, org_id)
        observations = await self._repository.list_prediction_observations(
            collection_id,
            org_id,
            tuple(entry["dataset_id"] for entry in entries),
        )
        by_member = self._observations_by_member(observations)
        return [
            self._coverage_for_entry(
                entry,
                default_model_id=collection.default_model_id,
                observations=by_member.get(entry["member_id"], ()),
            )
            for entry in entries
        ]

    async def predict_new_members(
        self,
        collection_id: str,
        revision_id: str,
        org_id: str,
        actor_id: str,
    ) -> CollectionPredictionBatch | None:
        collection = await self._require_collection(collection_id, org_id)
        if collection.default_model_id is None:
            return None
        existing = self._batch_for_request(
            await self._repository.list_prediction_batches(collection_id, org_id),
            kind="incremental",
            request_id=revision_id,
        )
        if existing is not None:
            return existing[0]
        revision = await self._resolve_revision(
            collection_id, org_id, revision_id=revision_id
        )
        await self._require_current_revision(revision, org_id)
        revisions = await self._repository.list_revisions(collection_id, org_id)
        previous = next(
            (
                candidate
                for candidate in revisions
                if candidate.status == "ready"
                and candidate.revision_number < revision.revision_number
            ),
            None,
        )
        previous_member_ids = {
            entry["member_id"]
            for entry in await self._revision_entries(previous, org_id)
        }
        new_entries = [
            entry
            for entry in await self._revision_entries(revision, org_id)
            if entry["member_id"] not in previous_member_ids
        ]
        eligible = await self._without_exact_prediction(
            collection,
            org_id,
            new_entries,
        )
        if not eligible:
            return None
        return await self._create_and_dispatch_batch(
            collection=collection,
            revision=revision,
            org_id=org_id,
            actor_id=actor_id,
            kind="incremental",
            request_id=revision.id,
            entries=eligible,
        )

    async def create_reconciliation_batch(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        revision_id: str,
        expected_default_model_id: str,
        request_id: str,
        dataset_ids: tuple[str, ...],
    ) -> tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]:
        collection = await self._require_collection(collection_id, org_id)
        self._require_owner(collection, actor_id)
        if not request_id.strip():
            raise DatasetCollectionValidationError(
                "request_id_required", "A request ID is required"
            )
        if not dataset_ids or any(not item.strip() for item in dataset_ids):
            raise DatasetCollectionValidationError(
                "datasets_required", "Select one or more Datasets to predict"
            )
        if len(set(dataset_ids)) != len(dataset_ids):
            raise DatasetCollectionValidationError(
                "duplicate_dataset_selection", "A Dataset may only be selected once"
            )
        existing = self._batch_for_request(
            await self._repository.list_prediction_batches(collection_id, org_id),
            kind="reconciliation",
            request_id=request_id.strip(),
        )
        if existing is not None:
            batch, items = existing
            if (
                batch.collection_revision_id != revision_id
                or batch.model_id != expected_default_model_id
                or {item.dataset_id for item in items} != set(dataset_ids)
            ):
                raise DatasetCollectionValidationError(
                    "request_id_conflict",
                    "This request ID was already used with different prediction inputs",
                )
            return batch, items
        if collection.default_model_id is None:
            raise DatasetCollectionValidationError(
                "default_model_required",
                "Choose a default model before running prediction",
            )
        if collection.default_model_id != expected_default_model_id:
            raise DatasetCollectionValidationError(
                "default_model_changed",
                "The Collection default model changed; review the selection again",
            )
        revision = await self._resolve_revision(
            collection_id, org_id, revision_id=revision_id
        )
        await self._require_current_revision(revision, org_id)
        coverage = await self.list_coverage(
            collection_id, org_id, revision_id=revision.id
        )
        coverage_by_dataset = {item.dataset_id: item for item in coverage}
        missing = sorted(set(dataset_ids) - coverage_by_dataset.keys())
        if missing:
            raise DatasetCollectionValidationError(
                "datasets_not_in_revision",
                f"Datasets are not members of the selected Revision: {missing}",
            )
        already_current = sorted(
            dataset_id
            for dataset_id in dataset_ids
            if coverage_by_dataset[dataset_id].status
            is PredictionCoverageStatus.CURRENT
        )
        if already_current:
            raise DatasetCollectionValidationError(
                "prediction_already_current",
                f"Datasets already use the current default model: {already_current}",
            )
        entries_by_dataset = {
            entry["dataset_id"]: entry
            for entry in await self._revision_entries(revision, org_id)
        }
        entries = [entries_by_dataset[dataset_id] for dataset_id in dataset_ids]
        eligible = await self._without_exact_prediction(collection, org_id, entries)
        if len(eligible) != len(entries):
            raise DatasetCollectionValidationError(
                "prediction_already_running",
                "Prediction is already current, queued, or running for one or more "
                "selected Datasets",
            )
        batch = await self._create_and_dispatch_batch(
            collection=collection,
            revision=revision,
            org_id=org_id,
            actor_id=actor_id,
            kind="reconciliation",
            request_id=request_id.strip(),
            entries=eligible,
        )
        result = await self.get_batch(batch.id, org_id)
        return result

    async def retry_batch(
        self,
        batch_id: str,
        org_id: str,
        *,
        actor_id: str,
    ) -> tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]:
        batch, items = await self.get_batch(batch_id, org_id)
        collection = await self._require_collection(batch.collection_id, org_id)
        self._require_owner(collection, actor_id)
        retryable = [item for item in items if item.status in {"failed", "cancelled"}]
        if not retryable:
            raise DatasetCollectionValidationError(
                "no_failed_predictions", "This batch has no failed predictions to retry"
            )
        await self._dispatch_items(
            batch,
            retryable,
            org_id=org_id,
            actor_id=actor_id,
            submission_origin=PredictionSubmissionOrigin.MANUAL,
        )
        await self._refresh_batch_status(batch.id, org_id)
        return await self.get_batch(batch.id, org_id)

    async def get_batch(
        self,
        batch_id: str,
        org_id: str,
    ) -> tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]:
        result = await self._repository.get_prediction_batch(batch_id, org_id)
        if result is None:
            raise DatasetCollectionNotFoundError(
                "Collection prediction batch not found"
            )
        batch, items = result
        return replace(batch, status=self._derive_batch_status(items)), items

    async def list_batches(
        self,
        collection_id: str,
        org_id: str,
    ) -> list[tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]]:
        await self._require_collection(collection_id, org_id)
        batches = await self._repository.list_prediction_batches(collection_id, org_id)
        return [
            (replace(batch, status=self._derive_batch_status(items)), items)
            for batch, items in batches
        ]

    async def _create_and_dispatch_batch(
        self,
        *,
        collection: DatasetCollection,
        revision: DatasetCollectionRevision,
        org_id: str,
        actor_id: str,
        kind: str,
        request_id: str,
        entries: list[dict[str, str]],
    ) -> CollectionPredictionBatch:
        assert collection.default_model_id is not None
        now = _utcnow()
        batch = CollectionPredictionBatch(
            id=str(uuid4()),
            collection_id=collection.id,
            collection_revision_id=revision.id,
            model_id=collection.default_model_id,
            kind=kind,
            request_id=request_id,
            status="pending",
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        items = tuple(
            CollectionPredictionBatchItem(
                id=str(uuid4()),
                batch_id=batch.id,
                member_id=entry["member_id"],
                dataset_id=entry["dataset_id"],
                dataset_revision_id=entry["dataset_revision_id"],
                prediction_job_id=None,
                status="pending",
                attempt_count=0,
                error_detail=None,
                created_at=now,
                updated_at=now,
            )
            for entry in entries
        )
        (
            persisted,
            persisted_items,
            created,
        ) = await self._repository.create_or_get_prediction_batch(batch, items, org_id)
        if created:
            await self._dispatch_items(
                persisted,
                persisted_items,
                org_id=org_id,
                actor_id=actor_id,
                submission_origin=(
                    PredictionSubmissionOrigin.AUTOMATION
                    if kind == "incremental"
                    else PredictionSubmissionOrigin.MANUAL
                ),
            )
            await self._refresh_batch_status(persisted.id, org_id)
        return persisted

    async def _dispatch_items(
        self,
        batch: CollectionPredictionBatch,
        items: Iterable[CollectionPredictionBatchItem],
        *,
        org_id: str,
        actor_id: str,
        submission_origin: PredictionSubmissionOrigin,
    ) -> None:
        for item in items:
            try:
                job = await self._prediction_execution.submit_job(
                    PredictionJobCommand(
                        dataset_id=item.dataset_id,
                        collection_id=batch.collection_id,
                        collection_revision_id=batch.collection_revision_id,
                        model_id=batch.model_id,
                        org_id=org_id,
                        created_by=actor_id,
                        collection_prediction_batch_id=batch.id,
                        collection_member_id=item.member_id,
                        submission_origin=submission_origin,
                    )
                )
            except Exception as exc:
                await self._repository.update_prediction_batch_item(
                    item.id,
                    prediction_job_id=None,
                    status="failed",
                    error_detail=str(exc),
                    increment_attempt=True,
                )
                continue
            await self._repository.update_prediction_batch_item(
                item.id,
                prediction_job_id=job.id,
                status=job.status.value,
                error_detail=None,
                increment_attempt=True,
            )

    async def _refresh_batch_status(self, batch_id: str, org_id: str) -> None:
        _batch, items = await self.get_batch(batch_id, org_id)
        status = self._derive_batch_status(items)
        await self._repository.update_prediction_batch_status(batch_id, status)

    async def _without_exact_prediction(
        self,
        collection: DatasetCollection,
        org_id: str,
        entries: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        assert collection.default_model_id is not None
        observations = await self._repository.list_prediction_observations(
            collection.id,
            org_id,
            tuple(entry["dataset_id"] for entry in entries),
        )
        expected_revision_by_member = {
            entry["member_id"]: entry["dataset_revision_id"] for entry in entries
        }
        exact = {
            (observation.member_id, observation.dataset_id)
            for observation in observations
            if observation.model_id == collection.default_model_id
            and observation.status
            in {
                JobStatus.QUEUED.value,
                JobStatus.RUNNING.value,
                JobStatus.COMPLETED.value,
            }
            and observation.member_id is not None
            and observation.dataset_revision_id
            == expected_revision_by_member.get(observation.member_id)
        }
        return [
            entry
            for entry in entries
            if (entry["member_id"], entry["dataset_id"]) not in exact
        ]

    async def _require_collection(
        self, collection_id: str, org_id: str
    ) -> DatasetCollection:
        collection = await self._repository.get_collection(collection_id, org_id)
        if collection is None:
            raise DatasetCollectionNotFoundError("Dataset collection not found")
        return collection

    async def _resolve_revision(
        self,
        collection_id: str,
        org_id: str,
        *,
        revision_id: str | None,
    ) -> DatasetCollectionRevision:
        revision = (
            await self._repository.get_revision(collection_id, revision_id, org_id)
            if revision_id is not None
            else await self._repository.get_current_revision(collection_id, org_id)
        )
        if revision is None or revision.status != "ready":
            raise DatasetCollectionValidationError(
                "revision_required", "Save a ready Revision before running prediction"
            )
        return revision

    async def _require_current_revision(
        self,
        revision: DatasetCollectionRevision,
        org_id: str,
    ) -> None:
        current = await self._repository.get_current_revision(
            revision.collection_id, org_id
        )
        if current is None or current.id != revision.id:
            raise DatasetCollectionValidationError(
                "revision_changed",
                "The current Collection Revision changed; review prediction coverage again",
            )

    async def _revision_entries(
        self,
        revision: DatasetCollectionRevision | None,
        org_id: str,
    ) -> list[dict[str, str]]:
        if revision is None:
            return []
        identities: list[tuple[str, str]] = []
        for raw in revision.members:
            member_id = raw.get("member_id")
            dataset_id = raw.get("source_dataset_id")
            if (
                not isinstance(member_id, str)
                or not member_id
                or not isinstance(dataset_id, str)
                or not dataset_id
            ):
                raise DatasetCollectionValidationError(
                    "invalid_revision_membership",
                    "Revision member identity is incomplete",
                )
            identities.append((member_id, dataset_id))
        current = await self._dataset_revisions.list_current(
            tuple(dataset_id for _, dataset_id in identities), org_id
        )
        missing = [
            dataset_id for _, dataset_id in identities if dataset_id not in current
        ]
        if missing:
            raise DatasetCollectionValidationError(
                "dataset_revision_required",
                f"Current Dataset revisions are unavailable: {missing}",
            )
        entries: list[dict[str, str]] = []
        for member_id, dataset_id in identities:
            entries.append(
                {
                    "member_id": member_id,
                    "dataset_id": dataset_id,
                    "dataset_revision_id": current[dataset_id].id,
                }
            )
        return entries

    @staticmethod
    def _observations_by_member(
        observations: Iterable[CollectionPredictionObservation],
    ) -> dict[str, tuple[CollectionPredictionObservation, ...]]:
        grouped: dict[str, list[CollectionPredictionObservation]] = {}
        for observation in observations:
            if observation.member_id is None:
                continue
            grouped.setdefault(observation.member_id, []).append(observation)
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    def _batch_for_request(
        batches: list[
            tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]]
        ],
        *,
        kind: str,
        request_id: str,
    ) -> tuple[CollectionPredictionBatch, list[CollectionPredictionBatchItem]] | None:
        return next(
            (
                item
                for item in batches
                if item[0].kind == kind and item[0].request_id == request_id
            ),
            None,
        )

    @staticmethod
    def _derive_batch_status(items: list[CollectionPredictionBatchItem]) -> str:
        statuses = {item.status for item in items}
        if not statuses:
            return "pending"
        if statuses <= {JobStatus.COMPLETED.value}:
            return "completed"
        if statuses <= {JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
            return "failed"
        if statuses & {JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
            return "partial"
        if statuses & {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
            return "submitted"
        return "pending"

    @staticmethod
    def _coverage_for_entry(
        entry: dict[str, str],
        *,
        default_model_id: str | None,
        observations: tuple[CollectionPredictionObservation, ...],
    ) -> CollectionPredictionCoverage:
        successful = next(
            (
                observation
                for observation in observations
                if observation.status == JobStatus.COMPLETED.value
            ),
            None,
        )
        active = next(
            (
                observation
                for observation in observations
                if observation.status
                in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}
            ),
            None,
        )
        if successful is None or default_model_id is None:
            status = PredictionCoverageStatus.NOT_PREDICTED
        elif successful.model_id != default_model_id:
            status = PredictionCoverageStatus.MODEL_MISMATCH
        elif successful.dataset_revision_id != entry["dataset_revision_id"]:
            status = PredictionCoverageStatus.DATA_OUTDATED
        else:
            status = PredictionCoverageStatus.CURRENT
        return CollectionPredictionCoverage(
            member_id=entry["member_id"],
            dataset_id=entry["dataset_id"],
            expected_dataset_revision_id=entry["dataset_revision_id"],
            status=status,
            default_model_id=default_model_id,
            latest_prediction_job_id=(
                successful.prediction_job_id if successful is not None else None
            ),
            latest_prediction_model_id=(
                successful.model_id if successful is not None else None
            ),
            latest_prediction_dataset_revision_id=(
                successful.dataset_revision_id if successful is not None else None
            ),
            latest_prediction_status=(
                successful.status if successful is not None else None
            ),
            active_prediction_job_id=(
                active.prediction_job_id if active is not None else None
            ),
            active_prediction_status=(active.status if active is not None else None),
        )

    @staticmethod
    def _validate_model_compatibility(
        collection: DatasetCollection,
        model: Model,
    ) -> None:
        trainer_id = model.trainer_id or model.trainer_name or ""
        if not trainer_id:
            raise DatasetCollectionValidationError(
                "model_has_no_predictor", "The selected model cannot run prediction"
            )
        try:
            predictor_id = runtime_catalog.resolve_predictor_id(trainer_id)
            predictor = runtime_catalog.get_predictor_meta(predictor_id)
        except (KeyError, ValueError) as exc:
            raise DatasetCollectionValidationError(
                "model_has_no_predictor", str(exc)
            ) from exc
        if predictor.input_view.view_id != collection.target_view_id:
            raise DatasetCollectionValidationError(
                "model_collection_incompatible",
                f"Model expects {predictor.input_view.view_id}; Collection provides "
                f"{collection.target_view_id}",
            )
        metadata = model.metadata if isinstance(model.metadata, dict) else {}
        try:
            runtime_catalog.validate_predictor_model_contract(
                predictor_id,
                model_contract=metadata.get("model_contract"),
                model_schema_version=metadata.get("model_schema_version"),
            )
        except ValueError as exc:
            raise DatasetCollectionValidationError(
                "model_collection_incompatible", str(exc)
            ) from exc

    @staticmethod
    def _require_owner(collection: DatasetCollection, actor_id: str) -> None:
        if collection.created_by != actor_id:
            raise DatasetCollectionPermissionError(
                "Only the collection creator can change its model automation"
            )


class CollectionRevisionPublishingService:
    """Publish one Revision, then start prediction only for newly admitted members."""

    @inject
    def __init__(
        self,
        collections: DatasetCollectionManagementPort,
        automation_admission: CollectionAutomationAdmissionPort,
        model_automation: CollectionModelAutomationService,
    ) -> None:
        self._collections = collections
        self._automation_admission = automation_admission
        self._model_automation = model_automation

    async def create_revision(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision:
        revision = await self._collections.create_revision(
            collection_id,
            org_id,
            actor_id=actor_id,
            expected_definition_version=expected_definition_version,
            trigger_kind=trigger_kind,
            trigger_ref=trigger_ref,
        )
        try:
            await self._model_automation.predict_new_members(
                collection_id,
                revision.id,
                org_id,
                actor_id,
            )
        except Exception:
            _logger.exception(
                "Revision %s was published, but incremental prediction could not "
                "be prepared; the Revision remains current",
                revision.id,
            )
        return revision

    async def create_revision_for_automation(
        self,
        collection_id: str,
        org_id: str,
        *,
        actor_id: str,
        expected_definition_version: int,
        trigger_kind: str,
        trigger_ref: str | None,
    ) -> DatasetCollectionRevision:
        revision = await self._automation_admission.publish_revision_for_automation(
            collection_id,
            org_id,
            actor_id=actor_id,
            expected_definition_version=expected_definition_version,
            trigger_kind=trigger_kind,
            trigger_ref=trigger_ref,
        )
        try:
            await self._model_automation.predict_new_members(
                collection_id,
                revision.id,
                org_id,
                actor_id,
            )
        except Exception:
            _logger.exception(
                "Revision %s was published, but incremental prediction could not "
                "be prepared; the Revision remains current",
                revision.id,
            )
        return revision


# TODO(candidate-training): add a separate cron-gated Candidate pipeline with named
# readiness checks and regression evaluation. It must never replace default_model_id
# automatically; promotion remains an explicit future product decision.


__all__ = [
    "CollectionModelAutomationService",
    "CollectionRevisionPublishingService",
]
