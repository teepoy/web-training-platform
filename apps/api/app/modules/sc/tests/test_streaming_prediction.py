from __future__ import annotations

from collections.abc import Sequence

import polars as pl
import pytest

from app.modules.sc.runtime.streaming_prediction import (
    stream_sc_prediction_image_pairs,
)


class _ImageStream:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    async def resolve_images(
        self,
        *,
        roles: Sequence[str],
        items: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        self.calls.append(
            (
                tuple(roles),
                tuple(str(item["sample_id"]) for item in items),
            )
        )
        return [
            {
                **item,
                "error": "",
                "images": [
                    {
                        "role": role,
                        "image_data": f"{role}:{item['sample_id']}".encode(),
                        "content_type": "image/png",
                        "error": (
                            "archive missing"
                            if item["sample_id"] == "sample-3"
                            else ""
                        ),
                    }
                    for role in roles
                ],
            }
            for item in items
        ]


def _rows(count: int) -> pl.LazyFrame:
    return pl.DataFrame(
        {
            "sample_id": [f"sample-{index}" for index in range(count)],
            "inspection_time": ["2026-08-16T10:00:00"] * count,
            "wafer_key": [42] * count,
            "defect_id": [str(index + 1) for index in range(count)],
        }
    ).lazy()


@pytest.mark.asyncio
async def test_prediction_stream_batches_rows_and_preserves_order() -> None:
    stream = _ImageStream()

    output = [
        item
        async for item in stream_sc_prediction_image_pairs(
            _rows(513),
            image_stream=stream,
            input_batch_rows=512,
        )
    ]

    assert [str(item["sample_id"]) for item in output] == [
        f"sample-{index}" for index in range(513)
    ]
    assert [len(samples) for _, samples in stream.calls] == [512, 1]
    assert output[3]["error"] == (
        "image resolution failed: patch_defective: archive missing; "
        "patch_template: archive missing"
    )
    assert output[2]["patch_defective_bytes"] == b"patch_defective:sample-2"


@pytest.mark.asyncio
async def test_prediction_stream_requires_service_locator_columns() -> None:
    stream = _ImageStream()
    rows = pl.DataFrame({"sample_id": ["sample-1"]}).lazy()

    with pytest.raises(ValueError, match="defect_id, inspection_time, wafer_key"):
        _ = [
            item
            async for item in stream_sc_prediction_image_pairs(
                rows,
                image_stream=stream,
                input_batch_rows=512,
            )
        ]
