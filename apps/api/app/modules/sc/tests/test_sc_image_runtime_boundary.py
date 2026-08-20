from __future__ import annotations

from app.main import app


def test_upstream_sc_image_surfaces_are_not_fastapi_routes() -> None:
    """Preview image rendering belongs to image-parser, not the Python API."""

    paths = set(app.openapi()["paths"])

    assert not any(path.startswith("/api/v1/sc/images/") for path in paths)
    assert not any(path.startswith("/api/v1/sc/sprites/") for path in paths)
    assert not any(path.startswith("/api/v1/sc/sprite-atlases/") for path in paths)

    assert (
        "/api/v1/sc/datasets/{dataset_id}/samples/{sample_id}/images/{image_id}"
        not in paths
    )
