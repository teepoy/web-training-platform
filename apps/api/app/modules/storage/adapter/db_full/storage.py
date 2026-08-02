from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.sql import alias

from app.modules.datasets.domain.sample_row import (
    BulkSampleRow,
    PredictionResult,
    SampleRow,
)
from app.modules.storage.domain.storage_agg import MaterializeResult
from app.shared.api.schemas import (
    Annotation,
    DatasetStorageMode,
    Sample,
    SampleFeature,
)
from app.shared.db.registry import (
    AnnotationORM,
    AnnotationVersionORM,
    DatasetORM,
    PlatformPredictionORM,
    PredictionCollectionItemORM,
    PredictionCollectionORM,
    PredictionJobORM,
    PredictionReviewActionORM,
    SampleFeatureORM,
    SampleORM,
)
from app.modules.datasets.adapter.repositories.dataset_sql_repository import (
    DatasetSqlRepository,
)
from app.shared.domain.protocols import ArtifactStorage

_MATERIALIZE_PAGE_SIZE = 1000


class DbFullDatasetStorage:
    """Dataset storage backed entirely by the relational database (DB_FULL mode).

    All samples, labels, and predictions live in Postgres/SQLite tables.
    Implements the ``DatasetStorageAgg`` protocol structurally (no inheritance).
    """

    def __init__(
        self,
        dataset_id: str,
        org_id: str | None,
        repo: DatasetSqlRepository,
        session_factory: async_sessionmaker,
        storage: ArtifactStorage,
    ) -> None:
        self._dataset_id: str = dataset_id
        self._org_id: str | None = org_id
        self._repo: DatasetSqlRepository = repo
        self._session_factory: async_sessionmaker = session_factory
        self._storage: ArtifactStorage = storage

        # Derive sync engine for polars read_database() support.
        _bind = self._session_factory.kw["bind"]
        self._sync_engine: Engine = _bind.sync_engine

    # ── properties ──────────────────────────────────────────────────

    @property
    def dataset_id(self) -> str:
        return self._dataset_id

    @property
    def storage_mode(self) -> DatasetStorageMode:
        return DatasetStorageMode.DB_FULL

    # ── get_dataset_metadata ────────────────────────────────────────────

    async def get_dataset_metadata(self) -> Any:
        """Return the Dataset domain object for this storage instance."""
        return await self._repo.get_dataset(self._dataset_id, self._org_id)

    async def _resolve_latest_prediction_job_id(self) -> str | None:
        async with self._session_factory() as session:
            stmt = (
                select(PredictionJobORM.id)
                .where(
                    PredictionJobORM.dataset_id == self._dataset_id,
                    PredictionJobORM.status == "completed",
                )
                .order_by(PredictionJobORM.created_at.desc())
                .limit(1)
            )
            if self._org_id:
                stmt = stmt.where(PredictionJobORM.org_id == self._org_id)
            return (await session.execute(stmt)).scalars().first()

    # ── list_samples (the meat) ─────────────────────────────────────

    async def list_samples(
        self,
        offset: int = 0,
        limit: int = 50,
        *,
        with_labels: bool = False,
        with_predictions: bool = False,
        prediction_job_id: str | None = None,
        label_filter: str | None = None,
        order_by: str = "id",
        random_seed: int | None = None,
        sample_ids: list[str] | None = None,
        return_lazyframe: bool = False,
    ) -> tuple[list[SampleRow], int] | Any:
        """Paginated sample listing with optional label / prediction enrichment.

        Returns ``(rows, total_count)`` or a ``pl.LazyFrame`` when
        *return_lazyframe* is True.
        """
        # ── lazyframe fast-path (polars on sync engine) ─────────
        if return_lazyframe:
            return await self._list_samples_lazyframe(
                with_labels=with_labels,
                with_predictions=with_predictions,
                prediction_job_id=prediction_job_id,
                label_filter=label_filter,
                order_by=order_by,
                random_seed=random_seed,
                sample_ids=sample_ids,
            )

        if sample_ids is not None and len(sample_ids) == 0:
            return [], 0

        async with self._session_factory() as session:
            need_labels = with_labels or label_filter is not None or order_by == "label"
            need_predictions = with_predictions or prediction_job_id is not None
            effective_prediction_job_id = prediction_job_id
            if need_predictions and effective_prediction_job_id is None:
                stmt = (
                    select(PredictionJobORM.id)
                    .where(
                        PredictionJobORM.dataset_id == self._dataset_id,
                        PredictionJobORM.status == "completed",
                    )
                    .order_by(PredictionJobORM.created_at.desc())
                    .limit(1)
                )
                if self._org_id:
                    stmt = stmt.where(PredictionJobORM.org_id == self._org_id)
                effective_prediction_job_id = (
                    (await session.execute(stmt)).scalars().first()
                )
                if effective_prediction_job_id is None:
                    need_predictions = False

            cols: list[Any] = [
                SampleORM.id,
                SampleORM.dataset_id,
                SampleORM.image_uris,
                SampleORM.metadata_json,
                SampleORM.ls_task_id,
                SampleORM.created_at,
            ]

            AnnA = alias(AnnotationORM.__table__, name="ann")
            PredA = alias(PlatformPredictionORM.__table__, name="pred")

            # ── Build base columns and joins together ─────────────
            base = select(*cols).where(SampleORM.dataset_id == self._dataset_id)

            if need_labels:
                latest_ann_subq = (
                    select(
                        AnnotationORM.sample_id.label("ann_sid"),
                        func.max(AnnotationORM.created_at).label("max_ann_ca"),
                    )
                    .group_by(AnnotationORM.sample_id)
                    .subquery("latest_ann_time")
                )
                base = (
                    base.outerjoin(
                        latest_ann_subq, latest_ann_subq.c.ann_sid == SampleORM.id
                    )
                    .outerjoin(
                        AnnA,
                        and_(
                            AnnA.c.sample_id == SampleORM.id,
                            AnnA.c.created_at == latest_ann_subq.c.max_ann_ca,
                        ),
                    )
                    .add_columns(
                        AnnA.c.id.label("ann_id"),
                        AnnA.c.label.label("ann_label"),
                        AnnA.c.annotation_value.label("ann_value"),
                    )
                )

            if need_predictions:
                base = base.outerjoin(
                    PredA,
                    and_(
                        PredA.c.sample_id == SampleORM.id,
                        PredA.c.job_id == effective_prediction_job_id,
                    ),
                )
                base = base.add_columns(
                    PredA.c.id.label("pred_id"),
                    PredA.c.predicted_label.label("pred_label"),
                    PredA.c.confidence.label("pred_confidence"),
                    PredA.c.all_scores_json.label("pred_all_scores"),
                    PredA.c.model_id.label("pred_model_id"),
                    PredA.c.target.label("pred_target"),
                    PredA.c.model_version.label("pred_model_version"),
                    PredA.c.job_id.label("pred_job_id"),
                    PredA.c.error.label("pred_error"),
                )

            stmt = base

            # ── label filter ─────────────────────────────────────
            if label_filter == "__unlabeled__":
                stmt = stmt.where(AnnA.c.id.is_(None))
            elif label_filter == "__annotated__":
                stmt = stmt.where(AnnA.c.id.isnot(None))
            elif label_filter is not None:
                stmt = stmt.where(AnnA.c.label == label_filter)

            # ── sample_ids filter ────────────────────────────────
            if sample_ids is not None:
                stmt = stmt.where(SampleORM.id.in_(sample_ids))

            # ── count ────────────────────────────────────────────
            count_stmt = select(func.count()).select_from(stmt.subquery("filtered"))
            total: int = await session.scalar(count_stmt) or 0

            # ── ordering ─────────────────────────────────────────
            if random_seed is not None:
                stmt = stmt.order_by(func.random())
            elif order_by == "label":
                stmt = stmt.order_by(AnnA.c.label.nullslast())
            elif order_by == "created_at":
                stmt = stmt.order_by(SampleORM.created_at.desc())
            else:
                stmt = stmt.order_by(SampleORM.id)

            # ── paginate ─────────────────────────────────────────
            stmt = stmt.offset(offset).limit(limit)

            rows = (await session.execute(stmt)).mappings().all()

            # ── convert to SampleRow ─────────────────────────────
            result: list[SampleRow] = []
            for row in rows:
                sr = SampleRow(
                    sample_id=row["id"],
                    dataset_id=row["dataset_id"],
                    image_uris=row["image_uris"],
                    metadata=row["metadata_json"],
                    ls_task_id=row["ls_task_id"],
                    created_at=row["created_at"],
                )
                if need_labels and row.get("ann_id") is not None:
                    sr.latest_label = row["ann_label"]
                    sr.annotation_id = row["ann_id"]
                    sr.annotation_value = row.get("ann_value")
                if need_predictions and row.get("pred_id") is not None:
                    sr.latest_prediction = {
                        "predicted_label": row["pred_label"],
                        "confidence": row["pred_confidence"],
                        "all_scores": row["pred_all_scores"],
                        "model_id": row["pred_model_id"],
                        "target": row["pred_target"],
                        "model_version": row["pred_model_version"],
                        "job_id": row["pred_job_id"],
                        "error": row["pred_error"],
                    }
                result.append(sr)

            return result, total

    # ── lazyframe path ─────────────────────────────────────────────

    async def _list_samples_lazyframe(
        self,
        *,
        with_labels: bool = False,
        with_predictions: bool = False,
        prediction_job_id: str | None = None,
        label_filter: str | None = None,
        order_by: str = "id",
        random_seed: int | None = None,
        sample_ids: list[str] | None = None,
    ) -> Any:
        """Return a ``pl.LazyFrame`` over the samples table."""
        import polars as pl

        params: dict[str, Any] = {}

        def _bind(value: Any) -> str:
            name = f"param_{len(params)}"
            params[name] = value
            return f":{name}"

        where_clauses = [f"s.dataset_id = {_bind(self._dataset_id)}"]
        joins = ""

        if sample_ids is not None and len(sample_ids) > 0:
            placeholders = ", ".join(_bind(sample_id) for sample_id in sample_ids)
            where_clauses.append(f"s.id IN ({placeholders})")

        if label_filter == "__unlabeled__":
            where_clauses.append("ann.id IS NULL")
        elif label_filter == "__annotated__":
            where_clauses.append("ann.id IS NOT NULL")
        elif label_filter is not None:
            where_clauses.append(f"ann.label = {_bind(label_filter)}")

        if with_labels or label_filter is not None or order_by == "label":
            joins += """
 LEFT JOIN (
     SELECT sample_id, MAX(created_at) AS max_ca
     FROM annotations
     GROUP BY sample_id
 ) latest_ann ON latest_ann.sample_id = s.id
 LEFT JOIN annotations ann
     ON ann.sample_id = s.id AND ann.created_at = latest_ann.max_ca
"""

        pred_select = ""
        if with_predictions or prediction_job_id is not None:
            effective_prediction_job_id = prediction_job_id
            if effective_prediction_job_id is None:
                effective_prediction_job_id = (
                    await self._resolve_latest_prediction_job_id()
                )
            if effective_prediction_job_id is not None:
                pred_select = ", pp.predicted_label, pp.confidence, pp.all_scores_json, pp.model_id, pp.target, pp.model_version, pp.job_id, pp.error"
                joins += f"""
 LEFT JOIN platform_predictions pp
     ON pp.sample_id = s.id AND pp.job_id = {_bind(effective_prediction_job_id)}
"""

        # Ordering
        order_clause = "s.id"
        if random_seed is not None:
            order_clause = (
                "RANDOM()" if self._sync_engine.dialect.name == "sqlite" else "RANDOM()"
            )
        elif order_by == "label":
            order_clause = "ann.label NULLS LAST"
        elif order_by == "created_at":
            order_clause = "s.created_at DESC"

        select_cols = "s.id, s.dataset_id, s.image_uris, s.metadata_json, s.ls_task_id, s.created_at"
        if with_labels:
            select_cols += ", ann.label AS latest_label, ann.label AS label"
        if with_predictions:
            select_cols += pred_select

        query = (
            f"SELECT {select_cols} FROM samples s{joins}"
            f" WHERE {' AND '.join(where_clauses)}"
            f" ORDER BY {order_clause}"
        )

        async with self._session_factory() as session:
            result = await session.execute(text(query), params)
            rows = [dict(row) for row in result.mappings().all()]

        df = pl.DataFrame(rows)
        return df.lazy()

    # ── stub methods (TBD in subsequent tasks) ──────────────────────

    _NOT_IMPLEMENTED = "TBD in subsequent tasks"

    async def get_sample(self, sample_id: str) -> SampleRow | None:
        async with self._session_factory() as session:
            orm_row = await session.get(SampleORM, sample_id)
            if orm_row is None or orm_row.dataset_id != self._dataset_id:
                return None
            return SampleRow(
                sample_id=orm_row.id,
                dataset_id=orm_row.dataset_id,
                image_uris=orm_row.image_uris,
                metadata=orm_row.metadata_json,
                ls_task_id=orm_row.ls_task_id,
                created_at=orm_row.created_at,
            )

    async def update_sample_image_uris(
        self, sample_id: str, image_uris: list[str]
    ) -> SampleRow | None:
        async with self._session_factory() as session:
            orm_row = await session.get(SampleORM, sample_id)
            if orm_row is None or orm_row.dataset_id != self._dataset_id:
                return None
            orm_row.image_uris = image_uris
            await session.commit()
            return SampleRow(
                sample_id=orm_row.id,
                dataset_id=orm_row.dataset_id,
                image_uris=orm_row.image_uris,
                metadata=orm_row.metadata_json,
                ls_task_id=orm_row.ls_task_id,
                created_at=orm_row.created_at,
            )

    # ── upsert_sample_feature ──────────────────────────────────

    async def upsert_sample_feature(
        self,
        sample_id: str,
        embedding: list[float],
        embed_model: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            row = await session.get(SampleFeatureORM, sample_id)
            if row is None:
                row = SampleFeatureORM(
                    sample_id=sample_id,
                    embedding=embedding,
                    embed_model=embed_model,
                    computed_at=now,
                )
                session.add(row)
            else:
                row.embedding = embedding
                row.embed_model = embed_model
                row.computed_at = now
            await session.commit()

            if session.bind is None:
                raise RuntimeError("Database session has no bound engine")
            dialect_name = session.bind.dialect.name
            if dialect_name == "postgresql":
                vec_str = str(embedding)
                await session.execute(
                    text(
                        "UPDATE sample_features SET embedding_vec = :vec::vector WHERE sample_id = :sid"
                    ),
                    {"vec": vec_str, "sid": sample_id},
                )
                await session.commit()

    async def get_sample_feature(self, sample_id: str) -> SampleFeature | None:
        async with self._session_factory() as session:
            row = await session.get(SampleFeatureORM, sample_id)
            if row is None:
                return None
            return SampleFeature(
                sample_id=row.sample_id,
                embedding=row.embedding,
                embed_model=row.embed_model,
                computed_at=row.computed_at,
            )

    # ── similarity_search ──────────────────────────────────────

    async def similarity_search(
        self,
        embedding: list[float],
        k: int,
        exclude_id: str = "",
    ) -> list[dict]:
        """Find k nearest samples in this dataset by cosine similarity.

        Uses pgvector <=> operator on Postgres, falls back to Python
        cosine on SQLite.  Returns ``[{"sample_id": str, "score": float}]``
        sorted by score descending.
        """
        async with self._session_factory() as session:
            if session.bind is None:
                raise RuntimeError("Database session has no bound engine")
            dialect = session.bind.dialect.name

            if dialect == "postgresql":
                vec_str = str(embedding)
                sql = text("""
                    SELECT sf.sample_id,
                           1 - (sf.embedding_vec <=> :vec::vector) AS score
                    FROM sample_features sf
                    JOIN samples s ON s.id = sf.sample_id
                    WHERE s.dataset_id = :did
                      AND sf.sample_id != :exclude
                      AND sf.embedding_vec IS NOT NULL
                    ORDER BY sf.embedding_vec <=> :vec::vector
                    LIMIT :k
                """)
                rows = (
                    await session.execute(
                        sql,
                        {
                            "vec": vec_str,
                            "did": self._dataset_id,
                            "exclude": exclude_id,
                            "k": k,
                        },
                    )
                ).fetchall()
                return [{"sample_id": str(r[0]), "score": float(r[1])} for r in rows]

            # SQLite implementation — Python cosine over JSON embeddings.
            import math

            sql = text("""
                SELECT sf.sample_id, sf.embedding
                FROM sample_features sf
                JOIN samples s ON s.id = sf.sample_id
                WHERE s.dataset_id = :did
                  AND sf.sample_id != :exclude
            """)
            rows = (
                await session.execute(
                    sql,
                    {
                        "did": self._dataset_id,
                        "exclude": exclude_id,
                    },
                )
            ).fetchall()

            if not rows:
                return []

            def _cosine(a: list[float], b: list[float]) -> float:
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a))
                nb = math.sqrt(sum(x * x for x in b))
                if na == 0 or nb == 0:
                    return 0.0
                return dot / (na * nb)

            results: list[dict] = []
            for r in rows:
                candidate_embedding: Any = r[1]
                if not candidate_embedding:
                    continue
                if isinstance(candidate_embedding, str):
                    candidate_embedding = _json.loads(candidate_embedding)
                score = _cosine(embedding, candidate_embedding)
                results.append({"sample_id": str(r[0]), "score": score})

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:k]

    # ── materialize ────────────────────────────────────────────

    async def materialize(self) -> MaterializeResult:
        """Read all samples from the DB, create a parquet payload.

        Returns ``MaterializeResult`` with at minimum ``manifest_uri``
        and ``row_count`` populated.
        """
        import io as _io

        import pyarrow as pa
        import pyarrow.parquet as pq

        rows_data: list[dict[str, object]] = []
        offset = 0
        while True:
            samples, total = await self.list_samples(
                offset=offset,
                limit=_MATERIALIZE_PAGE_SIZE,
            )
            for sr in samples:
                row_dict: dict[str, object] = {
                    "sample_id": sr.sample_id,
                    "image_uris": sr.image_uris,
                    "metadata": _json.dumps(sr.metadata) if sr.metadata else "{}",
                }
                for uri in sr.image_uris:
                    try:
                        row_dict["image_bytes"] = await self._storage.get_bytes(uri)
                        break
                    except FileNotFoundError:
                        continue
                rows_data.append(row_dict)

            offset += len(samples)
            if offset >= total:
                break
            if not samples:
                raise RuntimeError(
                    "Dataset storage returned an empty page before the reported total"
                )

        buf = _io.BytesIO()
        if rows_data:
            table = pa.Table.from_pylist(rows_data)
            pq.write_table(table, buf)
        else:
            schema = pa.schema(
                [
                    ("sample_id", pa.string()),
                    ("image_uris", pa.list_(pa.string())),
                    ("metadata", pa.string()),
                ]
            )
            pq.write_table(pa.table({}, schema=schema), buf)

        parquet_bytes = buf.getvalue()
        row_count = len(rows_data)

        import uuid

        prefix = f"materialized/{self._dataset_id}/{uuid.uuid4().hex[:8]}/"
        parquet_key = f"{prefix}materialized.parquet"
        manifest_uri = await self._storage.put_bytes(
            object_name=parquet_key,
            data=parquet_bytes,
            content_type="application/octet-stream",
        )

        return MaterializeResult(
            manifest_uri=manifest_uri,
            runtime_bucket="finetune-runtime-inputs",
            prefix="",
            row_count=row_count,
        )

    # ── recent_annotations ─────────────────────────────────────

    async def recent_annotations(self, limit: int = 20) -> dict:
        """Return the most recent annotations for samples in this dataset."""
        async with self._session_factory() as session:
            stmt = (
                select(
                    AnnotationORM.id,
                    AnnotationORM.sample_id,
                    AnnotationORM.label,
                    AnnotationORM.created_by,
                    AnnotationORM.created_at,
                )
                .join(SampleORM, SampleORM.id == AnnotationORM.sample_id)
                .where(SampleORM.dataset_id == self._dataset_id)
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

    async def get_samples_by_id(
        self,
        sample_ids: list[str],
    ) -> dict[str, SampleRow]:
        if not sample_ids:
            return {}

        async with self._session_factory() as session:
            stmt = select(SampleORM).where(
                SampleORM.dataset_id == self._dataset_id,
                SampleORM.id.in_(sample_ids),
            )
            rows = (await session.execute(stmt)).scalars().all()

            orm_map: dict[str, SampleORM] = {r.id: r for r in rows}

            return {
                sid: SampleRow(
                    sample_id=row.id,
                    dataset_id=row.dataset_id,
                    image_uris=row.image_uris,
                    metadata=row.metadata_json,
                    ls_task_id=row.ls_task_id,
                    created_at=row.created_at,
                )
                for sid in sample_ids
                if (row := orm_map.get(sid)) is not None
            }

    async def existing_sample_ids(self, sample_ids: set[str]) -> set[str]:
        if not sample_ids:
            return set()

        async with self._session_factory() as session:
            stmt = select(SampleORM.id).where(
                SampleORM.dataset_id == self._dataset_id,
                SampleORM.id.in_(sample_ids),
            )
            return set((await session.execute(stmt)).scalars().all())

    async def write_samples(
        self,
        rows: AsyncIterator[BulkSampleRow],
        *,
        schema_columns: list[Any] | None = None,
        batch_size: int = 1000,
    ) -> int:
        """Bulk write samples from an async iterator.

        Accumulates batches of *batch_size* and persists samples through the
        repository.  Label Studio task creation is an application-layer
        operation; callers pass an explicit ``ls_task_id`` in ``row.extra``.
        """
        total = 0
        batch: list[BulkSampleRow] = []

        async for row in rows:
            batch.append(row)
            if len(batch) >= batch_size:
                total += await self._flush_writes(batch)
                batch = []

        if batch:
            total += await self._flush_writes(batch)

        return total

    async def _flush_writes(self, batch: list[BulkSampleRow]) -> int:
        """Persist a single batch of BulkSampleRows."""
        samples = [
            Sample(
                id=row.sample_id,
                dataset_id=self._dataset_id,
                image_uris=row.image_uris,
                metadata=row.metadata,
                ls_task_id=(
                    int(row.extra["ls_task_id"])
                    if row.extra and row.extra.get("ls_task_id") is not None
                    else None
                ),
            )
            for row in batch
        ]
        await self._repo.create_samples(samples)
        return len(samples)

    async def create_annotations(self, annotations: list[Annotation]) -> int:
        """Bulk insert annotations via session.add_all() + single commit."""
        if not annotations:
            return 0

        async with self._session_factory() as session:
            session.add_all(
                [
                    AnnotationORM(
                        id=a.id,
                        sample_id=a.sample_id,
                        label=a.label,
                        annotation_value=a.annotation_value,
                        created_by=a.created_by,
                        created_at=a.created_at,
                        user_id=None,
                    )
                    for a in annotations
                ]
            )
            await session.commit()
        return len(annotations)

    async def update_annotations(self, updates: list[tuple[str, str]]) -> int:
        """Bulk update annotation labels. Each tuple is (annotation_id, new_label)."""
        if not updates:
            return 0

        total = 0
        async with self._session_factory() as session:
            for ann_id, new_label in updates:
                result = await session.execute(
                    update(AnnotationORM)
                    .where(AnnotationORM.id == ann_id)
                    .values(label=new_label)
                )
                total += result.rowcount
            await session.commit()
        return total

    async def delete_annotations(self, annotation_ids: list[str]) -> int:
        """Bulk delete annotations by id."""
        if not annotation_ids:
            return 0

        async with self._session_factory() as session:
            result = await session.execute(
                delete(AnnotationORM).where(AnnotationORM.id.in_(annotation_ids))
            )
            await session.commit()
            return result.rowcount

    async def get_annotation_stats(self) -> dict:
        """Return aggregate annotation statistics for this dataset.

        Returns a dict with keys: total_samples, annotated_samples,
        unlabeled_samples, label_counts.
        """
        async with self._session_factory() as session:
            # Subquery: latest annotation per sample (max created_at)
            latest_ann_subq = (
                select(
                    AnnotationORM.sample_id.label("sample_id"),
                    func.max(AnnotationORM.created_at).label("max_created_at"),
                )
                .group_by(AnnotationORM.sample_id)
                .subquery("latest_ann_time")
            )

            AnnAlias = alias(AnnotationORM.__table__, name="ann_stats")

            # Base: all samples in dataset LEFT JOIN to latest annotation
            base = (
                select(
                    SampleORM.id.label("sample_id"),
                    AnnAlias.c.label.label("ann_label"),
                )
                .where(SampleORM.dataset_id == self._dataset_id)
                .outerjoin(
                    latest_ann_subq,
                    latest_ann_subq.c.sample_id == SampleORM.id,
                )
                .outerjoin(
                    AnnAlias,
                    and_(
                        AnnAlias.c.sample_id == SampleORM.id,
                        AnnAlias.c.created_at == latest_ann_subq.c.max_created_at,
                    ),
                )
                .subquery("base_stats")
            )

            # Total samples
            total_stmt = select(func.count()).select_from(base)
            total_samples = await session.scalar(total_stmt) or 0

            # Annotated samples (ann_label IS NOT NULL)
            annotated_stmt = select(func.count()).select_from(
                select(base.c.sample_id).where(base.c.ann_label.isnot(None)).subquery()
            )
            annotated_samples = await session.scalar(annotated_stmt) or 0

            # Label counts
            label_stmt = (
                select(
                    base.c.ann_label,
                    func.count().label("cnt"),
                )
                .where(base.c.ann_label.isnot(None))
                .group_by(base.c.ann_label)
            )
            label_rows = (await session.execute(label_stmt)).all()
            label_counts = {row[0]: row[1] for row in label_rows}

            return {
                "total_samples": total_samples,
                "annotated_samples": annotated_samples,
                "unlabeled_samples": total_samples - annotated_samples,
                "label_counts": label_counts,
            }

    async def metadata_histogram(self, key: str) -> dict:
        """Return value counts for a metadata JSON key."""
        async with self._session_factory() as session:
            dialect = session.bind.dialect.name if session.bind else "sqlite"
            if dialect == "postgresql":
                val_col = SampleORM.metadata_json[key].astext.label("val")
            else:
                val_col = func.json_extract(SampleORM.metadata_json, f"$.{key}").label(
                    "val"
                )
            stmt = (
                select(val_col, func.count().label("cnt"))
                .where(SampleORM.dataset_id == self._dataset_id)
                .where(val_col.isnot(None))
                .group_by(val_col)
                .order_by(func.count().desc())
                .limit(200)
            )
            rows = (await session.execute(stmt)).all()
            histogram = [{"value": row[0], "count": row[1]} for row in rows]
            return {
                "key": key,
                "histogram": histogram,
                "total_non_null": sum(row["count"] for row in histogram),
            }

    async def wafer_points(self) -> dict:
        """Return wafer point coordinates derived from sample metadata."""
        async with self._session_factory() as session:
            dialect = session.bind.dialect.name if session.bind else "sqlite"
            if dialect == "postgresql":
                x_col = SampleORM.metadata_json["x"].astext.label("x")
                y_col = SampleORM.metadata_json["y"].astext.label("y")
            else:
                x_col = func.json_extract(SampleORM.metadata_json, "$.x").label("x")
                y_col = func.json_extract(SampleORM.metadata_json, "$.y").label("y")
            stmt = select(SampleORM.id, x_col, y_col).where(
                SampleORM.dataset_id == self._dataset_id
            )
            rows = (await session.execute(stmt)).all()
            points = [
                {
                    "id": str(row[0]),
                    "x": float(row[1] or 0.0),
                    "y": float(row[2] or 0.0),
                }
                for row in rows
            ]
            return {"points": points, "total": len(points)}

    async def list_annotations(
        self,
        *,
        sample_id: str | None = None,
        dataset_id: str | None = None,
        limit: int | None = None,
    ) -> list[Annotation]:
        if sample_id:
            return await self._repo.list_annotations_for_sample(sample_id)
        if dataset_id:
            return await self._repo.list_annotations_for_dataset(dataset_id)
        return []

    async def list_annotations_by_sample_ids(
        self, sample_ids: list[str]
    ) -> list[Annotation]:
        if not sample_ids:
            return []
        async with self._session_factory() as session:
            stmt = select(AnnotationORM).where(AnnotationORM.sample_id.in_(sample_ids))
            rows = (await session.execute(stmt)).scalars().all()
            return [
                Annotation(
                    id=r.id,
                    sample_id=r.sample_id,
                    label=r.label,
                    annotation_value=r.annotation_value,
                    created_by=r.created_by,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    async def get_annotations_batch(
        self, annotation_ids: list[str]
    ) -> list[Annotation]:
        if not annotation_ids:
            return []
        async with self._session_factory() as session:
            stmt = select(AnnotationORM).where(
                AnnotationORM.id.in_(annotation_ids),
                AnnotationORM.sample_id.in_(
                    select(SampleORM.id).where(SampleORM.dataset_id == self._dataset_id)
                ),
            )
            rows = (await session.execute(stmt)).scalars().all()
            by_id = {
                row.id: Annotation(
                    id=row.id,
                    sample_id=row.sample_id,
                    label=row.label,
                    annotation_value=row.annotation_value,
                    created_by=row.created_by,
                    created_at=row.created_at,
                )
                for row in rows
            }
            return [
                by_id[annotation_id]
                for annotation_id in annotation_ids
                if annotation_id in by_id
            ]

    async def replace_annotations_for_samples(
        self, items: list[tuple[str, str | None]], *, created_by: str = ""
    ) -> int:
        if not items:
            return 0
        seen: dict[str, str | None] = {}
        for sample_id, label in items:
            seen[sample_id] = label

        sample_ids = list(seen.keys())
        async with self._session_factory() as session:
            await session.execute(
                delete(AnnotationORM).where(AnnotationORM.sample_id.in_(sample_ids))
            )

            to_create: list[str] = [
                sid for sid, label in seen.items() if label is not None
            ]
            if to_create:
                session.add_all(
                    [
                        AnnotationORM(
                            id=str(uuid4()),
                            sample_id=sid,
                            label=seen[sid],
                            created_by=created_by,
                            created_at=datetime.now(timezone.utc),
                        )
                        for sid in to_create
                    ]
                )
            await session.commit()
        return len(to_create)

    async def write_predictions(
        self,
        results: AsyncIterator[PredictionResult],
        *,
        job_id: str,
        model_id: str,
        model_version: str | None = None,
        batch_size: int = 500,
    ) -> int:
        """Persist predictions in batches using bulk INSERT.

        Drains *results* (async iterator) in chunks of *batch_size*,
        opening a fresh session and committing each batch.
        """
        total = 0
        batch: list[PredictionResult] = []

        async for r in results:
            batch.append(r)
            if len(batch) >= batch_size:
                await self._write_prediction_batch(
                    batch,
                    job_id=job_id,
                    model_id=model_id,
                    model_version=model_version,
                )
                total += len(batch)
                batch.clear()

        if batch:
            await self._write_prediction_batch(
                batch,
                job_id=job_id,
                model_id=model_id,
                model_version=model_version,
            )
            total += len(batch)

        return total

    async def _write_prediction_batch(
        self,
        batch: list[PredictionResult],
        *,
        job_id: str,
        model_id: str,
        model_version: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        orms: list[PlatformPredictionORM] = []
        for r in batch:
            orms.append(
                PlatformPredictionORM(
                    id=str(uuid4()),
                    org_id=self._org_id or "",
                    dataset_id=self._dataset_id,
                    sample_id=r.sample_id,
                    model_id=model_id,
                    target=r.target or "",
                    job_id=job_id,
                    model_version=model_version,
                    predicted_label=r.predicted_label,
                    confidence=r.confidence,
                    all_scores_json=r.all_scores,
                    error=r.error,
                    created_by="system",
                    created_at=now,
                )
            )
        async with self._session_factory() as session:
            session.add_all(orms)
            await session.commit()

    async def list_predictions(
        self,
        *,
        job_id: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        latest_per_sample: bool = False,
    ) -> list[PredictionResult]:
        conditions = [PlatformPredictionORM.dataset_id == self._dataset_id]
        if self._org_id:
            conditions.append(PlatformPredictionORM.org_id == self._org_id)
        if job_id is not None:
            conditions.append(PlatformPredictionORM.job_id == job_id)

        async with self._session_factory() as session:
            if latest_per_sample:
                ranked = (
                    select(
                        PlatformPredictionORM.id,
                        PlatformPredictionORM.sample_id,
                        PlatformPredictionORM.predicted_label,
                        PlatformPredictionORM.confidence,
                        PlatformPredictionORM.all_scores_json,
                        PlatformPredictionORM.model_id,
                        PlatformPredictionORM.target,
                        PlatformPredictionORM.model_version,
                        PlatformPredictionORM.job_id,
                        PlatformPredictionORM.error,
                        PlatformPredictionORM.created_at,
                        func.row_number()
                        .over(
                            partition_by=PlatformPredictionORM.sample_id,
                            order_by=(
                                PlatformPredictionORM.created_at.desc(),
                                PlatformPredictionORM.id.desc(),
                            ),
                        )
                        .label("row_number"),
                    )
                    .where(*conditions)
                    .subquery()
                )
                stmt = (
                    select(ranked)
                    .where(ranked.c.row_number == 1)
                    .order_by(ranked.c.sample_id)
                    .offset(offset)
                )
                if limit is not None:
                    stmt = stmt.limit(limit)
                rows = (await session.execute(stmt)).mappings().all()
                return [
                    PredictionResult(
                        id=row["id"],
                        sample_id=row["sample_id"],
                        predicted_label=row["predicted_label"],
                        confidence=row["confidence"],
                        all_scores=row["all_scores_json"],
                        model_id=row["model_id"],
                        target=row["target"],
                        model_version=row["model_version"],
                        job_id=row["job_id"],
                        created_at=row["created_at"],
                        error=row["error"],
                    )
                    for row in rows
                ]

            stmt = (
                select(PlatformPredictionORM)
                .where(*conditions)
                .order_by(
                    PlatformPredictionORM.created_at,
                    PlatformPredictionORM.id,
                )
                .offset(offset)
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                PredictionResult(
                    id=row.id,
                    sample_id=row.sample_id,
                    predicted_label=row.predicted_label,
                    confidence=row.confidence,
                    all_scores=row.all_scores_json,
                    model_id=row.model_id,
                    target=row.target,
                    model_version=row.model_version,
                    job_id=row.job_id,
                    created_at=row.created_at,
                    error=row.error,
                )
                for row in rows
            ]

    async def prediction_summary(self) -> dict:
        async with self._session_factory() as session:
            total_stmt = (
                select(func.count())
                .select_from(PlatformPredictionORM)
                .where(PlatformPredictionORM.dataset_id == self._dataset_id)
            )
            total = await session.scalar(total_stmt) or 0

            model_stmt = (
                select(
                    PlatformPredictionORM.model_id,
                    func.count().label("cnt"),
                )
                .where(PlatformPredictionORM.dataset_id == self._dataset_id)
                .group_by(PlatformPredictionORM.model_id)
            )
            model_rows = (await session.execute(model_stmt)).all()

            label_stmt = (
                select(
                    PlatformPredictionORM.predicted_label,
                    func.count().label("cnt"),
                )
                .where(PlatformPredictionORM.dataset_id == self._dataset_id)
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

    async def delete_samples(self, sample_ids: list[str]) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                delete(SampleORM).where(
                    SampleORM.id.in_(sample_ids),
                    SampleORM.dataset_id == self._dataset_id,
                )
            )
            await session.commit()
            return result.rowcount

    async def delete(self) -> None:
        async with self._session_factory() as session:
            did = self._dataset_id

            sample_ids = select(SampleORM.id).where(SampleORM.dataset_id == did)
            annotation_ids = select(AnnotationORM.id).where(
                AnnotationORM.sample_id.in_(sample_ids)
            )
            collection_ids = select(PredictionCollectionORM.id).where(
                PredictionCollectionORM.dataset_id == did
            )

            await session.execute(
                delete(PredictionCollectionItemORM).where(
                    PredictionCollectionItemORM.collection_id.in_(collection_ids)
                )
            )
            await session.execute(
                delete(AnnotationVersionORM).where(
                    AnnotationVersionORM.annotation_id.in_(annotation_ids)
                )
            )
            await session.execute(
                delete(PredictionCollectionORM).where(
                    PredictionCollectionORM.dataset_id == did
                )
            )
            await session.execute(
                delete(PlatformPredictionORM).where(
                    PlatformPredictionORM.dataset_id == did
                )
            )
            await session.execute(
                delete(SampleFeatureORM).where(
                    SampleFeatureORM.sample_id.in_(sample_ids)
                )
            )
            await session.execute(
                delete(AnnotationORM).where(AnnotationORM.sample_id.in_(sample_ids))
            )
            await session.execute(delete(SampleORM).where(SampleORM.dataset_id == did))
            await session.execute(
                delete(PredictionReviewActionORM).where(
                    PredictionReviewActionORM.dataset_id == did
                )
            )
            dataset_orm = await session.get(DatasetORM, did)
            if dataset_orm is not None:
                await session.delete(dataset_orm)
            await session.commit()
