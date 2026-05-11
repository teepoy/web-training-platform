"""Unit tests for LabelStudioClient and format converters.

Tests mock the label-studio-sdk so no real Label Studio server is needed.
Async tests use pytest-asyncio (@pytest.mark.asyncio).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.label_studio import (
    LabelStudioClient,
    LabelStudioConnectionError,
    LabelStudioError,
    LabelStudioNotFoundError,
    ls_annotation_to_platform,
    platform_annotation_to_ls,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pydantic_obj(fields: dict):
    """Return a minimal mock that behaves like a Pydantic v2 model."""
    obj = MagicMock()
    obj.model_dump.return_value = fields
    # Ensure dict() also works (backwards compat path)
    obj.dict.return_value = fields
    return obj


def _make_ls_client() -> LabelStudioClient:
    """Construct a LabelStudioClient with a mocked SDK backend."""
    with patch("app.services.label_studio.LabelStudioClient.__init__", return_value=None):
        client = LabelStudioClient.__new__(LabelStudioClient)
        client._client = MagicMock()
    return client


# ---------------------------------------------------------------------------
# generate_image_classification_config
# ---------------------------------------------------------------------------


def test_generate_image_classification_config():
    xml = LabelStudioClient.generate_image_classification_config(["cat", "dog"])
    assert "<Choice value=\"cat\"/>" in xml
    assert "<Choice value=\"dog\"/>" in xml
    assert "<Image" in xml
    assert "<Choices" in xml
    assert "toName=\"image\"" in xml


def test_generate_image_classification_config_single_label():
    xml = LabelStudioClient.generate_image_classification_config(["yes"])
    assert "<Choice value=\"yes\"/>" in xml


def test_generate_image_classification_config_empty_labels():
    xml = LabelStudioClient.generate_image_classification_config([])
    # Still valid XML structure, just no Choice elements
    assert "<View>" in xml
    assert "<Choices" in xml


# ---------------------------------------------------------------------------
# platform_annotation_to_ls
# ---------------------------------------------------------------------------


def test_platform_annotation_to_ls():
    result = platform_annotation_to_ls("cat")
    assert isinstance(result, list)
    assert len(result) == 1
    item = result[0]
    assert item["from_name"] == "classification"
    assert item["to_name"] == "image"
    assert item["type"] == "choices"
    assert item["value"]["choices"] == ["cat"]


def test_platform_annotation_to_ls_with_config_info():
    """label_config_info is accepted but does not change the output."""
    result = platform_annotation_to_ls("dog", label_config_info={"some": "hint"})
    assert result[0]["value"]["choices"] == ["dog"]


# ---------------------------------------------------------------------------
# ls_annotation_to_platform
# ---------------------------------------------------------------------------


def test_ls_annotation_to_platform():
    result = [
        {
            "from_name": "classification",
            "to_name": "image",
            "type": "choices",
            "value": {"choices": ["cat"]},
        }
    ]
    assert ls_annotation_to_platform(result) == "cat"


def test_ls_annotation_to_platform_empty():
    assert ls_annotation_to_platform([]) == ""


def test_ls_annotation_to_platform_no_choices_type():
    result = [{"type": "rectanglelabels", "value": {"rectanglelabels": ["dog"]}}]
    assert ls_annotation_to_platform(result) == ""


def test_ls_annotation_to_platform_empty_choices_list():
    result = [{"type": "choices", "value": {"choices": []}}]
    assert ls_annotation_to_platform(result) == ""


def test_ls_annotation_to_platform_missing_value_key():
    result = [{"type": "choices"}]
    assert ls_annotation_to_platform(result) == ""


# ---------------------------------------------------------------------------
# Roundtrip: platform → LS → platform
# ---------------------------------------------------------------------------


def test_annotation_roundtrip():
    label = "airplane"
    ls_result = platform_annotation_to_ls(label)
    recovered = ls_annotation_to_platform(ls_result)
    assert recovered == label


# ---------------------------------------------------------------------------
# LabelStudioClient — mocked SDK delegation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_client_create_project_delegates_to_sdk():
    client = _make_ls_client()
    mock_project = _pydantic_obj({"id": 1, "title": "My Project"})
    client._client.projects.create = MagicMock(return_value=mock_project)

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_project)):
        result = await client.create_project("My Project", "<View/>")

    assert result["id"] == 1
    assert result["title"] == "My Project"


@pytest.mark.asyncio
async def test_real_client_get_project_delegates_to_sdk():
    client = _make_ls_client()
    mock_project = _pydantic_obj({"id": 5, "title": "Flowers"})

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_project)):
        result = await client.get_project(5)

    assert result["id"] == 5


@pytest.mark.asyncio
async def test_real_client_list_projects_delegates_to_sdk():
    client = _make_ls_client()
    proj1 = _pydantic_obj({"id": 1, "title": "A"})
    proj2 = _pydantic_obj({"id": 2, "title": "B"})
    mock_pager = [proj1, proj2]

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_pager)):
        result = await client.list_projects()

    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2


@pytest.mark.asyncio
async def test_real_client_create_task_delegates_to_sdk():
    client = _make_ls_client()
    mock_task = _pydantic_obj({"id": 10, "project": 1, "data": {"image": "http://img"}})

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_task)):
        result = await client.create_task(1, {"image": "http://img"})

    assert result["id"] == 10


@pytest.mark.asyncio
async def test_real_client_list_tasks_delegates_to_sdk():
    client = _make_ls_client()
    task1 = _pydantic_obj({"id": 1})
    task2 = _pydantic_obj({"id": 2})
    # Build a mock pager with no response (total falls back to len)
    mock_pager = MagicMock()
    mock_pager.__iter__ = MagicMock(return_value=iter([task1, task2]))
    mock_pager.response = None

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_pager)):
        tasks, total = await client.list_tasks(1, page=1, page_size=10)

    assert len(tasks) == 2
    assert total == 2


@pytest.mark.asyncio
async def test_real_client_list_tasks_uses_response_total():
    client = _make_ls_client()
    task1 = _pydantic_obj({"id": 1})
    mock_pager = MagicMock()
    mock_pager.__iter__ = MagicMock(return_value=iter([task1]))
    mock_response = MagicMock()
    mock_response.total = 42
    mock_pager.response = mock_response

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_pager)):
        tasks, total = await client.list_tasks(1)

    assert total == 42


@pytest.mark.asyncio
async def test_real_client_get_task_delegates_to_sdk():
    client = _make_ls_client()
    mock_task = _pydantic_obj({"id": 99})

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_task)):
        result = await client.get_task(99)

    assert result["id"] == 99


@pytest.mark.asyncio
async def test_real_client_create_annotation_delegates_to_sdk():
    client = _make_ls_client()
    result_payload = [{"type": "choices", "value": {"choices": ["cat"]}}]
    mock_annotation = _pydantic_obj({"id": 7, "task": 3, "result": result_payload})

    with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_annotation)):
        result = await client.create_annotation(3, result_payload)

    assert result["id"] == 7
    assert result["task"] == 3


@pytest.mark.asyncio
async def test_real_client_list_annotations_delegates_to_sdk():
    client = _make_ls_client()
    ann1 = _pydantic_obj({"id": 1, "result": []})
    ann2 = _pydantic_obj({"id": 2, "result": []})

    with patch("asyncio.to_thread", new=AsyncMock(return_value=[ann1, ann2])):
        result = await client.list_annotations(5)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_real_client_export_project_delegates_to_sdk():
    client = _make_ls_client()
    tasks = [{"id": 1, "annotations": []}, {"id": 2, "annotations": []}]

    with patch("asyncio.to_thread", new=AsyncMock(return_value=tasks)):
        result = await client.export_project(1)

    assert len(result) == 2
    assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_real_client_export_project_non_list_returns_empty():
    client = _make_ls_client()

    with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        result = await client.export_project(1)

    assert result == []


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_client_maps_404_to_not_found_error():
    from label_studio_sdk.core.api_error import ApiError

    client = _make_ls_client()
    exc = ApiError(status_code=404, body="not found")

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=exc)):
        with pytest.raises(LabelStudioNotFoundError):
            await client.get_project(999)


@pytest.mark.asyncio
async def test_real_client_maps_500_to_label_studio_error():
    from label_studio_sdk.core.api_error import ApiError

    client = _make_ls_client()
    exc = ApiError(status_code=500, body="server error")

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=exc)):
        with pytest.raises(LabelStudioError):
            await client.get_project(1)


@pytest.mark.asyncio
async def test_real_client_maps_connection_error():
    client = _make_ls_client()
    exc = ConnectionRefusedError("refused")

    with patch("asyncio.to_thread", new=AsyncMock(side_effect=exc)):
        with pytest.raises(LabelStudioConnectionError):
            await client.list_projects()
