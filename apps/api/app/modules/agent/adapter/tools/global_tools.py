"""Global agent tools — expanded tool set for the platform-wide agent.

Includes read tools (datasets, jobs, models, trainers, schedules, dashboard),
write tools (create dataset, start training, run predictions, create schedule,
cancel job), and sidebar tools (set_panel, remove_panel, get_surface_state)
that are only active on the classify page.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.agent.port.http.schemas import AgentContext, AgentPanelDescriptor
from app.shared.api.schemas import WaferPoint, WaferPointsResponse  # noqa: F401
from app.shared.db.registry import AnnotationORM, SampleORM
from app.shared.domain.protocols import LabelStudioClient
from app.shared.infrastructure.surface_store import SurfaceStore

if TYPE_CHECKING:
    from app.modules.datasets.adapter.storage_factory import DatasetStorageFactory
    from app.shared.db.sql_repository import SqlRepository
    from app.modules.models.app.services.model_service import ModelService
    from app.modules.training.app.services.orchestrator import (
        TrainingOrchestrator,
    )
    from app.modules.prediction.app.services.prediction_orchestrator import (
        PredictionOrchestrator,
    )
    from app.modules.schedules.app.services.scheduler import SchedulerService

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definition helpers
# ---------------------------------------------------------------------------


def _fn(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


# ---------------------------------------------------------------------------
# Read tool definitions
# ---------------------------------------------------------------------------

READ_TOOLS: list[dict[str, Any]] = [
    _fn(
        "list_datasets",
        "List all datasets in the current organization. Returns id, name, type, sample count.",
        _obj({}),
    ),
    _fn(
        "get_dataset",
        "Get detailed info about a dataset: sample count, label space, annotation stats.",
        _obj({"dataset_id": {"type": "string"}}, required=["dataset_id"]),
    ),
    _fn(
        "list_training_jobs",
        "List training jobs. Optionally filter by dataset_id or status.",
        _obj(
            {
                "dataset_id": {"type": "string", "description": "Filter by dataset"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "completed", "failed", "cancelled"],
                },
            }
        ),
    ),
    _fn(
        "get_training_job",
        "Get details of a specific training job.",
        _obj({"job_id": {"type": "string"}}, required=["job_id"]),
    ),
    _fn(
        "list_trainers",
        "List available trainers with their names and IDs.",
        _obj({}),
    ),
    _fn(
        "list_models",
        "List trained model artifacts. Optionally filter by dataset_id.",
        _obj({"dataset_id": {"type": "string", "description": "Filter by dataset"}}),
    ),
    _fn(
        "list_prediction_jobs",
        "List prediction/inference jobs.",
        _obj({}),
    ),
    _fn(
        "list_schedules",
        "List cron-based training schedules.",
        _obj({}),
    ),
    _fn(
        "get_dashboard",
        "Get overall platform dashboard statistics: dataset count, job count, model count.",
        _obj({}),
    ),
    _fn(
        "query_data",
        (
            "Run a read-only data query against a dataset. "
            "Supported query_type: annotation-stats, sample-slice, "
            "metadata-histogram, recent-annotations, prediction-summary."
        ),
        _obj(
            {
                "dataset_id": {"type": "string"},
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
            required=["dataset_id", "query_type"],
        ),
    ),
]

# ---------------------------------------------------------------------------
# Write tool definitions
# ---------------------------------------------------------------------------

WRITE_TOOLS: list[dict[str, Any]] = [
    _fn(
        "create_dataset",
        (
            "Create a new dataset. Requires a name and label_space. "
            "Always confirm with the user before calling."
        ),
        _obj(
            {
                "name": {
                    "type": "string",
                    "description": "Human-readable dataset name",
                },
                "task_type": {
                    "type": "string",
                    "enum": ["classification", "vqa"],
                    "description": "Task type (default: classification)",
                },
                "label_space": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of valid label names",
                },
            },
            required=["name", "label_space"],
        ),
    ),
    _fn(
        "start_training_job",
        (
            "Start a training job on a dataset with a trainer. "
            "Always confirm with the user before calling."
        ),
        _obj(
            {
                "dataset_id": {"type": "string"},
                "trainer_id": {"type": "string"},
            },
            required=["dataset_id", "trainer_id"],
        ),
    ),
    _fn(
        "run_predictions",
        (
            "Run model predictions on a dataset. "
            "Always confirm with the user before calling."
        ),
        _obj(
            {
                "dataset_id": {"type": "string"},
                "model_id": {"type": "string"},
                "target": {
                    "type": "string",
                    "description": "Prediction target (default: image_classification)",
                },
            },
            required=["dataset_id", "model_id"],
        ),
    ),
    _fn(
        "create_schedule",
        (
            "Create a cron-based training schedule. "
            "Always confirm with the user before calling."
        ),
        _obj(
            {
                "name": {"type": "string"},
                "flow_name": {
                    "type": "string",
                    "description": "Prefect flow name (e.g. 'train-job')",
                },
                "cron": {
                    "type": "string",
                    "description": "Cron expression (e.g. '0 2 * * *')",
                },
                "parameters": {"type": "object", "description": "Flow parameters"},
                "description": {"type": "string"},
            },
            required=["name", "flow_name", "cron"],
        ),
    ),
    _fn(
        "cancel_training_job",
        ("Cancel a running training job. Always confirm with the user before calling."),
        _obj({"job_id": {"type": "string"}}, required=["job_id"]),
    ),
]

# ---------------------------------------------------------------------------
# Sidebar tool definitions (only enabled on classify page)
# ---------------------------------------------------------------------------

SIDEBAR_TOOLS: list[dict[str, Any]] = [
    _fn(
        "set_panel",
        "Add or replace a panel on the classify sidebar display surface.",
        _obj(
            {
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
            required=["id", "component", "title"],
        ),
    ),
    _fn(
        "remove_panel",
        "Remove a panel from the classify sidebar by its panel ID.",
        _obj({"panel_id": {"type": "string"}}, required=["panel_id"]),
    ),
    _fn(
        "get_surface_state",
        "Read the current panels on the classify sidebar display surface.",
        _obj({}),
    ),
]


def get_tool_definitions(context: AgentContext) -> list[dict[str, Any]]:
    """Return the tool definitions appropriate for the current context.

    Sidebar tools are only included when the user is on a classify page.
    """
    tools = READ_TOOLS + WRITE_TOOLS
    if context.page and "/classify" in context.page:
        tools = tools + SIDEBAR_TOOLS
    return tools


# ---------------------------------------------------------------------------
# Tool implementations — reads
# ---------------------------------------------------------------------------

MAX_PANELS = 8


async def execute_list_datasets(
    *, repository: SqlRepository, org_id: str
) -> dict[str, Any]:
    datasets = await repository.list_datasets(org_id=org_id)
    return {
        "datasets": [
            {
                "id": d.id,
                "name": d.name,
                "dataset_type": str(d.dataset_type) if d.dataset_type else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in datasets
        ],
        "count": len(datasets),
    }


async def execute_get_dataset(
    *,
    dataset_id: str,
    repository: SqlRepository,
    factory: DatasetStorageFactory | None = None,
    org_id: str,
) -> dict[str, Any]:
    dataset = await repository.get_dataset(dataset_id, org_id=org_id)
    if dataset is None:
        return {"error": f"Dataset '{dataset_id}' not found"}
    if factory is not None:
        storage = await factory.open(dataset_id, org_id)
        stats = await storage.get_annotation_stats()
    else:
        stats = await repository.get_annotation_stats(dataset_id)
    task_spec = dataset.task_spec
    label_space: list[str] = []
    if task_spec and hasattr(task_spec, "label_space"):
        label_space = task_spec.label_space
    elif isinstance(task_spec, dict):
        label_space = task_spec.get("label_space", [])
    return {
        "id": dataset.id,
        "name": dataset.name,
        "dataset_type": str(dataset.dataset_type) if dataset.dataset_type else None,
        "label_space": label_space,
        "sample_count": stats.get("total_samples", 0),
        "annotated_samples": stats.get("annotated_samples", 0),
        "unlabeled_samples": stats.get("unlabeled_samples", 0),
        "label_counts": stats.get("label_counts", {}),
        "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
    }


async def execute_list_training_jobs(
    *,
    repository: SqlRepository,
    org_id: str,
    dataset_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    jobs = await repository.list_jobs(org_id=org_id)
    results = []
    for j in jobs:
        if dataset_id and j.dataset_id != dataset_id:
            continue
        if status and str(j.status).lower() != status.lower():
            continue
        results.append(
            {
                "id": j.id,
                "dataset_id": j.dataset_id,
                "trainer_id": j.trainer_id,
                "status": str(j.status),
                "created_by": j.created_by,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
        )
    return {"jobs": results, "count": len(results)}


async def execute_get_training_job(
    *, job_id: str, repository: SqlRepository, org_id: str
) -> dict[str, Any]:
    job = await repository.get_job(job_id, org_id=org_id)
    if job is None:
        return {"error": f"Training job '{job_id}' not found"}
    return {
        "id": job.id,
        "dataset_id": job.dataset_id,
        "trainer_id": job.trainer_id,
        "status": str(job.status),
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


async def execute_list_trainers(*, trainer_registry: Any = None) -> dict[str, Any]:
    from app.modules.types import catalog

    trainers = [
        catalog.get_trainer_meta(trainer_id)
        for trainer_id in catalog.list_trainer_ids()
    ]
    return {
        "trainers": [
            {
                "id": t["id"],
                "name": t["name"],
                "trainable": True,
            }
            for t in trainers
        ],
        "count": len(trainers),
    }


async def execute_list_models(
    *, model_service: ModelService, org_id: str, dataset_id: str | None = None
) -> dict[str, Any]:
    models = await model_service.list_models(org_id=org_id, dataset_id=dataset_id)
    return {
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "job_id": m.job_id,
                "dataset_id": m.dataset_id,
                "trainer_id": m.trainer_id,
                "format": m.format,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in models
        ],
        "count": len(models),
    }


async def execute_list_prediction_jobs(
    *, repository: SqlRepository, org_id: str
) -> dict[str, Any]:
    jobs = await repository.list_prediction_jobs(org_id=org_id)
    return {
        "jobs": [
            {
                "id": j.id,
                "dataset_id": j.dataset_id,
                "model_id": j.model_id,
                "status": str(j.status),
                "target": j.target,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ],
        "count": len(jobs),
    }


async def execute_list_schedules(
    *, scheduler_service: SchedulerService, org_id: str
) -> dict[str, Any]:
    schedules = await scheduler_service.list_schedules(org_id=org_id)
    return {
        "schedules": [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "cron": s.get("cron"),
                "is_active": s.get("is_schedule_active", not s.get("paused", False)),
            }
            for s in schedules
        ],
        "count": len(schedules),
    }


async def execute_get_dashboard(
    *, repository: SqlRepository, org_id: str
) -> dict[str, Any]:
    datasets = await repository.list_datasets(org_id=org_id)
    jobs = await repository.list_jobs(org_id=org_id)
    running = [j for j in jobs if str(j.status).lower() == "running"]
    completed = [j for j in jobs if str(j.status).lower() == "completed"]
    failed = [j for j in jobs if str(j.status).lower() == "failed"]
    return {
        "dataset_count": len(datasets),
        "job_count": len(jobs),
        "jobs_running": len(running),
        "jobs_completed": len(completed),
        "jobs_failed": len(failed),
    }


async def execute_query_data(
    *,
    dataset_id: str,
    query_type: str,
    params: dict[str, Any] | None,
    factory: DatasetStorageFactory,
    session_factory: async_sessionmaker | None = None,
    org_id: str,
) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Tool implementations — writes
# ---------------------------------------------------------------------------


async def execute_create_dataset(
    *,
    name: str,
    label_space: list[str],
    task_type: str | None,
    repository: SqlRepository,
    org_id: str,
    label_studio_client: LabelStudioClient,
    user_id: str,
) -> dict[str, Any]:
    """Create a new dataset with a Label Studio project."""
    from app.shared.api.schemas import Dataset, TaskSpec

    tt = "vqa" if task_type == "vqa" else "classification"
    ds_type = "image_vqa" if tt == "vqa" else "image_classification"

    # Create LS project
    try:
        from app.shared.infrastructure.label_studio.client import (
            LabelStudioClient as _LSC,
        )

        if tt == "vqa":
            label_config = _LSC.generate_vqa_config()
        else:
            label_config = _LSC.generate_image_classification_config(label_space)
        project = await label_studio_client.create_project(name, label_config)
        ls_project_id = str(project.get("id", ""))
        if not ls_project_id:
            return {"error": "Label Studio project creation returned no ID"}
    except Exception as exc:
        return {"error": f"Label Studio project creation failed: {exc}"}

    dataset = Dataset(
        name=name,
        dataset_type=ds_type,
        task_spec=TaskSpec(task_type=tt, label_space=label_space),
        org_id=org_id,
        ls_project_id=ls_project_id,
    )
    created = await repository.create_dataset(dataset)
    return {"id": created.id, "name": created.name, "status": "created"}


async def execute_start_training_job(
    *,
    dataset_id: str,
    trainer_id: str,
    repository: SqlRepository,
    org_id: str,
    orchestrator: TrainingOrchestrator,
    user_id: str,
) -> dict[str, Any]:
    from app.modules.types import catalog
    from app.shared.api.schemas import TrainingJob

    dataset = await repository.get_dataset(dataset_id, org_id=org_id)
    if dataset is None:
        return {"error": f"Dataset '{dataset_id}' not found"}
    try:
        catalog.get_trainer_meta(trainer_id)
    except KeyError:
        return {"error": f"Trainer '{trainer_id}' not found"}

    job = TrainingJob(
        dataset_id=dataset_id,
        trainer_id=trainer_id,
        created_by=user_id,
        org_id=org_id,
    )
    started = await orchestrator.start_job(job)
    return {
        "id": started.id,
        "status": str(started.status),
        "dataset_id": dataset_id,
        "trainer_id": trainer_id,
    }


async def execute_run_predictions(
    *,
    dataset_id: str,
    model_id: str,
    target: str | None,
    repository: SqlRepository,
    org_id: str,
    prediction_orchestrator: PredictionOrchestrator,
    user_id: str,
) -> dict[str, Any]:
    """Run predictions on a dataset."""
    from app.shared.api.schemas import PredictionJob

    dataset = await repository.get_dataset(dataset_id, org_id=org_id)
    if dataset is None:
        return {"error": f"Dataset '{dataset_id}' not found"}

    job = PredictionJob(
        dataset_id=dataset_id,
        model_id=model_id,
        created_by=user_id,
        target=target or "image_classification",
        org_id=org_id,
    )
    started = await prediction_orchestrator.start_job(job)
    return {
        "id": started.id,
        "status": str(started.status),
        "dataset_id": dataset_id,
        "model_id": model_id,
    }


async def execute_create_schedule(
    *,
    name: str,
    flow_name: str,
    cron: str,
    parameters: dict[str, Any] | None,
    description: str | None,
    scheduler_service: SchedulerService,
    org_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Create a cron-based schedule."""
    try:
        raw = await scheduler_service.create_schedule(
            org_id=org_id,
            created_by=user_id,
            name=name,
            flow_name=flow_name,
            cron=cron,
            parameters=parameters or {},
            description=description or "",
        )
        return {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "cron": raw.get("cron"),
            "status": "created",
        }
    except Exception as exc:
        return {"error": f"Failed to create schedule: {exc}"}


async def execute_cancel_training_job(
    *,
    job_id: str,
    orchestrator: TrainingOrchestrator,
    repository: SqlRepository,
    org_id: str,
) -> dict[str, Any]:
    """Cancel a running training job."""
    job = await repository.get_job(job_id, org_id=org_id)
    if job is None:
        return {"error": f"Training job '{job_id}' not found"}
    ok = await orchestrator.cancel_job(job_id)
    if ok:
        return {"id": job_id, "status": "cancelled"}
    return {
        "error": f"Could not cancel job '{job_id}' — it may already be completed or not running."
    }


# ---------------------------------------------------------------------------
# Tool implementations — sidebar
# ---------------------------------------------------------------------------


async def execute_set_panel(
    *,
    session_id: str,
    surface_id: str,
    surface_store: SurfaceStore,
    **panel_kwargs: Any,
) -> dict[str, Any]:
    """Add or replace a panel on the sidebar surface."""
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
    """Remove a panel from the sidebar surface."""
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
    """Read current sidebar surface state."""
    doc = await surface_store.get_state(session_id, surface_id)
    return doc.model_dump(mode="json")
