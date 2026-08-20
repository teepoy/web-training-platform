from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.modules.prediction.domain.repository import PredictionRepository
from app.modules.runtime.domain.context import (
    TrainAndPredictRuntimeContext,
    TrainingRuntimeContext,
)
from app.modules.runtime.domain.events import (
    ArtifactOutput,
    LocalArtifactFile,
    MetricsReported,
    OperationCompleted,
    collect_runtime_events,
)
from app.modules.sc.runtime import ultralytics, workflows
from app.modules.sc.runtime.ultralytics import (
    ScYoloTrainingResult,
    _prediction_checkpoint,
)
from app.modules.training.domain.repository import TrainingRepository
from app.shared.api.schemas import ArtifactRef, Model, PredictionJob
from app.shared.context import AppContext


@pytest.mark.asyncio
async def test_train_and_predict_uses_two_tasks_and_overlaps_checkpoint_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_names: list[str] = []

    def immediate_task(*, name: str, persist_result: bool):
        assert persist_result is False
        task_names.append(name)

        def decorate(function):
            return function

        return decorate

    training_repository = AsyncMock()
    prediction_repository = AsyncMock()
    prediction_repository.create_prediction_job.return_value = PredictionJob(
        id="prediction-1",
        dataset_id="dataset-1",
        model_id="model-1",
        created_by="user-1",
        org_id="org-1",
    )
    injector = SimpleNamespace(
        get=lambda dependency: (
            training_repository
            if dependency is TrainingRepository
            else prediction_repository
            if dependency is PredictionRepository
            else None
        )
    )
    artifact_storage = SimpleNamespace(get_file=AsyncMock())
    app_context = cast(
        AppContext,
        SimpleNamespace(
            injector=injector,
            shared=SimpleNamespace(artifact_storage=artifact_storage),
        ),
    )
    context = TrainAndPredictRuntimeContext(
        app_context=app_context,
        job_id="training-1",
        dataset_id="dataset-1",
        trainer_id="yolo-sc-v1",
        predictor_id="yolo-sc-v1",
        org_id="org-1",
        created_by="user-1",
        target="sc_defect_classification",
    )
    upload_started = asyncio.Event()
    upload_release = asyncio.Event()

    async def train(
        _context,
        *,
        work_dir: Path,
    ) -> ScYoloTrainingResult:
        checkpoint_path = work_dir / "checkpoint.pt"
        checkpoint_path.parent.mkdir(parents=True)
        checkpoint_path.write_bytes(b"checkpoint")
        return ScYoloTrainingResult(
            artifact=ArtifactOutput(
                id="model-1",
                kind="model",
                payload=LocalArtifactFile(
                    path=checkpoint_path,
                    object_name="models/training-1/checkpoint.pt",
                ),
                metadata={"label_space": ["40", "60"]},
            ),
            metrics=MetricsReported({"accuracy": 0.9}),
            issues=(),
        )

    async def persist(_sink, output: ArtifactOutput) -> ArtifactRef:
        upload_started.set()
        await upload_release.wait()
        return ArtifactRef(
            id=output.id,
            uri="memory://checkpoint.pt",
            kind=output.kind,
            metadata=dict(output.metadata),
        )

    async def predict(_context, *, model, checkpoint_path):
        assert upload_started.is_set()
        assert not upload_release.is_set()
        assert model.id == "model-1"
        assert checkpoint_path.read_bytes() == b"checkpoint"
        assert artifact_storage.get_file.await_count == 0
        upload_release.set()
        yield OperationCompleted({"processed": 10})

    monkeypatch.setattr(workflows, "task", immediate_task)
    monkeypatch.setattr(workflows, "execute_yolo_sc_training", train)
    monkeypatch.setattr(
        workflows,
        "yolo_sc_predictor_from_local_checkpoint",
        predict,
    )
    monkeypatch.setattr(
        workflows.PlatformArtifactOutputSink,
        "persist",
        persist,
    )

    result = await collect_runtime_events(workflows.run_sc_train_and_predict(context))

    assert task_names == ["sc-train", "sc-predict"]
    assert result["model_id"] == "model-1"
    assert result["prediction"] == {"processed": 10}
    assert result["training"] == {
        "job_id": "training-1",
        "status": "completed",
        "artifacts": [
            {
                "id": "model-1",
                "uri": "memory://checkpoint.pt",
                "kind": "model",
                "metadata": {"label_space": ["40", "60"]},
                "name": None,
                "file_size": None,
                "file_hash": None,
                "format": None,
                "created_at": None,
            }
        ],
        "metrics": {"accuracy": 0.9},
    }
    artifact_storage.get_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_local_prediction_checkpoint_skips_artifact_download(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.pt"
    checkpoint_path.write_bytes(b"local-checkpoint")
    storage = SimpleNamespace(get_file=AsyncMock())
    app_context = SimpleNamespace(shared=SimpleNamespace(artifact_storage=storage))
    model = Model(
        id="model-1",
        uri="s3://models/checkpoint.pt",
        kind="model",
        job_id="training-1",
    )

    async with _prediction_checkpoint(
        app_context=app_context,
        model=model,
        local_checkpoint=checkpoint_path,
        job_id="prediction-1",
    ) as resolved:
        assert resolved == checkpoint_path
        assert resolved.read_bytes() == b"local-checkpoint"

    storage.get_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_standalone_training_keeps_checkpoint_until_artifact_sink_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_context = cast(AppContext, SimpleNamespace())
    context = TrainingRuntimeContext(
        app_context=app_context,
        job_id="training-standalone",
        dataset_id="dataset-1",
        trainer_id="yolo-sc-v1",
        created_by="user-1",
    )

    async def train(
        _context: TrainingRuntimeContext,
        *,
        work_dir: Path,
    ) -> ScYoloTrainingResult:
        checkpoint_path = work_dir / "checkpoint.pt"
        checkpoint_path.write_bytes(b"standalone")
        return ScYoloTrainingResult(
            artifact=ArtifactOutput(
                id="model-standalone",
                kind="model",
                payload=LocalArtifactFile(
                    path=checkpoint_path,
                    object_name="models/training-standalone/checkpoint.pt",
                ),
            ),
            metrics=MetricsReported({}),
            issues=(),
        )

    class Sink:
        async def persist(self, output: ArtifactOutput) -> ArtifactRef:
            assert isinstance(output.payload, LocalArtifactFile)
            assert output.payload.path.read_bytes() == b"standalone"
            return ArtifactRef(
                id=output.id,
                uri="memory://standalone",
                kind=output.kind,
            )

    monkeypatch.setattr(ultralytics, "execute_yolo_sc_training", train)

    result = await collect_runtime_events(
        ultralytics.yolo_sc_train(context),
        artifact_sink=Sink(),
    )

    artifacts = cast(list[dict[str, object]], result["artifacts"])
    assert artifacts[0]["id"] == "model-standalone"
