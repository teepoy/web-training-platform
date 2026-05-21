"""Prompt assembler for the classify workspace agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.classify.api.schemas import DeclaredMetadataKey, MetadataKeyInfo
from app.modules.classify.infrastructure.tools.metadata_inference import (
    build_metadata_block,
    scan_metadata_types,
)


_TEMPLATE_PATH = Path(__file__).parent / "prompt_template.md"
_template_cache: str | None = None


def _load_template() -> str:
    global _template_cache
    if _template_cache is None:
        _template_cache = _TEMPLATE_PATH.read_text()
    return _template_cache


def assemble_prompt(
    *,
    dataset_name: str,
    dataset_type: str,
    sample_count: int,
    label_space: list[str],
    annotation_stats: dict[str, Any],
    metadata_dicts: list[dict[str, Any]],
    declared_metadata: dict[str, dict[str, str]] | None = None,
    has_predictions: bool = False,
    has_embeddings: bool = False,
) -> str:
    """Build a complete system prompt for the classify agent."""
    template = _load_template()

    declared: dict[str, DeclaredMetadataKey] | None = None
    if declared_metadata:
        declared = {k: DeclaredMetadataKey(**v) for k, v in declared_metadata.items()}

    inferred: dict[str, MetadataKeyInfo] | None = None
    if metadata_dicts:
        inferred = scan_metadata_types(metadata_dicts)

    metadata_keys_block = build_metadata_block(declared, inferred)
    label_counts = annotation_stats.get("label_counts", {})

    return template.format(
        dataset_name=dataset_name,
        dataset_type=dataset_type,
        sample_count=sample_count,
        label_space=", ".join(label_space[:50]),
        metadata_keys_block=metadata_keys_block,
        total_samples=annotation_stats.get("total_samples", sample_count),
        annotated_samples=annotation_stats.get("annotated_samples", 0),
        unlabeled_samples=annotation_stats.get("unlabeled_samples", sample_count),
        label_counts_json=json.dumps(label_counts, indent=None),
        has_predictions=str(has_predictions).lower(),
        has_embeddings=str(has_embeddings).lower(),
    )
