"""Public Protocol interfaces for the datasets module.

Other modules MUST import these Protocols from `port.local` and
declare their constructor dependencies using these Protocol types.
The concrete service classes (in ``app.services.*``) structurally
satisfy these protocols; the composition root wires concrete
instances.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.modules.storage.port.local import (
    DatasetStorageFactoryPort as DatasetStorageFactoryPort,
    SparseImportWriterFactoryPort as SparseImportWriterFactoryPort,
    SparseImportWriterPort as SparseImportWriterPort,
)
from app.shared.api.schemas import Annotation, Dataset
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository


# =============================================================================
# IDatasetService
# =============================================================================


class IDatasetService(Protocol):
    """Dataset-level operations (label-space merge, LS export)."""

    def to_response(self, dataset: Dataset) -> Dataset:
        """Enrich a dataset with computed response fields such as its LS URL."""
        ...

    async def to_list_responses(self, datasets: list[Dataset]) -> list[Dataset]: ...

    async def build_export_data(
        self,
        dataset_id: str,
        org_id: str,
        ls_read_repository: LsReadRepository,
    ) -> tuple[Dataset, list[Any], list[Annotation]]:
        """Return (dataset, samples, annotations) sourced from Label Studio."""
        ...

    async def merge_label_space(
        self,
        dataset_id: str,
        org_id: str,
        incoming_labels: set[str],
    ) -> bool:
        """Merge new labels into the dataset's task_spec.label_space."""
        ...


# =============================================================================
# SampleSimilarityPort
# =============================================================================


class SampleSimilarityPort(Protocol):
    """Find samples near a given sample using stored feature vectors."""

    async def similarity_search(
        self,
        sample_id: str,
        dataset_id: str,
        org_id: str,
        k: int = 5,
    ) -> dict: ...
