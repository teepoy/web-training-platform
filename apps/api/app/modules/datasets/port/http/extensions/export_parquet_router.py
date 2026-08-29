from __future__ import annotations

import json
import logging
import os
import tempfile
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


_IMAGE_TYPE = pa.struct([pa.field("bytes", pa.binary()), pa.field("path", pa.string())])
_EXPORT_SCHEMA = pa.schema(
    [
        pa.field("sample_id", pa.string()),
        pa.field("image", pa.list_(_IMAGE_TYPE)),
        pa.field("label", pa.string()),
        pa.field("metadata", pa.string()),
    ]
)


def _rows_to_table(rows: list[Any]) -> pa.Table:
    return pa.Table.from_arrays(
        [
            pa.array([str(row.sample_id) for row in rows], type=pa.string()),
            pa.array(
                [
                    [_build_image_struct(uri) for uri in row.image_uris] or [{}]
                    for row in rows
                ],
                type=pa.list_(_IMAGE_TYPE),
            ),
            pa.array([row.latest_label for row in rows], type=pa.string()),
            pa.array(
                [
                    json.dumps(
                        dict(row.metadata or {}),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    for row in rows
                ],
                type=pa.string(),
            ),
        ],
        schema=_EXPORT_SCHEMA,
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
    filename = f"{dataset.name.replace(' ', '_')}_export.parquet"
    fd, temp_path = tempfile.mkstemp(suffix=".parquet")
    os.close(fd)
    writer: pq.ParquetWriter | None = None
    exported_rows = 0
    try:
        writer = pq.ParquetWriter(temp_path, _EXPORT_SCHEMA)
        offset = 0
        while True:
            rows, total = await ds_storage.list_samples(
                offset=offset,
                limit=_EXPORT_PAGE_SIZE,
                with_labels=True,
            )
            if rows:
                writer.write_table(_rows_to_table(rows), row_group_size=100)
            exported_rows += len(rows)
            offset += len(rows)
            if offset >= total:
                break
            if not rows:
                raise RuntimeError(
                    "Dataset storage returned an empty page before the reported total"
                )
        writer.close()
        writer = None
        uri = await storage.put_file(
            f"exports/{dataset_id}/{filename}",
            temp_path,
            content_type="application/octet-stream",
        )
    finally:
        if writer is not None:
            writer.close()
        os.unlink(temp_path)

    return {"uri": uri, "rows": exported_rows, "format": "parquet"}


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
