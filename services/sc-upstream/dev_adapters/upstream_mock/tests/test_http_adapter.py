from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sc_upstream_mock_adapter.http import HttpUpstreamAdapter
from sc_upstream.upstream_db import (
    InspectionDiscoveryOrder,
    InspectionDiscoveryQuery,
    InspectionPublicationCursor,
)


def test_sample_stream_pages_without_crossing_requested_count(monkeypatch) -> None:
    adapter = HttpUpstreamAdapter(
        base_url="http://source.test",
        token="test-token",
        timeout_seconds=1,
    )
    calls: list[dict[str, object]] = []

    def fake_get(_path: str, params: dict[str, object]):
        calls.append(params)
        count = int(params["count"])
        offset = int(params["offset"])
        rows = []
        for index in range(count):
            rows.append(
                {
                    "wafer_key": 1,
                    "inspection_time": "2026-08-30T00:00:00Z",
                    "defect_id": offset + index,
                    "test_id": 1,
                    "class_number": 0,
                    "rough_bin": 1,
                    "wafer_x": 1,
                    "wafer_y": 1,
                    "index_x": 0,
                    "index_y": 0,
                    "adder": 0,
                    "cluster": 0,
                    "images": 0,
                    "size_x": 1,
                    "size_y": 1,
                    "size_d": 1,
                    "area": 1,
                    "final_bin": 0,
                    "manual_bin": 0,
                    "kill_ratio": 0.0,
                    "lot_id": "LOT-1",
                    "wafer_id": "WAFER-1",
                    "layer_id": "LAYER-1",
                    "inspect_equip_id": "EQP-1",
                    "device": "DEVICE-1",
                    "origin_x": 0,
                    "origin_y": 0,
                    "die_size_x": 1,
                    "die_size_y": 1,
                    "recipe_id": "RECIPE-1",
                    "die_x": 0,
                    "die_y": 0,
                }
            )
        return {"rows": rows}

    monkeypatch.setattr(adapter, "_get", fake_get)

    stream = adapter.open_list_samples_stream(
        datetime(2026, 8, 30, tzinfo=UTC),
        1,
        batch_size=2,
        offset=5,
        count=3,
    )
    assert [frame.height for frame in stream.batches] == [2, 1]
    assert [(call["offset"], call["count"]) for call in calls] == [(5, 2), (7, 1)]


def test_publication_discovery_uses_full_keyset_cursor(monkeypatch) -> None:
    adapter = HttpUpstreamAdapter(
        base_url="http://source.test",
        token="test-token",
        timeout_seconds=1,
    )
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(path: str, params: dict[str, object]):
        calls.append((path, params))
        return [
            {
                "inspection_time": "2026-08-01T08:00:00+08:00",
                "wafer_key": 3,
                "published_at": "2026-08-30T01:00:00Z",
                "layer_id": "M1",
            }
        ]

    monkeypatch.setattr(adapter, "_get", fake_get)
    page = asyncio.run(
        adapter.list_discovery_inspections(
            InspectionDiscoveryQuery(
                order=InspectionDiscoveryOrder.PUBLICATION,
                page_size=256,
                published_from=datetime(2026, 8, 30, tzinfo=UTC),
                published_until=datetime(2026, 8, 30, 2, tzinfo=UTC),
                after_publication=InspectionPublicationCursor(
                    published_at=datetime(2026, 8, 30, 0, 30, tzinfo=UTC),
                    inspection_time=datetime(2026, 8, 1, 7, tzinfo=UTC),
                    wafer_key=2,
                ),
            )
        )
    )

    assert page.height == 1
    assert calls == [
        (
            "/upstream/v1/discovery-inspections",
            {
                "order": "publication",
                "page_size": 256,
                "start_time": None,
                "end_time": None,
                "published_from": "2026-08-30T00:00:00+00:00",
                "published_until": "2026-08-30T02:00:00+00:00",
                "after_published_at": "2026-08-30T00:30:00+00:00",
                "after_inspection_time": "2026-08-01T07:00:00+00:00",
                "after_wafer_key": 2,
            },
        )
    ]
