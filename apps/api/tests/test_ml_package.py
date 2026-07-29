"""Tests for API-local ML type implementations and Protocol conformance.

These tests keep the current in-process demo trainer/predictor implementations
honest without preserving a separate ``libs/ml`` workspace package.

Test categories
---------------
1. **Import existence** – worker-only demo modules under
   ``app.runtime_compat.ml.demo`` import.
2. **Trainer / Predictor Protocol conformance** – once the modules exist,
   the exported classes must satisfy ``app.shared.domain.runtime.Trainer``
   and ``app.shared.domain.runtime.Predictor``.
3. **Heavy-import boundary** – importing ``app.registrations`` must NOT
   cause ``torch`` (or equivalent heavy ML frameworks) to be imported
   at API startup time.  These pass now and serve as regression guards.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _modules_loaded() -> frozenset[str]:
    return frozenset(sys.modules.keys())


_EXPECTED_CLASSES: dict[str, dict[str, list[str]]] = {
    "classification": {
        "trainer": ["app.runtime_compat.ml.demo.classification.trainer", "ClassificationTrainer"],
        "predictor": ["app.runtime_compat.ml.demo.classification.predictor", "ClassificationPredictor"],
    },
    "detection": {
        "trainer": ["app.runtime_compat.ml.demo.detection.trainer", "DetectionTrainer"],
        "predictor": ["app.runtime_compat.ml.demo.detection.predictor", "DetectionPredictor"],
    },
    "vqa": {
        "trainer": ["app.runtime_compat.ml.demo.vqa.trainer", "VqaTrainer"],
        "predictor": ["app.runtime_compat.ml.demo.vqa.predictor", "VqaPredictor"],
    },
}


def _import_class(family: str, role: str) -> type[Any]:
    module_path, class_name = _EXPECTED_CLASSES[family][role]
    mod = __import__(module_path, fromlist=[class_name])
    cls = getattr(mod, class_name)
    if cls is None:
        raise ImportError(f"{class_name} not found in {module_path}")
    return cls


# ============================================================================
# 1.  Import existence — RED (modules don't exist yet)
# ============================================================================


class TestClassificationImports:
    def test_import_classification_trainer(self) -> None:
        import app.runtime_compat.ml.demo.classification.trainer  # noqa: F401

    def test_import_classification_predictor(self) -> None:
        import app.runtime_compat.ml.demo.classification.predictor  # noqa: F401


class TestDetectionImports:
    def test_import_detection_trainer(self) -> None:
        import app.runtime_compat.ml.demo.detection.trainer  # noqa: F401

    def test_import_detection_predictor(self) -> None:
        import app.runtime_compat.ml.demo.detection.predictor  # noqa: F401


class TestVqaImports:
    def test_import_vqa_trainer(self) -> None:
        import app.runtime_compat.ml.demo.vqa.trainer  # noqa: F401

    def test_import_vqa_predictor(self) -> None:
        import app.runtime_compat.ml.demo.vqa.predictor  # noqa: F401


class TestTopLevelImport:
    def test_import_libs_ml(self) -> None:
        import app.runtime_compat.ml.demo  # noqa: F401


# ============================================================================
# 2.  Protocol conformance — RED (can't import to check, yet)
# ============================================================================

from app.shared.domain.runtime import (  # noqa: E402
    Predictor,
    Trainer,
)


class TestTrainerProtocol:
    @pytest.mark.parametrize("family", ["classification", "detection", "vqa"])
    def test_trainer_issubclass_of_protocol(self, family: str) -> None:
        cls = _import_class(family, "trainer")  # ← ModuleNotFoundError (RED)
        assert issubclass(
            cls, Trainer
        ), f"{cls.__name__} must satisfy Trainer Protocol"

    @pytest.mark.parametrize("family", ["classification", "detection", "vqa"])
    def test_trainer_has_async_train(self, family: str) -> None:
        cls = _import_class(family, "trainer")  # ← ModuleNotFoundError (RED)
        assert callable(getattr(cls, "train", None)), f"{cls.__name__} missing 'train'"


class TestPredictorProtocol:
    @pytest.mark.parametrize("family", ["classification", "detection", "vqa"])
    def test_predictor_issubclass_of_protocol(self, family: str) -> None:
        cls = _import_class(family, "predictor")  # ← ModuleNotFoundError (RED)
        assert issubclass(
            cls, Predictor
        ), f"{cls.__name__} must satisfy Predictor Protocol"

    @pytest.mark.parametrize("family", ["classification", "detection", "vqa"])
    def test_predictor_has_required_methods(self, family: str) -> None:
        cls = _import_class(family, "predictor")  # ← ModuleNotFoundError (RED)
        for method in ("load_model", "predict_batch", "predict_single", "unload_model"):
            assert callable(
                getattr(cls, method, None)
            ), f"{cls.__name__} missing '{method}'"


# ============================================================================
# 3.  Heavy-import boundary — GREEN now, regression guard
# ============================================================================


HEAVY_PREFIXES: tuple[str, ...] = (
    "torch",
    "torchvision",
    "transformers",
    "tensorflow",
    "jax",
    "dspy",
    "safetensors",
    "tokenizers",
)


def _new_heavy_modules(pre: frozenset[str], post: frozenset[str]) -> set[str]:
    new_mods = post - pre
    return {
        m
        for m in new_mods
        if any(m == pfx or m.startswith(pfx + ".") for pfx in HEAVY_PREFIXES)
    }


class TestHeavyImportBoundary:
    @pytest.fixture(autouse=True)
    def _snapshot(self) -> None:
        self._pre = _modules_loaded()

    def test_registrations_import_does_not_load_torch(self) -> None:
        import app.registrations  # noqa: F401

        heavy = _new_heavy_modules(self._pre, _modules_loaded())
        torch_mods = {m for m in heavy if m.startswith("torch")}
        assert not torch_mods, (
            f"app.registrations import loaded torch modules: {sorted(torch_mods)}"
        )

    def test_registrations_import_does_not_load_transformers(self) -> None:
        import app.registrations  # noqa: F401

        heavy = _new_heavy_modules(self._pre, _modules_loaded())
        tf_mods = {m for m in heavy if m.startswith("transformers")}
        assert not tf_mods, (
            f"app.registrations import loaded transformers: {sorted(tf_mods)}"
        )

    def test_registrations_import_does_not_load_any_heavy_ml(self) -> None:
        import app.registrations  # noqa: F401

        heavy = _new_heavy_modules(self._pre, _modules_loaded())
        assert not heavy, (
            f"app.registrations import loaded heavy ML packages: {sorted(heavy)}"
        )

    def test_main_import_does_not_load_torch(self) -> None:
        import app.main  # noqa: F401

        heavy = _new_heavy_modules(self._pre, _modules_loaded())
        torch_mods = {m for m in heavy if m.startswith("torch")}
        assert not torch_mods, (
            f"app.main import loaded torch modules: {sorted(torch_mods)}"
        )

    def test_main_import_does_not_load_any_heavy_ml(self) -> None:
        import app.main  # noqa: F401

        heavy = _new_heavy_modules(self._pre, _modules_loaded())
        assert not heavy, (
            f"app.main import loaded heavy ML packages: {sorted(heavy)}"
        )
