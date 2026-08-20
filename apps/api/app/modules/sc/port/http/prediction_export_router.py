from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sampling_rules import InvalidSamplingRuleError

from app.modules.auth.port.http.deps import get_current_org, get_current_user
from app.modules.sc.app.services.prediction_export_service import (
    ScPredictionExportError,
)
from app.modules.sc.data_provider.sampling import sampling_program_from_request
from app.modules.sc.domain.prediction_export import (
    ScKlarfVersion,
    ScPredictionExportResult,
)
from app.modules.sc.port.http.deps import ScPredictionExportDep
from app.modules.sc.port.http.prediction_export_schemas import (
    ScCollectionPredictionExportRequest,
    ScPredictionExportRequest,
    ScPredictionExportResponse,
)
from app.shared.api.schemas import Organization, User
from app.shared.sse.emit import emit_sse
from app.shared.sse.events import (
    DoneEvent,
    ScDataEvent,
    ScErrorEvent,
    ScProgressEvent,
    SSEEvent,
)

router = APIRouter(prefix="/api/v1/sc", tags=["sc-prediction-export"])
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
_EXPORT_HEARTBEAT_SECONDS = 15.0
_ACTIVE_EXPORT_TASKS: set[asyncio.Task[ScPredictionExportResult]] = set()


def _track_export_task(
    task: asyncio.Task[ScPredictionExportResult],
) -> asyncio.Task[ScPredictionExportResult]:
    """Keep disconnected large exports alive until disk/upload cleanup finishes."""
    _ACTIVE_EXPORT_TASKS.add(task)

    def _forget(completed: asyncio.Task[ScPredictionExportResult]) -> None:
        _ACTIVE_EXPORT_TASKS.discard(completed)
        if not completed.cancelled():
            completed.exception()

    task.add_done_callback(_forget)
    return task


@router.post(
    "/datasets/{dataset_id}/prediction-exports/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent export progress and result events",
            "content": {"text/event-stream": {}},
        }
    },
)
async def export_sc_predictions_stream(
    dataset_id: str,
    body: ScPredictionExportRequest,
    request: Request,
    service: ScPredictionExportDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> StreamingResponse:
    sampling = body.sampling
    return _stream_export(
        request,
        lambda: service.export(
            dataset_id=dataset_id,
            org_id=org.id,
            created_by=current_user.id,
            export_format=body.format,
            klarf_version=body.klarf_version or ScKlarfVersion.V1_2,
            sampling_program=(
                sampling_program_from_request(sampling.program)
                if sampling is not None
                else None
            ),
            sampling_seed=(sampling.seed if sampling is not None else None),
            include_images=body.include_images,
        ),
    )


@router.post(
    "/dataset-collections/{collection_id}/prediction-exports/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent Collection export progress and result events",
            "content": {"text/event-stream": {}},
        }
    },
)
async def export_sc_collection_predictions_stream(
    collection_id: str,
    body: ScCollectionPredictionExportRequest,
    request: Request,
    service: ScPredictionExportDep,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
) -> StreamingResponse:
    sampling = body.sampling
    return _stream_export(
        request,
        lambda: service.export_collection(
            collection_id=collection_id,
            member_ids=tuple(body.member_ids),
            org_id=org.id,
            created_by=current_user.id,
            export_format=body.format,
            klarf_version=body.klarf_version or ScKlarfVersion.V1_2,
            sampling_program=(
                sampling_program_from_request(sampling.program)
                if sampling is not None
                else None
            ),
            sampling_seed=(sampling.seed if sampling is not None else None),
            include_images=body.include_images,
        ),
    )


def _stream_export(
    request: Request,
    run_export: Callable[[], Awaitable[ScPredictionExportResult]],
) -> StreamingResponse:
    async def await_export() -> ScPredictionExportResult:
        return await run_export()

    async def event_generator() -> AsyncIterator[str]:
        if await request.is_disconnected():
            return
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.prediction-export",
                    status="loading",
                    message="Preparing current prediction results",
                )
            )
        )
        try:
            export_task = _track_export_task(asyncio.create_task(await_export()))
            while True:
                completed, _pending = await asyncio.wait(
                    {export_task},
                    timeout=_EXPORT_HEARTBEAT_SECONDS,
                )
                if completed:
                    result = export_task.result()
                    break
                yield emit_sse(
                    SSEEvent(
                        ScProgressEvent(
                            event_type="progress",
                            operation="sc.prediction-export",
                            status="processing",
                            message=(
                                "Generating, packaging, and uploading the export; "
                                "large files can take several minutes"
                            ),
                        )
                    )
                )
        except (InvalidSamplingRuleError, ScPredictionExportError) as exc:
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
        payload = ScPredictionExportResponse(
            uri=result.uri,
            format=result.format,
            rows=result.row_count,
            sampled=result.sampled,
            filename=result.filename,
            klarf_version=result.klarf_version,
        ).model_dump(mode="json")
        yield emit_sse(
            SSEEvent(
                ScProgressEvent(
                    event_type="progress",
                    operation="sc.prediction-export",
                    status="persisted",
                    message="Prediction export persisted",
                    loaded_count=result.row_count,
                    total_count=result.row_count,
                )
            )
        )
        yield emit_sse(
            SSEEvent(
                ScDataEvent(
                    event_type="data",
                    operation="sc.prediction-export",
                    payload=payload,
                )
            )
        )
        yield emit_sse(
            SSEEvent(
                DoneEvent(
                    event_type="done",
                    uri=result.uri,
                    rows=result.row_count,
                )
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
