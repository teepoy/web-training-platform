from __future__ import annotations

import pytest

from app.modules.sc.domain.image_source import require_sc_image_source_format
from app.shared.api.schemas import Dataset, ImageSourceBinding


def test_historical_profile_binding_is_readable_but_not_inferred_or_backfilled() -> None:
    legacy = ImageSourceBinding.model_validate(
        {"contract": "sc.patch_archive.v1", "profile": "old-deployment-profile"}
    )
    dataset = Dataset(id="legacy-dataset", name="Legacy", image_source=legacy)

    assert legacy.format is None
    with pytest.raises(ValueError, match="not inferred or backfilled"):
        require_sc_image_source_format(dataset)
