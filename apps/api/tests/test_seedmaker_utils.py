from __future__ import annotations

from seedmaker.utils import _find_by_name


def test_find_by_name_accepts_paginated_response() -> None:
    body = {
        "items": [
            {"id": "dataset-1", "name": "Other"},
            {"id": "dataset-2", "name": "Wafer Demo"},
        ],
        "total": 2,
    }

    assert _find_by_name(body, "Wafer Demo") == {
        "id": "dataset-2",
        "name": "Wafer Demo",
    }


def test_find_by_name_accepts_legacy_list_response() -> None:
    body = [
        {"id": "dataset-1", "name": "Other"},
        {"id": "dataset-2", "name": "Wafer Demo"},
    ]

    assert _find_by_name(body, "Wafer Demo") == {
        "id": "dataset-2",
        "name": "Wafer Demo",
    }


def test_find_by_name_ignores_unexpected_response_items() -> None:
    body = {"items": ["items", {"id": "dataset-1", "name": "Wafer Demo"}]}

    assert _find_by_name(body, "Wafer Demo") == {
        "id": "dataset-1",
        "name": "Wafer Demo",
    }
