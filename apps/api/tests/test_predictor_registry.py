"""Tests for predictor registry separation: metadata catalog vs executable registry.

T13: Separate executable predictor registry from catalog metadata naming.

These tests verify:
1.  ``get_predictor()`` only returns executable predictors (raises KeyError
    for metadata-only entries).
2.  ``get_predictor_by_id()`` only reads executable registrations.
3.  The flow runtime loader resolves SC predictors from the central registry.
4.  Metadata-only predictor IDs fail clearly when no executable exists.
"""

from __future__ import annotations

import pytest


class TestMetadataCatalogVsExecutableRegistry:
    """Verify the distinction between metadata catalog and executable registry.

    Per CORE_DESIGNS §6, metadata belongs to the catalog while executable
    callables belong to the central executable registry.
    """

    # ── get_predictor (executable-only, no catalog fallback) ──────────

    def test_sc_predictor_has_catalog_entry(self) -> None:
        """resnet50-sc-v1 metadata remains available without eager ML imports."""
        from app.modules.types import catalog

        meta = catalog.get_predictor_meta("resnet50-sc-v1")
        assert meta.id == "resnet50-sc-v1"
        assert meta.name == "ResNet-50 SC Defect Prediction"

    def test_get_predictor_rejects_unknown_id(self) -> None:
        """get_predictor raises KeyError for completely unknown IDs."""
        from app.core.registry import get_predictor

        with pytest.raises(KeyError, match="No executable predictor registered"):
            get_predictor("nonexistent-predictor-v99")

    # ── get_predictor_by_id (executable registry only) ────────────────

    def test_get_predictor_by_id_resolves_sc_predictor(self) -> None:
        """get_predictor_by_id resolves an imported executable."""
        from app.modules.runtime.app.services.executable_loader import get_predictor
        from app.core.registry import get_predictor_by_id

        get_predictor("resnet50-sc-v1")
        pred = get_predictor_by_id("resnet50-sc-v1")
        assert pred is not None
        assert pred.predictor_id == "resnet50-sc-v1"
        assert pred.name == "ResNet-50 SC Defect Prediction"
        assert pred.view_id == "patch_image_v1"

    def test_metadata_catalog_does_not_create_executable_stub(self) -> None:
        """Catalog lookup remains separate from the executable registry."""
        from app.core.registry import _Registry
        from app.modules.types import catalog

        isolated_registry = _Registry()
        with pytest.raises(KeyError):
            catalog.get_predictor_meta("clip-zero-shot-v1")
        assert isolated_registry.get_predictor_by_id("clip-zero-shot-v1") is None

    # ── get_predictor_by_id returns None for unknown ID ───────────────

    def test_get_predictor_by_id_returns_none_for_unknown(self) -> None:
        """get_predictor_by_id returns None for IDs not in catalog either."""
        from app.core.registry import get_predictor_by_id

        assert get_predictor_by_id("completely-unknown-v999") is None

    # ── Flow runtime loader ───────────────────────────────────────────

    def test_sc_executable_predictor_resolves_in_flow_registry(self) -> None:
        """The flow loader returns the raw centrally registered callable."""
        from app.modules.runtime.app.services.executable_loader import (
            get_predictor as flow_get_predictor,
        )
        from app.core.registry import get_predictor

        fn = flow_get_predictor("resnet50-sc-v1")
        assert callable(fn), "SC predictor should be a callable in flow registry"
        assert fn is get_predictor("resnet50-sc-v1").func
        assert getattr(fn, "_view_id") == "patch_image_v1"

    def test_flow_registry_rejects_metadata_only_ids(self) -> None:
        """The flow loader rejects IDs without a flow executable module."""
        from app.modules.runtime.app.services.executable_loader import (
            get_predictor as flow_get_predictor,
        )

        with pytest.raises(KeyError, match="Unknown predictor capability"):
            flow_get_predictor("clip-zero-shot-v1")

    # ── Naming clarity ───────────────────────────────────────────────

    def test_get_predictor_is_exported_at_module_level(self) -> None:
        """get_predictor is exported from app.core.registry (was missing before T13)."""
        import app.core.registry as reg_mod

        assert hasattr(reg_mod, "get_predictor"), (
            "get_predictor must be exported at module level"
        )
        assert callable(reg_mod.get_predictor)

    def test_catalog_stub_surface_is_removed(self) -> None:
        """Metadata-only executable facades are not part of the registry."""
        import app.core.registry as reg_mod

        assert not hasattr(reg_mod, "_make_metadata_only_predictor"), (
            "old _make_metadata_only_predictor function name removed"
        )
        assert not hasattr(reg_mod, "_make_catalog_stub_predictor")
        assert not hasattr(reg_mod, "_make_catalog_stub_trainer")

    def test_registry_class_documents_namespaces(self) -> None:
        """_Registry.__doc__ explains the distinction between views/trainers/predictors."""
        from app.core.registry import _Registry

        assert _Registry.__doc__ is not None, "_Registry must have a docstring"
        assert "executable" in _Registry.__doc__.lower(), (
            "_Registry docstring must mention executable registrations"
        )
        assert "metadata" in _Registry.__doc__.lower() or "catalog" in _Registry.__doc__.lower(), (
            "_Registry docstring must mention metadata/catalog"
        )
