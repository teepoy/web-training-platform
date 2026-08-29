from __future__ import annotations

import io
import json

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.modules.datasets.port.http.extensions.import_parquet_router import (
    _extract_image_uri,
    _find_image_columns,
    _find_label_column,
    _is_image_struct,
    _parquet_to_sample_items,
)
from app.modules.datasets.port.http.extensions.export_parquet_router import (
    _build_image_struct,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Unit tests — helper functions
# ---------------------------------------------------------------------------


class TestIsImageStruct:
    def test_dict_with_bytes_key(self) -> None:
        assert _is_image_struct({"bytes": b"\x89PNG", "path": "img.png"}) is True

    def test_dict_with_path_key_only(self) -> None:
        assert _is_image_struct({"path": "img.png"}) is True

    def test_dict_with_bytes_key_only(self) -> None:
        assert _is_image_struct({"bytes": b"data"}) is True

    def test_plain_dict(self) -> None:
        assert _is_image_struct({"name": "cat"}) is False

    def test_string(self) -> None:
        assert _is_image_struct("hello") is False

    def test_none(self) -> None:
        assert _is_image_struct(None) is False

    def test_list(self) -> None:
        assert _is_image_struct([1, 2]) is False

    def test_empty_dict(self) -> None:
        assert _is_image_struct({}) is False


class TestExtractImageUri:
    def test_none(self) -> None:
        assert _extract_image_uri("image", None) == []

    def test_single_struct_with_path(self) -> None:
        val = {"bytes": b"\x89PNG", "path": "train/img1.jpg"}
        assert _extract_image_uri("image", val) == ["train/img1.jpg"]

    def test_single_struct_without_path(self) -> None:
        val = {"bytes": b"\x89PNG"}
        assert _extract_image_uri("image", val) == []

    def test_single_struct_with_empty_path(self) -> None:
        val = {"bytes": b"\x89PNG", "path": ""}
        assert _extract_image_uri("image", val) == []

    def test_list_of_structs(self) -> None:
        val = [
            {"bytes": b"a", "path": "img1.jpg"},
            {"bytes": b"b", "path": "img2.jpg"},
        ]
        assert _extract_image_uri("image", val) == ["img1.jpg", "img2.jpg"]

    def test_list_with_non_image_element(self) -> None:
        val = [{"bytes": b"a", "path": "img1.jpg"}, "not-a-struct"]
        assert _extract_image_uri("image", val) == ["img1.jpg"]

    def test_plain_string(self) -> None:
        assert _extract_image_uri("image", "just-a-string") == []

    def test_int(self) -> None:
        assert _extract_image_uri("image", 42) == []


class TestFindImageColumns:
    def test_detects_struct_column(self) -> None:
        image_type = pa.struct(
            [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
        )
        table = pa.table(
            {
                "image": pa.array(
                    [{"bytes": b"\x89", "path": "a.jpg"}], type=image_type
                ),
                "label": pa.array(["cat"]),
            }
        )
        assert _find_image_columns(table) == ["image"]

    def test_detects_list_of_struct_column(self) -> None:
        image_type = pa.struct(
            [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
        )
        table = pa.table(
            {
                "images": pa.array(
                    [[{"bytes": b"\x89", "path": "a.jpg"}]], type=pa.list_(image_type)
                ),
                "label": pa.array(["cat"]),
            }
        )
        assert _find_image_columns(table) == ["images"]

    def test_no_image_columns(self) -> None:
        table = pa.table(
            {
                "text": pa.array(["hello"]),
                "label": pa.array(["cat"]),
            }
        )
        assert _find_image_columns(table) == []

    def test_multiple_image_columns(self) -> None:
        image_type = pa.struct(
            [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
        )
        table = pa.table(
            {
                "image": pa.array(
                    [{"bytes": b"\x89", "path": "a.jpg"}], type=image_type
                ),
                "thumbnail": pa.array(
                    [{"bytes": b"\x89", "path": "thumb_a.jpg"}], type=image_type
                ),
                "label": pa.array(["cat"]),
            }
        )
        result = _find_image_columns(table)
        assert set(result) == {"image", "thumbnail"}


class TestFindLabelColumn:
    def test_finds_label(self) -> None:
        table = pa.table({"label": pa.array(["cat"]), "text": pa.array(["desc"])})
        assert _find_label_column(table, []) == "label"

    def test_finds_class(self) -> None:
        table = pa.table({"class": pa.array(["cat"]), "text": pa.array(["desc"])})
        assert _find_label_column(table, []) == "class"

    def test_finds_category(self) -> None:
        table = pa.table({"category": pa.array(["cat"]), "text": pa.array(["desc"])})
        assert _find_label_column(table, []) == "category"

    def test_skips_image_col(self) -> None:
        table = pa.table({"label": pa.array(["cat"])})
        assert _find_label_column(table, ["label"]) is None

    def test_no_match(self) -> None:
        table = pa.table({"text": pa.array(["desc"]), "value": pa.array([42])})
        assert _find_label_column(table, []) is None


class TestParquetToSampleItems:
    def _make_hf_table(self, rows: int = 3) -> pa.Table:
        image_type = pa.struct(
            [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
        )
        images = pa.array(
            [[{"bytes": b"\x89", "path": f"train/{i}.jpg"}] for i in range(rows)],
            type=pa.list_(image_type),
        )
        labels = pa.array([f"class_{i}" for i in range(rows)], type=pa.string())
        captions = pa.array([f"caption {i}" for i in range(rows)], type=pa.string())
        return pa.table({"image": images, "label": labels, "caption": captions})

    def test_extracts_image_uris(self) -> None:
        table = self._make_hf_table(2)
        items, warnings = _parquet_to_sample_items(table)
        assert len(items) == 2
        assert items[0].image_uris == ["train/0.jpg"]
        assert items[1].image_uris == ["train/1.jpg"]

    def test_extracts_labels(self) -> None:
        table = self._make_hf_table(2)
        items, _ = _parquet_to_sample_items(table)
        assert items[0].label == "class_0"
        assert items[1].label == "class_1"

    def test_extracts_metadata_columns(self) -> None:
        table = self._make_hf_table(2)
        items, _ = _parquet_to_sample_items(table)
        assert items[0].metadata["caption"] == "caption 0"
        assert items[1].metadata["caption"] == "caption 1"

    def test_extracts_portable_sample_id_outside_user_metadata(self) -> None:
        table = self._make_hf_table(1).append_column(
            "sample_id", pa.array(["portable-sample-1"])
        )
        items, _ = _parquet_to_sample_items(table)
        assert items[0].metadata["__platform_sample_id"] == "portable-sample-1"

    def test_decodes_portable_json_metadata(self) -> None:
        table = self._make_hf_table(1).append_column(
            "metadata", pa.array(['{"source":"portable","rank":3}'])
        )
        items, _ = _parquet_to_sample_items(table)
        assert items[0].metadata["source"] == "portable"
        assert items[0].metadata["rank"] == 3

    def test_no_image_columns_warns(self) -> None:
        table = pa.table({"text": pa.array(["hello"]), "label": pa.array(["cat"])})
        items, warnings = _parquet_to_sample_items(table)
        assert len(warnings) == 1
        assert "No image columns" in warnings[0]
        assert items[0].image_uris == []

    def test_no_label_column(self) -> None:
        image_type = pa.struct(
            [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
        )
        table = pa.table(
            {
                "image": pa.array(
                    [[{"bytes": b"\x89", "path": "a.jpg"}]], type=pa.list_(image_type)
                ),
                "caption": pa.array(["a drawing of a cat"]),
            }
        )
        items, _ = _parquet_to_sample_items(table)
        assert items[0].label is None
        assert items[0].metadata["caption"] == "a drawing of a cat"

    def test_null_label(self) -> None:
        image_type = pa.struct(
            [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
        )
        table = pa.table(
            {
                "image": pa.array(
                    [[{"bytes": b"\x89", "path": "a.jpg"}]], type=pa.list_(image_type)
                ),
                "label": pa.array([None], type=pa.string()),
            }
        )
        items, _ = _parquet_to_sample_items(table)
        assert items[0].label is None

    def test_null_metadata_value_skipped(self) -> None:
        image_type = pa.struct(
            [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
        )
        table = pa.table(
            {
                "image": pa.array(
                    [[{"bytes": b"\x89", "path": "a.jpg"}]], type=pa.list_(image_type)
                ),
                "extra": pa.array([None], type=pa.string()),
            }
        )
        items, _ = _parquet_to_sample_items(table)
        assert "extra" not in items[0].metadata


class TestBuildImageStruct:
    def test_with_path_only(self) -> None:
        result = _build_image_struct("train/img.jpg")
        assert result == {"bytes": None, "path": "train/img.jpg"}

    def test_with_bytes_and_path(self) -> None:
        result = _build_image_struct("img.jpg", image_bytes=b"\x89PNG")
        assert result == {"bytes": b"\x89PNG", "path": "img.jpg"}


# ---------------------------------------------------------------------------
# Integration tests — import endpoint
# ---------------------------------------------------------------------------


def _make_parquet_bytes(table: pa.Table) -> bytes:
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def _make_hf_parquet(rows: int = 3) -> bytes:
    image_type = pa.struct(
        [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
    )
    images = pa.array(
        [
            [{"bytes": b"\x89", "path": f"memory://parquet/{i}.jpg"}]
            for i in range(rows)
        ],
        type=pa.list_(image_type),
    )
    labels = pa.array([f"cls_{i}" for i in range(rows)], type=pa.string())
    table = pa.table({"image": images, "label": labels})
    return _make_parquet_bytes(table)


class TestImportParquetEndpoint:
    def test_import_valid_parquet(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-import-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cls_0", "cls_1", "cls_2"],
                    },
                },
            )
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]

            parquet_data = _make_hf_parquet(3)
            r = c.post(
                f"/api/v1/plugins/import-parquet/import?dataset_id={dataset_id}",
                files={
                    "file": (
                        "train.parquet",
                        io.BytesIO(parquet_data),
                        "application/octet-stream",
                    )
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["imported"] == 3
            assert body["failed"] == 0
            assert len(body["sample_ids"]) == 3
            assert len(body["ls_task_ids"]) == 3

    def test_import_parquet_with_labels_creates_annotations(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-label-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat", "dog"],
                    },
                },
            )
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]

            image_type = pa.struct(
                [pa.field("bytes", pa.binary()), pa.field("path", pa.string())]
            )
            table = pa.table(
                {
                    "image": pa.array(
                        [[{"bytes": b"\x89", "path": "memory://cat.jpg"}]],
                        type=pa.list_(image_type),
                    ),
                    "label": pa.array(["cat"]),
                }
            )
            parquet_data = _make_parquet_bytes(table)

            r = c.post(
                f"/api/v1/plugins/import-parquet/import?dataset_id={dataset_id}",
                files={
                    "file": (
                        "train.parquet",
                        io.BytesIO(parquet_data),
                        "application/octet-stream",
                    )
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["imported"] == 1

            listed = c.get(f"/api/v1/datasets/{dataset_id}/samples")
            assert listed.status_code == 200
            sample_id = listed.json()["items"][0]["id"]

            anns = c.get(
                f"/api/v1/datasets/{dataset_id}/samples/{sample_id}/annotations"
            )
            assert anns.status_code == 200
            assert any(a["label"] == "cat" for a in anns.json())

    def test_import_preserves_portable_sample_id(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-portable-id-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat"],
                    },
                },
            )
            dataset_id = ds.json()["id"]
            table = pa.table(
                {
                    "sample_id": pa.array(["portable-sample-1"]),
                    "label": pa.array(["cat"]),
                }
            )
            response = c.post(
                f"/api/v1/plugins/import-parquet/import?dataset_id={dataset_id}",
                files={
                    "file": (
                        "portable.parquet",
                        io.BytesIO(_make_parquet_bytes(table)),
                        "application/octet-stream",
                    )
                },
            )
            assert response.status_code == 200
            assert response.json()["sample_ids"] == ["portable-sample-1"]

    def test_import_rejects_sample_id_used_by_another_dataset(self) -> None:
        with TestClient(app) as c:
            source = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-id-source",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat"],
                    },
                },
            )
            source_id = source.json()["id"]
            sample = c.post(
                f"/api/v1/datasets/{source_id}/samples",
                json={"image_uris": []},
            )
            sample_id = sample.json()["id"]
            target = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-id-target",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat"],
                    },
                },
            )
            target_id = target.json()["id"]
            table = pa.table(
                {
                    "sample_id": pa.array([sample_id]),
                    "label": pa.array(["cat"]),
                }
            )
            response = c.post(
                f"/api/v1/plugins/import-parquet/import?dataset_id={target_id}",
                files={
                    "file": (
                        "conflict.parquet",
                        io.BytesIO(_make_parquet_bytes(table)),
                        "application/octet-stream",
                    )
                },
            )
            assert response.status_code == 409
            assert "already exist" in response.json()["detail"]
            listed = c.get(f"/api/v1/datasets/{target_id}/samples")
            assert listed.json()["total"] == 0

    def test_import_invalid_file(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-bad-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["a"],
                    },
                },
            )
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]

            r = c.post(
                f"/api/v1/plugins/import-parquet/import?dataset_id={dataset_id}",
                files={
                    "file": (
                        "bad.parquet",
                        io.BytesIO(b"not a parquet file"),
                        "application/octet-stream",
                    )
                },
            )
            assert r.status_code == 400
            assert "Invalid parquet file" in r.json()["detail"]

    def test_import_rejects_unknown_label_before_writes(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-label-contract-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat"],
                    },
                },
            )
            dataset_id = ds.json()["id"]
            table = pa.table({"label": pa.array(["horse"])})
            response = c.post(
                f"/api/v1/plugins/import-parquet/import?dataset_id={dataset_id}",
                files={
                    "file": (
                        "unknown-label.parquet",
                        io.BytesIO(_make_parquet_bytes(table)),
                        "application/octet-stream",
                    )
                },
            )
            assert response.status_code == 422
            assert "not in the target Dataset label space" in response.json()["detail"]
            listed = c.get(f"/api/v1/datasets/{dataset_id}/samples")
            assert listed.json()["total"] == 0

    def test_import_empty_parquet(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-empty-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["a"],
                    },
                },
            )
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]

            empty_table = pa.table({"label": pa.array([], type=pa.string())})
            parquet_data = _make_parquet_bytes(empty_table)

            r = c.post(
                f"/api/v1/plugins/import-parquet/import?dataset_id={dataset_id}",
                files={
                    "file": (
                        "empty.parquet",
                        io.BytesIO(parquet_data),
                        "application/octet-stream",
                    )
                },
            )
            assert r.status_code == 400
            assert "no rows" in r.json()["detail"].lower()

    def test_import_dataset_not_found(self) -> None:
        with TestClient(app) as c:
            parquet_data = _make_hf_parquet(1)
            r = c.post(
                "/api/v1/plugins/import-parquet/import?dataset_id=nonexistent-id-99999",
                files={
                    "file": (
                        "train.parquet",
                        io.BytesIO(parquet_data),
                        "application/octet-stream",
                    )
                },
            )
            assert r.status_code == 404

    def test_import_parquet_no_image_columns_still_succeeds(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-no-img-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat"],
                    },
                },
            )
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]

            table = pa.table({"text": pa.array(["hello"]), "label": pa.array(["cat"])})
            parquet_data = _make_parquet_bytes(table)

            r = c.post(
                f"/api/v1/plugins/import-parquet/import?dataset_id={dataset_id}",
                files={
                    "file": (
                        "noimg.parquet",
                        io.BytesIO(parquet_data),
                        "application/octet-stream",
                    )
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["imported"] == 1
            assert any("No image columns" in e for e in body["errors"])


# ---------------------------------------------------------------------------
# Integration tests — export endpoint
# ---------------------------------------------------------------------------


class TestExportParquetEndpoint:
    def test_export_dataset_with_samples(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-export-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat", "dog"],
                    },
                },
            )
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]

            c.post(
                f"/api/v1/datasets/{dataset_id}/samples/import",
                json={
                    "items": [
                        {
                            "image_uris": ["memory://export/cat.jpg"],
                            "metadata": {"source": "test"},
                            "label": "cat",
                        },
                        {
                            "image_uris": ["memory://export/dog.jpg"],
                            "metadata": {"source": "test"},
                            "label": "dog",
                        },
                    ]
                },
            )
            r = c.post(
                f"/api/v1/plugins/export-parquet/export?dataset_id={dataset_id}",
            )
            assert r.status_code == 200
            body = r.json()
            assert body["rows"] == 2
            assert body["format"] == "parquet"
            assert "uri" in body

    def test_export_dataset_not_found(self) -> None:
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/plugins/export-parquet/export?dataset_id=nonexistent-id-99999",
            )
            assert r.status_code == 404

    def test_export_empty_dataset(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-export-empty",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["a"],
                    },
                },
            )
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]

            r = c.post(
                f"/api/v1/plugins/export-parquet/export?dataset_id={dataset_id}",
            )
            assert r.status_code == 200
            body = r.json()
            assert body["rows"] == 0
            assert body["format"] == "parquet"

    def test_export_roundtrip_parquet(self) -> None:
        with TestClient(app) as c:
            ds = c.post(
                "/api/v1/datasets",
                json={
                    "name": "parquet-roundtrip-ds",
                    "dataset_type": "image_classification",
                    "task_spec": {
                        "task_type": "classification",
                        "label_space": ["cat", "dog"],
                    },
                },
            )
            assert ds.status_code == 200
            dataset_id = ds.json()["id"]

            imported = c.post(
                f"/api/v1/datasets/{dataset_id}/samples/import",
                json={
                    "items": [
                        {
                            "image_uris": ["memory://round/cat.jpg"],
                            "metadata": {"idx": 0},
                            "label": "cat",
                        },
                    ]
                },
            )
            source_sample_id = imported.json()["sample_ids"][0]

            r = c.post(
                f"/api/v1/plugins/export-parquet/export?dataset_id={dataset_id}",
            )
            assert r.status_code == 200
            body = r.json()
            assert body["rows"] == 1

            export_uri = body["uri"]

            resolve_r = c.get(f"/api/v1/images/resolve?uri={export_uri}")
            assert resolve_r.status_code in (200, 307, 308)

            if resolve_r.status_code == 200:
                content = resolve_r.content
                table = pq.read_table(io.BytesIO(content))
                assert table.num_rows == 1
                assert table.column("sample_id")[0].as_py() == source_sample_id
                assert "image" in table.column_names
                assert "label" in table.column_names
                assert json.loads(table.column("metadata")[0].as_py()) == {"idx": 0}

                deleted = c.delete(f"/api/v1/datasets/{dataset_id}")
                assert deleted.status_code == 204

                target = c.post(
                    "/api/v1/datasets",
                    json={
                        "name": "parquet-roundtrip-target",
                        "dataset_type": "image_classification",
                        "task_spec": {
                            "task_type": "classification",
                            "label_space": ["cat", "dog"],
                        },
                    },
                )
                target_id = target.json()["id"]
                restored = c.post(
                    f"/api/v1/plugins/import-parquet/import?dataset_id={target_id}",
                    files={
                        "file": (
                            "roundtrip.parquet",
                            io.BytesIO(content),
                            "application/octet-stream",
                        )
                    },
                )
                assert restored.status_code == 200
                assert restored.json()["sample_ids"] == [source_sample_id]
                restored_samples = c.get(f"/api/v1/datasets/{target_id}/samples")
                assert restored_samples.json()["items"][0]["metadata"] == {"idx": 0}
