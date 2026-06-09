"""Torch Dataset adapter boundary — protocol and reference types.

This module defines the **interface boundary** where stored platform datasets
(view-projected samples from the API database) are converted into
``torch.utils.data.Dataset`` instances for training and inference workers.

**Design rule**: the protocol is Torch-free.  It describes the conversion
contract (what goes in, what comes out) without importing ``torch``.
Concrete implementations live in ``libs/ml`` or downstream worker packages
where Torch is already a dependency.  The API never imports this module or
any Torch adapter — it only produces the ``ViewDatasetRef`` inputs that
describe stored datasets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ViewDatasetRef:
    """Descriptor for a stored, view-projected dataset ready for Torch conversion.

    This is the input shape that the platform (API) produces and the Torch
    adapter consumes.  It carries enough metadata for the adapter to locate
    assets, select relevant samples, and project them through the correct
    view type before wrapping them in a Torch ``Dataset``.
    """

    dataset_id: str = ""
    """Platform dataset identifier."""

    view_type: str = ""
    """View projection applied before conversion — e.g. ``"classification"``,
    ``"detection"``, ``"vqa"``."""

    storage_mode: str = ""
    """Storage semantics — ``"db_full"`` or ``"file_shard_sparse"``."""

    sample_ids: list[str] | None = None
    """Optional subset of sample IDs to include. ``None`` means all samples."""

    label_space: list[str] = field(default_factory=list)
    """Label names for classification-type views."""

    storage_uri_prefix: str = ""
    """Base URI prefix for asset retrieval (S3, MinIO, local filesystem)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extension point for dataset-type-specific conversion parameters."""


class TorchDatasetAdapter(Protocol):
    """Protocol for converting a stored view dataset into a Torch ``Dataset``.

    This is the **adapter boundary**: the platform runtime (or a worker
    orchestrator) resolves an adapter implementing this protocol, passes a
    ``ViewDatasetRef``, and receives a Torch ``Dataset`` that can be fed
    into a ``DataLoader``.

    The return type is ``Any`` to keep the protocol Torch-free.  Concrete
    return types are expected to be ``torch.utils.data.Dataset``
    subclasses.  The protocol does **not** prescribe batching, shuffling,
    or augmentation — those are downstream concerns on the returned
    dataset.

    Example (conceptual, not importable from here)::

        from torch.utils.data import DataLoader

        adapter: TorchDatasetAdapter = resolve_adapter(view_ref.view_type)
        torch_ds: Any = adapter.to_torch_dataset(view_ref)
        loader = DataLoader(torch_ds, batch_size=32, shuffle=True)
    """

    def to_torch_dataset(self, view_dataset: ViewDatasetRef) -> Any:
        """Convert a stored view dataset into a Torch Dataset.

        Args:
            view_dataset: Descriptor for the stored dataset to convert.

        Returns:
            A ``torch.utils.data.Dataset`` instance (concrete type is
            view-type-dependent — e.g. a classification dataset subclass,
            a detection dataset subclass).

        Raises:
            NotImplementedError: If the adapter does not support the
                requested ``view_type`` or ``storage_mode``.
        """
        ...
