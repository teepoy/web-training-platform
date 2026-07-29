from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.modules.datasets.app.session import DatasetSession
from app.modules.storage.domain.storage_agg import DatasetStorageAgg


@pytest.mark.asyncio
async def test_dataset_session_forwards_sample_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = SimpleNamespace(
        list_samples=AsyncMock(return_value=([], 0)),
    )
    monkeypatch.setattr(
        "app.modules.datasets.app.session._resolve_row_projector",
        lambda _view_type: lambda row, context: row,
    )
    session = DatasetSession(
        dataset_type="image_sc",
        access=cast(DatasetStorageAgg, access),
        dataset_id="dataset-1",
    )

    await session.list_samples(
        "patch_image_v1",
        offset=20,
        limit=10,
        sample_ids=["101", "205"],
    )

    access.list_samples.assert_awaited_once_with(
        offset=20,
        limit=10,
        with_labels=True,
        with_predictions=True,
        order_by="id",
        sample_ids=["101", "205"],
    )
