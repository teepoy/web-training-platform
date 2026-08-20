from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.sc.domain.prediction_export import (
    ScKlarfVersion,
    ScPredictionExportFormat,
    ScPredictionExportResult,
)
from app.modules.sc.port.http import prediction_export_router
from app.modules.sc.port.http.deps import get_sc_prediction_export_service


class _SlowPredictionExport:
    def __init__(self) -> None:
        self.collection_kwargs: dict[str, object] = {}

    async def export(self, **_kwargs: object) -> ScPredictionExportResult:
        await asyncio.sleep(0.04)
        return ScPredictionExportResult(
            uri="memory://exports/dataset-1/predictions/export.parquet",
            format=ScPredictionExportFormat.PARQUET,
            row_count=123,
            sampled=False,
            filename="export.parquet",
            klarf_version=None,
        )

    async def export_collection(self, **kwargs: object) -> ScPredictionExportResult:
        self.collection_kwargs = kwargs
        return ScPredictionExportResult(
            uri="memory://exports/collections/collection-1/predictions/export.zip",
            format=ScPredictionExportFormat.KLARF,
            row_count=456,
            sampled=False,
            filename="collection_predictions_klarf.zip",
            klarf_version=ScKlarfVersion.V1_8,
        )


def test_prediction_export_sends_heartbeat_during_long_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prediction_export_router, "_EXPORT_HEARTBEAT_SECONDS", 0.005)
    app.dependency_overrides[get_sc_prediction_export_service] = (
        lambda: _SlowPredictionExport()
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/sc/datasets/dataset-1/prediction-exports/stream",
                json={"format": "parquet", "sampling": None},
            )
    finally:
        app.dependency_overrides.pop(get_sc_prediction_export_service, None)

    assert response.status_code == 200, response.text
    assert '"status":"processing"' in response.text
    assert "large files can take several minutes" in response.text
    assert '"event_type":"done"' in response.text


def test_collection_prediction_export_passes_selected_member_records() -> None:
    service = _SlowPredictionExport()
    app.dependency_overrides[get_sc_prediction_export_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/sc/dataset-collections/collection-1/prediction-exports/stream",
                json={
                    "format": "klarf",
                    "klarf_version": "1.8",
                    "include_images": True,
                    "sampling": None,
                    "member_ids": ["member-1", "member-2"],
                },
            )
    finally:
        app.dependency_overrides.pop(get_sc_prediction_export_service, None)

    assert response.status_code == 200, response.text
    assert '"rows":456' in response.text
    assert '"klarf_version":"1.8"' in response.text
    assert "collection_predictions_klarf.zip" in response.text
    assert service.collection_kwargs["klarf_version"] is ScKlarfVersion.V1_8
    assert service.collection_kwargs["include_images"] is True


def test_parquet_export_rejects_klarf_version() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sc/datasets/dataset-1/prediction-exports/stream",
            json={
                "format": "parquet",
                "klarf_version": "1.8",
                "sampling": None,
            },
        )

    assert response.status_code == 422
    assert "klarf_version is available only" in response.text


def test_parquet_export_rejects_defect_images() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sc/datasets/dataset-1/prediction-exports/stream",
            json={
                "format": "parquet",
                "include_images": True,
                "sampling": None,
            },
        )

    assert response.status_code == 422
    assert "include_images is available only" in response.text
