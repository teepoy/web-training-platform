from __future__ import annotations

import io
import logging
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.shared.domain.protocols import ArtifactStorage
from app.shared.api.schemas import Organization, User
from app.modules.auth.port.http.deps import (
    get_current_org,
    get_current_user,
)
from app.modules.storage.adapter.factory import DatasetStorageFactory
from app.modules.datasets.port.http.deps import (
    get_artifact_storage,
    get_dataset_storage_factory,
    get_repository,
)
from app.modules.datasets.domain.repository import DatasetRepository
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    DoneEvent,
    ScDataEvent,
    ScErrorEvent,
    ScProgressEvent,
    SSEEvent,
)

router = APIRouter(prefix="/api/v1/plugins/export-parquet", tags=["plugins"])
_logger = logging.getLogger(__name__)
_EXPORT_PAGE_SIZE = 1000
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _build_image_struct(path: str, image_bytes: bytes | None = None) -> dict:
    return {
        "bytes": image_bytes,
        "path": path,
    }


async def _list_all_samples_with_labels(ds_storage: Any) -> list[Any]:
    rows: list[Any] = []
    offset = 0
    while True:
        page, total = await ds_storage.list_samples(
            offset=offset,
            limit=_EXPORT_PAGE_SIZE,
            with_labels=True,
        )
        rows.extend(page)
        offset += len(page)
        if offset >= total:
            return rows
        if not page:
            raise RuntimeError(
                "Dataset storage returned an empty page before the reported total"
            )


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
    rows = await _list_all_samples_with_labels(ds_storage)

    image_arrays: list[list[dict]] = []
    label_arrays: list[str | None] = []
    metadata_arrays: list[dict] = []

    for row in rows:
        image_structs = [_build_image_struct(uri) for uri in row.image_uris]
        image_arrays.append(image_structs if image_structs else [{}])

        label_arrays.append(row.latest_label)

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


@router.post("/export/stream")
async def export_parquet_stream(
    request: Request,
    dataset_id: str,
    repo: DatasetRepository = Depends(get_repository),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    factory: DatasetStorageFactory = Depends(get_dataset_storage_factory),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> StreamingResponse:
    async def event_generator():
        if await request.is_disconnected():
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="dataset.export.parquet",
                    status="loading",
                    message="Reading dataset rows",
                )
            )
        )
        try:
            result = await export_parquet(
                dataset_id,
                repo,
                storage,
                factory,
                current_user,
                org,
            )
        except Exception as exc:
            yield emit_sse(
                SSEEvent(
                    ScErrorEvent(
                        event_type="error",
                        status="failed",
                        error=str(exc),
                    )
                )
            )
            return
        rows = int(result.get("rows", 0))
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="dataset.export.parquet",
                    status="persisted",
                    message="Parquet export persisted",
                    loaded_count=rows,
                    total_count=rows,
                )
            )
        )
        yield emit_sse(
            SSEEvent(
                ScDataEvent(
                    event_type="data",
                    operation="dataset.export.parquet",
                    payload=result,
                )
            )
        )
        yield emit_sse(
            SSEEvent(
                DoneEvent(
                    event_type="done",
                    uri=str(result.get("uri", "")),
                    rows=rows,
                )
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
