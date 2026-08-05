from __future__ import annotations

from app.modules.runtime.catalog import runtime_catalog


class DatasetCompatibilityError(ValueError):
    """A registered runtime type cannot consume one of the dataset views."""


def validate_trainer_for_dataset(
    trainer_id: str,
    view_types: list[str],
) -> None:
    """Validate that a *trainer* is compatible with a dataset.

    Compatibility rule: a trainer is valid iff its ``view_id``
    is one of the dataset's ``view_types``.

    Raises :class:`DatasetCompatibilityError` when the combination is invalid.
    """
    # ── trainer lookup ───────────────────────────────────────────────
    try:
        trainer_meta = runtime_catalog.get_trainer_meta(trainer_id)
    except KeyError:
        raise DatasetCompatibilityError(
            f"Trainer '{trainer_id}' is not registered"
        ) from None

    # ── view compatibility ───────────────────────────────────────────
    trainer_view = trainer_meta.view_id
    if trainer_view not in view_types:
        raise DatasetCompatibilityError(
            f"Trainer '{trainer_id}' (view='{trainer_view}') "
            f"is not compatible with dataset views={view_types}"
        )


def validate_predictor_for_dataset(
    predictor_id: str,
    view_types: list[str],
) -> None:
    """Validate that a *predictor* is compatible with a dataset.

    Compatibility rule: a predictor is valid iff its
    ``view_id`` is one of the dataset's ``view_types``.

    Raises :class:`DatasetCompatibilityError` when the combination is invalid.
    """
    # ── predictor lookup ─────────────────────────────────────────────
    try:
        predictor_meta = runtime_catalog.get_predictor_meta(predictor_id)
    except KeyError:
        raise DatasetCompatibilityError(
            f"Predictor '{predictor_id}' is not registered"
        ) from None

    # ── view compatibility ───────────────────────────────────────────
    predictor_view = predictor_meta.view_id
    if predictor_view not in view_types:
        raise DatasetCompatibilityError(
            f"Predictor '{predictor_id}' (view='{predictor_view}') "
            f"is not compatible with dataset views={view_types}"
        )


def validate_view_for_dataset(
    view_type: str,
    dataset_view_types: list[str],
) -> None:
    """Validate that *view_type* is enabled for a dataset.

    Raises :class:`DatasetCompatibilityError` when *view_type* is not
    present in *dataset_view_types*.
    """
    if view_type not in dataset_view_types:
        raise DatasetCompatibilityError(
            f"View '{view_type}' is not enabled for this dataset "
            f"(enabled: {dataset_view_types})"
        )
