from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import pytest
from proto_stubs.imageparser.v1 import service_pb2 as pb

from app.modules.sc.adapter import grpc_job_image_stream as adapter
from app.modules.sc.adapter.grpc_job_image_stream import (
    GrpcJobImageStreamFactory,
    ScImageStreamUseCase,
)


class _FakeCall:
    def __init__(self) -> None:
        self.responses: list[pb.StreamImagesResponse] = []
        self.cancelled = False
        self.last_sequence = 0

    async def write(self, request: pb.StreamImagesRequest) -> None:
        payload = request.WhichOneof("payload")
        if payload == "open_context":
            opened = request.open_context
            self.responses.append(
                pb.StreamImagesResponse(
                    context_opened=pb.ImageContextOpened(
                        context_id=opened.context_id,
                        eqp_id="EQP01",
                        limits=pb.ImageStreamLimits(
                            max_batch_items=2,
                            max_response_bytes=64 * 1024 * 1024,
                            max_active_contexts=8,
                            max_in_flight_batches=2,
                        ),
                    )
                )
            )
            return
        if payload == "sample_batch":
            batch = request.sample_batch
            assert all(
                sample.sequence > self.last_sequence for sample in batch.samples
            )
            self.last_sequence = batch.samples[-1].sequence
            self.responses.append(
                pb.StreamImagesResponse(
                    sample_batch=pb.ImageSampleBatchResponse(
                        context_id=batch.context_id,
                        samples=[
                            pb.ImageSampleResult(
                                sequence=sample.sequence,
                                sample_id=sample.sample_id,
                                defect_id=sample.defect_id,
                                images=[
                                    pb.ImageRoleResult(
                                        role="patch_defective",
                                        image_data=sample.sample_id.encode(),
                                        content_type="image/png",
                                    )
                                ],
                            )
                            for sample in reversed(batch.samples)
                        ],
                        ack_sequence=batch.samples[-1].sequence,
                    )
                )
            )
            return
        if payload == "close_context":
            self.responses.append(
                pb.StreamImagesResponse(
                    context_closed=pb.ImageContextClosed(
                        context_id=request.close_context.context_id
                    )
                )
            )
            return
        raise AssertionError(f"unexpected payload {payload!r}")

    async def read(self) -> object:
        assert self.responses
        return self.responses.pop(0)

    async def done_writing(self) -> None:
        return None

    def cancel(self) -> bool:
        self.cancelled = True
        return True


class _PrefillCall(_FakeCall):
    def __init__(self) -> None:
        super().__init__()
        self.pending_batches: list[pb.StreamImagesRequest] = []

    async def write(self, request: pb.StreamImagesRequest) -> None:
        if request.WhichOneof("payload") != "sample_batch":
            await super().write(request)
            return
        self.pending_batches.append(request)
        if len(self.pending_batches) == 2:
            for batch in self.pending_batches:
                await super().write(batch)

    async def read(self) -> object:
        if not self.responses and len(self.pending_batches) < 2:
            raise AssertionError(
                "client read the first response before prefilling the advertised window"
            )
        return await super().read()


class _FakeMultiCallable:
    def __init__(self, path: str, calls: list[str], call: _FakeCall | None) -> None:
        self._path = path
        self._calls = calls
        self._call = call

    def __call__(self) -> _FakeCall:
        self._calls.append(self._path)
        return self._call or _FakeCall()


class _FakeChannel:
    def __init__(self, call: _FakeCall | None = None) -> None:
        self.calls: list[str] = []
        self.closed = False
        self.call = call

    def stream_stream(self, path: str, **_: object) -> _FakeMultiCallable:
        return _FakeMultiCallable(path, self.calls, self.call)

    def unary_unary(self, path: str, **_: object) -> _FakeMultiCallable:
        return _FakeMultiCallable(path, self.calls, self.call)

    def unary_stream(self, path: str, **_: object) -> _FakeMultiCallable:
        return _FakeMultiCallable(path, self.calls, self.call)

    async def close(self) -> None:
        self.closed = True


def _items(count: int) -> Sequence[dict[str, object]]:
    return [
        {
            "sample_id": f"sample-{index}",
            "inspection_time": "2026-08-21T10:00:00",
            "wafer_key": 7,
            "defect_id": str(index + 1),
        }
        for index in range(count)
    ]


def _alternating_context_items() -> Sequence[dict[str, object]]:
    items = list(_items(4))
    items[1]["wafer_key"] = 8
    items[3]["wafer_key"] = 8
    return items


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("use_case", "rpc_name"),
    [
        (ScImageStreamUseCase.PREDICTION, "StreamPredictionImages"),
        (ScImageStreamUseCase.TRAINING, "StreamTrainingImages"),
        (ScImageStreamUseCase.EXPORT, "StreamExportImages"),
    ],
)
async def test_semantic_stream_uses_own_rpc_and_preserves_sample_order(
    monkeypatch: pytest.MonkeyPatch,
    use_case: ScImageStreamUseCase,
    rpc_name: str,
) -> None:
    channel = _FakeChannel()
    monkeypatch.setattr(
        adapter.grpc_aio,
        "insecure_channel",
        lambda *_args, **_kwargs: cast(adapter.grpc_aio.Channel, channel),
    )
    factory = GrpcJobImageStreamFactory(addr="image-parser:9092", use_case=use_case)

    async with factory.open() as stream:
        results = await stream.resolve_images(
            roles=("patch_defective",),
            items=_items(3),
        )

    assert [result["sample_id"] for result in results] == [
        "sample-0",
        "sample-1",
        "sample-2",
    ]
    assert channel.calls == [f"/imageparser.v1.ImageParser/{rpc_name}"]
    assert channel.closed is True


@pytest.mark.asyncio
async def test_stream_keeps_global_sequence_monotonic_across_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _FakeChannel()
    monkeypatch.setattr(
        adapter.grpc_aio,
        "insecure_channel",
        lambda *_args, **_kwargs: cast(adapter.grpc_aio.Channel, channel),
    )
    factory = GrpcJobImageStreamFactory(
        addr="image-parser:9092",
        use_case=ScImageStreamUseCase.PREDICTION,
    )

    async with factory.open() as stream:
        results = await stream.resolve_images(
            roles=("patch_defective",),
            items=_alternating_context_items(),
        )

    assert [result["sequence"] for result in results] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_prediction_stream_prefills_advertised_in_flight_batch_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = _PrefillCall()
    channel = _FakeChannel(call)
    monkeypatch.setattr(
        adapter.grpc_aio,
        "insecure_channel",
        lambda *_args, **_kwargs: cast(adapter.grpc_aio.Channel, channel),
    )
    factory = GrpcJobImageStreamFactory(
        addr="image-parser:9092",
        use_case=ScImageStreamUseCase.PREDICTION,
    )

    async with factory.open() as stream:
        results = await stream.resolve_images(
            roles=("patch_defective",),
            items=_items(4),
        )

    assert len(call.pending_batches) == 2
    assert [result["sample_id"] for result in results] == [
        "sample-0",
        "sample-1",
        "sample-2",
        "sample-3",
    ]
