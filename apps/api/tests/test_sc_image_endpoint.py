from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.sc.port.http.router import (
    VALID_IMAGE_TYPES,
    _normalize_inspection_time,
)

# Match mock data generation in MockScDataStore._build_inspections:
#   base_time = datetime.now(timezone.utc) - timedelta(days=1)
#   base_time = base_time.replace(hour=8, minute=0, second=0, microsecond=0)
_YESTERDAY_08_UTC = (
    datetime.now(timezone.utc) - timedelta(days=1)
).replace(hour=8, minute=0, second=0, microsecond=0)

ISO_TIME = _YESTERDAY_08_UTC.strftime("%Y-%m-%dT%H:%M:%S+00:00")
EPOCH_SEC = str(int(_YESTERDAY_08_UTC.timestamp()))
EPOCH_MS = str(int(_YESTERDAY_08_UTC.timestamp() * 1000))
VALID_WAFER = 1
VALID_DEFECT = "1"
API_PREFIX = "/api/v1"


class TestNormalizeInspectionTime:
    """Unit tests for _normalize_inspection_time."""

    def test_iso_with_timezone(self) -> None:
        result = _normalize_inspection_time("2026-01-15T08:00:00+00:00")
        assert result == datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)

    def test_iso_with_z_suffix(self) -> None:
        result = _normalize_inspection_time("2026-01-15T08:00:00Z")
        assert result == datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)

    def test_iso_without_timezone(self) -> None:
        result = _normalize_inspection_time("2026-01-15T08:00:00")
        assert result == datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)

    def test_iso_date_only(self) -> None:
        result = _normalize_inspection_time("2026-01-15")
        assert result == datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

    def test_epoch_seconds(self) -> None:
        result = _normalize_inspection_time(EPOCH_SEC)
        assert result == _YESTERDAY_08_UTC

    def test_epoch_milliseconds(self) -> None:
        result = _normalize_inspection_time(EPOCH_MS)
        assert result == _YESTERDAY_08_UTC

    def test_epoch_negative(self) -> None:
        result = _normalize_inspection_time("-1")
        assert result == datetime(1969, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    def test_invalid_raises_http_400(self) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _normalize_inspection_time("not-a-valid-time")
        assert exc.value.status_code == 400


class TestScImageEndpoint:
    """Integration tests for the SC image serving endpoint."""

    def test_difference_image_type_returns_200(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/difference"
            )
            resp = client.get(url)
            assert resp.status_code == 200, resp.text
            assert resp.headers["content-type"] == "image/png"
            assert len(resp.content) > 0

    def test_unsupported_image_type_returns_400(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/bogus_type"
            )
            resp = client.get(url)
            assert resp.status_code == 400, resp.text
            detail = resp.json()["detail"]
            assert "bogus_type" in detail
            assert "Invalid image_type" in detail

    def test_template_image_type_returns_200(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/template"
            )
            resp = client.get(url)
            assert resp.status_code == 200, resp.text
            assert resp.headers["content-type"] == "image/png"

    def test_defective_image_type_returns_200(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/defective"
            )
            resp = client.get(url)
            assert resp.status_code == 200, resp.text
            assert resp.headers["content-type"] == "image/png"

    def test_epoch_seconds_inspection_time(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{EPOCH_SEC}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/template"
            )
            resp = client.get(url)
            assert resp.status_code == 200, resp.text

    def test_epoch_milliseconds_inspection_time(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{EPOCH_MS}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/template"
            )
            resp = client.get(url)
            assert resp.status_code == 200, resp.text

    def test_invalid_inspection_time_returns_400(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/not-a-time/"
                f"{VALID_WAFER}/{VALID_DEFECT}/template"
            )
            resp = client.get(url)
            assert resp.status_code == 400, resp.text

    def test_nonexistent_defect_returns_404(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/99999999/template"
            )
            resp = client.get(url)
            assert resp.status_code == 404, resp.text

    def test_review_image_type_with_id_returns_200(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/review"
            )
            resp = client.get(url, params={"review_image_id": 1})
            assert resp.status_code == 200, resp.text
            assert resp.headers["content-type"] == "image/png"
            assert len(resp.content) > 0

    def test_review_image_type_missing_id_returns_400(self) -> None:
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/review"
            )
            resp = client.get(url)
            assert resp.status_code == 400, resp.text
            assert "review_image_id" in resp.json()["detail"]

    def test_review_high_mag_image_type_returns_200(self) -> None:
        """REVIEW_HIGH_MAG alias returns 200 without review_image_id."""
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/REVIEW_HIGH_MAG"
            )
            resp = client.get(url)
            assert resp.status_code == 200, resp.text
            assert resp.headers["content-type"] == "image/png"
            assert len(resp.content) > 0

    def test_patch_template_image_type_returns_200(self) -> None:
        """PATCH_TEMPLATE alias returns 200."""
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/PATCH_TEMPLATE"
            )
            resp = client.get(url)
            assert resp.status_code == 200, resp.text
            assert resp.headers["content-type"] == "image/png"
            assert len(resp.content) > 0

    def test_patch_defective_image_type_returns_200(self) -> None:
        """PATCH_DEFECTIVE alias returns 200."""
        with TestClient(app) as client:
            url = (
                f"{API_PREFIX}/sc/images/{ISO_TIME}/"
                f"{VALID_WAFER}/{VALID_DEFECT}/PATCH_DEFECTIVE"
            )
            resp = client.get(url)
            assert resp.status_code == 200, resp.text
            assert resp.headers["content-type"] == "image/png"
            assert len(resp.content) > 0


class TestValidImageTypes:
    """Verify VALID_IMAGE_TYPES includes all expected entries."""

    def test_difference_is_valid(self) -> None:
        assert "difference" in VALID_IMAGE_TYPES

    def test_all_baseline_types_present(self) -> None:
        assert "template" in VALID_IMAGE_TYPES
        assert "defective" in VALID_IMAGE_TYPES
        assert "review" in VALID_IMAGE_TYPES
        assert "PATCH_TEMPLATE" in VALID_IMAGE_TYPES
        assert "PATCH_DEFECTIVE" in VALID_IMAGE_TYPES
        assert "REVIEW_HIGH_MAG" in VALID_IMAGE_TYPES
