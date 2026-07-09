from __future__ import annotations

from datetime import datetime

from app.modules.sc.app.services.import_rows import iter_patch_samples_from_upstream_chunk


def test_upstream_row_carries_test_id_into_patch_sample() -> None:
    [sample] = list(
        iter_patch_samples_from_upstream_chunk(
            {
                "defect_id": 42,
                "inspection_time": datetime(2026, 1, 1),
                "wafer_key": 7,
                "lot_id": "LOT-1",
                "wafer_x": 10,
                "wafer_y": 20,
                "die_x": 1,
                "die_y": 2,
                "rough_bin": 3,
                "class_number": 4,
                "test_id": 9,
            }
        )
    )

    assert sample.test_id == 9
