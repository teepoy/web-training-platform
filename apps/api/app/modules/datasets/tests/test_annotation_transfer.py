from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.datasets.app.services.annotation_transfer import (
    export_annotations_jsonl,
    import_annotations_jsonl,
)
from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.shared.api.schemas import Dataset, TaskSpec


def _dataset() -> Dataset:
    return Dataset(
        id="dataset-1",
        name="portable",
        task_spec=TaskSpec(task_type="classification", label_space=["cat", "dog"]),
    )


def _header() -> bytes:
    return (
        b'{"format":"platform.annotations.jsonl","version":1,'
        b'"identity":"sample_id","mode":"replace_provided",'
        b'"dataset_contract":{"dataset_type":"image_classification",'
        b'"task_type":"classification","label_space":["cat","dog"]}}\n'
    )


@pytest.mark.asyncio
async def test_annotation_jsonl_round_trip_uses_platform_sample_ids() -> None:
    source = AsyncMock(spec=DatasetStorageAgg)
    source.list_samples.return_value = (
        [
            SimpleNamespace(sample_id="sample-1", latest_label="cat"),
            SimpleNamespace(sample_id="sample-2", latest_label=None),
        ],
        2,
    )
    chunks = [
        chunk
        async for chunk in export_annotations_jsonl(_dataset(), source, page_rows=10)
    ]
    lines = b"".join(chunks).splitlines()
    assert json.loads(lines[0])["identity"] == "sample_id"
    assert [json.loads(line) for line in lines[1:]] == [
        {"sample_id": "sample-1", "label": "cat"}
    ]

    target = AsyncMock(spec=DatasetStorageAgg)
    target.existing_sample_ids.return_value = {"sample-1"}
    target.replace_annotations_for_samples.return_value = 1
    result = await import_annotations_jsonl(
        _dataset(),
        target,
        io.BytesIO(b"".join(chunks)),
        actor_id="user-1",
        max_bytes=10_000,
        max_records=100,
        batch_rows=10,
    )

    assert result.imported == 1
    assert result.cleared == 0
    target.replace_annotations_for_samples.assert_awaited_once_with(
        [("sample-1", "cat")], created_by="user-1"
    )


@pytest.mark.asyncio
async def test_annotation_import_fails_before_writes_for_unknown_sample() -> None:
    storage = AsyncMock(spec=DatasetStorageAgg)
    storage.existing_sample_ids.return_value = set()
    payload = _header() + b'{"sample_id":"missing","label":"dog"}\n'

    with pytest.raises(ValueError, match="unknown sample IDs"):
        await import_annotations_jsonl(
            _dataset(),
            storage,
            io.BytesIO(payload),
            actor_id="user-1",
            max_bytes=10_000,
            max_records=100,
            batch_rows=10,
        )
    storage.replace_annotations_for_samples.assert_not_awaited()


@pytest.mark.asyncio
async def test_annotation_import_rejects_unknown_label() -> None:
    storage = AsyncMock(spec=DatasetStorageAgg)
    payload = _header() + b'{"sample_id":"sample-1","label":"horse"}\n'

    with pytest.raises(ValueError, match="label space"):
        await import_annotations_jsonl(
            _dataset(),
            storage,
            io.BytesIO(payload),
            actor_id="user-1",
            max_bytes=10_000,
            max_records=100,
            batch_rows=10,
        )


@pytest.mark.asyncio
async def test_annotation_import_rejects_mismatched_dataset_contract() -> None:
    storage = AsyncMock(spec=DatasetStorageAgg)
    payload = _header().replace(b'"cat","dog"', b'"cat"')

    with pytest.raises(ValueError, match="contract does not match"):
        await import_annotations_jsonl(
            _dataset(),
            storage,
            io.BytesIO(payload),
            actor_id="user-1",
            max_bytes=10_000,
            max_records=100,
            batch_rows=10,
        )
    storage.replace_annotations_for_samples.assert_not_awaited()


def test_annotation_http_export_import_round_trip() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/datasets",
            json={
                "name": "annotation-transfer-roundtrip",
                "dataset_type": "image_classification",
                "task_spec": {
                    "task_type": "classification",
                    "label_space": ["cat", "dog"],
                },
            },
        )
        assert created.status_code == 200
        dataset_id = created.json()["id"]
        sample = client.post(
            f"/api/v1/datasets/{dataset_id}/samples",
            json={"image_uris": []},
        )
        sample_id = sample.json()["id"]
        annotation = client.post(
            "/api/v1/annotations",
            json={
                "dataset_id": dataset_id,
                "sample_id": sample_id,
                "label": "cat",
                "created_by": "roundtrip-test",
            },
        )
        assert annotation.status_code == 200

        exported = client.get(f"/api/v1/datasets/{dataset_id}/annotations/export")
        assert exported.status_code == 200
        exported_lines = exported.content.splitlines()
        assert json.loads(exported_lines[1]) == {"sample_id": sample_id, "label": "cat"}

        clear_payload = exported_lines[0] + b"\n" + _jsonl_record(sample_id, None)
        cleared = client.post(
            f"/api/v1/datasets/{dataset_id}/annotations/import",
            files={"file": ("clear.jsonl", clear_payload, "application/x-ndjson")},
        )
        assert cleared.status_code == 200
        assert cleared.json()["cleared"] == 1

        restored = client.post(
            f"/api/v1/datasets/{dataset_id}/annotations/import",
            files={
                "file": (
                    "annotations.jsonl",
                    exported.content,
                    "application/x-ndjson",
                )
            },
        )
        assert restored.status_code == 200
        assert restored.json() == {"imported": 1, "cleared": 0}
        annotations = client.get(
            f"/api/v1/datasets/{dataset_id}/samples/{sample_id}/annotations"
        )
        assert annotations.status_code == 200
        assert annotations.json()[-1]["label"] == "cat"


def _jsonl_record(sample_id: str, label: str | None) -> bytes:
    return json.dumps({"sample_id": sample_id, "label": label}).encode() + b"\n"
