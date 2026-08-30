from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

import pytest

from app.shared.infrastructure.label_studio.client import LabelStudioClient


@pytest.mark.asyncio
async def test_create_project_normalises_long_title_with_stable_suffix() -> None:
    sdk = MagicMock()
    sdk.projects.create.return_value = {"id": 1, "title": "created"}
    client = LabelStudioClient.__new__(LabelStudioClient)
    client._client = sdk
    long_name = "dataset-name-" + "x" * 80

    result = await client.create_project(long_name, "<View />")

    assert result == {"id": 1, "title": "created"}
    title = sdk.projects.create.call_args.kwargs["title"]
    assert len(title) == 50
    assert title.startswith(long_name[:41])
    expected_digest = hashlib.sha256(long_name.encode("utf-8")).hexdigest()[:8]
    assert title.endswith(f"-{expected_digest}")


@pytest.mark.asyncio
async def test_create_project_preserves_title_within_label_studio_limit() -> None:
    sdk = MagicMock()
    sdk.projects.create.return_value = {"id": 1}
    client = LabelStudioClient.__new__(LabelStudioClient)
    client._client = sdk

    await client.create_project("short dataset", "<View />")

    assert sdk.projects.create.call_args.kwargs["title"] == "short dataset"


@pytest.mark.asyncio
async def test_delete_task_uses_string_task_identity() -> None:
    sdk = MagicMock()
    client = LabelStudioClient.__new__(LabelStudioClient)
    client._client = sdk

    await client.delete_task(42)

    sdk.tasks.delete.assert_called_once_with(id="42")
