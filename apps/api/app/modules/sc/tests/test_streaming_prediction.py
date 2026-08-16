from __future__ import annotations

from collections.abc import AsyncIterator
import polars as pl
import pytest

from app.modules.sc.runtime.streaming_prediction import (
    stream_sc_prediction_image_pairs,
)


class _ImageFetcher:
    def __init__(self, *, fail_profile: str | None = None) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.fail_profile = fail_profile

    async def resolve_patch_images(
        self,
        *,
        source_profile: str,
        roles: list[str],
        items: list[dict[str, object]],
    ) -> AsyncIterator[dict[str, object]]:
        self.calls.append(
            (
                source_profile,
                tuple(str(item["sample_id"]) for item in items),
            )
        )
        if source_profile == self.fail_profile:
            raise RuntimeError("source unavailable")
        for item in items:
            for role in roles:
                yield {
                    **item,
                    "role": role,
                    "image_data": f"{source_profile}:{role}".encode(),
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
async def test_prediction_stream_batches_rows_and_supports_mixed_collection_profiles() -> None:
    fetcher = _ImageFetcher()

    output = [
        item
        async for item in stream_sc_prediction_image_pairs(
            _collection_rows(513),
            image_fetcher=fetcher,  # type: ignore[arg-type]
            image_source_profiles={"dataset-a": "upstream", "dataset-b": "folder"},
            direct_dataset_id=None,
            input_batch_rows=512,
        )
    ]

    assert [str(item["sample_id"]) for item in output] == [
        f"dataset-{'a' if index % 2 == 0 else 'b'}::sample-{index}"
        for index in range(513)
    ]
    assert len(set(str(item["sample_id"]) for item in output)) == 513
    assert [(profile, len(samples)) for profile, samples in fetcher.calls] == [
        ("upstream", 256),
        ("folder", 256),
        ("upstream", 1),
    ]
    assert output[3]["error"] == (
        "image resolution failed: patch_defective: archive missing; "
        "patch_template: archive missing"
    )
    assert output[2]["patch_defective_bytes"] == b"upstream:patch_defective"


@pytest.mark.asyncio
async def test_prediction_stream_propagates_source_wide_failure() -> None:
    fetcher = _ImageFetcher(fail_profile="folder")

    with pytest.raises(RuntimeError, match="source unavailable"):
        _ = [
            item
            async for item in stream_sc_prediction_image_pairs(
                _collection_rows(2),
                image_fetcher=fetcher,  # type: ignore[arg-type]
                image_source_profiles={
                    "dataset-a": "upstream",
                    "dataset-b": "folder",
                },
                direct_dataset_id=None,
                input_batch_rows=512,
            )
        ]

@pytest.mark.asyncio
async def test_prediction_stream_requires_explicit_profile() -> None:
    fetcher = _ImageFetcher()

    with pytest.raises(ValueError, match="has no image source profile"):
        _ = [
            item
            async for item in stream_sc_prediction_image_pairs(
                _collection_rows(1),
                image_fetcher=fetcher,  # type: ignore[arg-type]
                image_source_profiles={},
                direct_dataset_id=None,
                input_batch_rows=512,
            )
        ]
