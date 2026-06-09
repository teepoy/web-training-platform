from __future__ import annotations

import io
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq

from platform_runtime.contracts import ArtifactStorage

_SPARSE_ANNOTATION_SCHEMA = pa.schema(
    [
        ("annotation_id", pa.string()),
        ("sample_id", pa.string()),
        ("label", pa.string()),
        ("annotation_value", pa.string()),
        ("created_by", pa.string()),
        ("created_at", pa.string()),
        ("user_id", pa.string()),
    ]
)


@dataclass(frozen=True, slots=True)
class SparseAnnotationRecord:
    annotation_id: str
    sample_id: str
    label: str
    annotation_value: str
    created_by: str
    created_at: str
    user_id: str


class SparseAnnotationStore:
    """Append-only parquet sidecar for sparse-dataset annotations.

    Layout: ``datasets/{org_id}/{dataset_id}/annotations/{uuid}.parquet``.
    Each ``append`` writes one new parquet file; ``load_all`` lists the
    prefix and concatenates. Latest-wins-per-sample is resolved on read
    by ordering on ``created_at``.
    """

    def __init__(self, storage: ArtifactStorage) -> None:
        self._storage = storage

    @staticmethod
    def get_annotations_prefix(dataset_id: str, org_id: str) -> str:
        return f"datasets/{org_id}/{dataset_id}/annotations"

    async def append(
        self,
        *,
        dataset_id: str,
        org_id: str,
        items: list[SparseAnnotationRecord],
    ) -> str:
        if not items:
            raise ValueError("append() requires at least one record")

        columns = {
            field.name: [getattr(item, field.name) for item in items]
            for field in _SPARSE_ANNOTATION_SCHEMA
        }
        table = pa.table(columns, schema=_SPARSE_ANNOTATION_SCHEMA)

        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        data = buf.getvalue()

        object_name = f"{self.get_annotations_prefix(dataset_id, org_id)}/{uuid.uuid4().hex}.parquet"
        return await self._storage.put_bytes(
            object_name=object_name,
            data=data,
            content_type="application/octet-stream",
        )

    async def load_all(
        self, *, dataset_id: str, org_id: str
    ) -> list[SparseAnnotationRecord]:
        prefix = self.get_annotations_prefix(dataset_id, org_id) + "/"
        uris = await self._storage.list_prefix(prefix)
        records: list[SparseAnnotationRecord] = []
        for uri in uris:
            raw = await self._storage.get_bytes(uri)
            table = pq.read_table(io.BytesIO(raw))
            rows = table.to_pylist()
            for row in rows:
                records.append(
                    SparseAnnotationRecord(
                        annotation_id=row["annotation_id"],
                        sample_id=row["sample_id"],
                        label=row["label"],
                        annotation_value=row["annotation_value"] or "",
                        created_by=row["created_by"] or "",
                        created_at=row["created_at"] or "",
                        user_id=row["user_id"] or "",
                    )
                )
        return records

    async def latest_by_sample(
        self, *, dataset_id: str, org_id: str
    ) -> dict[str, SparseAnnotationRecord]:
        records = await self.load_all(dataset_id=dataset_id, org_id=org_id)
        latest: dict[str, SparseAnnotationRecord] = {}
        for record in records:
            existing = latest.get(record.sample_id)
            if existing is None or record.created_at >= existing.created_at:
                latest[record.sample_id] = record
        return latest

    async def stats(self, *, dataset_id: str, org_id: str) -> dict[str, int]:
        latest = await self.latest_by_sample(dataset_id=dataset_id, org_id=org_id)
        counter: Counter[str] = Counter()
        for record in latest.values():
            counter[record.label] += 1
        return dict(counter)


def build_annotation_record(
    *,
    sample_id: str,
    label: str,
    annotation_value: str = "",
    created_by: str = "",
    user_id: str = "",
    created_at: datetime | None = None,
) -> SparseAnnotationRecord:
    when = (created_at or datetime.now(timezone.utc)).isoformat()
    return SparseAnnotationRecord(
        annotation_id=uuid.uuid4().hex,
        sample_id=sample_id,
        label=label,
        annotation_value=annotation_value,
        created_by=created_by,
        created_at=when,
        user_id=user_id,
    )
