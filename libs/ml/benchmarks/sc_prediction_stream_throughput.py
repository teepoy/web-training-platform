from __future__ import annotations

import argparse
import asyncio
import io
import json
import time
from collections.abc import AsyncIterator

from PIL import Image

from ml_library.ultralytics import _preprocess_prediction_stream


def _png_fixture(image_size: int, *, offset: int) -> bytes:
    pixels = bytes(
        (row * 17 + column * 31 + offset) % 256
        for row in range(image_size)
        for column in range(image_size)
    )
    image = Image.frombytes("L", (image_size, image_size), pixels)
    output = io.BytesIO()
    image.save(output, format="PNG", compress_level=6)
    return output.getvalue()


async def _samples(
    count: int,
    *,
    defective: bytes,
    template: bytes,
) -> AsyncIterator[dict[str, object]]:
    for index in range(count):
        yield {
            "sample_id": str(index),
            "patch_defective_bytes": defective,
            "patch_template_bytes": template,
        }


async def _measure(args: argparse.Namespace) -> tuple[int, float]:
    defective = _png_fixture(args.image_size, offset=19)
    template = _png_fixture(args.image_size, offset=73)
    started = time.perf_counter()
    completed = 0
    async for item in _preprocess_prediction_stream(
        _samples(
            args.samples,
            defective=defective,
            template=template,
        ),
        image_size=args.image_size,
        workers=args.workers,
        task_size=args.task_size,
        prefetch_tasks=args.prefetch_tasks,
    ):
        if item["error"] is not None:
            raise RuntimeError(str(item["error"]))
        completed += 1
    return completed, time.perf_counter() - started


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure bounded SC prediction image decode/resize/tensor throughput. "
            "GPU model inference is intentionally excluded."
        )
    )
    parser.add_argument("--samples", type=int, default=12_000)
    parser.add_argument("--minimum-samples-per-second", type=float, default=3_000.0)
    parser.add_argument("--image-size", type=int, default=128)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--task-size", type=int, default=64)
    parser.add_argument("--prefetch-tasks", type=int, default=8)
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("--samples must be greater than zero")
    if args.minimum_samples_per_second <= 0:
        parser.error("--minimum-samples-per-second must be greater than zero")
    return args


def main() -> int:
    args = _parse_args()
    completed, elapsed = asyncio.run(_measure(args))
    rate = completed / elapsed
    print(
        json.dumps(
            {
                "samples": completed,
                "elapsed_seconds": round(elapsed, 6),
                "samples_per_second": round(rate, 2),
                "minimum_samples_per_second": args.minimum_samples_per_second,
                "workers": args.workers,
                "task_size": args.task_size,
                "prefetch_tasks": args.prefetch_tasks,
                "image_size": args.image_size,
            },
            sort_keys=True,
        )
    )
    if completed != args.samples:
        print(f"expected {args.samples} samples, completed {completed}")
        return 1
    if rate < args.minimum_samples_per_second:
        print(
            "SC prediction preprocessing throughput below required minimum: "
            f"{rate:.2f} < {args.minimum_samples_per_second:.2f} samples/s"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
