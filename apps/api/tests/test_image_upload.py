from fastapi.testclient import TestClient

from app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_SPEC = {"task_type": "classification", "label_space": ["a"]}


def _create_dataset_and_sample(c: TestClient) -> tuple[str, str]:
    """Create a dataset and one sample, return (dataset_id, sample_id)."""
    ds = c.post("/api/v1/datasets", json={"name": "upload-test-ds", "task_spec": _TASK_SPEC})
    assert ds.status_code == 200
    dataset_id = ds.json()["id"]

    sample = c.post(f"/api/v1/datasets/{dataset_id}/samples", json={"image_uris": []})
    assert sample.status_code == 200
    sample_id = sample.json()["id"]
    return dataset_id, sample_id


# ---------------------------------------------------------------------------
# Test 1: Upload success
# ---------------------------------------------------------------------------


def test_upload_success() -> None:
    with TestClient(app) as c:
        _, sample_id = _create_dataset_and_sample(c)

        resp = c.post(
            f"/api/v1/samples/{sample_id}/upload",
            files={"file": ("test.jpg", b"\xff\xd8\xff" + b"fake-jpeg-data", "image/jpeg")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sample_id"] == sample_id
        assert body["index"] == 0
        assert isinstance(body["uri"], str)
        assert body["uri"]  # non-empty


# ---------------------------------------------------------------------------
# Test 2: Upload appends to existing (index increments, image_uris grows)
# ---------------------------------------------------------------------------


def test_upload_appends_to_existing() -> None:
    with TestClient(app) as c:
        dataset_id, sample_id = _create_dataset_and_sample(c)

        # First upload
        resp1 = c.post(
            f"/api/v1/samples/{sample_id}/upload",
            files={"file": ("img1.jpg", b"\xff\xd8\xff" + b"img1-data", "image/jpeg")},
        )
        assert resp1.status_code == 200
        assert resp1.json()["index"] == 0

        # Second upload
        resp2 = c.post(
            f"/api/v1/samples/{sample_id}/upload",
            files={"file": ("img2.jpg", b"\xff\xd8\xff" + b"img2-data", "image/jpeg")},
        )
        assert resp2.status_code == 200
        assert resp2.json()["index"] == 1

        # GET sample → image_uris should have 2 items
        sample_resp = c.get(f"/api/v1/samples/{sample_id}")
        assert sample_resp.status_code == 200
        assert len(sample_resp.json()["image_uris"]) == 2


# ---------------------------------------------------------------------------
# Test 3: Proxy resolves uploaded URI (roundtrip bytes match)
# ---------------------------------------------------------------------------


def test_proxy_resolves_uploaded_uri() -> None:
    with TestClient(app) as c:
        _, sample_id = _create_dataset_and_sample(c)

        image_bytes = b"\xff\xd8\xff" + b"roundtrip-payload"
        resp = c.post(
            f"/api/v1/samples/{sample_id}/upload",
            files={"file": ("rt.jpg", image_bytes, "image/jpeg")},
        )
        assert resp.status_code == 200
        uri = resp.json()["uri"]
        assert uri  # non-empty

        proxy_resp = c.get(f"/api/v1/images/resolve?uri={uri}")
        assert proxy_resp.status_code == 200
        assert proxy_resp.content == image_bytes


# ---------------------------------------------------------------------------
# Test 4: Proxy resolves data: URI
# ---------------------------------------------------------------------------


def test_proxy_resolves_data_uri() -> None:
    # "aGVsbG8=" decodes to b"hello" — valid base64, no padding issues
    data_uri = "data:image/png;base64,aGVsbG8="
    with TestClient(app) as c:
        resp = c.get(f"/api/v1/images/resolve?uri={data_uri}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/png")
        assert resp.content == b"hello"


# ---------------------------------------------------------------------------
# Test 5: Oversized upload → 413
# ---------------------------------------------------------------------------


def test_upload_oversized_file() -> None:
    with TestClient(app) as c:
        _, sample_id = _create_dataset_and_sample(c)

        big_data = b"x" * (10 * 1024 * 1024 + 1)
        resp = c.post(
            f"/api/v1/samples/{sample_id}/upload",
            files={"file": ("big.jpg", big_data, "image/jpeg")},
        )
        assert resp.status_code == 413


# ---------------------------------------------------------------------------
# Test 6: Upload to non-existent sample → 404
# ---------------------------------------------------------------------------


def test_upload_to_nonexistent_sample() -> None:
    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/samples/nonexistent-sample-id/upload",
            files={"file": ("img.jpg", b"\xff\xd8\xff" + b"data", "image/jpeg")},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 7: Proxy with unknown scheme → 400
# ---------------------------------------------------------------------------


def test_proxy_unknown_scheme() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/images/resolve?uri=ftp://example.com/foo")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test 8: Proxy with http scheme (rejected for security) → 400
# ---------------------------------------------------------------------------


def test_proxy_http_scheme_rejected() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/images/resolve?uri=http://example.com/img.jpg")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test 9: Proxy with missing memory key → 404
# ---------------------------------------------------------------------------


def test_proxy_missing_memory_key() -> None:
    with TestClient(app) as c:
        resp = c.get("/api/v1/images/resolve?uri=memory://does-not-exist")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 10: Upload non-image content-type → 400
# ---------------------------------------------------------------------------


def test_upload_non_image_content_type() -> None:
    with TestClient(app) as c:
        _, sample_id = _create_dataset_and_sample(c)

        resp = c.post(
            f"/api/v1/samples/{sample_id}/upload",
            files={"file": ("readme.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 400
