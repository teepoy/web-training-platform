"""Pytest fixtures for DatasetStorageAgg test implementations.

Provides reusable fixture infrastructure that prepares test datasets in both
db_full (SQLite-backed) and sparse (parquet-shard-backed) modes, plus shared
SampleRow / PredictionResult test data.

Fixtures:
  db_full_fixture  – (dataset_id, org_id) tuple with 5 SQLite samples + labels
  sparse_fixture   – (dataset_id, org_id) tuple with 5-row parquet shard + manifest
  sample_data      – list[SampleRow]  (3 labelled + 2 unlabelled)
  prediction_data  – list[PredictionResult]
"""

from __future__ import annotations

import io as _io
from datetime import datetime, timezone
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import pytest_asyncio  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.datasets.domain.sample_row import PredictionResult, SampleRow
from app.shared.api.schemas import (
    Annotation,
    Dataset,
    DatasetStorageMode,
    Sample,
    TaskSpec,
)
from app.shared.db.registry import Base, OrganizationORM
from app.shared.db.session import create_session_factory
from app.modules.datasets.adapter.repositories.dataset_sql_repository import (
    DatasetSqlRepository,
)
from tests.support.artifact_storage import InMemoryArtifactStorage
from app.modules.storage.domain.sparse import (
    DatasetManifest,
    DatasetPayloadStore,
    SampleLocator,
    ShardEntry,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_parquet_shard_bytes(sample_ids: list[str]) -> bytes:
    """Create an in-memory parquet shard with sample_id + images columns."""
    table = pa.table(
        {
            "sample_id": pa.array(sample_ids, type=pa.string()),
            "images": pa.array(
                [f"fake_image_content_for_{sid}".encode() for sid in sample_ids],
                type=pa.binary(),
            ),
        }
    )
    buf = _io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


# ── shared infrastructure ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def _test_infra(request):
    """Set up test infrastructure: SQLite engine, repo, storage, org.

    Creates an in-memory SQLite database, initialises all tables, creates a
    test organisation, and returns a dict of wired dependencies.  Teardown
    disposes the engine when all dependent fixtures have finished.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    repo = DatasetSqlRepository(session_factory)
    storage = InMemoryArtifactStorage()
    payload_store = DatasetPayloadStore(storage)

    org_id = str(uuid4())
    org_slug = f"fixture-org-{uuid4().hex[:8]}"
    async with session_factory() as session:
        session.add(OrganizationORM(id=org_id, name=org_slug, slug=org_slug))
        await session.commit()

    infra = {
        "repo": repo,
        "storage": storage,
        "payload_store": payload_store,
        "session_factory": session_factory,
        "org_id": org_id,
        "org_name": org_slug,
    }

    yield infra

    await engine.dispose()


# ── dataset fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_full_fixture(_test_infra: dict):  # type: ignore[return-type]  # pytest fixture yields via generator
    """Create a db_full dataset with 5 samples and 3 annotations in SQLite.

    Returns (dataset_id, org_id).
    """
    repo: DatasetSqlRepository = _test_infra["repo"]
    org_id: str = _test_infra["org_id"]

    dataset_id = str(uuid4())
    dataset = Dataset(
        id=dataset_id,
        name=f"test-db-full-{uuid4().hex[:8]}",
        dataset_type="image_classification",
        task_spec=TaskSpec(task_type="classification", label_space=["cat", "dog"]),
        storage_mode=DatasetStorageMode.DB_FULL,
        ls_project_id="DB_FULL_TEST",
    )

    await repo.create_dataset(dataset, org_id=org_id)

    sample_ids = [str(uuid4()) for _ in range(5)]
    samples = [
        Sample(
            id=sid,
            dataset_id=dataset_id,
            image_uris=[f"https://example.com/{sid}.png"],
            metadata={"index": i},
        )
        for i, sid in enumerate(sample_ids)
    ]
    await repo.create_samples(samples)

    # Label the first three samples
    _labels = ["cat", "dog", "cat"]
    for sid, label in zip(sample_ids[:3], _labels):
        ann = Annotation(
            id=str(uuid4()),
            sample_id=sid,
            label=label,
            annotation_value=None,
            created_by="fixture-user",
            created_at=_utcnow(),
        )
        await repo.create_annotation(ann)

    yield dataset_id, org_id

    # Cleanup: cascade-delete the dataset (samples + annotations follow)
    await repo.delete_dataset(dataset_id, org_id=org_id)


@pytest_asyncio.fixture
async def sparse_fixture(_test_infra: dict):  # type: ignore[return-type]  # pytest fixture yields via generator
    """Create a file_shard_sparse dataset with a 5-row parquet shard and manifest.

    Returns (dataset_id, org_id).
    """
    repo: DatasetSqlRepository = _test_infra["repo"]
    payload_store: DatasetPayloadStore = _test_infra["payload_store"]
    org_id: str = _test_infra["org_id"]

    dataset_id = str(uuid4())
    dataset = Dataset(
        id=dataset_id,
        name=f"test-sparse-{uuid4().hex[:8]}",
        dataset_type="image_classification",
        task_spec=TaskSpec(task_type="classification", label_space=["cat", "dog"]),
        storage_mode=DatasetStorageMode.FILE_SHARD_SPARSE,
        ls_project_id="SPARSE_NO_LS",
    )

    await repo.create_dataset(dataset, org_id=org_id)

    sample_ids = [f"sparse-{i:03d}" for i in range(5)]
    shard_data = _make_parquet_shard_bytes(sample_ids)

    shard_entry: ShardEntry = await payload_store.put_shard(
        dataset_id=dataset_id,
        org_id=org_id,
        shard_index=0,
        data=shard_data,
        row_count=5,
        format="parquet",
    )

    sample_index: dict[str, SampleLocator] = {
        sid: SampleLocator(dataset_id=dataset_id, shard_index=0, row_index=i)
        for i, sid in enumerate(sample_ids)
    }

    manifest = DatasetManifest(
        dataset_id=dataset_id,
        storage_mode="file_shard_sparse",
        shard_count=1,
        total_rows=5,
        shards=[shard_entry],
        sample_index=sample_index,
    )
    await payload_store.put_manifest(manifest, org_id=org_id)

    yield dataset_id, org_id

    # Cleanup: delete payload objects from storage, then cascade-delete DB record
    try:
        await payload_store.delete_dataset_payload(dataset_id, org_id)
    except Exception:
        pass  # best-effort — some backends may have already evicted the objects

    await repo.delete_dataset(dataset_id, org_id=org_id)


# ── reusable test data ───────────────────────────────────────────────────────


@pytest.fixture
def sample_data() -> list[SampleRow]:
    """Return 5 SampleRow objects: 3 labelled + 2 unlabelled."""
    dataset_id = "data-ds-00000000-0000-0000-0000-000000000001"
    return [
        SampleRow(
            sample_id="data-smpl-001",
            dataset_id=dataset_id,
            image_uris=["https://example.com/cat1.png"],
            label="cat",
            latest_label="cat",
            metadata={"breed": "persian"},
        ),
        SampleRow(
            sample_id="data-smpl-002",
            dataset_id=dataset_id,
            image_uris=["https://example.com/dog1.png"],
            label="dog",
            latest_label="dog",
            metadata={"breed": "labrador"},
        ),
        SampleRow(
            sample_id="data-smpl-003",
            dataset_id=dataset_id,
            image_uris=["https://example.com/cat2.png"],
            label="cat",
            latest_label="cat",
            metadata={"breed": "siamese"},
        ),
        SampleRow(
            sample_id="data-smpl-004",
            dataset_id=dataset_id,
            image_uris=["https://example.com/unknown1.png"],
            label=None,
            latest_label=None,
            metadata={},
        ),
        SampleRow(
            sample_id="data-smpl-005",
            dataset_id=dataset_id,
            image_uris=["https://example.com/unknown2.png"],
            label=None,
            latest_label=None,
            metadata={},
        ),
    ]


@pytest.fixture
def prediction_data() -> list[PredictionResult]:
    """Return 3 PredictionResult entries for use in write_predictions tests."""
    return [
        PredictionResult(
            sample_id="data-smpl-001",
            predicted_label="cat",
            confidence=0.92,
            all_scores={"cat": 0.92, "dog": 0.08},
            model_id="model-test-001",
            target="image_classification",
            model_version="v1.0",
            job_id="job-test-predict-001",
        ),
        PredictionResult(
            sample_id="data-smpl-002",
            predicted_label="dog",
            confidence=0.87,
            all_scores={"cat": 0.13, "dog": 0.87},
            model_id="model-test-001",
            target="image_classification",
            model_version="v1.0",
            job_id="job-test-predict-001",
        ),
        PredictionResult(
            sample_id="data-smpl-003",
            predicted_label="cat",
            confidence=0.65,
            all_scores={"cat": 0.65, "dog": 0.35},
            model_id="model-test-001",
            target="image_classification",
            model_version="v1.0",
            job_id="job-test-predict-001",
        ),
    ]
