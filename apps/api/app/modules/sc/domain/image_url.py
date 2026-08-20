from __future__ import annotations

from numbers import Integral
from urllib.parse import quote, urlencode


_PATCH_IMAGE_TYPES = {
    "patch_template": "template",
    "reference": "template",
    "template": "template",
    "patch_defective": "defective",
    "defective": "defective",
    "patch_difference": "difference",
    "difference": "difference",
}


def build_sc_image_url(
    *,
    inspection_time: object,
    wafer_key: object,
    defect_id: object,
    image_type: object,
    review_image_id: object | None = None,
) -> str:
    """Build the canonical browser route owned by the image-parser service."""

    inspection = str(inspection_time or "").strip()
    defect = str(defect_id or "").strip()
    wafer = _positive_integer(wafer_key, "wafer_key")
    normalized = str(image_type or "").strip().lower()
    if not inspection or wafer <= 0 or not defect:
        raise ValueError(
            "SC image URL requires inspection_time, positive wafer_key, and defect_id"
        )
    if normalized in {"review", "review_high_mag"}:
        review_id = _positive_integer(review_image_id, "review_image_id")
        image_path = "review"
        query = "?" + urlencode({"review_image_id": review_id})
    else:
        image_path = _PATCH_IMAGE_TYPES.get(normalized, "")
        if not image_path:
            raise ValueError(f"unsupported SC image type {image_type!r}")
        query = ""
    return (
        f"/api/v1/sc/images/{quote(inspection, safe='')}/{wafer}/"
        f"{quote(defect, safe='')}/{image_path}{query}"
    )


def _positive_integer(value: object, field: str) -> int:
    as_py = getattr(value, "as_py", None)
    if callable(as_py):
        value = as_py()
    if isinstance(value, bool):
        raise ValueError(f"SC image URL requires a positive {field}")
    if isinstance(value, Integral):
        parsed = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise ValueError(f"SC image URL requires a positive {field}")
    if parsed <= 0:
        raise ValueError(f"SC image URL requires a positive {field}")
    return parsed


__all__ = ["build_sc_image_url"]
