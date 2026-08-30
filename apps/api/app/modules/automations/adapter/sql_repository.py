from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import case, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.automations.domain.models import AutomationRunOverview
from app.shared.db.models.dataset_collections import (
    CollectionPredictionBatchItemORM,
    CollectionPredictionBatchORM,
    DatasetCollectionORM,
)
from app.shared.db.models.prediction import PredictionJobORM
from app.shared.db.models.source_discovery import CollectionDiscoveryRunORM


_ATTENTION_STATUSES = ("failed", "partial", "needs_attention")


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _db_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class AutomationOverviewSqlRepository:
    """Read-only projection over target-bound Collection runs.

    The projection always uses one count query and one page query. Collection names
    and prediction child status are joined/aggregated in SQL, so page size never
    changes the query count.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_runs(
        self,
        org_id: str,
        *,
        offset: int,
        limit: int,
        status: str | None,
        recipe_kind: str | None,
        query: str | None,
    ) -> tuple[list[AutomationRunOverview], int]:
        projection = self._projection(org_id)
        conditions = []
        if status == "needs_attention":
            conditions.append(projection.c.needs_attention.is_(True))
        elif status is not None:
            conditions.append(projection.c.status == status)
        if recipe_kind is not None:
            conditions.append(projection.c.recipe_kind == recipe_kind)
        if query:
            pattern = _like_pattern(query)
            conditions.append(
                or_(
                    projection.c.id.ilike(pattern, escape="\\"),
                    projection.c.target_id.ilike(pattern, escape="\\"),
                    projection.c.target_label.ilike(pattern, escape="\\"),
                )
            )

        async with self._session_factory() as session:
            total = int(
                await session.scalar(
                    select(func.count()).select_from(projection).where(*conditions)
                )
                or 0
            )
            rows = (
                await session.execute(
                    select(projection)
                    .where(*conditions)
                    .order_by(projection.c.started_at.desc(), projection.c.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).mappings()
            return [self._to_domain(row) for row in rows], total

    @staticmethod
    def _projection(org_id: str):
        discovery_recipe = case(
            (CollectionDiscoveryRunORM.kind == "backfill", literal("backfill")),
            (CollectionDiscoveryRunORM.kind == "retry", literal("retry")),
            else_=literal("discovery"),
        )
        discovery_attention = CollectionDiscoveryRunORM.status.in_(_ATTENTION_STATUSES)
        discovery = (
            select(
                CollectionDiscoveryRunORM.id.label("id"),
                literal("discovery").label("run_source"),
                literal("collection").label("target_type"),
                CollectionDiscoveryRunORM.collection_id.label("target_id"),
                DatasetCollectionORM.name.label("target_label"),
                discovery_recipe.label("recipe_kind"),
                CollectionDiscoveryRunORM.status.label("status"),
                CollectionDiscoveryRunORM.created_at.label("started_at"),
                CollectionDiscoveryRunORM.completed_at.label("completed_at"),
                discovery_attention.label("needs_attention"),
                # Discovery attention can mean a changed Source record, a publication
                # failure, or failed items. Only the owning resource workflow has the
                # full pinned-input context needed to offer the correct recovery.
                literal(False).label("retry_supported"),
                CollectionDiscoveryRunORM.error_detail.label("detail"),
            )
            .join(
                DatasetCollectionORM,
                DatasetCollectionORM.id == CollectionDiscoveryRunORM.collection_id,
            )
            .where(CollectionDiscoveryRunORM.org_id == org_id)
        )

        effective_prediction_status = func.coalesce(
            PredictionJobORM.status, CollectionPredictionBatchItemORM.status
        )
        item_counts = (
            select(
                CollectionPredictionBatchItemORM.batch_id.label("batch_id"),
                func.count().label("total"),
                func.sum(
                    case(
                        (effective_prediction_status == "completed", 1),
                        else_=0,
                    )
                ).label("completed"),
                func.sum(
                    case(
                        (
                            effective_prediction_status.in_(("failed", "cancelled")),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failed"),
                func.sum(
                    case(
                        (
                            effective_prediction_status.in_(("queued", "running")),
                            1,
                        ),
                        else_=0,
                    )
                ).label("active"),
                func.max(PredictionJobORM.updated_at).label("last_job_updated_at"),
            )
            .outerjoin(
                PredictionJobORM,
                PredictionJobORM.id
                == CollectionPredictionBatchItemORM.prediction_job_id,
            )
            .group_by(CollectionPredictionBatchItemORM.batch_id)
            .subquery()
        )
        batch_status = case(
            (
                func.coalesce(item_counts.c.total, 0) == 0,
                CollectionPredictionBatchORM.status,
            ),
            (item_counts.c.completed == item_counts.c.total, literal("completed")),
            (item_counts.c.failed == item_counts.c.total, literal("failed")),
            (item_counts.c.failed > 0, literal("partial")),
            (item_counts.c.active > 0, literal("running")),
            else_=literal("pending"),
        )
        batch_attention = batch_status.in_(("failed", "partial"))
        batch_completed_at = case(
            (
                batch_status.in_(("completed", "failed", "partial")),
                func.coalesce(
                    item_counts.c.last_job_updated_at,
                    CollectionPredictionBatchORM.updated_at,
                ),
            ),
            else_=None,
        )
        prediction = (
            select(
                CollectionPredictionBatchORM.id.label("id"),
                literal("prediction_batch").label("run_source"),
                literal("collection").label("target_type"),
                CollectionPredictionBatchORM.collection_id.label("target_id"),
                DatasetCollectionORM.name.label("target_label"),
                literal("prediction").label("recipe_kind"),
                batch_status.label("status"),
                CollectionPredictionBatchORM.created_at.label("started_at"),
                batch_completed_at.label("completed_at"),
                batch_attention.label("needs_attention"),
                batch_attention.label("retry_supported"),
                case(
                    (
                        (func.coalesce(item_counts.c.total, 0) == 0)
                        & (CollectionPredictionBatchORM.status == "failed"),
                        literal(
                            "Prediction preparation failed before child jobs were created"
                        ),
                    ),
                    (
                        batch_attention,
                        literal("One or more Dataset predictions need attention"),
                    ),
                    else_=None,
                ).label("detail"),
            )
            .join(
                DatasetCollectionORM,
                DatasetCollectionORM.id == CollectionPredictionBatchORM.collection_id,
            )
            .outerjoin(
                item_counts,
                item_counts.c.batch_id == CollectionPredictionBatchORM.id,
            )
            .where(DatasetCollectionORM.org_id == org_id)
        )
        return union_all(discovery, prediction).subquery("automation_run_overview")

    @staticmethod
    def _to_domain(row) -> AutomationRunOverview:
        completed_at = cast(datetime | None, row["completed_at"])
        return AutomationRunOverview(
            id=cast(str, row["id"]),
            run_source=cast(str, row["run_source"]),
            target_type=cast(str, row["target_type"]),
            target_id=cast(str, row["target_id"]),
            target_label=cast(str, row["target_label"]),
            recipe_kind=cast(str, row["recipe_kind"]),
            status=cast(str, row["status"]),
            started_at=_db_utc(cast(datetime, row["started_at"])),
            completed_at=_db_utc(completed_at) if completed_at is not None else None,
            needs_attention=bool(row["needs_attention"]),
            retry_supported=bool(row["retry_supported"]),
            detail=cast(str | None, row["detail"]),
        )
