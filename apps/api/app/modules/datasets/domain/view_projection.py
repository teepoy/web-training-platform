from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ViewProjectionContext:
    """Context supplied uniformly to every SampleRow view projector."""

    dataset_id: str
    dataset_type: str
