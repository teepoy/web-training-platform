from __future__ import annotations

from typing import Any

import httpx
import pytest

from seedmaker.upstream_mock import publish_dev_showcase


def test_publish_dev_showcase_uses_only_control_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTREAM_MOCK_URL", "http://simulator.test")
    monkeypatch.setenv("UPSTREAM_MOCK_TOKEN", "secret")
    monkeypatch.setenv("UPSTREAM_MOCK_TIMEOUT_SECONDS", "30")
    request: dict[str, Any] = {}

    def post(url: str, **kwargs: Any) -> httpx.Response:
        request.update(url=url, **kwargs)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "inspections": [
                    {"reused": False},
                    {"reused": True},
                    {"reused": True},
                    {"reused": True},
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", post)

    publish_dev_showcase(
        inspection_time="2026-08-01T04:00:00+08:00",
        total_defects=10,
        imaged_defects=2,
        images_per_defect=1,
        gallery_defects=3,
        gallery_imaged_defects=1,
        defects_per_archive=5,
        append_batch_size=5,
    )

    assert request["url"] == "http://simulator.test/api/v1/scenarios/dev-showcase"
    assert request["headers"] == {"Authorization": "Bearer secret"}
    assert request["json"]["total_defects"] == 10
    assert request["json"]["published_at"] == "2026-08-01T04:05:00+08:00"


def test_publish_dev_showcase_requires_aware_source_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTREAM_MOCK_URL", "http://simulator.test")
    monkeypatch.setenv("UPSTREAM_MOCK_TOKEN", "secret")
    monkeypatch.setenv("UPSTREAM_MOCK_TIMEOUT_SECONDS", "30")

    with pytest.raises(ValueError, match="timezone offset"):
        publish_dev_showcase(
            inspection_time="2026-08-01T04:00:00",
            total_defects=10,
            imaged_defects=2,
            images_per_defect=1,
            gallery_defects=3,
            gallery_imaged_defects=1,
            defects_per_archive=5,
            append_batch_size=5,
        )
