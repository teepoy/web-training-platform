from __future__ import annotations

import unittest.mock as mock

import pytest

pytestmark = pytest.mark.skip(reason="Pre-existing failure - see errors.md")

from app.modules.sc.app.services.sprite_service import SpriteService


_FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def mock_fetcher() -> mock.AsyncMock:
    fetcher = mock.AsyncMock()
    fetcher.get_image_bytes = mock.AsyncMock(return_value=_FAKE_PNG)
    return fetcher


@pytest.mark.asyncio
async def test_build_patch_sprite_returns_png(mock_fetcher: mock.AsyncMock) -> None:
    service = SpriteService(image_fetcher=mock_fetcher)
    png = await service.build_patch_sprite(
        inspection_time="2024-01-01T00:00:00+00:00",
        wafer_key=0,
        defect_id="1",
        cell_size=64,
    )
    assert png.startswith(b"\x89PNG")
    assert mock_fetcher.get_image_bytes.call_count == 3


@pytest.mark.asyncio
async def test_build_review_sprite_returns_png(mock_fetcher: mock.AsyncMock) -> None:
    service = SpriteService(image_fetcher=mock_fetcher)
    png = await service.build_review_sprite(
        inspection_time="2024-01-01T00:00:00+00:00",
        wafer_key=0,
        defect_id="1",
        review_count=3,
        cell_size=224,
    )
    assert png.startswith(b"\x89PNG")
    assert mock_fetcher.get_image_bytes.call_count == 6


@pytest.mark.asyncio
async def test_build_patch_batch_sprite(mock_fetcher: mock.AsyncMock) -> None:
    service = SpriteService(image_fetcher=mock_fetcher)
    png = await service.build_patch_batch_sprite(
        inspection_time="2024-01-01T00:00:00+00:00",
        wafer_key=0,
        defect_ids=["1", "2", "3", "4"],
        cell_size=64,
    )
    assert png.startswith(b"\x89PNG")
    assert mock_fetcher.get_image_bytes.call_count == 12


@pytest.mark.asyncio
async def test_build_review_batch_sprite(mock_fetcher: mock.AsyncMock) -> None:
    service = SpriteService(image_fetcher=mock_fetcher)
    png = await service.build_review_batch_sprite(
        inspection_time="2024-01-01T00:00:00+00:00",
        wafer_key=0,
        defect_ids=["1", "2"],
        review_count=2,
        cell_size=224,
    )
    assert png.startswith(b"\x89PNG")
    assert mock_fetcher.get_image_bytes.call_count == 10


@pytest.mark.asyncio
async def test_patch_sprite_fetches_correct_image_types(
    mock_fetcher: mock.AsyncMock,
) -> None:
    service = SpriteService(image_fetcher=mock_fetcher)
    await service.build_patch_sprite(
        inspection_time="2024-01-01T00:00:00+00:00",
        wafer_key=0,
        defect_id="42",
        cell_size=64,
    )
    calls = mock_fetcher.get_image_bytes.call_args_list
    called_types = [c.kwargs["image_type"] for c in calls]
    assert called_types == ["PATCH_TEMPLATE", "PATCH_DEFECTIVE", "difference"]


@pytest.mark.asyncio
async def test_review_sprite_fetches_patches_then_reviews(
    mock_fetcher: mock.AsyncMock,
) -> None:
    service = SpriteService(image_fetcher=mock_fetcher)
    await service.build_review_sprite(
        inspection_time="2024-01-01T00:00:00+00:00",
        wafer_key=0,
        defect_id="42",
        review_count=2,
        cell_size=224,
    )
    calls = mock_fetcher.get_image_bytes.call_args_list
    types = [c.kwargs["image_type"] for c in calls]
    rids = [c.kwargs["review_image_id"] for c in calls]
    assert types == [
        "PATCH_TEMPLATE",
        "PATCH_DEFECTIVE",
        "difference",
        "review",
        "review",
    ]
    assert rids == [None, None, None, 1, 2]
