from __future__ import annotations
# pyright: reportMissingModuleSource=false

import argparse
import asyncio
import json
import time

from grpc import aio as grpc_aio
from proto_stubs.imageparser.v1 import service_pb2 as pb
from proto_stubs.imageparser.v1 import service_pb2_grpc as pb_grpc

_MAX_MESSAGE_BYTES = 72 * 1024 * 1024


async def _run(args: argparse.Namespace) -> dict[str, int | float]:
    channel = grpc_aio.insecure_channel(
        args.addr,
        options=(
            ("grpc.max_send_message_length", _MAX_MESSAGE_BYTES),
            ("grpc.max_receive_message_length", _MAX_MESSAGE_BYTES),
        ),
    )
    call = pb_grpc.ImageParserStub(channel).StreamPredictionImages()
    context_id = "prediction-throughput-gate"
    try:
        await call.write(
            pb.StreamImagesRequest(
                open_context=pb.OpenImageContext(
                    context_id=context_id,
                    inspection_time=args.inspection_time,
                    wafer_key=args.wafer_key,
                    roles=("patch_defective", "patch_template"),
                )
            )
        )
        opened = await call.read()
        if opened.WhichOneof("payload") != "context_opened":
            raise RuntimeError(f"image context failed to open: {opened}")
        limit = int(opened.context_opened.limits.max_batch_items)
        if limit <= 0:
            raise RuntimeError("image-parser advertised an invalid batch limit")
        batch_size = min(args.batch_size, limit)

        received = 0
        image_bytes = 0
        errors = 0
        last_sequence = 0
        started = time.perf_counter()
        for start in range(1, args.samples + 1, batch_size):
            stop = min(start + batch_size, args.samples + 1)
            await call.write(
                pb.StreamImagesRequest(
                    sample_batch=pb.ImageSampleBatchRequest(
                        context_id=context_id,
                        samples=[
                            pb.ImageSampleRequest(
                                sequence=sequence,
                                sample_id=f"sample-{sequence}",
                                defect_id=str(sequence),
                            )
                            for sequence in range(start, stop)
                        ],
                    )
                )
            )
            expected_ack = stop - 1
            while last_sequence < expected_ack:
                response = await call.read()
                if response.WhichOneof("payload") == "context_error":
                    raise RuntimeError(
                        f"image context {response.context_error.code}: "
                        f"{response.context_error.error}"
                    )
                if response.WhichOneof("payload") != "sample_batch":
                    raise RuntimeError(f"unexpected image stream response: {response}")
                batch = response.sample_batch
                for sample in batch.samples:
                    if sample.sequence != received + 1:
                        raise RuntimeError(
                            "image-parser returned an out-of-order sequence: "
                            f"got={sample.sequence} expected={received + 1}"
                        )
                    received += 1
                    if sample.error or len(sample.images) != 2:
                        errors += 1
                    for image in sample.images:
                        image_bytes += len(image.image_data)
                        if image.error or not image.image_data:
                            errors += 1
                last_sequence = int(batch.ack_sequence)
        elapsed = time.perf_counter() - started

        await call.write(
            pb.StreamImagesRequest(
                close_context=pb.CloseImageContext(context_id=context_id)
            )
        )
        closed = await call.read()
        if closed.WhichOneof("payload") != "context_closed":
            raise RuntimeError(f"image context failed to close: {closed}")
        await call.done_writing()
    finally:
        call.cancel()
        await channel.close()

    throughput = received / elapsed
    if received != args.samples or errors:
        raise RuntimeError(
            f"image receipt mismatch: received={received} expected={args.samples} "
            f"errors={errors}"
        )
    if throughput < args.minimum_samples_per_second:
        raise RuntimeError(
            "prediction image receipt throughput below minimum: "
            f"{throughput:.2f} < {args.minimum_samples_per_second:.2f}"
        )
    return {
        "samples": received,
        "images": received * 2,
        "image_bytes": image_bytes,
        "elapsed_seconds": round(elapsed, 6),
        "samples_per_second": round(throughput, 2),
        "batch_size": batch_size,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure warm-cache image-parser ZIP parsing through Python receipt."
    )
    parser.add_argument("--addr", required=True)
    parser.add_argument("--inspection-time", required=True)
    parser.add_argument("--wafer-key", type=int, required=True)
    parser.add_argument("--samples", type=int, default=300_000)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--minimum-samples-per-second", type=float, default=3000.0)
    args = parser.parse_args()
    if args.samples <= 0 or args.batch_size <= 0 or args.wafer_key <= 0:
        parser.error("samples, batch-size, and wafer-key must be positive")
    return args


def main() -> int:
    args = _parse_args()
    print(json.dumps(asyncio.run(_run(args)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
