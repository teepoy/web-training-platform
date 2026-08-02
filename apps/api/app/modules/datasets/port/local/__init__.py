from __future__ import annotations

# ===========================================================================
# datasets/port/local  ——  single public import surface for all modules
# that depend on datasets.
#
# ── Protocol interfaces (I* prefix) ────────────────────────────────────
#   Other modules declare constructor dependencies using these:
#       def __init__(self, dss: IDatasetService, ...) -> None:
#
# Concrete implementations are intentionally not re-exported here.
# ===========================================================================

# ── Protocol interfaces ────────────────────────────────────────────────────
from app.modules.datasets.port.local._protocols import (
    DatasetDeletionGuardPort,
    DatasetStorageFactoryPort,
    IDatasetService,
    SampleSimilarityPort,
    SparseImportWriterFactoryPort,
    SparseImportWriterPort,
)

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
    DatasetCompatibilityError,
    validate_predictor_for_dataset,
    validate_trainer_for_dataset,
)

__all__ = [
    "DatasetDeletionGuardPort",
    "IDatasetService",
    "DatasetStorageFactoryPort",
    "SparseImportWriterFactoryPort",
    "SparseImportWriterPort",
    "SampleSimilarityPort",
    "DatasetRepository",
    "SampleRow",
    "BulkSampleRow",
    "BulkImageRef",
    "validate_predictor_for_dataset",
    "validate_trainer_for_dataset",
    "DatasetCompatibilityError",
]
