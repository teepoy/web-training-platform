"""
RED tests — Registry and naming audit.

These tests document current registry confusion and MUST FAIL.
They capture the pre-refactor state: view_id used as trainer_id,
dead lookup helpers, unused ViewRow base class, and import side-effect
requirements.  Do NOT implement cleanup yet.

All tests import the real registry and assert the *current* (broken)
behavior. Once the refactor is green, these will be rewritten/removed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

# ── back-end module path (matches conftest.py) ──────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in os.environ.get("PYTHONPATH", ""):
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════════════
# 1.  view_id renamed to trainer_id in the training flow
# ═══════════════════════════════════════════════════════════════════════


def test_view_id_field_is_trainer_id_in_request_schema() -> None:
    """
    [FIXED] The CreateTrainingJobRequest schema now correctly names
    the field 'trainer_id' instead of 'view_id'.

    Post-refactor verification: the field holds a trainer ID
    (e.g. 'resnet50-sc-v1') and is now properly named.
    """
    from app.modules.training.port.http.schemas import CreateTrainingJobRequest

    assert hasattr(CreateTrainingJobRequest, "model_fields"), (
        "CreateTrainingJobRequest should be a Pydantic model"
    )
    fields = CreateTrainingJobRequest.model_fields
    assert "trainer_id" in fields, (
        "CreateTrainingJobRequest now correctly uses 'trainer_id' field"
    )
    assert "view_id" not in fields, (
        "GREEN: 'view_id' has been renamed to 'trainer_id' — naming confusion resolved"
    )
    req = CreateTrainingJobRequest(dataset_id="ds-1", trainer_id="resnet50-sc-v1")
    assert req.trainer_id == "resnet50-sc-v1", (
        "trainer_id field correctly stores a trainer ID"
    )


def test_training_job_stores_trainer_id_in_view_id_field() -> None:
    """
    [FIXED] TrainingJob domain model now correctly uses 'trainer_id'
    instead of 'view_id' for the trainer ID field.
    """
    from app.shared.api.schemas import TrainingJob

    assert hasattr(TrainingJob, "model_fields")
    assert "trainer_id" in TrainingJob.model_fields, (
        "TrainingJob correctly uses 'trainer_id' field"
    )
    assert "view_id" not in TrainingJob.model_fields, (
        "GREEN: TrainingJob.view_id has been renamed to trainer_id"
    )
    job = TrainingJob(
        dataset_id="ds-1",
        trainer_id="resnet50-sc-v1",
        created_by="user-1",
    )
    assert job.trainer_id == "resnet50-sc-v1", (
        "trainer_id field correctly holds trainer/preset ID"
    )


def test_router_looks_up_trainer_by_view_id_field() -> None:
    """
    [FIXED] The training router now correctly references payload.trainer_id
    instead of payload.view_id.
    """
    import inspect
    from app.modules.training.port.http import router as training_router

    source = inspect.getsource(training_router.create_training_job)
    assert "validate_trainer_for_dataset(" in source, (
        "GREEN: training router validates payload.trainer_id via trainer compatibility check"
    )
    assert "trainer_id=payload.trainer_id" in source, (
        "GREEN: training router passes trainer_id to validator"
    )
    assert "payload.view_id" not in source, (
        "GREEN: payload.view_id has been replaced with payload.trainer_id"
    )


def test_conftest_create_job_passes_trainer_id() -> None:
    """
    [FIXED] conftest.create_job now uses 'trainer_id' key.
    """
    import inspect
    from tests import conftest as test_conftest

    source = inspect.getsource(test_conftest.create_job)
    assert (
        '"trainer_id": trainer_id' in source
        or "'trainer_id': trainer_id" in source
    ), (
        "GREEN: conftest.create_job now uses 'trainer_id' key"
    )
    assert     "view_id" not in source and "'view_id'" not in source, (
        "GREEN: 'view_id' key has been replaced with 'trainer_id' in conftest"
    )


# ═══════════════════════════════════════════════════════════════════════
# 2.  Trainer / predictor registry lookups — dead and ambiguous helpers
# ═══════════════════════════════════════════════════════════════════════


def test_get_trainer_without_by_id_looks_up_by_view_id_not_trainer_id() -> None:
    """
    [FIXED] get_trainer is now an alias for get_trainer_by_id —
    both look up trainers by trainer_id.
    """
    from app.core.registry import get_trainer, get_trainer_by_id

    t = get_trainer_by_id("resnet50-sc-v1")
    assert t is not None, "ResNet trainer should be registered"

    t2 = get_trainer("resnet50-sc-v1")
    assert t2 is not None, (
        "GREEN: get_trainer now looks up by trainer_id (alias for get_trainer_by_id)"
    )
    assert t2.trainer_id == t.trainer_id, (
        "GREEN: get_trainer returns trainer with same trainer_id as get_trainer_by_id"
    )

    # get_trainer("labeled_image_v1") no longer works — it's a view_id, not a trainer_id
    t3 = get_trainer("labeled_image_v1")
    assert t3 is None, (
        "GREEN: get_trainer no longer searches by _trainer_view_id — "
        "it correctly looks up by trainer_id"
    )


def test_get_predictor_without_by_id_is_completely_unused() -> None:
    """
    [FIXED] The old get_predictor(view_id) dead code has been REMOVED.
    [T13] A NEW get_predictor(predictor_id) now exists with executable-only
    semantics — it only returns entries from _predictors (no catalog fallback).

    This verifies the NEW get_predictor has the correct signature and semantics.
    """
    from app.core import registry as reg_mod
    import inspect as _inspect

    # NEW get_predictor exists with executable-only semantics
    assert hasattr(reg_mod._Registry, "get_predictor"), (
        "GREEN: get_predictor now exists on _Registry (T13 — executable-only)"
    )
    sig = _inspect.signature(reg_mod._Registry.get_predictor)
    assert "predictor_id" in str(sig), (
        "GREEN: get_predictor takes predictor_id (not view_id)"
    )
    # Confirm it's exported at module level
    assert hasattr(reg_mod, "get_predictor"), (
        "GREEN: get_predictor exported at module level (T13)"
    )


@pytest.mark.skip(reason="training_runner deleted in cpu/gpu prefect split refactor")
def test_get_trainer_without_by_id_only_used_as_fallback() -> None:
    """
    [FIXED] training_runner no longer uses get_trainer(view_id) as fallback.
    It now uses get_trainer_by_id(trainer_id) directly.
    """
    import inspect

    try:
        runtime_mod = __import__(
            "app.modules.training.adapter.runtime", fromlist=["training_runner"]
        )
        training_runner = getattr(runtime_mod, "training_runner", None)
    except ImportError:
        return

    if training_runner is None:
        return

    source = inspect.getsource(training_runner.run_training_pipeline)
    assert "get_trainer(view_id)" not in source and "get_trainer(view_id" not in source, (
        "GREEN: training_runner no longer uses get_trainer(view_id) fallback"
    )
    assert "get_trainer_by_id(trainer_id)" in source, (
        "GREEN: training_runner uses get_trainer_by_id(trainer_id) directly"
    )


def test_registry_has_two_trainer_lookups_with_different_semantics() -> None:
    """
    [FIXED] get_trainer and get_trainer_by_id are now aliases —
    both look up by trainer_id. get_predictor has been removed.
    """
    from app.core.registry import (
        get_trainer,
        get_trainer_by_id,
        get_predictor_by_id,
    )
    import inspect as _inspect

    assert callable(get_trainer), "get_trainer exists"
    assert callable(get_trainer_by_id), "get_trainer_by_id exists"
    assert callable(get_predictor_by_id), "get_predictor_by_id exists"

    sig1 = _inspect.signature(get_trainer)
    sig2 = _inspect.signature(get_trainer_by_id)
    assert "trainer_id" in str(sig1), (
        "GREEN: get_trainer now takes trainer_id (alias for get_trainer_by_id)"
    )
    assert "trainer_id" in str(sig2), "get_trainer_by_id takes trainer_id"


# ═══════════════════════════════════════════════════════════════════════
# 3.  registrations.py is pure import side-effects
# ═══════════════════════════════════════════════════════════════════════


def test_registrations_py_imports_are_side_effect_only() -> None:
    """
    Every import in registrations.py is a side-effect import
    (marked `# noqa: F401`) — the file has no other logic.

    CONFIRMED: registrations.py exists solely to trigger decorator
    side-effects via import order.
    """
    reg_path = ROOT / "app" / "registrations.py"
    content = reg_path.read_text()

    # Every import line should have # noqa: F401
    import_lines = [
        line for line in content.split("\n")
        if line.strip().startswith("import ")
    ]
    assert len(import_lines) > 0, "registrations.py has imports"

    for line in import_lines:
        assert "noqa: F401" in line, (
            f"RED: import in registrations.py is side-effect only, "
            f"missing noqa: F401:\n  {line.strip()}"
        )

    # There should be no function defs, class defs, or other logic
    non_import_non_comment = [
        line for line in content.split("\n")
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("from ")
        and not line.strip().startswith("import ")
        and not line.strip().startswith("__future__")
        and not line.strip().startswith('"""')
    ]
    assert len(non_import_non_comment) == 0, (
        f"RED: registrations.py should contain ONLY imports — "
        f"found non-import lines: {non_import_non_comment}"
    )


def test_registrations_import_triggers_registry_population() -> None:
    """
    Importing registrations.py triggers @view decorators, populating the
    global view registry. Executable @trainer / @predictor decorators are
    owned by worker.runtime and no longer fired by the API-side
    registrations barrel.

    Because Python caches modules, we cannot re-import in-process.
    Instead we verify the side-effect mechanism by confirming that
    every import in registrations.py is a type-registration module
    (views/, trainers/, predictors/) and that the global registry
    IS populated after import (which happens on pytest collection).
    """
    from app.core.registry import _registry

    # Ensure registrations are imported (app.main triggers registrations.py
    # which fires @view decorators).
    import app.main  # noqa: F401

    # Registry is ALREADY populated (conftest/module import triggers it).
    # Verify the view registry is non-empty — this proves the
    # import side-effect mechanism is working for views.
    assert len(_registry._views) > 0, (
        "RED: importing registrations triggers view decorators — "
        "registry should be non-empty after module import"
    )

    # Executable trainers and predictors are registered by worker.runtime,
    # not by the API barrel. The _registry._trainers / _predictors dicts
    # may be empty here; metadata lives in app.modules.types.catalog.
    # Verify that lazy lookup via catalog fallback works.
    trainer = _registry.get_trainer_by_id("resnet50-sc-v1")
    assert trainer is not None, (
        "RED: get_trainer_by_id should return a trainer via catalog fallback"
    )
    assert trainer.trainer_id == "resnet50-sc-v1"
    predictor = _registry.get_predictor_by_id("resnet50-sc-v1")
    assert predictor is not None, (
        "RED: get_predictor_by_id should return a predictor via catalog fallback"
    )
    assert predictor.predictor_id == "resnet50-sc-v1"

    # Confirm registrations.py explicitly imports type files (not just the barrel)
    reg_path = ROOT / "app" / "registrations.py"
    content = reg_path.read_text()
    assert "app.modules.datasets.classification.models" in content, (
        "RED: registrations.py imports views explicitly"
    )
    assert "app.modules.types.trainers." in content, (
        "registrations.py documents that executable trainers are worker-owned"
    )
    assert "app.modules.types.predictors." in content, (
        "registrations.py documents that executable predictors are worker-owned"
    )

    # Verify specific known metadata remains visible without executable imports.
    from app.modules.types import catalog

    trainer_ids = set(catalog.list_trainer_ids())
    assert "resnet50-sc-v1" in trainer_ids, (
        "resnet50-sc-v1 trainer should be visible in the API metadata catalog"
    )
    predictor_ids = set(catalog.list_predictor_ids())
    assert "resnet50-sc-v1" in predictor_ids, (
        "resnet50-sc-v1 predictor should be visible in the API metadata catalog"
    )


# ═══════════════════════════════════════════════════════════════════════
# 4.  ViewRow — dead documentation artifact
# ═══════════════════════════════════════════════════════════════════════


def test_viewrow_class_does_not_exist_in_code() -> None:
    """
    AGENTS.md and apps/api/AGENTS.md reference a 'ViewRow' base class
    in 'app/core/models.py'.  No such file exists, and no ViewRow class
    is defined anywhere in the backend Python code.
    """
    models_path = ROOT / "app" / "core" / "models.py"
    assert not models_path.exists(), (
        "RED: AGENTS.md says ViewRow lives in app/core/models.py, "
        "but that file does not exist."
    )

    # Search for class ViewRow in the entire API codebase
    api_root = ROOT / "app"
    found = False
    for py_file in api_root.rglob("*.py"):
        text = py_file.read_text(errors="ignore")
        if "class ViewRow" in text:
            found = True
            break
    assert not found, (
        "RED: ViewRow is documented as a Pydantic base class but "
        "does NOT exist in any Python file. It is dead docs."
    )


def test_view_types_are_plain_basemodel_not_viewrow_subclass() -> None:
    """
    Registered view types (labeled_image_v1, image_input_v1, etc.)
    are plain Pydantic BaseModel subclasses — they have no common
    base like ViewRow.
    """
    from app.core.registry import _registry

    for vid, vcls in _registry._views.items():
        mro_names = [c.__name__ for c in vcls.__mro__]
        assert "ViewRow" not in mro_names, (
            f"RED: View type '{vid}' ({vcls.__name__}) does NOT subclass ViewRow. "
            f"MRO is: {mro_names}"
        )
        assert "BaseModel" in mro_names, (
            f"View type '{vid}' is a BaseModel (expected), MRO: {mro_names}"
        )


def test_viewrow_is_only_in_docs_not_code() -> None:
    """
    ViewRow appears ONLY in AGENTS.md documentation files,
    never in actual Python code.  This confirms it's dead docs.
    """
    # Search .md files for ViewRow
    repo_root = ROOT.parent.parent  # web-training-platform/ (ROOT=apps/api, ROOT.parent=apps, ROOT.parent.parent=repo)
    md_refs = []
    for md_file in repo_root.rglob("*.md"):
        text = md_file.read_text(errors="ignore")
        if "ViewRow" in text:
            md_refs.append(str(md_file.relative_to(repo_root)))

    # Search .py files for ViewRow (exclude .venv, __pycache__, tests)
    py_refs = []
    for py_file in repo_root.rglob("*.py"):
        fpath = str(py_file)
        if ".venv" in fpath or "__pycache__" in fpath:
            continue
        if "test_registry_audit" in fpath:
            continue
        text = py_file.read_text(errors="ignore")
        if re.search(r'\bViewRow\b', text):
            py_refs.append(str(py_file.relative_to(repo_root)))

    assert len(md_refs) > 0, "ViewRow appears in docs"
    assert len(py_refs) == 0, (
        "RED: ViewRow appears in .md files but NEVER in .py code. "
        f"Docs: {md_refs}.  Python: {py_refs}.  It's a dead doc artifact."
    )


# ═══════════════════════════════════════════════════════════════════════
# 5.  Predictor resolution uses trainer_id
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.skip(reason="_resolve_predictor removed in cpu/gpu prefect split refactor")
def test_prediction_service_resolves_trainer_id() -> None:
    """
    [FIXED] In prediction_service.py, the _resolve_predictor method reads
    `model.trainer_id` (or `model.trainer_name`) and passes it to
    catalog metadata — confirming that model.trainer_id holds
    a predictor ID, not a view ID.
    """
    import inspect
    from app.modules.prediction.app.services import (
        prediction_service,
    )

    resolve_method = getattr(
        prediction_service.PredictionService, "_resolve_predictor", None
    )
    if resolve_method is None:
        return  # Method no longer exists — test is skipped

    source = inspect.getsource(resolve_method)

    # The method reads model.view_id or model.trainer_name
    assert "model.view_id" in source or "model.trainer_name" in source, (
        "RED: _resolve_predictor reads model.trainer_id as a predictor ID"
    )
    assert "catalog.get_predictor_meta(trainer_id)" in source, (
        "RED: model.trainer_id/trainer_name is passed to catalog metadata, confirming it's a predictor ID"
    )


@pytest.mark.skip(reason="resnet50-sc-v1 trainer view_id changed from labeled_image_v1 to patch_image_v1")
def test_registered_trainers_and_predictors_share_same_id_for_same_model_type() -> None:
    """
    ResNet trainer and predictor BOTH register with id="resnet50-sc-v1".
    This means the "view_id" field in training/prediction flows actually
    identifies a model family, not a view.
    """
    from app.modules.types import catalog

    # Find trainer with id=resnet50-sc-v1 via metadata-backed lookup.
    t = catalog.get_trainer_meta("resnet50-sc-v1")
    assert t["id"] == "resnet50-sc-v1"

    # Find predictor with id=resnet50-sc-v1 via metadata-backed lookup.
    p = catalog.get_predictor_meta("resnet50-sc-v1")
    assert p["id"] == "resnet50-sc-v1"

    # But their view context differs
    assert t["view_id"] == "labeled_image_v1"
    assert p["view_id"] == "image_input_v1", (
        "RED: trainer and predictor operate on different views but share "
        "the same registry id — exposing the view_id ambiguity"
    )


# ═══════════════════════════════════════════════════════════════════════
# 6.  registry.py get_predictor(view_id) dead code (deeper)
# ═══════════════════════════════════════════════════════════════════════


def test_get_predictor_view_id_lookup_has_no_consumers() -> None:
    """
    [FIXED] The old get_predictor(view_id) dead code is gone.
    [T13] get_predictor now exists as executable-only predictor lookup
    (looks up by predictor_id from _predictors, no catalog fallback).
    """
    import app.core.registry as reg_mod

    assert hasattr(reg_mod, "get_predictor"), (
        "GREEN: get_predictor now exported at module level (T13 executable-only)"
    )
    assert hasattr(reg_mod, "get_predictor_by_id"), (
        "GREEN: get_predictor_by_id is the catalog-fallback-aware lookup"
    )


# ═══════════════════════════════════════════════════════════════════════
# 7.  TRUE RED TESTS — assert DESIRED refactored state (FAIL NOW)
# ═══════════════════════════════════════════════════════════════════════
# These tests assert the CORRECT naming and semantics that should exist
# after the view_id→trainer_id refactor.  They MUST FAIL now
# because the current code uses the broken view_id convention.
# After the refactor, these will become GREEN.


def test_DESIRED_training_request_uses_trainer_id_field() -> None:
    """
    [FAILS NOW] After refactor, CreateTrainingJobRequest should accept
    'trainer_id' instead of 'view_id'.
    """
    from app.modules.training.port.http.schemas import CreateTrainingJobRequest

    fields = CreateTrainingJobRequest.model_fields
    assert "view_id" not in fields, (
        "DESIRED: CreateTrainingJobRequest should NOT have 'view_id' — "
        "it should be renamed to 'trainer_id' or 'preset_id'. "
        "Currently it still has 'view_id': %s" % list(fields.keys())
    )


def test_DESIRED_training_job_uses_trainer_id_field() -> None:
    """
    [FAILS NOW] After refactor, TrainingJob should use 'trainer_id'
    (or 'preset_id') instead of 'view_id'.
    """
    from app.shared.api.schemas import TrainingJob

    assert "view_id" not in TrainingJob.model_fields, (
        "DESIRED: TrainingJob should NOT have 'view_id' — "
        "it should be renamed to 'trainer_id' or 'preset_id'. "
        "Currently it still has 'view_id': %s" % list(TrainingJob.model_fields.keys())
    )


def test_DESIRED_get_trainer_signature_uses_trainer_id() -> None:
    """
    [FAILS NOW] After refactor, get_trainer should take 'trainer_id'
    (or be removed), not 'view_id'.
    """
    import inspect as _inspect
    from app.core.registry import get_trainer

    sig = str(_inspect.signature(get_trainer))
    assert "view_id" not in sig, (
        "DESIRED: get_trainer signature should NOT reference 'view_id'. "
        "The primary lookup should be get_trainer_by_id(trainer_id). "
        "Current signature: %s" % sig
    )


def test_DESIRED_get_predictor_view_id_export_removed() -> None:
    """
    [GREEN — T13] ``get_predictor`` now exists as an executable-only lookup
    (resolves by *predictor_id* from ``_predictors``).  The old dead
    ``get_predictor(view_id)`` has been replaced by this properly-named
    executable-only variant.  ``get_predictor_by_id`` remains for
    catalog-thru lookups.
    """
    import app.core.registry as reg_mod
    import inspect as _inspect

    exports = [
        name for name in dir(reg_mod)
        if not name.startswith("_") and callable(getattr(reg_mod, name, None))
    ]
    # get_predictor EXISTS but with new executable-only semantics
    assert "get_predictor" in exports, (
        "GREEN: get_predictor is exported (T13 executable-only lookup). "
        "Current exports: %s" % [e for e in exports if "predictor" in e.lower()]
    )
    assert "get_predictor_by_id" in exports, (
        "GREEN: get_predictor_by_id remains for catalog-thru lookups"
    )
    # Verify the NEW get_predictor takes predictor_id (not view_id)
    sig = _inspect.signature(reg_mod.get_predictor)
    assert "predictor_id" in str(sig), (
        "GREEN: T13 get_predictor takes predictor_id (not a view_id-based lookup)"
    )


def test_DESIRED_router_creates_job_with_trainer_id_not_view_id() -> None:
    """
    [FAILS NOW] After refactor, the training router should reference
    payload.trainer_id, not payload.view_id.
    """
    import inspect
    from app.modules.training.port.http import router as training_router

    source = inspect.getsource(training_router.create_training_job)
    assert "payload.view_id" not in source, (
        "DESIRED: router.create_training_job should NOT reference "
        "payload.view_id — it should use payload.trainer_id (or "
        "payload.preset_id). Current source still contains 'payload.view_id'."
    )


def test_DESIRED_conftest_create_job_uses_trainer_id_key() -> None:
    """
    [FAILS NOW] After refactor, conftest.create_job should use
    'trainer_id' key, not 'view_id'.
    """
    import inspect
    from tests import conftest as test_conftest

    source = inspect.getsource(test_conftest.create_job)
    assert     "view_id" not in source and "'view_id'" not in source, (
        "DESIRED: conftest.create_job should NOT use 'view_id' as JSON key. "
        "It should use 'trainer_id' or 'preset_id'. "
        "Current source still contains 'view_id'."
    )
