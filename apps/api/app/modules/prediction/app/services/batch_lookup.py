"""Batch lookup service for efficient dataset-level prediction queries.

Provides :class:`BatchPredictionService` for fetching the latest prediction
per sample in a single batch query, avoiding N+1 per-sample lookups.
"""

from __future__ import annotations

from sqlalchemy import and_, func, select

from app.modules.prediction.port.http.schemas import PredictionResultResponse
from app.shared.api.schemas import DatasetStorageMode
from app.shared.db.registry import PlatformPredictionORM, SampleORM
from app.shared.db.sql_repository import SqlRepository


class BatchPredictionService:
    """Efficient batch lookup of latest predictions across a dataset.

    Returns one prediction per sample (the latest by ``created_at``, with
    ``id`` as tiebreaker).  Samples with no predictions are absent from the
    result list.  An empty dataset simply returns an empty list.
    """

    def __init__(self, repository: SqlRepository) -> None:
        self._repo = repository

    async def get_latest_predictions(
        self,
        dataset_id: str,
        storage_mode: DatasetStorageMode | None = None,
    ) -> list[PredictionResultResponse]:
        """Return the latest prediction for each sample in the dataset.

        Parameters
        ----------
        dataset_id:
            Platform dataset ID.
        storage_mode:
            Dataset storage mode.  When ``file_shard_sparse`` the query
            filters by ``PlatformPredictionORM.dataset_id`` directly
            instead of joining through ``SampleORM`` (which has no rows
            for sparse datasets).  Defaults to ``None`` (legacy behaviour
            via SampleORM join, equivalent to ``db_full``).

        Returns
        -------
        list[PredictionResultResponse]
            One response per sample that has at least one prediction.
            Samples without predictions are absent.
        """
        async with self._repo.session_factory() as session:
            if storage_mode is DatasetStorageMode.FILE_SHARD_SPARSE:
                # Sparse datasets have no SampleORM rows — filter by
                # dataset_id directly and group by (dataset_id, sample_id).
                latest_subq = (
                    select(
                        PlatformPredictionORM.sample_id,
                        func.max(PlatformPredictionORM.created_at).label("max_ts"),
                    )
                    .where(PlatformPredictionORM.dataset_id == dataset_id)
                    .group_by(
                        PlatformPredictionORM.dataset_id,
                        PlatformPredictionORM.sample_id,
                    )
                    .subquery("latest_pred")
                )
            else:
                # DB_FULL path: join through SampleORM to scope to dataset.
                latest_subq = (
                    select(
                        PlatformPredictionORM.sample_id,
                        func.max(PlatformPredictionORM.created_at).label("max_ts"),
                    )
                    .where(
                        PlatformPredictionORM.sample_id.in_(
                            select(SampleORM.id).where(
                                SampleORM.dataset_id == dataset_id
                            )
                        )
                    )
                    .group_by(PlatformPredictionORM.sample_id)
                    .subquery("latest_pred")
                )

            # Main query: join back to get full prediction rows,
            # tiebreaker on highest id (desc) when created_at ties
            stmt = (
                select(PlatformPredictionORM)
                .join(
                    latest_subq,
                    and_(
                        PlatformPredictionORM.sample_id == latest_subq.c.sample_id,
                        PlatformPredictionORM.created_at == latest_subq.c.max_ts,
                    ),
                )
                .order_by(
                    PlatformPredictionORM.sample_id,
                    PlatformPredictionORM.id.desc(),
                )
            )

            result = await session.execute(stmt)
            rows = result.scalars().all()

            # Deduplicate: keep only the first row per sample_id
            seen: set[str] = set()
            unique: list[PlatformPredictionORM] = []
            for r in rows:
                if r.sample_id not in seen:
                    seen.add(r.sample_id)
                    unique.append(r)

            return [
                PredictionResultResponse(
                    id=r.id,
                    sample_id=r.sample_id,
                    predicted_label=r.predicted_label,
                    confidence=r.confidence,
                    model_id=r.model_id,
                    target=r.target,
                    model_version=r.model_version,
                    job_id=r.job_id,
                    created_at=r.created_at,
                    error=r.error,
                )
                for r in unique
            ]
