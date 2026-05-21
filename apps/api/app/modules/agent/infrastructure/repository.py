from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.db.registry import AnnotationORM, PlatformPredictionORM, SampleORM


class AgentQueryRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_random_samples(self, dataset_id: str, limit: int = 100) -> list[dict]:
        """Return up to *limit* random samples from a dataset (metadata only)."""
        async with self.session_factory() as session:
            # SQLite uses RANDOM(), Postgres uses RANDOM() too
            stmt = (
                select(SampleORM)
                .where(SampleORM.dataset_id == dataset_id)
                .order_by(func.random())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": r.id,
                    "dataset_id": r.dataset_id,
                    "image_uris": r.image_uris,
                    "metadata": r.metadata_json,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    async def metadata_histogram(self, dataset_id: str, key: str) -> dict:
        """Return value counts for a single metadata JSON key.

        Uses SQLAlchemy ``func.json_extract`` for SQLite and
        ``->>`` operator for Postgres.
        """
        async with self.session_factory() as session:
            # Detect dialect
            dialect = session.bind.dialect.name if session.bind else "sqlite"

            if dialect == "postgresql":
                val_col = SampleORM.metadata_json[key].astext.label("val")
            else:
                # SQLite json_extract
                val_col = func.json_extract(SampleORM.metadata_json, f"$.{key}").label(
                    "val"
                )

            stmt = (
                select(val_col, func.count().label("cnt"))
                .where(SampleORM.dataset_id == dataset_id)
                .where(val_col.isnot(None))
                .group_by(val_col)
                .order_by(func.count().desc())
                .limit(200)
            )
            rows = (await session.execute(stmt)).all()
            return {
                "key": key,
                "histogram": [{"value": r[0], "count": r[1]} for r in rows],
                "total_non_null": sum(r[1] for r in rows),
            }

    async def recent_annotations(self, dataset_id: str, limit: int = 20) -> dict:
        """Return the most recent annotations for samples in a dataset."""
        async with self.session_factory() as session:
            stmt = (
                select(
                    AnnotationORM.id,
                    AnnotationORM.sample_id,
                    AnnotationORM.label,
                    AnnotationORM.created_by,
                    AnnotationORM.created_at,
                )
                .join(SampleORM, SampleORM.id == AnnotationORM.sample_id)
                .where(SampleORM.dataset_id == dataset_id)
                .order_by(AnnotationORM.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()
            return {
                "entries": [
                    {
                        "id": r[0],
                        "sample_id": r[1],
                        "label": r[2],
                        "created_by": r[3],
                        "created_at": r[4].isoformat() if r[4] else None,
                    }
                    for r in rows
                ]
            }

    async def prediction_summary(self, dataset_id: str) -> dict:
        """Aggregate prediction stats for a dataset."""
        async with self.session_factory() as session:
            total_stmt = (
                select(func.count())
                .select_from(PlatformPredictionORM)
                .where(PlatformPredictionORM.dataset_id == dataset_id)
            )
            total = await session.scalar(total_stmt) or 0

            model_stmt = (
                select(
                    PlatformPredictionORM.model_id,
                    func.count().label("cnt"),
                )
                .where(PlatformPredictionORM.dataset_id == dataset_id)
                .group_by(PlatformPredictionORM.model_id)
            )
            model_rows = (await session.execute(model_stmt)).all()

            label_stmt = (
                select(
                    PlatformPredictionORM.predicted_label,
                    func.count().label("cnt"),
                )
                .where(PlatformPredictionORM.dataset_id == dataset_id)
                .group_by(PlatformPredictionORM.predicted_label)
                .order_by(func.count().desc())
                .limit(50)
            )
            label_rows = (await session.execute(label_stmt)).all()

            return {
                "total_predictions": total,
                "models": [{"model_id": r[0], "count": r[1]} for r in model_rows],
                "label_distribution": {r[0]: r[1] for r in label_rows},
            }
