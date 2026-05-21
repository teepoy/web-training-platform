from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from app.modules.preview.domain.preview import PreviewItem


@dataclass
class DatasetSchema:
    """Descriptor for a dataset/task type pairing.

    Each dataset type registers exactly one ``DatasetSchema``.  The descriptor
    bundles together everything that is specific to that type:

    * The ``dataset_type`` / ``task_type`` string identifiers used in the DB and API.
    * How to generate a Label Studio labeling config for the type.
    * How to convert annotations between the platform format and Label Studio.
    * How to generate synthetic sample items (used by seed scripts, mock upstreams,
      and Storybook fixtures — a single function, one source of truth).

    Parameters
    ----------
    dataset_type:
        String identifier, e.g. ``"image_classification"``.
    task_type:
        String identifier, e.g. ``"classification"``.
    annotation_type:
        High-level annotation shape.  One of ``"choice"`` (single-label),
        ``"boxes"`` (bounding boxes), ``"text"`` (free text), ``"none"``.
    label_space_mode:
        Whether a label space is required, optional, or forbidden for this type.
    generate_ls_config:
        ``(label_space: list[str]) -> str`` — returns a Label Studio XML config.
    platform_annotation_to_ls:
        ``(label: str, annotation_value: dict | list | None) -> list[dict]``
        Converts a platform annotation to a list of LS result objects.
    ls_annotation_to_platform:
        ``(ls_results: list[dict]) -> tuple[str, dict | list | None]``
        Extracts ``(label, annotation_value)`` from LS annotation results.
    mock_item_generator:
        ``(index: int, label_space: list[str]) -> PreviewItem``
        Generates a deterministic synthetic sample item.  The same function is
        reused by seed scripts, mock upstream adapters, and Storybook fixtures.
    metadata_schema:
        Optional hint dict for UI display (field name → {"type": ..., "label": ...}).
    """

    dataset_type: str
    task_type: str
    annotation_type: str  # "choice" | "boxes" | "text" | "none"
    label_space_mode: str  # "required" | "optional" | "forbidden"
    generate_ls_config: Callable[[list[str]], str]
    platform_annotation_to_ls: Callable[[str, Any], list[dict[str, Any]]]
    ls_annotation_to_platform: Callable[[list[dict[str, Any]]], tuple[str, Any]]
    mock_item_generator: Callable[[int, list[str]], PreviewItem]
    metadata_schema: dict[str, dict[str, str]] = field(default_factory=dict)
