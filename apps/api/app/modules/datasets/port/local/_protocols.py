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
from app.modules.datasets.domain.entities import (
    DatasetRevision,
    DatasetRevisionOperation,
)
from app.modules.datasets.domain.status import DatasetStatus
from app.shared.api.schemas import Annotation, Dataset
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository


# =============================================================================
# IDatasetService
# =============================================================================


class IDatasetService(Protocol):
    """Dataset-level status, response, and Label Studio export operations."""

    def to_response(self, dataset: Dataset) -> Dataset:
        """Enrich a dataset with computed response fields such as its LS URL."""
        ...

    async def get_status(self, dataset_id: str, org_id: str) -> DatasetStatus: ...

    async def build_export_data(
        self,
        dataset_id: str,
        org_id: str,
        ls_read_repository: LsReadRepository,
    ) -> tuple[Dataset, list[Any], list[Annotation]]:
        """Return (dataset, samples, annotations) sourced from Label Studio."""
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


class DatasetDeletionGuardPort(Protocol):
    """Prevent deletion while runtime jobs still depend on a dataset."""

    async def ensure_deletable(self, *, dataset_id: str, org_id: str) -> None: ...


class DatasetRevisionReaderPort(Protocol):
    async def get_current(self, dataset_id: str, org_id: str) -> DatasetRevision: ...

    async def list_current(
        self, dataset_ids: tuple[str, ...], org_id: str
    ) -> dict[str, DatasetRevision]: ...

    async def get_revision(
        self,
        *,
        dataset_id: str,
        revision_id: str,
        org_id: str,
    ) -> DatasetRevision: ...

    async def resolve_or_create_baseline(
        self,
        *,
        dataset_id: str,
        org_id: str,
        created_by: str,
    ) -> DatasetRevision: ...

    async def list_history(
        self,
        dataset_id: str,
        org_id: str,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[DatasetRevision], int]: ...


class DatasetRevisionPublisherPort(Protocol):
    async def publish_sparse_revision(
        self,
        *,
        dataset_id: str,
        org_id: str,
        operation: DatasetRevisionOperation,
        created_by: str,
        provenance: dict[str, object] | None = None,
        operation_ref: str | None = None,
    ) -> DatasetRevision: ...
