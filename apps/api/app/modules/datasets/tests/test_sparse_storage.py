"""Integration tests for SparseDatasetStorage covering the core public methods.

Uses real in-memory storage via the ``_test_infra`` and ``sparse_fixture``
fixtures from ``conftest.py`` — no mocks.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio  # type: ignore[import-untyped]

from app.modules.datasets.adapter.sparse_storage import SparseDatasetStorage
from app.modules.datasets.domain.sample_row import (
    BulkSampleRow,
    PredictionResult,
    SampleRow,
)
from app.shared.api.schemas import Annotation, Dataset, DatasetStorageMode
from app.shared.db.registry import PredictionJobORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── storage fixture wired to sparse_fixture ─────────────────────────────


@pytest_asyncio.fixture
async def storage(
    _test_infra: dict, sparse_fixture: tuple[str, str]
) -> SparseDatasetStorage:
    """Return SparseDatasetStorage wired to the test infra and fixture dataset."""
    dataset_id, org_id = sparse_fixture
    return SparseDatasetStorage(
        dataset_id=dataset_id,
        org_id=org_id,
        storage=_test_infra["storage"],
        payload_store=_test_infra["payload_store"],
        session_factory=_test_infra["session_factory"],
        repo=_test_infra["repo"],
    )


# ── helper: async generator for write_predictions ──────────────────────


async def _prediction_stream(
    items: list[PredictionResult],
) -> AsyncIterator[PredictionResult]:
    for item in items:
        yield item


async def _bulk_sample_stream(
    items: list[BulkSampleRow],
) -> AsyncIterator[BulkSampleRow]:
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


# ═══════════════════════════════════════════════════════════════════════════
# Test class
# ═══════════════════════════════════════════════════════════════════════════


class TestSparseDatasetStorage:
    """Integration tests for core SparseDatasetStorage methods."""

    # ── 1. constructor ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_constructor(
        self, storage: SparseDatasetStorage, sparse_fixture: tuple[str, str]
    ) -> None:
        """Verify dataset_id, storage_mode, and capabilities."""
        dataset_id, _ = sparse_fixture
        assert storage.dataset_id == dataset_id
        assert storage.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE

        caps = storage.capabilities
        assert caps.can_write_samples is True
        assert caps.can_random is True
        assert caps.can_similarity is True
        assert caps.can_materialize is True
        assert caps.can_lazyframe is True

    @pytest.mark.asyncio
    async def test_write_samples_appends_to_existing_manifest(
        self,
        storage: SparseDatasetStorage,
        sparse_fixture: tuple[str, str],
        _test_infra: dict,
    ) -> None:
        dataset_id, org_id = sparse_fixture
        payload_store = _test_infra["payload_store"]

        count = await storage.write_samples(
            _bulk_sample_stream(
                [
                    BulkSampleRow(sample_id="sparse-005"),
                    BulkSampleRow(sample_id="sparse-006"),
                ]
            ),
            batch_size=1,
        )

        manifest = await payload_store.get_manifest(dataset_id, org_id)

        assert count == 2
        assert manifest.total_rows == 7
        assert manifest.shard_count == 3
        assert [shard.shard_index for shard in manifest.shards] == [0, 1, 2]
        assert set(manifest.sample_index) == {
            "sparse-000",
            "sparse-001",
            "sparse-002",
            "sparse-003",
            "sparse-004",
            "sparse-005",
            "sparse-006",
        }
        assert manifest.sample_index["sparse-005"].shard_index == 1
        assert manifest.sample_index["sparse-006"].shard_index == 2

    # ── 2. list_samples basic pagination ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_basic(self, storage: SparseDatasetStorage) -> None:
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
    async def test_list_samples_with_labels(self, storage: SparseDatasetStorage) -> None:
        """Create 2 annotations, then list with with_labels=True."""
        # Get sample IDs from the fixture
        rows, _ = await storage.list_samples(limit=2)
        sample_ids = [r.sample_id for r in rows]

        annotations = [
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[0],
                label="cat",
                annotation_value=None,
                created_by="test-user",
                created_at=_utcnow(),
            ),
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[1],
                label="dog",
                annotation_value=None,
                created_by="test-user",
                created_at=_utcnow(),
            ),
        ]
        await storage.create_annotations(annotations)

        rows2, total = await storage.list_samples(
            offset=0, limit=5, with_labels=True
        )
        assert total == 5
        labelled = [r for r in rows2 if r.latest_label is not None]
        assert len(labelled) == 2
        labels = {r.sample_id: r.latest_label for r in labelled}
        assert labels.get(sample_ids[0]) == "cat"
        assert labels.get(sample_ids[1]) == "dog"

    # ── 4. list_samples lazyframe ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_lazyframe(self, storage: SparseDatasetStorage) -> None:
        """return_lazyframe=True returns a polars LazyFrame."""
        try:
            import polars as pl  # noqa: F401
        except ImportError:
            pytest.skip("polars library not installed")

        lf: Any = await storage.list_samples(return_lazyframe=True)
        assert lf is not None
        df = lf.collect()
        assert df.height == 5

    @pytest.mark.asyncio
    async def test_list_samples_lazyframe_honors_sample_ids(
        self, storage: SparseDatasetStorage
    ) -> None:
        """return_lazyframe=True applies sample_ids before prediction consumers."""
        try:
            import polars as pl  # noqa: F401
        except ImportError:
            pytest.skip("polars library not installed")

        rows, _ = await storage.list_samples(limit=3)
        sample_ids = [r.sample_id for r in rows[:2]]

        lf: Any = await storage.list_samples(
            return_lazyframe=True,
            sample_ids=sample_ids,
        )
        df = lf.collect()

        assert df.height == 2
        assert set(df["sample_id"].to_list()) == set(sample_ids)

    # ── 5. list_samples lazyframe with labels ──────────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_lazyframe_with_labels(
        self, storage: SparseDatasetStorage
    ) -> None:
        """return_lazyframe=True with with_labels=True returns a LazyFrame
        with label and annotation_value columns."""
        try:
            import polars as pl  # noqa: F401
        except ImportError:
            pytest.skip("polars library not installed")

        rows, _ = await storage.list_samples(limit=2)
        sample_ids = [r.sample_id for r in rows]

        annotations = [
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[0],
                label="cat",
                annotation_value=None,
                created_by="test-user",
                created_at=_utcnow(),
            ),
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[1],
                label="dog",
                annotation_value=None,
                created_by="test-user",
                created_at=_utcnow(),
            ),
        ]
        await storage.create_annotations(annotations)

        lf: Any = await storage.list_samples(
            return_lazyframe=True, with_labels=True
        )
        assert lf is not None
        df = lf.collect()
        assert df.height == 5

        assert "label" in df.columns
        assert "annotation_value" in df.columns
        annotated = df.filter(pl.col("label").is_not_null())
        assert annotated.height == 2
        labels = annotated["label"].to_list()
        assert "cat" in labels
        assert "dog" in labels

    # ── 6. list_samples label_filter ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_samples_label_filter(
        self, storage: SparseDatasetStorage
    ) -> None:
        """Verify label_filter basic behaviour: '__unlabeled__' returns all 5 in a fresh dataset."""
        rows_unlab, total_unlab = await storage.list_samples(
            label_filter="__unlabeled__"
        )
        assert total_unlab == 5

    # ── 7. get_dataset_metadata ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_dataset_metadata_returns_dataset(
        self, storage: SparseDatasetStorage
    ) -> None:
        """get_dataset_metadata returns the Dataset record with expected fields."""
        ds = await storage.get_dataset_metadata()
        assert ds is not None
        assert isinstance(ds, Dataset)
        assert ds.id == storage.dataset_id
        assert ds.name
        assert ds.dataset_type == "image_classification"
        assert ds.storage_mode == DatasetStorageMode.FILE_SHARD_SPARSE

    # ── 8. get_sample ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_sample(self, storage: SparseDatasetStorage) -> None:
        """Get existing sample returns SampleRow, nonexistent returns None."""
        rows, _ = await storage.list_samples(limit=1)
        sid = rows[0].sample_id

        sr = await storage.get_sample(sid)
        assert sr is not None
        assert sr.sample_id == sid
        assert isinstance(sr, SampleRow)

        sr_none = await storage.get_sample("nonexistent-00000000")
        assert sr_none is None

    # ── 9. get_samples_batch ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_samples_batch(self, storage: SparseDatasetStorage) -> None:
        """Batch of 3 IDs returns 3 rows preserving order, None for missing."""
        rows, _ = await storage.list_samples(limit=3)
        ids = [r.sample_id for r in rows]

        batch = await storage.get_samples_batch(ids)
        assert len(batch) == 3
        for i, sr in enumerate(batch):
            assert sr is not None
            assert sr.sample_id == ids[i]

        # Include a nonexistent id
        batch2 = await storage.get_samples_batch(
            [ids[0], "nonexistent-00000000", ids[1]]
        )
        assert len(batch2) == 3
        assert batch2[0] is not None
        assert batch2[1] is None
        assert batch2[2] is not None

    # ── 10. create_annotations bulk ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_annotations_bulk(
        self, storage: SparseDatasetStorage
    ) -> None:
        """Create 3 annotations in batch, verify via stats and recent_annotations."""
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

        # Verify via recent_annotations
        ann_data = await storage.recent_annotations(limit=10)
        entries = ann_data["entries"]
        assert len(entries) >= 3
        entry_labels = {e["sample_id"] for e in entries}
        for sid in sample_ids:
            assert sid in entry_labels

    # ── 11. get_annotation_stats ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_annotation_stats(
        self, storage: SparseDatasetStorage
    ) -> None:
        """Create labels and verify stats reflect per-label counts."""
        rows, _ = await storage.list_samples(limit=3)
        sample_ids = [r.sample_id for r in rows]

        annotations = [
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[0],
                label="cat",
                annotation_value=None,
                created_by="stats-test",
                created_at=_utcnow(),
            ),
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[1],
                label="dog",
                annotation_value=None,
                created_by="stats-test",
                created_at=_utcnow(),
            ),
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[2],
                label="cat",
                annotation_value=None,
                created_by="stats-test",
                created_at=_utcnow(),
            ),
        ]
        await storage.create_annotations(annotations)

        stats = await storage.get_annotation_stats()
        assert isinstance(stats, dict)
        assert stats.get("cat") == 2
        assert stats.get("dog") == 1

    # ── 12. write_predictions ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_write_predictions(
        self,
        storage: SparseDatasetStorage,
        _test_infra: dict,
        sparse_fixture: tuple[str, str],
    ) -> None:
        """Stream 3 predictions, verify persisted and visible via listing."""
        dataset_id, org_id = sparse_fixture
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

        # Verify prediction_summary
        summary = await storage.prediction_summary()
        assert summary["total_predictions"] == 3

    @pytest.mark.asyncio
    async def test_with_predictions_without_job_id_reads_accumulated_final(
        self,
        storage: SparseDatasetStorage,
        sparse_fixture: tuple[str, str],
    ) -> None:
        """Unscoped prediction listing reads the accumulated final result."""
        _dataset_id, _org_id = sparse_fixture
        rows, _ = await storage.list_samples(limit=1)
        sample_id = rows[0].sample_id

        old_job_id = "old-prediction-job"
        latest_job_id = "latest-prediction-job"
        await storage.write_predictions(
            _prediction_stream(
                [
                    PredictionResult(
                        sample_id=sample_id,
                        predicted_label="old-label",
                        confidence=0.1,
                        model_id="test-model",
                        target="classification",
                        model_version="v1",
                        job_id=old_job_id,
                    )
                ]
            ),
            job_id=old_job_id,
            model_id="test-model",
            model_version="v1",
        )
        await storage.write_predictions(
            _prediction_stream(
                [
                    PredictionResult(
                        sample_id=sample_id,
                        predicted_label="latest-label",
                        confidence=0.9,
                        model_id="test-model",
                        target="classification",
                        model_version="v1",
                        job_id=latest_job_id,
                    )
                ]
            ),
            job_id=latest_job_id,
            model_id="test-model",
            model_version="v1",
        )

        listed, _ = await storage.list_samples(
            limit=1,
            with_predictions=True,
            sample_ids=[sample_id],
        )

        assert listed[0].latest_prediction is not None
        assert listed[0].latest_prediction["predicted_label"] == "latest-label"
        assert listed[0].latest_prediction["job_id"] == latest_job_id

        old_scoped, _ = await storage.list_samples(
            limit=1,
            with_predictions=True,
            prediction_job_id=old_job_id,
            sample_ids=[sample_id],
        )
        assert old_scoped[0].latest_prediction is not None
        assert old_scoped[0].latest_prediction["predicted_label"] == "old-label"
        assert old_scoped[0].latest_prediction["job_id"] == old_job_id

    @pytest.mark.asyncio
    async def test_accumulated_predictions_overwrite_and_preserve(
        self,
        storage: SparseDatasetStorage,
    ) -> None:
        rows, _ = await storage.list_samples(limit=2)
        first_id = rows[0].sample_id
        second_id = rows[1].sample_id

        await storage.write_predictions(
            _prediction_stream(
                [
                    PredictionResult(
                        sample_id=first_id,
                        predicted_label="first-v1",
                        confidence=0.1,
                        model_id="test-model",
                        target="classification",
                        model_version="v1",
                        job_id="job-one",
                    ),
                    PredictionResult(
                        sample_id=second_id,
                        predicted_label="second-v1",
                        confidence=0.2,
                        model_id="test-model",
                        target="classification",
                        model_version="v1",
                        job_id="job-one",
                    ),
                ]
            ),
            job_id="job-one",
            model_id="test-model",
            model_version="v1",
        )
        await storage.write_predictions(
            _prediction_stream(
                [
                    PredictionResult(
                        sample_id=first_id,
                        predicted_label="first-v2",
                        confidence=0.9,
                        model_id="test-model",
                        target="classification",
                        model_version="v2",
                        job_id="job-two",
                    )
                ]
            ),
            job_id="job-two",
            model_id="test-model",
            model_version="v2",
        )

        listed, _ = await storage.list_samples(
            limit=2,
            with_predictions=True,
            sample_ids=[first_id, second_id],
        )
        predictions = {
            row.sample_id: row.latest_prediction
            for row in listed
            if row.latest_prediction is not None
        }

        assert predictions[first_id]["predicted_label"] == "first-v2"
        assert predictions[first_id]["job_id"] == "job-two"
        assert predictions[second_id]["predicted_label"] == "second-v1"
        assert predictions[second_id]["job_id"] == "job-one"

    # ── 13. materialize ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_materialize(self, storage: SparseDatasetStorage) -> None:
        """Materialize produces valid parquet with row_count=5."""
        result = await storage.materialize()
        assert result.row_count == 5
        assert result.manifest_uri is not None

        # For InMemoryArtifactStorage, manifest_uri typically points to a
        # real temp path or is an in-memory key — try reading as parquet
        if os.path.isfile(result.manifest_uri):
            import pyarrow.parquet as pq

            table = pq.read_table(result.manifest_uri)
            assert table.num_rows == 5
            assert "sample_id" in table.column_names
            os.unlink(result.manifest_uri)

    # ── 14. recent_annotations ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_recent_annotations(self, storage: SparseDatasetStorage) -> None:
        """Create annotations and verify recent_annotations returns them."""
        rows, _ = await storage.list_samples(limit=2)
        sample_ids = [r.sample_id for r in rows]

        annotations = [
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[0],
                label="recent-cat",
                annotation_value=None,
                created_by="recent-test",
                created_at=_utcnow(),
            ),
            Annotation(
                id=str(uuid4()),
                sample_id=sample_ids[1],
                label="recent-dog",
                annotation_value=None,
                created_by="recent-test",
                created_at=_utcnow(),
            ),
        ]
        await storage.create_annotations(annotations)

        ann_data = await storage.recent_annotations(limit=10)
        entries = ann_data["entries"]
        assert len(entries) >= 2
        labels = {e["sample_id"]: e["label"] for e in entries}
        assert labels.get(sample_ids[0]) == "recent-cat"
        assert labels.get(sample_ids[1]) == "recent-dog"

    # ── 15. delete_samples ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_samples(self, storage: SparseDatasetStorage) -> None:
        """Delete 2 samples, verify remaining count is 3."""
        rows, _ = await storage.list_samples(limit=2)
        ids = [r.sample_id for r in rows]

        count = await storage.delete_samples(ids)
        assert count == 2

        _, total = await storage.list_samples()
        assert total == 3

    # ── 16. update_annotations ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_annotations(self, storage: SparseDatasetStorage) -> None:
        """Update label on an annotation and verify change via list_samples."""
        rows, _ = await storage.list_samples(limit=1)
        sid = rows[0].sample_id

        # Create initial annotation
        ann = Annotation(
            id=str(uuid4()),
            sample_id=sid,
            label="original",
            annotation_value=None,
            created_by="update-test",
            created_at=_utcnow(),
        )
        await storage.create_annotations([ann])

        # Get the annotation_id from recent_annotations
        ann_data = await storage.recent_annotations(limit=10)
        entries = ann_data["entries"]
        matching = [e for e in entries if e["sample_id"] == sid]
        assert len(matching) >= 1
        ann_id: str = matching[0]["id"]

        count = await storage.update_annotations([(ann_id, "updated-label")])
        assert count == 1

        rows2, _ = await storage.list_samples(limit=5, with_labels=True)
        updated = [r for r in rows2 if r.latest_label == "updated-label"]
        assert len(updated) == 1

    # ── 17. delete_annotations ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_annotations(self, storage: SparseDatasetStorage) -> None:
        """Delete an annotation and verify delete count is correct."""
        rows, _ = await storage.list_samples(limit=1)
        sid = rows[0].sample_id

        ann = Annotation(
            id=str(uuid4()),
            sample_id=sid,
            label="to-delete",
            annotation_value=None,
            created_by="delete-test",
            created_at=_utcnow(),
        )
        await storage.create_annotations([ann])

        ann_data = await storage.recent_annotations(limit=10)
        entries = ann_data["entries"]
        matching = [e for e in entries if e["sample_id"] == sid]
        assert len(matching) >= 1
        ann_id: str = matching[0]["id"]

        count = await storage.delete_annotations([ann_id])
        assert count >= 1
