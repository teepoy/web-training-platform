from __future__ import annotations

from app.modules.prediction.domain.submission import PredictionJobCommand


def prediction_workflow_parameters(
    command: PredictionJobCommand,
    *,
    job_id: str,
    predictor_id: str,
) -> dict[str, object]:
    """Map a prediction submission intent to the Prefect transport payload."""

    return {
        "job_id": job_id,
        "dataset_id": command.dataset_id,
        "collection_id": command.collection_id,
        "collection_revision_id": command.collection_revision_id,
        "model_id": command.model_id,
        "org_id": command.org_id,
        "created_by": command.created_by,
        "target": command.target,
        "model_version": command.model_version,
        "sample_ids": (
            list(command.sample_ids) if command.sample_ids is not None else None
        ),
        "prompt": command.prompt,
        "predictor_id": predictor_id,
    }
