from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import ml_library
import polars as pl
import pytest

from app.modules.dataset_collections.domain.models import DatasetCollectionRevision
from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.runtime.catalog import runtime_catalog
from app.modules.runtime.domain.context import PredictionRuntimeContext
from app.modules.runtime.domain.events import OperationCompleted
from app.modules.sc.capabilities import SC_PATCH_IMAGE_V1
from app.modules.sc.domain.image_stream import ScPredictionImageStreamFactory
from app.modules.sc.runtime import ultralytics
from app.modules.sc.runtime.data_source import ScRuntimeSource
from app.modules.training.app.services.submission_service import (
    TrainingSubmissionService,
)
from app.modules.training.domain.submission import TrainAndPredictCommand
from app.shared.api.schemas import Model
from app.shared.context import AppContext


def _sample_filter() -> dict[str, object]:
    return {
        "combinator": "and",
        "items": [
            {
                "kind": "condition",
                "field": "row_key",
                "condition": {
                    "filterType": "set",
                    "values": ["dataset-a::sample-1"],
                },
            },
            {
                "kind": "condition",
                "field": "final_class",
                "condition": {
                    "filterType": "set",
                    "values": ["Scratch"],
                },
            }
        ],
    }


def _collection_revision() -> DatasetCollectionRevision:
    return DatasetCollectionRevision(
        id="revision-1",
        collection_id="collection-1",
        revision_number=1,
        definition_version=1,
        definition_hash="definition-hash",
        target_view_id=SC_PATCH_IMAGE_V1.view_id,
        target_view_contract=SC_PATCH_IMAGE_V1.contract,
        target_schema_version=SC_PATCH_IMAGE_V1.schema_version,
        status="ready",
        source_snapshot=(),
        row_count=2,
        label_counts={"Scratch": 1, "Particle": 1},
        manifest_uri="memory://collection/revision-1.parquet",
        provenance_uri=None,
        trigger_kind="manual",
        trigger_ref=None,
        created_by="user-1",
        created_at=datetime.now(UTC),
        error_code=None,
        error_detail=None,
        manifest_format="collection_membership_v1",
        source_resolution="observed",
        reproducibility_capability=False,
    )


@pytest.mark.asyncio
async def test_filtered_collection_train_and_predict_submits_workflow() -> None:
    repository = AsyncMock()
    repository.create_job.side_effect = lambda job: job
    prefect_client = AsyncMock()
    prefect_client.resolve_deployment_id.return_value = "deployment-1"
    prefect_client.create_flow_run_from_deployment.return_value = {
        "id": "flow-run-1"
    }
    collection_revisions = AsyncMock()
    collection_revisions.get_revision.return_value = _collection_revision()
    status_reconciler = Mock()
    service = TrainingSubmissionService(
        engine=Mock(),
        notification_sink=Mock(),
        repository=repository,
        artifact_service=Mock(),
        dataset_reader=AsyncMock(),
        prefect_client=prefect_client,
        collection_revisions=collection_revisions,
        dataset_revisions=AsyncMock(),
        status_reconciler=status_reconciler,
    )

    result = await service.submit_train_and_predict(
        TrainAndPredictCommand(
            collection_id="collection-1",
            collection_revision_id="revision-1",
            trainer_id="yolo-sc-v1",
            org_id="org-1",
            created_by="user-1",
            sample_filter=_sample_filter(),
        )
    )

    assert result.workflow_run_id == "flow-run-1"
    parameters = prefect_client.create_flow_run_from_deployment.await_args.kwargs[
        "parameters"
    ]
    assert parameters["dataset_id"] is None
    assert parameters["collection_id"] == "collection-1"
    assert parameters["collection_revision_id"] == "revision-1"
    assert parameters["sample_filter"] == _sample_filter()
    status_reconciler.wake.assert_called_once_with()


class _ImageStream:
    async def resolve_images(
        self,
        *,
        roles: tuple[str, ...] | list[str],
        items: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        return [
            {
                **item,
                "error": "",
                "images": [
                    {
                        "role": role,
                        "image_data": f"{role}:{item['sample_id']}".encode(),
                        "content_type": "image/png",
                        "error": "",
                    }
                    for role in roles
                ],
            }
            for item in items
        ]


class _ImageStreamFactory:
    @asynccontextmanager
    async def open(self):
        yield _ImageStream()


@pytest.mark.asyncio
async def test_collection_prediction_applies_filter_to_namespaced_sample_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rows = pl.DataFrame(
        {
            "sample_id": ["dataset-a::sample-1", "dataset-b::sample-2"],
            "inspection_time": ["2026-08-16T10:00:00"] * 2,
            "wafer_key": [42, 43],
            "defect_id": ["1", "2"],
            "label": ["Scratch", None],
            "predicted_label": ["Particle", "Particle"],
        }
    ).lazy()
    source = ScRuntimeSource(
        rows=rows,
        source_identity="collection:collection-1/revision-1",
        label_space=("Scratch", "Particle"),
        view_types=(SC_PATCH_IMAGE_V1.view_id,),
        dataset_type="image_sc_collection",
        dataset_id=None,
        collection_id="collection-1",
        collection_revision_id="revision-1",
        source_dataset_ids=("dataset-a", "dataset-b"),
    )
    repo = AsyncMock()
    repo.get_prediction_job.return_value = None
    written_sample_ids: list[str] = []

    @asynccontextmanager
    async def open_source(*_args: object, **kwargs: object):
        assert kwargs == {"with_labels": True, "with_predictions": True}
        yield source

    async def predict_stream(
        _checkpoint_path: Path,
        _labels: list[str],
        samples: Any,
        **_kwargs: object,
    ):
        async for sample in samples:
            yield SimpleNamespace(
                sample_id=str(sample["sample_id"]),
                label="Scratch",
                confidence=1.0,
                scores={"Scratch": 1.0, "Particle": 0.0},
                error=None,
            )

    async def write_predictions(*, predictions: Any, **_kwargs: object) -> None:
        async for prediction in predictions:
            written_sample_ids.append(prediction.sample_id)

    injector = SimpleNamespace(
        get=lambda dependency: (
            repo
            if dependency is PredictionRepository
            else cast(ScPredictionImageStreamFactory, _ImageStreamFactory())
        )
    )
    pipeline = SimpleNamespace(
        prediction_progress_flush_rows=100,
        prediction_progress_flush_seconds=60.0,
        prediction_input_batch_rows=512,
        prediction_preprocess_workers=1,
        prediction_preprocess_task_rows=64,
        prediction_preprocess_prefetch_tasks=1,
        prediction_write_batch_rows=100,
    )
    app_context = cast(
        AppContext,
        SimpleNamespace(
            injector=injector,
            shared=SimpleNamespace(
                config=SimpleNamespace(sc=SimpleNamespace(pipeline=pipeline)),
                artifact_storage=SimpleNamespace(),
                redis_event_publisher=None,
            ),
        ),
    )
    trainer = runtime_catalog.get_trainer_meta("yolo-sc-v1")
    model = Model(
        id="model-1",
        uri="memory://model.pt",
        kind="model",
        job_id="training-1",
        metadata={
            "label_space": ["Scratch", "Particle"],
            "model_contract": trainer.output_model.contract,
            "model_schema_version": trainer.output_model.schema_version,
        },
    )
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"checkpoint")
    monkeypatch.setattr(ultralytics, "open_sc_runtime_source", open_source)
    monkeypatch.setattr(ultralytics, "write_sc_predictions", write_predictions)
    monkeypatch.setattr(ml_library, "predict_yolo_stream", predict_stream)
    context = PredictionRuntimeContext(
        app_context=app_context,
        job_id="prediction-1",
        dataset_id=None,
        model_id=model.id,
        org_id="org-1",
        predictor_id="yolo-sc-v1",
        created_by="user-1",
        target="image_classification",
        sample_filter=_sample_filter(),
        collection_id="collection-1",
        collection_revision_id="revision-1",
    )

    events = [
        event
        async for event in ultralytics.yolo_sc_predictor_from_local_checkpoint(
            context,
            model=model,
            checkpoint_path=checkpoint,
        )
    ]

    assert written_sample_ids == ["dataset-a::sample-1"]
    assert isinstance(events[-1], OperationCompleted)
    assert events[-1].summary["total_samples"] == 1
