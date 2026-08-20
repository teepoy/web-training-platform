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


def test_api_images_do_not_embed_image_parser_binaries() -> None:
    for dockerfile in _API_DOCKERFILES:
        content = dockerfile.read_text(encoding="utf-8")

        assert "image-parser-batch" not in content
        assert "image-parser-local" not in content


def test_image_parser_runtime_is_static_and_healthchecks_use_runtime_tools() -> None:
    dockerfile = (_ROOT / "services/image-parser/Dockerfile").read_text(encoding="utf-8")
    dev_compose = (_ROOT / "infra/compose/docker-compose.dev.yaml").read_text(
        encoding="utf-8"
    )
    prod_compose = (
        _ROOT / "infra/compose/production/compose.platform.yaml"
    ).read_text(encoding="utf-8")

    assert "CGO_ENABLED=0" in dockerfile
    assert "libvips" not in dockerfile
    assert 'test: ["CMD", "wget"' in dev_compose
    assert 'test: ["CMD", "wget"' in prod_compose
