from __future__ import annotations

# ===========================================================================
# datasets/port/local  ——  single public import surface for all modules
# that depend on datasets.
#
# ── Protocol interfaces (I* prefix) ────────────────────────────────────
#   Other modules declare constructor dependencies using these:
#       def __init__(self, dss: IDatasetService, ...) -> None:
#
# ── Concrete classes (bare name) ───────────────────────────────────────
#   Only for DI container / composition / deps code that CONSTRUCTS
#   instances.  Service code should NOT import the concrete classes
#   for dependency declarations.
# ===========================================================================

# ── Protocol interfaces ────────────────────────────────────────────────────
from app.modules.datasets.port.local._protocols import (
    IDatasetService,
    IFeatureOpsService,
)

# ── Concrete service re-exports (for DI construction use) ──────────────────
from app.modules.datasets.app.services.dataset_service import DatasetService
from app.modules.datasets.app.services.feature_ops import FeatureOpsService

# ── Existing Protocol (in domain/) ──────────────────────────────────────────
from app.modules.datasets.domain.repository import DatasetRepository

# ── Domain types (plain dataclasses) ────────────────────────────────────────
from app.modules.datasets.domain.sample_row import (
    BulkImageRef,
    BulkSampleRow,
    SampleRow,
)

# ── Validation ──────────────────────────────────────────────────────────────
from app.modules.datasets.domain.compatibility import (
    validate_predictor_for_dataset,
    validate_trainer_for_dataset,
)

# ── Composition entry point ─────────────────────────────────────────────────
from app.modules.datasets.container import init_datasets

__all__ = [
    "IDatasetService",
    "IFeatureOpsService",
    "DatasetService",
    "FeatureOpsService",
    "DatasetRepository",
    "SampleRow",
    "BulkSampleRow",
    "BulkImageRef",
    "validate_predictor_for_dataset",
    "validate_trainer_for_dataset",
    "init_datasets",
]
