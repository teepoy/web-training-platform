"""Public Protocol interfaces for the datasets module.

Other modules MUST import these Protocols from `port.local` and
declare their constructor dependencies using these Protocol types.
The concrete service classes (in ``app.services.*``) structurally
satisfy these protocols; the composition root wires concrete
instances.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.shared.api.schemas import Annotation, Dataset, Sample
from app.shared.infrastructure.label_studio.read_repository import LsReadRepository


# =============================================================================
# IDatasetService
# =============================================================================


class IDatasetService(Protocol):
    """Dataset-level operations (label-space merge, LS export)."""

    def to_response(self, dataset: Dataset) -> Dataset:
        """Enrich a dataset with computed fields (capabilities, LS URL)."""
        ...

    async def build_export_data(
        self,
        dataset_id: str,
        ls_read_repository: LsReadRepository,
    ) -> tuple[Dataset, list[Any], list[Annotation]]:
        """Return (dataset, samples, annotations) sourced from Label Studio."""
        ...

    async def merge_label_space(
        self, dataset_id: str, incoming_labels: set[str]
    ) -> bool:
        """Merge new labels into the dataset's task_spec.label_space."""
        ...


# =============================================================================
# IFeatureOpsService
# =============================================================================


class IFeatureOpsService(Protocol):
    """Embedding extraction, similarity search, and scoring operations."""

    async def extract_features(
        self,
        samples: list[Sample],
        embed_model: str,
        force: bool = False,
        storage: Any = None,
    ) -> dict: ...

    async def similarity_search(
        self,
        sample_id: str,
        dataset_id: str,
        k: int = 5,
    ) -> dict: ...

    async def uniqueness_scores(
        self,
        sample_ids: list[str],
        dataset_id: str,
    ) -> dict: ...

    async def representativeness_scores(
        self,
        sample_ids: list[str],
        dataset_id: str,
    ) -> dict: ...

    async def cluster_hints(
        self,
        sample_ids: list[str],
        dataset_id: str,
        k: int = 5,
    ) -> dict: ...

    async def uncovered_hints(
        self,
        sample_ids: list[str],
        dataset_id: str,
        k: int = 5,
    ) -> dict: ...
