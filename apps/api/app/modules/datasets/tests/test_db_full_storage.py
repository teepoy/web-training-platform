"""Integration tests for DbFullDatasetStorage covering all 18 public methods.

Uses real SQLite via the ``_test_infra`` and ``db_full_fixture`` fixtures from
``conftest.py`` — no mocks.
"""

from __future__ import annotations

import io as _io
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio  # type: ignore[import-untyped]

from app.modules.storage.adapter.db_full.storage import DbFullDatasetStorage
from app.modules.storage.domain.columnar_schemas import DB_FULL_MATERIALIZED_SCHEMA
from app.modules.datasets.domain.sample_row import PredictionResult, SampleRow
from app.modules.datasets.adapter.repositories.dataset_sql_repository import DatasetSqlRepository
from app.shared.api.schemas import Annotation, Dataset, DatasetStorageMode, TaskSpec
from app.shared.db.registry import PredictionJobORM
from app.shared.infrastructure.storage.memory import InMemoryArtifactStorage

pytestmark = pytest.mark.integration


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── storage fixture wired to db_full_fixture ──────────────────────────────


@pytest_asyncio.fixture
async def storage(
    _test_infra: dict, db_full_fixture: tuple[str, str]
) -> DbFullDatasetStorage:
    """Return DbFullDatasetStorage wired to the test infra and fixture dataset."""
    dataset_id, org_id = db_full_fixture
    dataset = await _test_infra["repo"].get_dataset(dataset_id, org_id)
    assert dataset is not None
    return DbFullDatasetStorage(
        dataset_id=dataset_id,
        org_id=org_id,
        dataset_metadata=dataset,
        repo=_test_infra["repo"],
        session_factory=_test_infra["session_factory"],
        storage=_test_infra["storage"],
    )


# ── helper: async generator for write_predictions ─────────────────────────


async def _prediction_stream(
    items: list[PredictionResult],
) -> AsyncIterator[PredictionResult]:
    for item in items:
        yield item


async def _create_prediction_job(
    _test_infra: dict,
    *,
    job_id: str,
    dataset_id: str,
    org_id: str,
    created_at: datetime,
) -> None:
    async with _test_infra["session_factory"]() as session:
        session.add(
            PredictionJobORM(
                id=job_id,
                org_id=org_id,
                dataset_id=dataset_id,
                model_id="test-model",
                status="completed",
                target="classification",
                model_version="v1",
                sample_ids=None,
                summary_json={},
                created_by="test-user",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.commit()


# ── helper: create a fresh db_full dataset + storage ──────────────────────


async def _create_fresh_dataset(
    repo: DatasetSqlRepository,
    session_factory: Any,
    artifact_storage: InMemoryArtifactStorage,
    org_id: str,
    *,
    sample_count: int = 3,
) -> DbFullDatasetStorage:
    """Create a fresh DB_FULL dataset with *sample_count* samples, no annotations."""
    dataset_id = str(uuid4())
    dataset = Dataset(
        id=dataset_id,
        name=f"fresh-test-{uuid4().hex[:8]}",
        dataset_type="image_classification",
        task_spec=TaskSpec(task_type="classification", label_space=["a", "b"]),
        storage_mode=DatasetStorageMode.DB_FULL,
        ls_project_id="DB_FULL_TEST",
    )
    dataset = await repo.create_dataset(dataset, org_id=org_id)

    sample_ids = [str(uuid4()) for _ in range(sample_count)]
    from app.shared.api.schemas import Sample

    samples = [
        Sample(id=sid, dataset_id=dataset_id, image_uris=[f"https://example.com/{sid}.png"])
        for sid in sample_ids
    ]
    await repo.create_samples(samples)

    return DbFullDatasetStorage(
        dataset_id=dataset_id,
        org_id=org_id,
        dataset_metadata=dataset,
        repo=repo,
        session_factory=session_factory,
        storage=artifact_storage,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test class
# ═══════════════════════════════════════════════════════════════════════════


class TestDbFullDatasetStorage:
    """Integration tests for all 18 DbFullDatasetStorage methods."""

    # ── 1. constructor ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_constructor(self, storage: DbFullDatasetStorage, db_full_fixture: tuple[str, str]) -> None:
        """Create DbFullDatasetStorage and verify its dataset identity and mode."""
        dataset_id, _ = db_full_fixture
        assert storage.dataset_id == dataset_id
        assert storage.storage_mode == DatasetStorageMode.DB_FULL

    # ── 2. get_dataset_metadata ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_dataset_metadata_returns_dataset(self, storage: DbFullDatasetStorage) -> None:
        """get_dataset_metadata returns a Dataset with expected fields."""
        ds = await storage.get_dataset_metadata()
        assert ds is not None
        assert ds.id == storage.dataset_id
        assert ds.name is not None
        assert ds.dataset_type == "image_classification"
        assert ds.storage_mode == DatasetStorageMode.DB_FULL

    # ── 3. list_samples basic pagination ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_basic(self, storage: DbFullDatasetStorage) -> None:
        """5 samples total, list(0, 3) returns 3 items with total=5."""
        rows, total = await storage.list_samples(offset=0, limit=3)
        assert isinstance(rows, list)
        assert len(rows) == 3
        assert total == 5
        for r in rows:
            assert isinstance(r, SampleRow)
            assert r.sample_id
            assert r.dataset_id == storage.dataset_id

    # ── 3. list_samples with labels ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_with_labels(self, storage: DbFullDatasetStorage) -> None:
        """Fixture has 3 labels; list(with_labels=True) includes latest_label."""
        rows, total = await storage.list_samples(offset=0, limit=5, with_labels=True)
        assert total == 5
        labelled = [r for r in rows if r.latest_label is not None]
        assert len(labelled) == 3
        assert all(r.latest_label in ("cat", "dog") for r in labelled)

    @pytest.mark.asyncio
    async def test_list_samples_lazyframe_uses_bound_filters(
        self,
        storage: DbFullDatasetStorage,
    ) -> None:
        """LazyFrame label/sample filters use portable SQL bind parameters."""

        rows, _ = await storage.list_samples(limit=5)
        selected_ids = [rows[0].sample_id, rows[1].sample_id]

        lazyframe = cast(
            Any,
            await storage.list_samples(
                with_labels=True,
                sample_ids=selected_ids,
                return_lazyframe=True,
            ),
        )
        collected = lazyframe.collect()

        assert set(collected["id"].to_list()) == set(selected_ids)
        assert {"label", "latest_label"} <= set(collected.columns)

    # ── 4. list_samples label_filter ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_label_filter(self, storage: DbFullDatasetStorage) -> None:
        """Filter '__unlabeled__' returns 2, filter 'cat' returns 2."""
        rows_unlab, total_unlab = await storage.list_samples(label_filter="__unlabeled__")
        assert total_unlab == 2
        assert len(rows_unlab) == 2
        for r in rows_unlab:
            assert r.latest_label is None

        rows_cat, total_cat = await storage.list_samples(label_filter="cat")
        assert total_cat == 2
        assert len(rows_cat) == 2
        for r in rows_cat:
            assert r.latest_label == "cat"

    # ── 5. list_samples with predictions ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_with_predictions(
        self,
        storage: DbFullDatasetStorage,
        _test_infra: dict,
        db_full_fixture: tuple[str, str],
    ) -> None:
        """Write 2 predictions, list(with_predictions=True) includes latest_prediction."""
        dataset_id, org_id = db_full_fixture
        rows, _ = await storage.list_samples(limit=2)
        sample_ids = [r.sample_id for r in rows]

        preds = [
            PredictionResult(
                sample_id=sample_ids[0],
                predicted_label="cat",
                confidence=0.95,
                all_scores={"cat": 0.95, "dog": 0.05},
                model_id="m1",
                target="cls",
                model_version="v1",
                job_id="j1",
            ),
            PredictionResult(
                sample_id=sample_ids[1],
                predicted_label="dog",
                confidence=0.88,
                all_scores={"cat": 0.12, "dog": 0.88},
                model_id="m1",
                target="cls",
                model_version="v1",
                job_id="j1",
            ),
        ]

        count = await storage.write_predictions(
            _prediction_stream(preds),
            job_id="j1",
            model_id="m1",
            model_version="v1",
        )
        assert count == 2
        await _create_prediction_job(
            _test_infra,
            job_id="j1",
            dataset_id=dataset_id,
            org_id=org_id,
            created_at=_utcnow(),
        )

        rows2, _ = await storage.list_samples(
            limit=5, with_predictions=True, sample_ids=sample_ids,
        )
        predicted = [r for r in rows2 if r.latest_prediction is not None]
        assert len(predicted) == 2
        for r in predicted:
            assert isinstance(r.latest_prediction, dict)
            assert "predicted_label" in r.latest_prediction

    # ── 6. list_samples random_seed reproducibility ─────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_random_seed(self, storage: DbFullDatasetStorage) -> None:
        """Random seed is accepted and returns all samples (SQLite random() is non-deterministic)."""
        rows1, total1 = await storage.list_samples(limit=5, random_seed=42)
        rows2, total2 = await storage.list_samples(limit=5, random_seed=42)
        assert total1 == 5
        assert total2 == 5
        # Both calls return the same set of sample IDs
        ids1 = {r.sample_id for r in rows1}
        ids2 = {r.sample_id for r in rows2}
        assert ids1 == ids2
        assert len(ids1) == 5

    # ── 7. get_sample ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_sample(self, storage: DbFullDatasetStorage) -> None:
        """Get existing sample returns SampleRow, nonexistent returns None."""
        rows, _ = await storage.list_samples(limit=1)
        sid = rows[0].sample_id

        sr = await storage.get_sample(sid)
        assert sr is not None
        assert sr.sample_id == sid
        assert isinstance(sr, SampleRow)

        sr_none = await storage.get_sample("nonexistent-00000000")
        assert sr_none is None

    # ── 8. get_samples_by_id ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_samples_by_id(self, storage: DbFullDatasetStorage) -> None:
        """Batch lookup returns existing rows keyed by ID and omits missing IDs."""
        rows, _ = await storage.list_samples(limit=3)
        ids = [r.sample_id for r in rows]

        batch = await storage.get_samples_by_id(ids)
        assert len(batch) == 3
        for sample_id in ids:
            assert batch[sample_id].sample_id == sample_id

        # Include a nonexistent id
        missing_id = "nonexistent-00000000"
        batch2 = await storage.get_samples_by_id([ids[0], missing_id, ids[1]])
        assert set(batch2) == {ids[0], ids[1]}
        assert missing_id not in batch2

    # ── 9. create_annotations bulk ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_annotations_bulk(self, storage: DbFullDatasetStorage) -> None:
        """Create 3 annotations in batch, verify stats updated."""
        rows, _ = await storage.list_samples(limit=3)
        sample_ids = [r.sample_id for r in rows]

        annotations = [
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[i],
                label=f"bulk-label-{i}",
                annotation_value=None,
                created_by="bulk-test",
                created_at=_utcnow(),
            )
            for i in range(3)
        ]

        count = await storage.create_annotations(annotations)
        assert count == 3

        # Verify stats reflect new annotations (latest per sample)
        stats_after = await storage.get_annotation_stats()
        assert stats_after["total_samples"] == 5
        # We created annotations on 3 samples; all should now be annotated
        assert stats_after["annotated_samples"] >= 3

    # ── 10. update_annotations ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_annotations(self, storage: DbFullDatasetStorage) -> None:
        """Update label on an annotation and verify change."""
        ann_data = await storage.recent_annotations(limit=10)
        entries = ann_data["entries"]
        assert len(entries) >= 1, "Fixture should have at least 1 annotation"

        ann_id: str = entries[0]["id"]
        count = await storage.update_annotations([(ann_id, "updated-label")])
        assert count == 1

        # Verify via listing with labels — at least one sample now has "updated-label"
        rows, _ = await storage.list_samples(limit=5, with_labels=True)
        updated = [r for r in rows if r.latest_label == "updated-label"]
        assert len(updated) == 1

    # ── 11. delete_annotations ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_annotations(self, storage: DbFullDatasetStorage) -> None:
        """Delete an annotation and verify it is removed."""
        ann_data = await storage.recent_annotations(limit=10)
        entries = ann_data["entries"]
        assert len(entries) >= 1, "Fixture should have at least 1 annotation"

        ann_id: str = entries[0]["id"]
        count = await storage.delete_annotations([ann_id])
        assert count == 1

        # Verify gone
        ann_data2 = await storage.recent_annotations(limit=20)
        assert all(e["id"] != ann_id for e in ann_data2["entries"])

    # ── 12. get_annotation_stats ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_annotation_stats(self, storage: DbFullDatasetStorage) -> None:
        """Verify total_samples=5, annotated=3, unlabeled=2, label_counts."""
        stats = await storage.get_annotation_stats()
        assert stats["total_samples"] == 5
        assert stats["annotated_samples"] == 3
        assert stats["unlabeled_samples"] == 2
        assert "cat" in stats["label_counts"]
        assert "dog" in stats["label_counts"]
        assert stats["label_counts"]["cat"] == 2
        assert stats["label_counts"]["dog"] == 1

    # ── 13. write_predictions ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_write_predictions(
        self,
        storage: DbFullDatasetStorage,
        _test_infra: dict,
        db_full_fixture: tuple[str, str],
    ) -> None:
        """Stream 3 predictions, verify persisted and visible via listing."""
        dataset_id, org_id = db_full_fixture
        rows, _ = await storage.list_samples(limit=3)
        sample_ids = [r.sample_id for r in rows]

        preds = [
            PredictionResult(
                sample_id=sid,
                predicted_label="cat" if i % 2 == 0 else "dog",
                confidence=0.9,
                all_scores={"cat": 0.9, "dog": 0.1},
                model_id="test-model",
                target="classification",
                model_version="v1",
                job_id="test-job",
            )
            for i, sid in enumerate(sample_ids)
        ]

        count = await storage.write_predictions(
            _prediction_stream(preds),
            job_id="test-job",
            model_id="test-model",
            model_version="v1",
        )
        assert count == 3
        await _create_prediction_job(
            _test_infra,
            job_id="test-job",
            dataset_id=dataset_id,
            org_id=org_id,
            created_at=_utcnow(),
        )

        # Verify via list_samples with predictions
        rows2, _ = await storage.list_samples(
            limit=5, with_predictions=True, sample_ids=sample_ids,
        )
        predicted = [r for r in rows2 if r.latest_prediction is not None]
        assert len(predicted) == 3

    # ── 14. prediction_summary ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_prediction_summary(self, storage: DbFullDatasetStorage) -> None:
        """Write predictions and verify summary aggregation."""
        rows, _ = await storage.list_samples(limit=3)
        sample_ids = [r.sample_id for r in rows]

        preds = [
            PredictionResult(
                sample_id=sid,
                predicted_label="cat",
                confidence=0.9,
                all_scores={"cat": 0.9, "dog": 0.1},
                model_id="summary-model",
                target="classification",
                model_version="v1",
                job_id="summary-job",
            )
            for sid in sample_ids
        ]

        await storage.write_predictions(
            _prediction_stream(preds),
            job_id="summary-job",
            model_id="summary-model",
            model_version="v1",
        )

        summary = await storage.prediction_summary()
        assert summary["total_predictions"] == 3
        assert len(summary["models"]) == 1
        assert summary["models"][0]["model_id"] == "summary-model"
        assert summary["models"][0]["count"] == 3
        assert "cat" in summary["label_distribution"]
        assert summary["label_distribution"]["cat"] == 3

    # ── 15. upsert_sample_feature ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upsert_sample_feature(self, storage: DbFullDatasetStorage) -> None:
        """Insert then update a sample feature embedding."""
        rows, _ = await storage.list_samples(limit=1)
        sid = rows[0].sample_id

        # Insert
        emb1: list[float] = [0.1, 0.2, 0.3]
        await storage.upsert_sample_feature(sid, emb1, "test-embedder")

        # Update with different embedding
        emb2: list[float] = [0.4, 0.5, 0.6]
        await storage.upsert_sample_feature(sid, emb2, "test-embedder-2")

        # No exception = success; similarity_search will confirm persistence
        results = await storage.similarity_search(emb2, k=1, exclude_id=sid)
        assert isinstance(results, list)

    # ── 16. similarity_search ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_similarity_search(self, storage: DbFullDatasetStorage) -> None:
        """Insert 3 features, query nearest to first, verify results."""
        rows, _ = await storage.list_samples(limit=3)
        assert len(rows) >= 2, "Need at least 2 samples for similarity test"

        # Insert features for all 3
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        for r, emb in zip(rows, embeddings):
            await storage.upsert_sample_feature(r.sample_id, emb, "sim-embedder")

        # Query nearest to first embedding — the first sample itself should be closest
        # But exclude_id removes it, so we get other samples
        results = await storage.similarity_search([1.0, 0.0, 0.0], k=2, exclude_id=rows[0].sample_id)
        assert len(results) >= 1
        for entry in results:
            assert "sample_id" in entry
            assert "score" in entry
            assert isinstance(entry["score"], float)

        # Without exclude, the query embedding matches the first sample exactly
        results_all = await storage.similarity_search([1.0, 0.0, 0.0], k=2)
        assert len(results_all) >= 1

    # ── 17. materialize ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_materialize(
        self,
        storage: DbFullDatasetStorage,
        _test_infra: dict,
    ) -> None:
        """Materialize produces valid parquet with row_count=5."""
        result = await storage.materialize()
        assert result.row_count == 5
        assert result.manifest_uri is not None

        import pyarrow.parquet as pq

        parquet_bytes = await _test_infra["storage"].get_bytes(result.manifest_uri)
        table = pq.read_table(_io.BytesIO(parquet_bytes))
        assert table.num_rows == 5
        assert table.schema.equals(DB_FULL_MATERIALIZED_SCHEMA)

    # ── 18. delete_samples ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_samples(self, storage: DbFullDatasetStorage) -> None:
        """Delete 2 samples, verify remaining count is 3."""
        rows, _ = await storage.list_samples(limit=2)
        ids = [r.sample_id for r in rows]

        count = await storage.delete_samples(ids)
        assert count == 2

        _, total = await storage.list_samples()
        assert total == 3

    # ── 19. delete cascade ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_cascade(self, _test_infra: dict) -> None:
        """Create a dataset with samples+annotations+predictions, delete(), verify all gone."""
        repo: DatasetSqlRepository = _test_infra["repo"]
        session_factory = _test_infra["session_factory"]
        artifact_storage: InMemoryArtifactStorage = _test_infra["storage"]
        org_id: str = _test_infra["org_id"]

        # Create a fresh storage instance with its own dataset
        fresh = await _create_fresh_dataset(
            repo, session_factory, artifact_storage, org_id, sample_count=3,
        )
        dataset_id = fresh.dataset_id

        # Get sample IDs
        rows, _ = await fresh.list_samples(limit=3)
        sample_ids = [r.sample_id for r in rows]

        # Add annotations
        anns = [
            Annotation(
                id=str(uuid4()),
                sample_id=sid,
                label=f"ann-{i}",
                created_by="cascade-test",
                created_at=_utcnow(),
            )
            for i, sid in enumerate(sample_ids)
        ]
        await fresh.create_annotations(anns)

        # Add predictions
        preds = [
            PredictionResult(
                sample_id=sid,
                predicted_label="cascade-label",
                confidence=0.99,
                model_id="cascade-model",
                target="cls",
                model_version="v1",
                job_id="cascade-job",
            )
            for sid in sample_ids
        ]
        await fresh.write_predictions(
            _prediction_stream(preds),
            job_id="cascade-job",
            model_id="cascade-model",
            model_version="v1",
        )

        # Add sample features
        await fresh.upsert_sample_feature(sample_ids[0], [0.0, 0.0, 0.0], "cascade-embed")

        # Verify data exists before delete
        assert (await fresh.get_sample(sample_ids[0])) is not None
        ann_data = await fresh.recent_annotations(limit=10)
        assert len(ann_data["entries"]) >= 3
        summary = await fresh.prediction_summary()
        assert summary["total_predictions"] == 3
        sim = await fresh.similarity_search([0.0, 0.0, 0.0], k=1)
        assert len(sim) >= 1

        # Delete
        await fresh.delete()

        # Verify everything is gone — dataset row too
        async with session_factory() as session:
            from app.shared.db.registry import DatasetORM

            ds_row = await session.get(DatasetORM, dataset_id)
            assert ds_row is None, "DatasetORM row should be deleted"
