from __future__ import annotations

import pytest

from app.modules.runtime.catalog import runtime_catalog


def test_predictor_metadata_and_callable_share_one_registration() -> None:
    registration = runtime_catalog.get_predictor("yolo-sc-v1")
    assert registration.metadata.id == "yolo-sc-v1"
    assert registration.metadata.name == "YOLO SC Defect Prediction"
    assert registration.metadata.view_id == "patch_image_v1"
    assert callable(registration.callable)


def test_unknown_predictor_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown predictor capability"):
        runtime_catalog.get_predictor("missing")
