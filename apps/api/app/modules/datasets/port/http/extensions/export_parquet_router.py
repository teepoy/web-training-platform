# pyright: reportMissingImports=false

import io
import logging

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, HTTPException

from app.shared.domain.protocols import ArtifactStorage
from app.shared.api.schemas import Organization, User
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
from app.modules.datasets.port.http.deps import (
    get_artifact_storage,
    get_dataset_storage_factory,
    get_repository,
)
from app.modules.datasets.domain.repository import DatasetRepository

router = APIRouter(prefix="/api/v1/plugins/export-parquet", tags=["plugins"])
_logger = logging.getLogger(__name__)


def _build_image_struct(path: str, image_bytes: bytes | None = None) -> dict:
    return {
        "bytes": image_bytes,
        "path": path,
    }


@router.post("/export")
async def export_parquet(
    dataset_id: str,
    repo: DatasetRepository = Depends(get_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    factory: DatasetStorageFactory = Depends(get_dataset_storage_factory),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> dict:
    dataset = await repo.get_dataset(dataset_id, org_id=org.id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset not found")

    ds_storage = await factory.open(dataset_id, org_id=org.id)
    rows, _ = await ds_storage.list_samples(limit=100_000)

    annotated_rows, _ = await ds_storage.list_samples(limit=100_000, with_labels=True)
    annotations_by_sample: dict[str, list[str]] = {}
    for r in annotated_rows:
        if r.latest_label is not None:
            annotations_by_sample.setdefault(r.sample_id, []).append(r.latest_label)

    image_arrays: list[list[dict]] = []
    label_arrays: list[str | None] = []
    metadata_arrays: list[dict] = []

    for row in rows:
        image_structs = [_build_image_struct(uri) for uri in row.image_uris]
        image_arrays.append(image_structs if image_structs else [{}])

        labels = annotations_by_sample.get(row.sample_id, [])
        label_arrays.append(labels[0] if labels else None)

        md = {k: v for k, v in row.metadata.items()} if row.metadata else {}
        metadata_arrays.append(md)

    image_type = pa.struct(
        [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
    )

    arrays: list[pa.Array] = []
    fields: list[pa.Field] = []

    image_array = pa.array(
        image_arrays,
        type=pa.list_(image_type),
    )
    fields.append(pa.field("image", pa.list_(image_type)))
    arrays.append(image_array)

    label_array = pa.array(label_arrays, type=pa.string())
    fields.append(pa.field("label", pa.string()))
    arrays.append(label_array)

    metadata_str_array = pa.array([str(m) for m in metadata_arrays], type=pa.string())
    fields.append(pa.field("metadata", pa.string()))
    arrays.append(metadata_str_array)

    table = pa.table({f.name: a for f, a in zip(fields, arrays)})

    buf = io.BytesIO()
    pq.write_table(table, buf, row_group_size=100)
    parquet_bytes = buf.getvalue()

    filename = f"{dataset.name.replace(' ', '_')}_export.parquet"
    uri = await storage.put_bytes(
        f"exports/{dataset_id}/{filename}",
        parquet_bytes,
        content_type="application/octet-stream",
    )

    return {"uri": uri, "rows": table.num_rows, "format": "parquet"}
