from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

_TASK_SPEC = {"task_type": "classification", "label_space": ["a", "b"]}


def _create_dataset(c: TestClient, name: str) -> str:
    ds = c.post(
        "/api/v1/datasets",
        json={"name": name, "dataset_type": "image_classification", "task_spec": _TASK_SPEC},
    )
    assert ds.status_code == 200
    return ds.json()["id"]


def _create_sample(c: TestClient, dataset_id: str, metadata: dict | None = None) -> str:
    body: dict = {"image_uris": []}
    if metadata is not None:
        body["metadata"] = metadata
    r = c.post(f"/api/v1/datasets/{dataset_id}/samples", json=body)
    assert r.status_code == 200
    return r.json()["id"]


class TestWaferPointsQueryShape:
    def test_response_shape_keys(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-shape-ds")
            _create_sample(c, dataset_id, metadata={"wafer_x": 1.0, "wafer_y": 2.0})

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert set(body.keys()) == {"points", "total"}
            assert isinstance(body["points"], list)
            assert isinstance(body["total"], int)

    def test_point_fields_are_id_x_y(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-fields-ds")
            _create_sample(c, dataset_id, metadata={"wafer_x": 5.5, "wafer_y": 7.25})

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            points = r.json()["points"]
            assert len(points) == 1
            point = points[0]
            assert set(point.keys()) == {"id", "x", "y"}
            assert isinstance(point["id"], str)
            assert isinstance(point["x"], float)
            assert isinstance(point["y"], float)


class TestWaferPointsCoordinateValues:
    def test_float_coordinates_preserved(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-coords-float-ds")
            sample_id = _create_sample(
                c, dataset_id, metadata={"wafer_x": 3.14, "wafer_y": -2.71}
            )

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1
            point = body["points"][0]
            assert point["id"] == sample_id
            assert point["x"] == pytest.approx(3.14)
            assert point["y"] == pytest.approx(-2.71)

    def test_string_encoded_coordinates_coerced_to_float(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-coords-str-ds")
            sample_id = _create_sample(
                c, dataset_id, metadata={"wafer_x": "10.5", "wafer_y": "20.0"}
            )

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1
            point = body["points"][0]
            assert point["id"] == sample_id
            assert isinstance(point["x"], float)
            assert isinstance(point["y"], float)
            assert point["x"] == pytest.approx(10.5)
            assert point["y"] == pytest.approx(20.0)

    def test_integer_coordinates_coerced_to_float(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-coords-int-ds")
            sample_id = _create_sample(
                c, dataset_id, metadata={"wafer_x": 7, "wafer_y": 3}
            )

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1
            point = body["points"][0]
            assert point["id"] == sample_id
            assert isinstance(point["x"], float)
            assert isinstance(point["y"], float)
            assert point["x"] == pytest.approx(7.0)
            assert point["y"] == pytest.approx(3.0)

    def test_multiple_samples_exact_coordinates(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-multi-coords-ds")
            fixtures = [
                (1.0, 2.0),
                (3.5, 4.5),
                (9.9, -1.1),
            ]
            id_to_coords: dict[str, tuple[float, float]] = {}
            for x, y in fixtures:
                sid = _create_sample(c, dataset_id, metadata={"wafer_x": x, "wafer_y": y})
                id_to_coords[sid] = (x, y)

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 3
            assert len(body["points"]) == 3

            returned = {p["id"]: (p["x"], p["y"]) for p in body["points"]}
            for sid, (exp_x, exp_y) in id_to_coords.items():
                assert sid in returned
                got_x, got_y = returned[sid]
                assert got_x == pytest.approx(exp_x)
                assert got_y == pytest.approx(exp_y)


class TestWaferPointsExclusion:
    def test_empty_dataset_returns_zero_points(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-empty-ds")

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 0
            assert body["points"] == []

    def test_samples_without_wafer_metadata_excluded(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-excl-none-ds")
            _create_sample(c, dataset_id, metadata={"label": "cat"})
            _create_sample(c, dataset_id, metadata={})
            _create_sample(c, dataset_id)

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 0
            assert body["points"] == []

    def test_sample_with_only_wafer_x_excluded(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-excl-x-only-ds")
            _create_sample(c, dataset_id, metadata={"wafer_x": 5.0})

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 0

    def test_sample_with_only_wafer_y_excluded(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-excl-y-only-ds")
            _create_sample(c, dataset_id, metadata={"wafer_y": 5.0})

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 0

    def test_mixed_samples_only_complete_wafer_included(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-mixed-ds")
            wafer_id = _create_sample(
                c, dataset_id, metadata={"wafer_x": 1.0, "wafer_y": 2.0}
            )
            _create_sample(c, dataset_id, metadata={"wafer_x": 3.0})
            _create_sample(c, dataset_id, metadata={"wafer_y": 4.0})
            _create_sample(c, dataset_id, metadata={"other": "data"})

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1
            assert len(body["points"]) == 1
            assert body["points"][0]["id"] == wafer_id


class TestPaginatedSampleRouteUnaffected:
    def test_paginated_samples_returns_all_samples_including_wafer(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-paginated-ds")
            ids = [
                _create_sample(c, dataset_id, metadata={"wafer_x": 1.0, "wafer_y": 2.0}),
                _create_sample(c, dataset_id, metadata={"wafer_x": 3.0, "wafer_y": 4.0}),
                _create_sample(c, dataset_id, metadata={"other": "value"}),
                _create_sample(c, dataset_id),
            ]

            r = c.get(f"/api/v1/datasets/{dataset_id}/samples?offset=0&limit=10")
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 4
            returned_ids = {s["id"] for s in body["items"]}
            assert returned_ids == set(ids)

    def test_paginated_samples_pagination_unaffected(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-paginated2-ds")
            for i in range(5):
                _create_sample(
                    c, dataset_id, metadata={"wafer_x": float(i), "wafer_y": float(i)}
                )

            r1 = c.get(f"/api/v1/datasets/{dataset_id}/samples?offset=0&limit=3")
            assert r1.status_code == 200
            body1 = r1.json()
            assert body1["total"] == 5
            assert len(body1["items"]) == 3

            r2 = c.get(f"/api/v1/datasets/{dataset_id}/samples?offset=3&limit=10")
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["total"] == 5
            assert len(body2["items"]) == 2

    def test_wafer_query_does_not_affect_sample_count(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "wafer-no-mutation-ds")
            for i in range(3):
                _create_sample(
                    c, dataset_id, metadata={"wafer_x": float(i), "wafer_y": float(i)}
                )

            r_query = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "wafer-points"},
            )
            assert r_query.status_code == 200
            assert r_query.json()["total"] == 3

            r_samples = c.get(f"/api/v1/datasets/{dataset_id}/samples?offset=0&limit=50")
            assert r_samples.status_code == 200
            assert r_samples.json()["total"] == 3


class TestSampleSliceByIds:
    def test_returns_only_specified_ids(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "slice-ids-basic-ds")
            ids = [_create_sample(c, dataset_id) for _ in range(5)]
            chosen = [ids[1], ids[3]]

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "sample-slice",
                    "params": {"sample_ids": chosen, "limit": 50},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 2
            returned_ids = {item["id"] for item in body["items"]}
            assert returned_ids == set(chosen)

    def test_returns_brushed_ids_outside_first_page(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "slice-ids-pagination-ds")
            ids = [_create_sample(c, dataset_id) for _ in range(20)]
            far_ids = ids[15:18]

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "sample-slice",
                    "params": {"sample_ids": far_ids, "offset": 0, "limit": 5},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 3
            returned_ids = {item["id"] for item in body["items"]}
            assert returned_ids == set(far_ids)

    def test_pagination_within_subset(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "slice-ids-page-ds")
            ids = [_create_sample(c, dataset_id) for _ in range(10)]
            subset = ids[:6]

            r1 = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "sample-slice",
                    "params": {"sample_ids": subset, "offset": 0, "limit": 4},
                },
            )
            assert r1.status_code == 200
            body1 = r1.json()
            assert body1["total"] == 6
            assert len(body1["items"]) == 4

            r2 = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "sample-slice",
                    "params": {"sample_ids": subset, "offset": 4, "limit": 4},
                },
            )
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["total"] == 6
            assert len(body2["items"]) == 2

    def test_cross_dataset_ids_excluded(self) -> None:
        with TestClient(app) as c:
            dataset_a = _create_dataset(c, "slice-ids-cross-a")
            dataset_b = _create_dataset(c, "slice-ids-cross-b")
            id_a = _create_sample(c, dataset_a)
            id_b = _create_sample(c, dataset_b)

            r = c.post(
                f"/api/v1/datasets/{dataset_a}/query",
                json={
                    "query_type": "sample-slice",
                    "params": {"sample_ids": [id_a, id_b]},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 1
            assert body["items"][0]["id"] == id_a

    def test_empty_ids_returns_empty_set(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "slice-ids-empty-ds")
            for _ in range(3):
                _create_sample(c, dataset_id)

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "sample-slice",
                    "params": {"sample_ids": []},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 0
            assert body["items"] == []

    def test_no_sample_ids_keeps_default_behavior(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "slice-ids-default-ds")
            for _ in range(3):
                _create_sample(c, dataset_id)

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "sample-slice", "params": {"limit": 50}},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 3
            assert len(body["items"]) == 3

    def test_invalid_sample_ids_type_returns_error(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, "slice-ids-invalid-ds")
            _create_sample(c, dataset_id)

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "sample-slice",
                    "params": {"sample_ids": "not-a-list"},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert "error" in body
