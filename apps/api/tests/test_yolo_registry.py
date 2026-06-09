"""YOLO SC registry and API tests — T34.

Verifies that YOLO SC metadata IDs and executable IDs are aligned,
dependency-guard behavior is correct, and catalog entries are consistent.
"""

from __future__ import annotations

import pytest
from platform_runtime.contracts import TrainContext

from app.core.registry import get_predictor_by_id, get_trainer_by_id
from app.modules.types import catalog

import app.modules.training.flows._trainers.sc  # noqa: F401  @trainer(resnet50-sc-v1)
import app.modules.training.flows._trainers.yolo_sc  # noqa: F401  @trainer(yolo-sc-v1)
import app.modules.prediction.flows._predictors.sc  # noqa: F401  @predictor(resnet50-sc-v1)
import app.modules.prediction.flows._predictors.yolo_sc  # noqa: F401  @predictor(yolo-sc-v1)


# ═══════════════════════════════════════════════════════════════════════
# 1.  ID alignment — catalog metadata ↔ executable registrations
# ═══════════════════════════════════════════════════════════════════════


def test_yolo_trainer_metadata_id_matches() -> None:
    """Catalog metadata ID 'yolo-sc-v1' matches executable trainer ID."""
    meta = catalog.get_trainer_meta("yolo-sc-v1")
    assert meta["id"] == "yolo-sc-v1"
    assert meta["name"] == "YOLO SC Detection Trainer"
    assert meta["view_id"] == "patch_image_v1"


def test_yolo_predictor_metadata_id_matches() -> None:
    """Catalog metadata ID 'yolo-sc-v1' matches executable predictor ID."""
    meta = catalog.get_predictor_meta("yolo-sc-v1")
    assert meta["id"] == "yolo-sc-v1"
    assert meta["name"] == "YOLO SC Detection"
    assert meta["view_id"] == "patch_image_v1"


def test_yolo_trainer_id_in_catalog_listing() -> None:
    """yolo-sc-v1 is in the trainer catalog listing."""
    trainer_ids = catalog.list_trainer_ids()
    assert "yolo-sc-v1" in trainer_ids


def test_yolo_predictor_id_in_catalog_listing() -> None:
    """yolo-sc-v1 is in the predictor catalog listing."""
    predictor_ids = catalog.list_predictor_ids()
    assert "yolo-sc-v1" in predictor_ids


# ═══════════════════════════════════════════════════════════════════════
# 2.  Registry resolution — get_trainer_by_id / get_predictor_by_id
# ═══════════════════════════════════════════════════════════════════════


def test_get_trainer_by_id_yolo_resolves() -> None:
    """get_trainer_by_id('yolo-sc-v1') returns a Trainer with correct metadata."""
    trainer = get_trainer_by_id("yolo-sc-v1")
    assert trainer is not None, "yolo-sc-v1 trainer must resolve"
    assert trainer.trainer_id == "yolo-sc-v1"
    # Name matches catalog metadata ("YOLO SC Detection") or executable
    # registration ("YOLO SC Detection Trainer") depending on whether the
    # executable module was loaded by an earlier test.
    assert trainer.name in {"YOLO SC Detection", "YOLO SC Detection Trainer"}, (
        f"Unexpected trainer name: {trainer.name!r}"
    )
    assert trainer.view_id == "patch_image_v1"


def test_get_predictor_by_id_yolo_resolves() -> None:
    """get_predictor_by_id('yolo-sc-v1') returns a Predictor with correct metadata."""
    predictor = get_predictor_by_id("yolo-sc-v1")
    assert predictor is not None, "yolo-sc-v1 predictor must resolve"
    assert predictor.predictor_id == "yolo-sc-v1"
    assert predictor.name in {"YOLO SC Detection", "YOLO SC Detection Predictor"}, (
        f"Unexpected predictor name: {predictor.name!r}"
    )
    assert predictor.view_id == "patch_image_v1"


# ═══════════════════════════════════════════════════════════════════════
# 3.  Missing dependency behavior — trainer
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.skip(reason="Requires Prefect flow/task run context for get_run_logger()")
@pytest.mark.asyncio
async def test_yolo_trainer_raises_on_missing_lazyframe() -> None:
    """Calling the YOLO trainer without a lazyframe raises ValueError."""
    trainer = get_trainer_by_id("yolo-sc-v1")
    assert trainer is not None
    ctx = TrainContext(job_id="test-yolo-trainer")
    with pytest.raises(ValueError, match="lazyframe"):
        await trainer(
            ctx,
            artifact_storage="mock",  # bypass artifact_storage guard
            lazyframe=None,
        )


@pytest.mark.skip(reason="Requires Prefect flow/task run context for get_run_logger()")
@pytest.mark.asyncio
async def test_yolo_trainer_error_message_mentions_lazyframe() -> None:
    """The YOLO trainer error message tells users about lazyframe requirement."""
    trainer = get_trainer_by_id("yolo-sc-v1")
    assert trainer is not None
    ctx = TrainContext(job_id="test-yolo-msg")
    with pytest.raises(Exception) as exc_info:
        await trainer(
            ctx,
            artifact_storage="mock",  # bypass artifact_storage guard
            lazyframe=None,
        )
    msg = str(exc_info.value).lower()
    assert "lazyframe" in msg, (
        f"Expected error mentioning 'lazyframe', got: {exc_info.value!r}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 4.  Flow runtime predictor registry
# ═══════════════════════════════════════════════════════════════════════


def test_yolo_predictor_resolves_in_flow_registry() -> None:
    """yolo-sc-v1 is registered in the flow runtime predictor registry."""
    from app.modules.prediction.flows._predictors import (
        get_predictor as flow_get_predictor,
    )

    fn = flow_get_predictor("yolo-sc-v1")
    assert callable(fn), "yolo-sc-v1 must be a callable in flow registry"


def test_yolo_predictor_is_generator() -> None:
    """yolo-sc-v1 predictor is a generator function, not a class."""
    import inspect

    from app.modules.prediction.flows._predictors import (
        get_predictor as flow_get_predictor,
    )

    fn = flow_get_predictor("yolo-sc-v1")
    assert callable(fn), "yolo-sc-v1 must be callable"
    assert inspect.isgeneratorfunction(fn), (
        "yolo-sc-v1 must be a generator function"
    )


@pytest.mark.skip(reason="Requires Prefect flow/task run context for get_run_logger()")
def test_yolo_predictor_raises_on_missing_storage() -> None:
    """yolo-sc-v1 predictor raises ValueError when artifact_storage is None."""
    from platform_runtime.contracts import ModelRef, PredictContext, DatasetRef

    from app.modules.prediction.flows._predictors import (
        get_predictor as flow_get_predictor,
    )

    fn = flow_get_predictor("yolo-sc-v1")
    ctx = PredictContext(
        job_id="test-yolo-pred",
        dataset_ref=DatasetRef(dataset_id="d1"),
        model_ref=ModelRef(uri="test.pt"),
    )
    with pytest.raises(ValueError, match="artifact_storage"):
        gen = fn(artifact_storage=None, ctx=ctx, lazyframe=[], model_ref=ModelRef(uri="test.pt"))
        next(gen)
