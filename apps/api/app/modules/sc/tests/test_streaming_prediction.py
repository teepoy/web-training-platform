from __future__ import annotations

from collections.abc import AsyncIterator
import polars as pl
import pytest

from app.modules.sc.runtime.streaming_prediction import (
    stream_sc_prediction_image_pairs,
)


class _ImageResolver:
    def __init__(self, *, fail_format: str | None = None) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.received_items: list[dict[str, object]] = []
        self.fail_format = fail_format

    async def resolve_patch_images(
        self,
        *,
        source_format: str,
        roles: list[str],
        items: list[dict[str, object]],
    ) -> AsyncIterator[dict[str, object]]:
        self.calls.append(
            (
                source_format,
                tuple(str(item["sample_id"]) for item in items),
            )
        )
        self.received_items.extend(items)
        if source_format == self.fail_format:
            raise RuntimeError("source unavailable")
        for item in items:
            for role in roles:
                yield {
                    **item,
                    "role": role,
                    "image_data": f"{source_format}:{role}".encode(),
                    "error": (
                        "archive missing"
                        if item["sample_id"] == "dataset-b::sample-3"
                        else ""
                    ),
                }


def _collection_rows(count: int) -> pl.LazyFrame:
    return pl.DataFrame(
        {
            "sample_id": [
                f"dataset-{'a' if index % 2 == 0 else 'b'}::sample-{index}"
                for index in range(count)
            ],
            "source_dataset_id": [
                "dataset-a" if index % 2 == 0 else "dataset-b"
                for index in range(count)
            ],
            "inspection_time": ["2026-08-16T10:00:00"] * count,
            "wafer_key": [42] * count,
            "defect_id": [str(index + 1) for index in range(count)],
        }
    ).lazy()


@pytest.mark.asyncio
async def test_prediction_stream_batches_rows_and_supports_mixed_collection_formats() -> None:
    resolver = _ImageResolver()

    output = [
        item
        async for item in stream_sc_prediction_image_pairs(
            _collection_rows(513),
            image_resolver=resolver,
            image_source_formats={"dataset-a": "format-a", "dataset-b": "format-b"},
            direct_dataset_id=None,
            input_batch_rows=512,
        )
    ]

    assert [str(item["sample_id"]) for item in output] == [
        f"dataset-{'a' if index % 2 == 0 else 'b'}::sample-{index}"
        for index in range(513)
    ]
    assert len(set(str(item["sample_id"]) for item in output)) == 513
    assert [(source_format, len(samples)) for source_format, samples in resolver.calls] == [
        ("format-a", 256),
        ("format-b", 256),
        ("format-a", 1),
    ]
    assert output[3]["error"] == (
        "image resolution failed: patch_defective: archive missing; "
        "patch_template: archive missing"
    )
    assert output[2]["patch_defective_bytes"] == b"format-a:patch_defective"


@pytest.mark.asyncio
async def test_prediction_stream_propagates_source_wide_failure() -> None:
    resolver = _ImageResolver(fail_format="format-b")

    with pytest.raises(RuntimeError, match="source unavailable"):
        _ = [
            item
            async for item in stream_sc_prediction_image_pairs(
                _collection_rows(2),
                image_resolver=resolver,
                image_source_formats={
                    "dataset-a": "format-a",
                    "dataset-b": "format-b",
                },
                direct_dataset_id=None,
                input_batch_rows=512,
            )
        ]

@pytest.mark.asyncio
async def test_prediction_stream_requires_explicit_format() -> None:
    resolver = _ImageResolver()

    with pytest.raises(ValueError, match="has no image source format"):
        _ = [
            item
            async for item in stream_sc_prediction_image_pairs(
                _collection_rows(1),
                image_resolver=resolver,
                image_source_formats={},
                direct_dataset_id=None,
                input_batch_rows=512,
            )
        ]


@pytest.mark.asyncio
async def test_prediction_stream_passes_explicit_paths_without_legacy_sc_identity() -> None:
    resolver = _ImageResolver()
    rows = pl.DataFrame(
        {
            "sample_id": ["sample-1"],
            "role_paths": [
                {
                    "patch_template": "wafer-1/template.tiff",
                    "patch_defective": "wafer-1/defective.tiff",
                }
            ],
        }
    ).lazy()

    output = [
        item
        async for item in stream_sc_prediction_image_pairs(
            rows,
            image_resolver=resolver,
            image_source_formats={"dataset-1": "filesystem.role-paths.v1"},
            direct_dataset_id="dataset-1",
            input_batch_rows=512,
        )
    ]

    assert output[0]["sample_id"] == "sample-1"
    assert resolver.received_items == [
        {
            "request_id": "0:0",
            "sample_id": "sample-1",
            "inspection_time": "",
            "wafer_key": 0,
            "defect_id": "",
            "role_paths": {
                "patch_template": "wafer-1/template.tiff",
                "patch_defective": "wafer-1/defective.tiff",
            },
        }
    ]
