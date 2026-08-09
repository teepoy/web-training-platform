from __future__ import annotations

import base64
import binascii
import io
import json
from typing import Any

from PIL import Image

from app.modules.sc.schema import find_images_by_role

SC_TRAINING_IMAGE_ROLES = ("patch_template", "patch_defective")


def decode_data_image_uri(uri: str) -> bytes | None:
    """Decode an inline base64 image URI.

    ``None`` means the value is not a supported, valid data URI. Callers can
    then try an object-store or upstream resolver without conflating a bad
    inline payload with an absent one.
    """

    if not uri.startswith("data:image/") or ";base64," not in uri:
        return None
    _, encoded = uri.split(",", 1)
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None


def image_bytes_are_readable(value: object) -> bool:
    """Return whether *value* contains a complete image Pillow can decode."""

    return readable_image_bytes(value) is not None


def readable_image_bytes(value: object) -> bytes | None:
    """Return normalized bytes when *value* is a complete decodable image."""

    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    if not isinstance(value, bytes) or not value:
        return None
    try:
        with Image.open(io.BytesIO(value)) as image:
            image.verify()
    except (OSError, ValueError):
        return None
    return value


def normalize_sc_training_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize db-full and sparse SC rows to the runtime ``images`` contract."""

    normalized = dict(row)
    metadata = _mapping_value(row.get("metadata_json") or row.get("metadata"))

    normalized["sample_id"] = str(
        row.get("sample_id") or row.get("id") or metadata.get("sample_id") or ""
    )
    normalized["label"] = _label_value(row.get("label") or row.get("latest_label"))
    for key in (
        "inspection_time",
        "wafer_key",
        "defect_id",
        "wafer_x",
        "wafer_y",
        "die_x",
        "die_y",
        "rough_bin",
        "class_number",
        "test_id",
    ):
        if normalized.get(key) is None or normalized.get(key) == "":
            if key in metadata:
                normalized[key] = metadata[key]

    images: list[dict[str, Any]] = []
    raw_images = row.get("images")
    if isinstance(raw_images, list):
        images.extend(dict(image) for image in raw_images if isinstance(image, dict))

    shard_images = row.get("shard_images") or metadata.get("shard_images")
    if isinstance(shard_images, list):
        for image in shard_images:
            if not isinstance(image, dict):
                continue
            role = str(image.get("role") or "")
            if not role:
                continue
            _append_image(
                images,
                role=role,
                image_id=str(image.get("image_id") or ""),
                image_type=str(image.get("image_type") or ""),
                content_type=str(image.get("content_type") or ""),
                filename=str(image.get("filename") or ""),
                source_uri=str(image.get("source_uri") or image.get("image_id") or ""),
                embedded=image.get("bytes"),
            )

    for image in images:
        if image.get("bytes") is not None:
            continue
        for key in ("source_uri", "image_id"):
            candidate = image.get(key)
            if not isinstance(candidate, str):
                continue
            decoded = decode_data_image_uri(candidate)
            if decoded is not None:
                image["bytes"] = decoded
                break

    normalized["images"] = images
    return normalized


def row_has_readable_training_images(row: dict[str, Any]) -> bool:
    """Return whether both required SC image roles contain decodable bytes."""

    images = row.get("images")
    if not isinstance(images, list):
        return False
    for role in SC_TRAINING_IMAGE_ROLES:
        refs = find_images_by_role(images, role)
        if not refs or not image_bytes_are_readable(refs[0].get("bytes")):
            return False
    return True


def row_has_runtime_resolvable_training_images(row: dict[str, Any]) -> bool:
    """Return whether missing bytes have enough identity for runtime fetching."""

    inspection_time = str(row.get("inspection_time") or "")
    defect_id = str(row.get("defect_id") or "")
    wafer_key = row.get("wafer_key")
    if not inspection_time or not defect_id or wafer_key is None or wafer_key == "":
        return False

    images = row.get("images")
    if not isinstance(images, list):
        images = []
    for role in SC_TRAINING_IMAGE_ROLES:
        refs = find_images_by_role(images, role)
        if not refs:
            # The materializer requests the known patch image types using the
            # scalar SC identity, so v3 rows need no per-row image locator.
            continue
        ref = refs[0]
        raw_bytes = ref.get("bytes")
        if image_bytes_are_readable(raw_bytes):
            continue
        if raw_bytes is not None:
            return False
    return True


async def resolve_sc_training_image_bytes(
    row: dict[str, Any],
    artifact_storage: Any,
) -> dict[str, Any]:
    """Resolve inline and object-store image references on a normalized row."""

    normalized = normalize_sc_training_row(row)
    images = normalized["images"]
    for role in SC_TRAINING_IMAGE_ROLES:
        refs = find_images_by_role(images, role)
        if not refs:
            continue
        ref = refs[0]
        if image_bytes_are_readable(ref.get("bytes")):
            continue
        uri = str(ref.get("source_uri") or ref.get("image_id") or "")
        if not uri.startswith(("s3://", "memory://")):
            continue
        try:
            ref["bytes"] = await artifact_storage.get_bytes(uri)
        except (FileNotFoundError, KeyError):
            continue
    return normalized


def _append_image(
    images: list[dict[str, Any]],
    *,
    role: str,
    image_id: str,
    image_type: str,
    content_type: str,
    filename: str,
    source_uri: str,
    embedded: object = None,
) -> None:
    if find_images_by_role(images, role):
        return
    images.append(
        {
            "image_id": image_id,
            "image_type": image_type,
            "role": role,
            "content_type": content_type,
            "filename": filename,
            "bytes": embedded,
            "review_image_id": None,
            "source_uri": source_uri or None,
        }
    )


def _mapping_value(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("SC sample metadata must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("SC sample metadata must be a JSON object")
        return dict(parsed)
    return {}


def _label_value(value: object) -> str | None:
    if value is None:
        return None
    label = str(value).strip()
    return label or None
