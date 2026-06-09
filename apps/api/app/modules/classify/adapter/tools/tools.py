"""Classify workspace agent tools."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.shared.api.schemas import AgentPanelDescriptor
from app.shared.db.registry import SampleORM
from app.shared.infrastructure.surface_store import SurfaceStore

if TYPE_CHECKING:
    from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_data",
            "description": (
                "Run a read-only data query against the current dataset. "
                "Supported query_type: annotation-stats, sample-slice, "
                "metadata-histogram, recent-annotations, prediction-summary, "
                "wafer-points."
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
                            "wafer-points",
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
                "properties": {"panel_id": {"type": "string"}},
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

MAX_PANELS = 8


async def execute_query_data(
    *,
    query_type: str,
    params: dict[str, Any] | None,
    dataset_id: str,
    factory: DatasetStorageFactory,
    session_factory: async_sessionmaker | None = None,
    org_id: str,
) -> dict[str, Any]:
    """Execute a data query and return the result dict."""
    storage = await factory.open(dataset_id, org_id)
    params = params or {}

    if query_type == "annotation-stats":
        return await storage.get_annotation_stats()

    if query_type == "sample-slice":
        offset = int(params.get("offset", 0))
        limit = min(int(params.get("limit", 50)), 200)
        label = params.get("label")
        order_by = params.get("order_by", "id")
        sample_ids_raw = params.get("sample_ids")
        sample_ids: list[str] | None = None
        if sample_ids_raw is not None:
            if not isinstance(sample_ids_raw, list):
                return {"error": "params.sample_ids must be a list of strings"}
            sample_ids = [
                str(value).strip()
                for value in sample_ids_raw
                if isinstance(value, (str, int)) and str(value).strip()
            ]
        rows, total = await storage.list_samples(
            offset=offset,
            limit=limit,
            with_labels=True,
            label_filter=label,
            order_by=order_by,
            sample_ids=sample_ids,
        )
        items = _rows_to_dicts(rows)
        return {"items": items, "total": total}

    if query_type == "metadata-histogram":
        key = params.get("key")
        if not key:
            return {"error": "params.key is required for metadata-histogram"}
        if session_factory is None:
            return {"error": "metadata-histogram requires session_factory"}
        return await _metadata_histogram(dataset_id, key, session_factory)

    if query_type == "recent-annotations":
        limit = min(int(params.get("limit", 20)), 100)
        return await storage.recent_annotations(limit)

    if query_type == "prediction-summary":
        return await storage.prediction_summary()

    if query_type == "wafer-points":
        if session_factory is None:
            return {"error": "wafer-points requires session_factory"}
        return await _wafer_points(dataset_id, session_factory)

    return {"error": f"Unknown query_type: {query_type}"}


async def _metadata_histogram(
    dataset_id: str,
    key: str,
    session_factory: async_sessionmaker,
) -> dict[str, Any]:
    """Self-implemented metadata histogram via direct SQLAlchemy query."""
    async with session_factory() as session:
        val_col = func.json_extract(SampleORM.metadata_json, f"$.{key}").label("val")
        stmt = (
            select(val_col, func.count())
            .where(SampleORM.dataset_id == dataset_id)
            .group_by(val_col)
            .order_by(func.count().desc())
        )
        rows = (await session.execute(stmt)).all()
        return {
            "bins": [
                {"value": row[0], "count": row[1]}
                for row in rows
            ]
        }


def _rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    """Convert SampleRow objects to dicts for agent consumption."""
    result: list[dict[str, Any]] = []
    for row in rows:
        d: dict[str, Any] = {
            "id": getattr(row, "sample_id", None),
            "metadata": getattr(row, "metadata", {}),
        }
        label = getattr(row, "latest_label", None) or getattr(row, "label", None)
        if label is not None:
            d["label"] = label
        result.append(d)
    return result


async def _wafer_points(
    dataset_id: str,
    session_factory: async_sessionmaker,
) -> dict[str, Any]:
    """Self-implemented wafer points via direct SQLAlchemy query."""
    async with session_factory() as session:
        stmt = (
            select(SampleORM.id, SampleORM.metadata_json)
            .where(SampleORM.dataset_id == dataset_id)
        )
        rows = (await session.execute(stmt)).all()
        points: list[dict[str, Any]] = []
        for row in rows:
            metadata = row[1] or {}
            x = float(str(metadata.get("x", 0.0)))
            y = float(str(metadata.get("y", 0.0)))
            points.append({"id": str(row[0]), "x": x, "y": y})
        return {
            "points": points,
            "total": len(points),
        }


async def execute_set_panel(
    *,
    session_id: str,
    surface_id: str,
    surface_store: SurfaceStore,
    **panel_kwargs: Any,
) -> dict[str, Any]:
    """Add or replace a panel on the surface."""
    current = await surface_store.get_state(session_id, surface_id)
    existing_ids = {p.id for p in current.panels}
    if panel_kwargs.get("id") not in existing_ids and len(current.panels) >= MAX_PANELS:
        return {"error": f"Maximum {MAX_PANELS} panels reached. Remove a panel first."}

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
