"""Integration tests for SC inspection endpoints — now sourced from wafer DB."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
import polars as pl
import pytest

from app.main import app
from app.modules.sc.port.http.deps import get_upstream_reader
from app.modules.sc.port.http.router import _apply_sample_table_sort
from proto_stubs.sc.v1 import sample_pb2

pytestmark = pytest.mark.integration

PB_CONTENT_TYPE = "application/x-protobuf"


def _parse_summary_resp(body: bytes) -> dict:
    import json

    return json.loads(body)


def _parse_map_points_resp(body: bytes) -> sample_pb2.WaferMapResponse:
    msg = sample_pb2.WaferMapResponse()
    msg.ParseFromString(body)
    return msg


# ── Inspection list tests ──────────────────────────────────────────

TODAY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
SAFE_START = (TODAY - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
SAFE_END = (TODAY + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")


def test_sample_table_sort_orders_defect_id_numerically():
    df = pl.DataFrame({"defect_id": ["1", "10", "2"]})

    sorted_df = _apply_sample_table_sort(
        df,
        SimpleNamespace(field="defect_id", direction="asc"),
        requested=None,
    )

    assert sorted_df["defect_id"].to_list() == ["1", "2", "10"]


def test_list_inspections_returns_items_and_total(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections",
                params={
                    "start_time": SAFE_START,
                    "end_time": SAFE_END,
                },
            )
            assert resp.status_code == 200, resp.text
            assert resp.headers.get("content-type", "").startswith("application/json")

            msg = _parse_summary_resp(resp.content)
            assert msg["total"] >= 1
            assert len(msg["items"]) >= 1
            assert all(
                "inspection_time" in it
                and "wafer_key" in it
                and "lot_id" in it
                and "wafer_id" in it
                and "layer_id" in it
                and "eqp_id" in it
                and "recipe_id" in it
                and "defects" in it
                and "images" in it
                for it in msg["items"]
            )
            # All required fields are present (no defaults)
            for it in msg["items"]:
                assert it["lot_id"] != ""
                assert it["wafer_id"] != ""
                assert it["layer_id"] != ""
                assert it["eqp_id"] != ""
                assert it["recipe_id"] != ""
                assert it["defects"] >= 0
                assert it["images"] >= 0
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_get_inspection_returns_summary_item(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            list_resp = client.get(
                "/api/v1/sc/inspections",
                params={
                    "start_time": SAFE_START,
                    "end_time": SAFE_END,
                },
            )
            assert list_resp.status_code == 200, list_resp.text
            first = _parse_summary_resp(list_resp.content)["items"][0]

            resp = client.get(
                f"/api/v1/sc/inspections/{first['inspection_time']}/{first['wafer_key']}",
            )
            assert resp.status_code == 200, resp.text
            item = _parse_summary_resp(resp.content)
            assert item["wafer_key"] == first["wafer_key"]
            assert item["defects"] == first["defects"]
            assert item["images"] == first["images"]
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_list_inspections_empty_time_range(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections",
                params={
                    "start_time": "1970-01-01T00:00:00",
                    "end_time": "1970-01-02T00:00:00",
                },
            )
            assert resp.status_code == 200, resp.text
            msg = _parse_summary_resp(resp.content)
            assert msg["total"] == 0
            assert len(msg["items"]) == 0
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_list_inspections_empty_time_range_with_eqp_filter(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections",
                params={
                    "start_time": "1970-01-01T00:00:00",
                    "end_time": "1970-01-02T00:00:00",
                    "eqp_id": "EQP01",
                },
            )
            assert resp.status_code == 200, resp.text
            msg = _parse_summary_resp(resp.content)
            assert msg["total"] == 0
            assert len(msg["items"]) == 0
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_list_inspections_range_exceeds_14_days_returns_400(
    mock_wafer_db_reader,
):
    from app.modules.sc.port.http.router import MAX_INSPECTION_RANGE_DAYS

    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            over_start = (TODAY - timedelta(days=MAX_INSPECTION_RANGE_DAYS + 1)).strftime("%Y-%m-%dT%H:%M:%S")
            over_end = TODAY.strftime("%Y-%m-%dT%H:%M:%S")
            resp = client.get(
                "/api/v1/sc/inspections",
                params={
                    "start_time": over_start,
                    "end_time": over_end,
                },
            )
            assert resp.status_code == 400
            assert f"must not exceed {MAX_INSPECTION_RANGE_DAYS} days" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


# ── Inspection samples tests ───────────────────────────────────────


def test_inspection_samples_success(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections",
                params={
                    "start_time": SAFE_START,
                    "end_time": SAFE_END,
                },
            )
            msg = _parse_summary_resp(resp.content)
            assert len(msg["items"]) >= 1

            first = msg["items"][0]
            insp_time = first["inspection_time"]
            wafer_key = first["wafer_key"]

            resp2 = client.post(
                f"/api/v1/sc/inspections/{insp_time}/{wafer_key}/sample-table-rows",
                json={"defect_ids": ["3", "1", "2"], "page": 0, "page_size": 10},
            )
            assert resp2.status_code == 200, resp.text
            body = resp2.json()
            assert body["total"] >= 1
            assert len(body["items"]) >= 1
            assert "defect_id" in body["items"][0]
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_sample_table_rows_stream_emits_progress_data_done(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections",
                params={
                    "start_time": SAFE_START,
                    "end_time": SAFE_END,
                },
            )
            first = _parse_summary_resp(resp.content)["items"][0]
            stream_resp = client.post(
                (
                    f"/api/v1/sc/inspections/{first['inspection_time']}/"
                    f"{first['wafer_key']}/sample-table-rows/stream"
                ),
                json={"defect_ids": ["3", "1", "2"], "page": 0, "page_size": 10},
            )
            assert stream_resp.status_code == 200, stream_resp.text
            assert stream_resp.headers.get("content-type", "").startswith(
                "text/event-stream"
            )
            body = stream_resp.text
            assert "event: progress" in body
            assert "event: data" in body
            assert "event: done" in body
            assert '"operation":"sc.sample-table"' in body
            assert '"items":' in body
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_sample_table_rows_filters_sorts_then_paginates(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            summary = client.get(
                "/api/v1/sc/inspections",
                params={"start_time": SAFE_START, "end_time": SAFE_END},
            )
            first = _parse_summary_resp(summary.content)["items"][0]
            url = (
                f"/api/v1/sc/inspections/{first['inspection_time']}/"
                f"{first['wafer_key']}/sample-table-rows"
            )

            response = client.post(
                url,
                json={
                    "page": 0,
                    "page_size": 5,
                    "filter": {
                        "rough_bin": {
                            "filterType": "set",
                            "values": [1, 2, 3],
                        },
                        "wafer_x": {
                            "filterType": "number",
                            "type": "inRange",
                            "filter": -1_000_000,
                            "filterTo": 1_000_000,
                        },
                    },
                    "sort": {"field": "defect_id", "direction": "desc"},
                },
            )

            assert response.status_code == 200, response.text
            body = response.json()
            defect_ids = [int(row["defect_id"]) for row in body["items"]]
            assert defect_ids == sorted(defect_ids, reverse=True)
            assert len(body["items"]) <= 5
            assert all(row["rough_bin"] in {1, 2, 3} for row in body["items"])
            assert all(
                -1_000_000 <= row["wafer_x"] <= 1_000_000
                for row in body["items"]
            )
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_inspection_defect_ids_binary_returns_sorted_int32(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            summary = client.get(
                "/api/v1/sc/inspections",
                params={"start_time": SAFE_START, "end_time": SAFE_END},
            )
            first = _parse_summary_resp(summary.content)["items"][0]
            response = client.get(
                f"/api/v1/sc/inspections/{first['inspection_time']}/"
                f"{first['wafer_key']}/defect-ids.bin"
            )

            assert response.status_code == 200, response.text
            assert response.headers.get("content-type", "").startswith(
                "application/octet-stream"
            )
            assert len(response.content) % 4 == 0
            defect_ids = [
                int.from_bytes(response.content[i : i + 4], "little", signed=True)
                for i in range(0, len(response.content), 4)
            ]
            assert defect_ids == [1, 2, 3]
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_inspection_map_points_stream_reports_sample_progress(
    mock_wafer_db_reader,
):
    original_samples = mock_wafer_db_reader.list_samples.return_value

    async def _list_samples_with_progress(*args, **kwargs):
        on_progress = kwargs.get("on_progress")
        if on_progress is not None:
            on_progress(1)
            on_progress(2)
            on_progress(3)
        return original_samples

    mock_wafer_db_reader.list_samples.side_effect = _list_samples_with_progress
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections/2026-01-01T00:00:00+00:00/1/map-points/stream"
            )
            assert resp.status_code == 200, resp.text
            assert '"loaded_count":1' in resp.text
            assert '"loaded_count":2' in resp.text
            assert '"loaded_count":3' in resp.text
            assert "event: done" in resp.text
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_inspection_split_preview_endpoints_success(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections",
                params={
                    "start_time": SAFE_START,
                    "end_time": SAFE_END,
                },
            )
            first = _parse_summary_resp(resp.content)["items"][0]
            insp_time = first["inspection_time"]
            wafer_key = first["wafer_key"]
            defects = first["defects"]

            map_resp = client.get(
                f"/api/v1/sc/inspections/{insp_time}/{wafer_key}/map-points",
                params={
                    "reticleXDieCount": 10,
                    "reticleYDieCount": 8,
                    "reticleXDieShift": 100,
                    "reticleYDieShift": 50,
                },
            )
            assert map_resp.status_code == 200, map_resp.text
            assert map_resp.headers.get("content-type", "").startswith(PB_CONTENT_TYPE)
            map_pb = _parse_map_points_resp(map_resp.content)
            assert map_pb.total == defects
            assert map_pb.wafer_key == wafer_key
            assert len(map_pb.wafer_points) == defects * 6
            assert len(map_pb.die_points) == defects * 6
            # Verify geometry fields exist
            assert map_pb.HasField("geometry")
            assert map_pb.geometry.center_x == first["center_x"]
            assert map_pb.geometry.center_y == first["center_y"]
            # Verify reticle data is also included
            assert len(map_pb.reticle_points) == defects * 6
            assert map_pb.reticle_x_die_count == 10
            assert map_pb.reticle_y_die_count == 8
            max_reticle_x = map_pb.reticle_x_die_count * map_pb.geometry.die_size_x
            max_reticle_y = map_pb.reticle_y_die_count * map_pb.geometry.die_size_y
            for i in range(0, len(map_pb.reticle_points), 6):
                assert 0 <= map_pb.reticle_points[i] < max_reticle_x
                assert 0 <= map_pb.reticle_points[i + 1] < max_reticle_y
            assert not map_pb.is_sampled

            # ── Sampled mode ─────────────────────────────────────────
            sampled_resp = client.get(
                f"/api/v1/sc/inspections/{insp_time}/{wafer_key}/map-points",
                params={
                    "sampled": True,
                    "gridSizeNm": 600,
                    "reticleXDieCount": 10,
                    "reticleYDieCount": 8,
                },
            )
            assert sampled_resp.status_code == 200, sampled_resp.text
            sampled_pb = _parse_map_points_resp(sampled_resp.content)
            assert sampled_pb.total == defects  # total still full count
            assert sampled_pb.is_sampled
            # Legacy mode omission still returns all three arrays.
            assert len(sampled_pb.wafer_points) // 6 <= defects
            assert len(sampled_pb.die_points) // 6 <= defects
            assert len(sampled_pb.reticle_points) // 6 <= defects
            # Geometry still present
            assert sampled_pb.HasField("geometry")
            assert sampled_pb.geometry.center_x == first["center_x"]

            reticle_resp = client.get(
                f"/api/v1/sc/inspections/{insp_time}/{wafer_key}/map-points",
                params={
                    "mode": "reticle",
                    "reticleXDieCount": 3,
                    "reticleYDieCount": 5,
                },
            )
            assert reticle_resp.status_code == 200, reticle_resp.text
            reticle_pb = _parse_map_points_resp(reticle_resp.content)
            assert len(reticle_pb.wafer_points) == 0
            assert len(reticle_pb.die_points) == 0
            assert len(reticle_pb.reticle_points) == defects * 6

            review_resp = client.get(
                f"/api/v1/sc/inspections/{insp_time}/{wafer_key}/review-images"
            )
            assert review_resp.status_code == 200, review_resp.text
            review_body = review_resp.json()
            assert review_body["total"] >= 1
            assert set(review_body["items"][0]) == {"defect_id", "review_images"}
            assert set(review_body["items"][0]["review_images"][0]) == {
                "image_name",
                "image_id",
                "image_type",
            }
            first_review_defect_id = review_body["items"][0]["defect_id"]
            filtered_review_resp = client.get(
                f"/api/v1/sc/inspections/{insp_time}/{wafer_key}/review-images",
                params={"defect_ids": first_review_defect_id},
            )
            assert filtered_review_resp.status_code == 200, filtered_review_resp.text
            filtered_review_body = filtered_review_resp.json()
            assert filtered_review_body["total"] == 1
            assert filtered_review_body["items"][0]["defect_id"] == first_review_defect_id
            filter_only_review_resp = client.get(
                f"/api/v1/sc/inspections/{insp_time}/{wafer_key}/review-images",
                params={
                    "sample_filter": json.dumps(
                        {
                            "defect_id": {
                                "filterType": "set",
                                "values": [first_review_defect_id],
                            }
                        }
                    )
                },
            )
            assert filter_only_review_resp.status_code == 200, filter_only_review_resp.text
            filter_only_review_body = filter_only_review_resp.json()
            assert filter_only_review_body["total"] == 1
            assert filter_only_review_body["items"][0]["defect_id"] == first_review_defect_id

            table_resp = client.post(
                f"/api/v1/sc/inspections/{insp_time}/{wafer_key}/sample-table-rows",
                json={"defect_ids": ["3", "1", "2"], "page": 0, "page_size": 10},
            )
            assert table_resp.status_code == 200, table_resp.text
            table_body = table_resp.json()
            assert table_body["total"] == 3
            assert table_body["next_anchor"] is None
            assert [row["defect_id"] for row in table_body["items"]] == ["3", "1", "2"]
            assert set(table_body["items"][0]) == {
                "defect_id",
                "rough_bin",
                "class_number",
                "images",
                "test_id",
                "wafer_x",
                "wafer_y",
                "index_x",
                "index_y",
                "adder",
                "cluster_id",
                "die_x",
                "die_y",
                "reticle_x",
                "reticle_y",
                "size_x",
                "size_y",
                "size_d",
                "area",
                "final_bin",
                "manual_bin",
                "kill_ratio",
            }
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_inspection_samples_nonexistent_wafer_404(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections/2026-01-15T08:00:00/99999/samples"
            )
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)


def test_inspection_samples_invalid_datetime_400(
    mock_wafer_db_reader,
):
    app.dependency_overrides[get_upstream_reader] = lambda: mock_wafer_db_reader
    try:
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/sc/inspections/not-a-date/1/review-images"
            )
            assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_upstream_reader, None)
