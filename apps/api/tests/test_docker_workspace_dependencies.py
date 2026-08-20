from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[3]
_API_DOCKERFILES = (
    _ROOT / "apps/api/Dockerfile",
    _ROOT / "apps/api/Dockerfile.prefect-worker-cpu",
    _ROOT / "apps/api/Dockerfile.prefect-worker-gpu",
)


def test_api_images_copy_klarf_workspace_metadata_and_source() -> None:
    for dockerfile in _API_DOCKERFILES:
        content = dockerfile.read_text(encoding="utf-8")

        assert "COPY libs/klarf/pyproject.toml libs/klarf/pyproject.toml" in content
        assert "COPY libs/klarf/ libs/klarf/" in content


def test_api_image_contains_configured_batch_image_resolver() -> None:
    content = (_ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")

    assert "FROM golang:" in content
    assert "go build" in content
    assert "/usr/local/bin/image-parser-batch" in content
