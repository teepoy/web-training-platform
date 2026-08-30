from __future__ import annotations

import io
import json
import struct
import zipfile

import pytest
from fastapi import HTTPException

from app.modules.models.app.services.model_service import ModelService


def _package_bytes(manifest: bytes, artifact: bytes = b"x") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as package:
        package.writestr("manifest.json", manifest)
        package.writestr("artifact", artifact)
    return output.getvalue()


def _valid_manifest(artifact: bytes = b"x") -> bytes:
    import hashlib

    return json.dumps(
        {
            "schema": "platform.model-package",
            "version": 1,
            "training_job_id": "job-id",
            "format": "pytorch",
            "artifact": {
                "filename": "model.pt",
                "size_bytes": len(artifact),
                "sha256": hashlib.sha256(artifact).hexdigest(),
            },
        }
    ).encode()


def test_model_package_rejects_non_utf8_manifest_as_bad_request(tmp_path) -> None:
    source = io.BytesIO(_package_bytes(b"\xff\xfe\xfa"))

    with pytest.raises(HTTPException) as exc_info:
        ModelService._extract_model_package(
            source,
            tmp_path / "artifact",
            max_bytes=1024,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid model package"


def test_model_package_rejects_unsupported_compression_as_bad_request(
    tmp_path,
) -> None:
    payload = bytearray(_package_bytes(_valid_manifest()))
    local_header = payload.index(b"PK\x03\x04", payload.index(b"artifact") - 64)
    central_header = payload.index(b"PK\x01\x02", local_header)
    struct.pack_into("<H", payload, local_header + 8, 99)
    struct.pack_into("<H", payload, central_header + 10, 99)

    with pytest.raises(HTTPException) as exc_info:
        ModelService._extract_model_package(
            io.BytesIO(payload),
            tmp_path / "artifact",
            max_bytes=1024,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid model package"


def test_model_package_rejects_non_hex_checksum_metadata(tmp_path) -> None:
    manifest = json.loads(_valid_manifest())
    manifest["artifact"]["sha256"] = "z" * 64

    with pytest.raises(HTTPException) as exc_info:
        ModelService._extract_model_package(
            io.BytesIO(_package_bytes(json.dumps(manifest).encode())),
            tmp_path / "artifact",
            max_bytes=1024,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Model package artifact metadata is invalid"


def test_model_package_rejects_validly_shaped_wrong_checksum(tmp_path) -> None:
    manifest = json.loads(_valid_manifest())
    manifest["artifact"]["sha256"] = "0" * 64

    with pytest.raises(HTTPException) as exc_info:
        ModelService._extract_model_package(
            io.BytesIO(_package_bytes(json.dumps(manifest).encode())),
            tmp_path / "artifact",
            max_bytes=1024,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == (
        "Model package artifact checksum does not match its manifest"
    )


def test_model_package_enforces_uncompressed_artifact_limit(tmp_path) -> None:
    artifact = b"too-large"

    with pytest.raises(HTTPException) as exc_info:
        ModelService._extract_model_package(
            io.BytesIO(_package_bytes(_valid_manifest(artifact), artifact)),
            tmp_path / "artifact",
            max_bytes=4,
        )

    assert exc_info.value.status_code == 413


def test_model_package_rejects_extra_archive_entries(tmp_path) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as package:
        package.writestr("manifest.json", _valid_manifest())
        package.writestr("artifact", b"x")
        package.writestr("unexpected", b"data")

    with pytest.raises(HTTPException) as exc_info:
        ModelService._extract_model_package(
            io.BytesIO(output.getvalue()),
            tmp_path / "artifact",
            max_bytes=1024,
        )

    assert exc_info.value.status_code == 400


def test_model_package_sanitizes_manifest_artifact_filename(tmp_path) -> None:
    manifest = json.loads(_valid_manifest())
    manifest["artifact"]["filename"] = "../../outside.pt"

    _, _, _, filename = ModelService._extract_model_package(
        io.BytesIO(_package_bytes(json.dumps(manifest).encode())),
        tmp_path / "artifact",
        max_bytes=1024,
    )

    assert filename == "outside.pt"


def test_model_package_accepts_entries_in_either_zip_order(tmp_path) -> None:
    artifact = b"x"
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as package:
        package.writestr("artifact", artifact)
        package.writestr("manifest.json", _valid_manifest(artifact))

    manifest, size, digest, filename = ModelService._extract_model_package(
        io.BytesIO(output.getvalue()),
        tmp_path / "artifact",
        max_bytes=1024,
    )

    assert manifest["schema"] == "platform.model-package"
    assert size == 1
    assert len(digest) == 64
    assert filename == "model.pt"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", True),
        ("artifact.size_bytes", True),
    ],
)
def test_model_package_rejects_boolean_numeric_fields(
    tmp_path,
    field: str,
    value: bool,
) -> None:
    manifest = json.loads(_valid_manifest())
    if field == "version":
        manifest["version"] = value
    else:
        manifest["artifact"]["size_bytes"] = value

    with pytest.raises(HTTPException) as exc_info:
        ModelService._extract_model_package(
            io.BytesIO(_package_bytes(json.dumps(manifest).encode())),
            tmp_path / "artifact",
            max_bytes=1024,
        )

    assert exc_info.value.status_code == 400
