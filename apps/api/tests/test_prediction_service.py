from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models import Model
from app.services.prediction_service import PredictionService


@pytest.mark.asyncio
async def test_resolve_predictor_passes_artifact_storage_to_torch_predictor() -> None:
    repository = MagicMock()
    artifact_storage = MagicMock()
    registry = MagicMock()
    preset = MagicMock()
    preset.id = "resnet50-cls-v1"
    preset.predict.targets = {"image_classification": MagicMock(entrypoint="app.runtime.torch:TorchPredictor")}
    preset.predict.entrypoint = "app.runtime.torch:TorchPredictor"
    registry.get_preset.return_value = preset

    svc = PredictionService(
        repository=repository,
        artifact_storage=artifact_storage,
        config=MagicMock(presets_dir="/tmp"),
        embedding_client=MagicMock(),
        llm_client=MagicMock(),
    )
    svc._load_preset_registry = MagicMock(return_value=registry)  # type: ignore[method-assign]

    model = Model(
        id="model-1",
        uri="memory://model.json",
        kind="model",
        metadata={"framework": "pytorch", "architecture": "resnet50", "base_model": "torchvision/resnet50"},
        job_id="job-1",
        preset_id="resnet50-cls-v1",
    )

    predictor, _ = await svc._resolve_predictor(model, org_id="org-1", target="image_classification")
    assert getattr(predictor, "_artifact_storage", None) is artifact_storage
