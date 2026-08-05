from __future__ import annotations

from app.modules.runtime.domain.routing import RuntimeDeploymentRoute
from app.modules.runtime.catalog import runtime_catalog
from app.modules.training.domain.submission import TrainAndPredictCommand


def train_and_predict_workflow_parameters(
    command: TrainAndPredictCommand,
    *,
    job_id: str,
    route: RuntimeDeploymentRoute,
) -> dict[str, object]:
    """Map a train-and-predict intent to the Prefect transport payload."""

    return {
        "job_id": job_id,
        "dataset_id": command.dataset_id,
        "trainer_id": command.trainer_id,
        "org_id": command.org_id,
        "created_by": command.created_by,
        "target": command.target,
        "model_version": command.model_version,
        "sample_ids": (
            list(command.sample_ids) if command.sample_ids is not None else None
        ),
        "sample_filter": command.sample_filter,
        "prompt": command.prompt,
        "predictor_id": runtime_catalog.resolve_predictor_id(
            command.trainer_id,
            requested_predictor_id=command.predictor_id,
        ),
        **route.to_parameters(),
    }
