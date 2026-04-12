"""Agent tools — callable functions the LLM agent can invoke.

Each tool is a plain async function that takes structured kwargs and returns
a dict result.  The ``TOOL_DEFINITIONS`` list provides the OpenAI-compatible
function schema that goes into the LLM ``tools`` parameter.
"""
from __future__ import annotations

import json
from typing import Any

from app.agent.surface_store import SurfaceStore
from app.api.schemas import AgentPanelDescriptor


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_data",
            "description": (
                "Run a read-only data query against the current dataset. "
                "Supported query_type: annotation-stats, sample-slice, "
                "metadata-histogram, recent-annotations, prediction-summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": [
                            "annotation-stats",
                            "sample-slice",
                            "metadata-histogram",
                            "recent-annotations",
                            "prediction-summary",
                        ],
                    },
                    "params": {
                        "type": "object",
                        "description": "Query-specific parameters",
                    },
                },
                "required": ["query_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_panel",
            "description": (
                "Add or replace a panel on the sidebar display surface. "
                "Provide a panel descriptor with id, component, title, and data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9\\-]*$"},
                    "component": {
                        "type": "string",
                        "enum": [
                            "echarts-generic",
                            "markdown-log",
                            "data-table",
                            "metric-cards",
                            "sample-viewer",
                        ],
                    },
                    "title": {"type": "string"},
                    "data": {
                        "type": "object",
                        "description": "Inline data: {inline: <payload>}",
                    },
                    "config": {"type": "object"},
                    "order": {"type": "integer", "minimum": 0},
                    "size": {"type": "string", "enum": ["compact", "normal", "large"]},
                    "ephemeral": {"type": "boolean"},
                },
                "required": ["id", "component", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_panel",
            "description": "Remove a panel from the sidebar by its panel ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "panel_id": {"type": "string"},
                },
                "required": ["panel_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_surface_state",
            "description": "Read the current panels on the sidebar display surface.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

MAX_PANELS = 8


async def execute_query_data(
    *,
    query_type: str,
    params: dict[str, Any] | None,
    dataset_id: str,
    repository: Any,
) -> dict[str, Any]:
    """Execute a data query and return the result dict."""
    params = params or {}

    if query_type == "annotation-stats":
        return await repository.get_annotation_stats(dataset_id)

    elif query_type == "sample-slice":
        offset = int(params.get("offset", 0))
        limit = min(int(params.get("limit", 50)), 200)
        label = params.get("label")
        order_by = params.get("order_by", "id")
        items, total = await repository.list_samples_with_labels(
            dataset_id=dataset_id,
            offset=offset,
            limit=limit,
            label_filter=label,
            order_by=order_by,
        )
        return {"items": items, "total": total}

    elif query_type == "metadata-histogram":
        key = params.get("key")
        if not key:
            return {"error": "params.key is required for metadata-histogram"}
        return await repository.metadata_histogram(dataset_id, key)

    elif query_type == "recent-annotations":
        limit = min(int(params.get("limit", 20)), 100)
        return await repository.recent_annotations(dataset_id, limit)

    elif query_type == "prediction-summary":
        return await repository.prediction_summary(dataset_id)

    else:
        return {"error": f"Unknown query_type: {query_type}"}


async def execute_set_panel(
    *,
    session_id: str,
    surface_id: str,
    surface_store: SurfaceStore,
    **panel_kwargs: Any,
) -> dict[str, Any]:
    """Add or replace a panel on the surface."""
    # Validate panel count
    current = await surface_store.get_state(session_id, surface_id)
    existing_ids = {p.id for p in current.panels}
    if panel_kwargs.get("id") not in existing_ids and len(current.panels) >= MAX_PANELS:
        return {"error": f"Maximum {MAX_PANELS} panels reached. Remove a panel first."}

    # Validate inline data size
    data = panel_kwargs.get("data")
    if data:
        data_str = json.dumps(data)
        if len(data_str) > 51200:
            return {"error": "Inline data exceeds 50KB limit."}

    panel = AgentPanelDescriptor(**panel_kwargs)
    doc = await surface_store.set_panel(session_id, surface_id, panel)
    return {"ok": True, "panel_id": panel.id, "total_panels": len(doc.panels)}


async def execute_remove_panel(
    *,
    session_id: str,
    surface_id: str,
    surface_store: SurfaceStore,
    panel_id: str,
) -> dict[str, Any]:
    """Remove a panel from the surface."""
    doc = await surface_store.remove_panel(session_id, surface_id, panel_id)
    if doc is None:
        return {"error": f"Panel '{panel_id}' not found"}
    return {"ok": True, "remaining_panels": len(doc.panels)}


async def execute_get_surface_state(
    *,
    session_id: str,
    surface_id: str,
    surface_store: SurfaceStore,
) -> dict[str, Any]:
    """Read current surface state."""
    doc = await surface_store.get_state(session_id, surface_id)
    return doc.model_dump(mode="json")
