from __future__ import annotations

from fastapi import HTTPException

from app.modules.types import catalog


def validate_trainer_for_dataset(
    trainer_id: str,
    dataset_type: str,
    view_types: list[str],
    storage_mode: str,
) -> None:
    """Validate that a *trainer* is compatible with a dataset.

    Compatibility rule: a trainer is valid iff its ``view_id``
    is one of the dataset's ``view_types``.

    The ``storage_mode`` gate is handled independently by
    :meth:`SampleAccess.capabilities` — this function only checks
    view compatibility.

    Raises :class:`HTTPException` (422) when the combination is invalid.
    """
    # ── trainer lookup ───────────────────────────────────────────────
    try:
        trainer_meta = catalog.get_trainer_meta(trainer_id)
    except KeyError:
        raise HTTPException(
            status_code=422,
            detail=f"Trainer '{trainer_id}' is not registered",
        ) from None

    # ── view compatibility ───────────────────────────────────────────
    trainer_view = trainer_meta["view_id"]
    if trainer_view not in view_types:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Trainer '{trainer_id}' (view='{trainer_view}') "
                f"is not compatible with dataset views={view_types}"
            ),
        )


def validate_predictor_for_dataset(
    predictor_id: str,
    dataset_type: str,
    view_types: list[str],
    storage_mode: str,
) -> None:
    """Validate that a *predictor* is compatible with a dataset.

    Compatibility rule: a predictor is valid iff its
    ``view_id`` is one of the dataset's ``view_types``.

    Note: ``file_shard_sparse`` datasets **are** compatible with
    prediction (prediction on sparse datasets is dispatched by the
    ``prediction-predict-job`` Prefect flow in
    :mod:`app.modules.prediction.flows.predict_job`).

    Raises :class:`HTTPException` (422) when the combination is invalid.
    """
    # ── predictor lookup ─────────────────────────────────────────────
    try:
        predictor_meta = catalog.get_predictor_meta(predictor_id)
    except KeyError:
        raise HTTPException(
            status_code=422,
            detail=f"Predictor '{predictor_id}' is not registered",
        ) from None

    # ── view compatibility ───────────────────────────────────────────
    predictor_view = predictor_meta["view_id"]
    if predictor_view not in view_types:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Predictor '{predictor_id}' (view='{predictor_view}') "
                f"is not compatible with dataset views={view_types}"
            ),
        )


def validate_view_for_dataset(
    view_type: str,
    dataset_view_types: list[str],
) -> None:
    """Validate that *view_type* is enabled for a dataset.

    Raises :class:`HTTPException` (422) when *view_type* is not
    present in *dataset_view_types*.
    """
    if view_type not in dataset_view_types:
        raise HTTPException(
            status_code=422,
            detail=(
                f"View '{view_type}' is not enabled for this dataset "
                f"(enabled: {dataset_view_types})"
            ),
        )
