from __future__ import annotations
# pyright: reportMissingModuleSource=false

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

import grpc
from grpc import aio as grpc_aio
from proto_stubs.imageparser.v1 import service_pb2 as pb
from proto_stubs.imageparser.v1 import service_pb2_grpc as pb_grpc

from app.modules.sc.domain.image_stream import ScImageStreamSession

_MAX_MESSAGE_BYTES = 72 * 1024 * 1024
_MAX_RECONNECTS = 2


class ScImageStreamUseCase(StrEnum):
    PREDICTION = "prediction"
    TRAINING = "training"
    EXPORT = "export"


class _StreamCall(Protocol):
    async def write(self, request: pb.StreamImagesRequest) -> None: ...

    async def read(self) -> object: ...

    async def done_writing(self) -> None: ...

    def cancel(self) -> bool: ...


@dataclass(slots=True)
class _ContextState:
    context_id: str
    inspection_time: str
    wafer_key: int
    roles: tuple[str, ...]
    opened: bool = False
    max_batch_items: int = 0


class GrpcJobImageStreamFactory:
    """Open one semantic image-parser stream for one runtime operation."""

    def __init__(
        self,
        *,
        addr: str,
        use_case: ScImageStreamUseCase,
        max_reconnects: int = _MAX_RECONNECTS,
    ) -> None:
        if not addr.strip():
            raise ValueError("image-parser gRPC address is required")
        if max_reconnects < 0:
            raise ValueError("max_reconnects cannot be negative")
        self._addr = addr
        self._use_case = use_case
        self._max_reconnects = max_reconnects

    @asynccontextmanager
    async def open(self) -> AsyncIterator[ScImageStreamSession]:
        channel = grpc_aio.insecure_channel(
            self._addr,
            options=(
                ("grpc.max_send_message_length", _MAX_MESSAGE_BYTES),
                ("grpc.max_receive_message_length", _MAX_MESSAGE_BYTES),
            ),
        )
        session = _GrpcJobImageStreamSession(
            channel=channel,
            use_case=self._use_case,
            max_reconnects=self._max_reconnects,
        )
        body_failed = False
        try:
            yield session
        except BaseException:
            body_failed = True
            raise
        finally:
            await session.close(suppress_errors=body_failed)


class _GrpcJobImageStreamSession:
    def __init__(
        self,
        *,
        channel: grpc_aio.Channel,
        use_case: ScImageStreamUseCase,
        max_reconnects: int,
    ) -> None:
        self._channel = channel
        self._stub = pb_grpc.ImageParserStub(channel)
        self._use_case = use_case
        self._max_reconnects = max_reconnects
        self._call: _StreamCall | None = None
        self._contexts: dict[tuple[str, int, tuple[str, ...]], _ContextState] = {}
        self._next_context = 1
        self._next_sequence = 1
        self._lock = asyncio.Lock()
        self._closed = False

    async def resolve_images(
        self,
        *,
        roles: Sequence[str],
        items: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        normalized_roles = tuple(role.strip() for role in roles if role.strip())
        if not normalized_roles:
            raise ValueError("at least one image role is required")
        if len(normalized_roles) != len(set(normalized_roles)):
            raise ValueError("image roles must be unique")
        if not items:
            return []

        async with self._lock:
            self._ensure_open()
            indexed: list[tuple[int, dict[str, object]]] = []
            segments: list[
                tuple[
                    tuple[str, int, tuple[str, ...]],
                    list[pb.ImageSampleRequest],
                ]
            ] = []
            for item in items:
                inspection_time = str(item.get("inspection_time") or "").strip()
                wafer_key = int(cast(object, item.get("wafer_key", 0)) or 0)  # type: ignore[arg-type]
                sample_id = str(item.get("sample_id") or "").strip()
                defect_id = str(item.get("defect_id") or "").strip()
                if (
                    not inspection_time
                    or wafer_key <= 0
                    or not sample_id
                    or not defect_id
                ):
                    raise ValueError(
                        "image stream item requires inspection_time, positive wafer_key, "
                        "sample_id, and defect_id"
                    )
                sequence = self._next_sequence
                self._next_sequence += 1
                request = pb.ImageSampleRequest(
                    sequence=sequence,
                    sample_id=sample_id,
                    defect_id=defect_id,
                )
                key = (inspection_time, wafer_key, normalized_roles)
                if segments and segments[-1][0] == key:
                    segments[-1][1].append(request)
                else:
                    segments.append((key, [request]))
                indexed.append((sequence, dict(item)))

            resolved: dict[int, pb.ImageSampleResult] = {}
            for key, requests in segments:
                state = self._contexts.get(key)
                if state is None:
                    state = _ContextState(
                        context_id=f"context-{self._next_context}",
                        inspection_time=key[0],
                        wafer_key=key[1],
                        roles=key[2],
                    )
                    self._next_context += 1
                    self._contexts[key] = state
                await self._resolve_context_batch(state, requests, resolved)

            output: list[dict[str, object]] = []
            for sequence, source in indexed:
                result = resolved.get(sequence)
                if result is None:
                    raise RuntimeError(
                        f"image-parser stream did not resolve sequence {sequence}"
                    )
                if result.sample_id != str(source["sample_id"]):
                    raise RuntimeError(
                        "image-parser stream returned a mismatched sample identity"
                    )
                output.append(
                    {
                        **source,
                        "sequence": sequence,
                        "error": result.error,
                        "images": [
                            {
                                "role": image.role,
                                "image_data": image.image_data,
                                "content_type": image.content_type,
                                "error": image.error,
                            }
                            for image in result.images
                        ],
                    }
                )
            return output

    async def _resolve_context_batch(
        self,
        state: _ContextState,
        requests: list[pb.ImageSampleRequest],
        resolved: dict[int, pb.ImageSampleResult],
    ) -> None:
        pending = requests
        reconnects = 0
        while pending:
            try:
                await self._ensure_context(state)
                if state.max_batch_items <= 0:
                    raise RuntimeError("image-parser returned an invalid batch limit")
                for offset in range(0, len(pending), state.max_batch_items):
                    chunk = pending[offset : offset + state.max_batch_items]
                    await self._write(
                        pb.StreamImagesRequest(
                            sample_batch=pb.ImageSampleBatchRequest(
                                context_id=state.context_id,
                                samples=chunk,
                            )
                        )
                    )
                    await self._read_chunk(state, chunk, resolved)
                return
            except grpc.aio.AioRpcError:
                if reconnects >= self._max_reconnects:
                    raise
                reconnects += 1
                pending = [item for item in requests if item.sequence not in resolved]
                await self._reset_call()

    async def _ensure_context(self, state: _ContextState) -> None:
        if state.opened:
            return
        await self._write(
            pb.StreamImagesRequest(
                open_context=pb.OpenImageContext(
                    context_id=state.context_id,
                    inspection_time=state.inspection_time,
                    wafer_key=state.wafer_key,
                    roles=state.roles,
                )
            )
        )
        response = await self._read()
        payload = response.WhichOneof("payload")
        if payload == "context_error":
            raise RuntimeError(
                f"image-parser context {response.context_error.code}: "
                f"{response.context_error.error}"
            )
        if payload != "context_opened":
            raise RuntimeError("image-parser did not acknowledge the opened context")
        opened = response.context_opened
        if opened.context_id != state.context_id:
            raise RuntimeError("image-parser acknowledged the wrong context")
        state.max_batch_items = int(opened.limits.max_batch_items)
        state.opened = True

    async def _read_chunk(
        self,
        state: _ContextState,
        chunk: list[pb.ImageSampleRequest],
        resolved: dict[int, pb.ImageSampleResult],
    ) -> None:
        expected = {item.sequence for item in chunk}
        last_sequence = chunk[-1].sequence
        ack_sequence = 0
        while ack_sequence < last_sequence:
            response = await self._read()
            payload = response.WhichOneof("payload")
            if payload == "context_error":
                raise RuntimeError(
                    f"image-parser context {response.context_error.code}: "
                    f"{response.context_error.error}"
                )
            if payload != "sample_batch":
                raise RuntimeError(
                    "image-parser returned an unexpected stream response"
                )
            batch = response.sample_batch
            if batch.context_id != state.context_id:
                raise RuntimeError(
                    "image-parser returned a response for another context"
                )
            for sample in batch.samples:
                if sample.sequence not in expected:
                    raise RuntimeError(
                        f"image-parser returned unknown sequence {sample.sequence}"
                    )
                previous = resolved.get(sample.sequence)
                if previous is not None and previous != sample:
                    raise RuntimeError(
                        f"image-parser returned conflicting duplicate sequence "
                        f"{sample.sequence}"
                    )
                resolved[sample.sequence] = sample
            ack_sequence = max(ack_sequence, int(batch.ack_sequence))
        missing = sorted(expected.difference(resolved))
        if missing:
            raise RuntimeError(
                "image-parser acknowledged a batch before returning sequences: "
                + ", ".join(str(item) for item in missing)
            )

    async def close(self, *, suppress_errors: bool) -> None:
        if self._closed:
            return
        self._closed = True
        error: BaseException | None = None
        if self._call is not None:
            try:
                for state in self._contexts.values():
                    if not state.opened:
                        continue
                    await self._write(
                        pb.StreamImagesRequest(
                            close_context=pb.CloseImageContext(
                                context_id=state.context_id
                            )
                        )
                    )
                    response = await self._read()
                    if (
                        response.WhichOneof("payload") != "context_closed"
                        or response.context_closed.context_id != state.context_id
                    ):
                        raise RuntimeError(
                            "image-parser did not acknowledge context close"
                        )
                await self._call.done_writing()
            except BaseException as exc:
                error = exc
                self._call.cancel()
        await self._channel.close()
        if error is not None and not suppress_errors:
            raise error

    async def _write(self, request: pb.StreamImagesRequest) -> None:
        call = self._ensure_call()
        await call.write(request)

    async def _read(self) -> pb.StreamImagesResponse:
        call = self._ensure_call()
        response = await call.read()
        if response is getattr(grpc.aio, "EOF"):
            raise RuntimeError("image-parser stream ended unexpectedly")
        return cast(pb.StreamImagesResponse, response)

    def _ensure_call(self) -> _StreamCall:
        if self._call is not None:
            return self._call
        match self._use_case:
            case ScImageStreamUseCase.PREDICTION:
                call = self._stub.StreamPredictionImages()
            case ScImageStreamUseCase.TRAINING:
                call = self._stub.StreamTrainingImages()
            case ScImageStreamUseCase.EXPORT:
                call = self._stub.StreamExportImages()
        self._call = cast(_StreamCall, call)
        return self._call

    async def _reset_call(self) -> None:
        if self._call is not None:
            self._call.cancel()
        self._call = None
        for state in self._contexts.values():
            state.opened = False
            state.max_batch_items = 0

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("image-parser stream session is closed")


__all__ = ["GrpcJobImageStreamFactory", "ScImageStreamUseCase"]
