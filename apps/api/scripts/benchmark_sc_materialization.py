from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import random
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import polars as pl
import psutil
from PIL import Image

from app.modules.sc.materialization.app.services.sc_inspection_materializer import (
    ScInspectionMaterializer,
)
from app.modules.storage.domain.data_plane import DataPlaneSchemaRegistry


class _InlineOnlyImageSource:
    async def resolve_patch_images(
        self,
        **_kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        raise AssertionError("benchmark rows must contain inline images")
        yield {}


class _InlineOnlyImageSourceFactory:
    @asynccontextmanager
    async def open(self) -> AsyncIterator[_InlineOnlyImageSource]:
        yield _InlineOnlyImageSource()


def _images(*, count: int, image_size: int, seed: int) -> list[bytes]:
    random_source = random.Random(seed)
    images: list[bytes] = []
    for _ in range(count):
        raw = random_source.randbytes(image_size * image_size * 3)
        image = Image.frombytes("RGB", (image_size, image_size), raw)
        output = io.BytesIO()
        image.save(output, format="PNG", compress_level=1)
        images.append(output.getvalue())
    return images


async def _benchmark(args: argparse.Namespace) -> dict[str, float | int]:
    images = _images(
        count=args.unique_images,
        image_size=args.image_size,
        seed=args.seed,
    )
    rows = [
        {
            "sample_id": f"sample-{index}",
            "defect_id": str(index),
            "inspection_time": "2026-01-01T00:00:00",
            "wafer_key": 42,
            "label": str(index % args.classes),
            "images": [
                {
                    "role": "patch_template",
                    "bytes": images[index % len(images)],
                },
                {
                    "role": "patch_defective",
                    "bytes": images[(index + 1) % len(images)],
                },
            ],
        }
        for index in range(args.rows)
    ]
    lazyframe = pl.DataFrame(rows, infer_schema_length=None).lazy()
    process = psutil.Process(os.getpid())
    baseline_rss = process.memory_info().rss

    with tempfile.TemporaryDirectory() as temp_dir:
        materializer = ScInspectionMaterializer(
            image_source_factory=_InlineOnlyImageSourceFactory(),
            schema_registry=DataPlaneSchemaRegistry.default(),
            batch_rows=args.batch_rows,
            max_error_records=1_000,
            temp_dir=temp_dir,
        )
        started = time.perf_counter()
        result = await materializer.materialize(
            rows_lazyframe=lazyframe,
            image_source_formats={"benchmark": "inline-only"},
            direct_dataset_id="benchmark",
            dataset_id="benchmark",
            job_id="benchmark",
            image_types=["patch_template", "patch_defective"],
            max_output_bytes=args.max_output_bytes,
        )
        elapsed = time.perf_counter() - started
        rss_delta = process.memory_info().rss - baseline_rss
        parquet_size = result.manifest.shards[0].size_bytes or 0
        result.cleanup()

    return {
        "rows": args.rows,
        "classes": args.classes,
        "unique_images": args.unique_images,
        "image_size_px": args.image_size,
        "elapsed_seconds": round(elapsed, 4),
        "rows_per_second": round(args.rows / elapsed),
        "rss_delta_mb": round(rss_delta / 1024 / 1024, 2),
        "parquet_mb": round(parquet_size / 1024 / 1024, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=5_000)
    parser.add_argument("--classes", type=int, default=5)
    parser.add_argument("--unique-images", type=int, default=1_000)
    parser.add_argument("--image-size", type=int, default=64)
    parser.add_argument("--batch-rows", type=int, default=512)
    parser.add_argument("--max-output-bytes", type=int, default=17_179_869_184)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    if (
        min(
            args.rows,
            args.classes,
            args.unique_images,
            args.image_size,
            args.batch_rows,
            args.max_output_bytes,
        )
        < 1
    ):
        parser.error("all numeric benchmark arguments must be positive")
    print(json.dumps(asyncio.run(_benchmark(args)), sort_keys=True))


if __name__ == "__main__":
    main()
