"""Global prompt assembler — builds the global agent system prompt.

Enriches the ``global_prompt_template.md`` with user/org context, platform
statistics, and — when the user is on a dataset page — dataset-specific
details.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.api.schemas import AgentContext


_TEMPLATE_PATH = Path(__file__).parent / "global_prompt_template.md"
_template_cache: str | None = None


def _load_template() -> str:
    global _template_cache
    if _template_cache is None:
        _template_cache = _TEMPLATE_PATH.read_text()
    return _template_cache


def _build_context_block(context: AgentContext, dataset_info: dict[str, Any] | None) -> str:
    """Build the context block that describes what the user is looking at."""
    lines: list[str] = []

    if context.dataset_id:
        lines.append(f"- Active dataset: `{context.dataset_id}`")
        if dataset_info:
            lines.append(f"  - Name: {dataset_info.get('name', '?')}")
            lines.append(f"  - Type: {dataset_info.get('dataset_type', '?')}")
            lines.append(f"  - Samples: {dataset_info.get('sample_count', '?')}")
            label_space = dataset_info.get("label_space", [])
            if label_space:
                lines.append(f"  - Labels: {', '.join(label_space[:30])}")
            ann = dataset_info.get("annotation_stats")
            if ann:
                lines.append(f"  - Annotated: {ann.get('annotated_samples', 0)}/{ann.get('total_samples', 0)}")

    if context.job_id:
        lines.append(f"- Active job: `{context.job_id}`")
    if context.schedule_id:
        lines.append(f"- Active schedule: `{context.schedule_id}`")

    on_classify = context.page and "/classify" in context.page
    if on_classify:
        lines.append("- **Sidebar tools are AVAILABLE** (user is on the classify page)")
    else:
        lines.append("- Sidebar tools are NOT available on this page")

    if not lines:
        return "- No specific entity selected"
    return "\n".join(lines)


def _build_platform_stats_block(stats: dict[str, Any] | None) -> str:
    """Build a brief platform overview."""
    if not stats:
        return "- Platform statistics not available"
    lines: list[str] = []
    lines.append(f"- Datasets: {stats.get('dataset_count', '?')}")
    lines.append(f"- Training jobs: {stats.get('job_count', '?')}")
    lines.append(f"- Models: {stats.get('model_count', '?')}")
    lines.append(f"- Presets: {stats.get('preset_count', '?')}")
    return "\n".join(lines)


async def assemble_global_prompt(
    *,
    context: AgentContext,
    user_email: str,
    org_id: str,
    org_name: str,
    dataset_info: dict[str, Any] | None = None,
    platform_stats: dict[str, Any] | None = None,
) -> str:
    """Build a complete system prompt for the global agent.

    Parameters
    ----------
    context:
        The client-provided context (page, dataset_id, etc.).
    user_email:
        Current user's email.
    org_id:
        Current organization ID.
    org_name:
        Current organization name.
    dataset_info:
        Optional enriched dataset information when on a dataset page.
    platform_stats:
        Optional platform-level statistics (counts of datasets, jobs, etc.).
    """
    template = _load_template()

    context_block = _build_context_block(context, dataset_info)
    platform_stats_block = _build_platform_stats_block(platform_stats)

    return template.format(
        user_email=user_email,
        org_id=org_id,
        org_name=org_name,
        current_page=context.page or "(unknown)",
        context_block=context_block,
        platform_stats_block=platform_stats_block,
    )
