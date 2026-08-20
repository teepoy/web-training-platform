from __future__ import annotations

import pytest

from app.modules.sc.domain.image_url import build_sc_image_url


class _ColumnarInteger:
    def __init__(self, value: int) -> None:
        self.value = value

    def as_py(self) -> int:
        return self.value


def test_build_sc_image_url_targets_image_parser_http_surface() -> None:
    assert build_sc_image_url(
        inspection_time="2026-08-21T10:11:12+08:00",
        wafer_key=7,
        defect_id="D/42",
        image_type="patch_defective",
    ) == (
        "/api/v1/sc/images/2026-08-21T10%3A11%3A12%2B08%3A00/7/"
        "D%2F42/defective"
    )
    assert build_sc_image_url(
        inspection_time="inspection",
        wafer_key=7,
        defect_id=42,
        image_type="review",
        review_image_id=9,
    ) == "/api/v1/sc/images/inspection/7/42/review?review_image_id=9"


def test_build_sc_image_url_accepts_integer_columnar_scalars() -> None:
    assert build_sc_image_url(
        inspection_time="inspection",
        wafer_key=_ColumnarInteger(7),
        defect_id=42,
        image_type="review",
        review_image_id=_ColumnarInteger(9),
    ) == "/api/v1/sc/images/inspection/7/42/review?review_image_id=9"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"inspection_time": "", "wafer_key": 1, "defect_id": 1, "image_type": "template"},
        {"inspection_time": "t", "wafer_key": 0, "defect_id": 1, "image_type": "template"},
        {"inspection_time": "t", "wafer_key": 1.5, "defect_id": 1, "image_type": "template"},
        {"inspection_time": "t", "wafer_key": 1, "defect_id": 1, "image_type": "review"},
        {"inspection_time": "t", "wafer_key": 1, "defect_id": 1, "image_type": "unknown"},
    ],
)
def test_build_sc_image_url_rejects_incomplete_or_unknown_identity(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        build_sc_image_url(**kwargs)
