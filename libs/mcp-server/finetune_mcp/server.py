"""MCP server exposing finetune platform tools.

Tools — Read:
  - list_datasets        — enumerate datasets in the org
  - get_dataset          — fetch dataset details
  - query_data           — run structured data queries
  - list_jobs            — list training jobs
  - get_job              — get training job details
  - list_presets         — list available training presets
  - list_models          — list trained model artifacts
  - list_prediction_jobs — list prediction/inference jobs
  - list_schedules       — list cron-based schedules

Tools — Write:
  - create_dataset       — create a new dataset
  - create_job           — start a training job
  - cancel_job           — cancel a running training job
  - run_predictions      — run model predictions on a dataset
  - create_schedule      — create a cron-based schedule
  - delete_schedule      — delete a schedule

Tools — Agent:
  - agent_chat           — send a message to the platform's global AI agent

Tools — Surface:
  - get_surface_state    — read sidebar panel state
  - set_panel            — add/replace a sidebar panel
  - remove_panel         — remove a sidebar panel
  - export_surface       — export a surface state document
  - import_surface       — import a surface state document

Run:
  finetune-mcp          # stdio transport (default)
  finetune-mcp --sse    # SSE transport on port 8100

Environment:
  FINETUNE_API_URL      — platform API (default http://localhost:8000/api/v1)
  FINETUNE_API_TOKEN    — bearer token (optional)
  FINETUNE_ORG_ID       — default org (optional)
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from finetune_mcp.client import PlatformClient
from finetune_mcp.config import McpConfig

_logger = logging.getLogger("finetune-mcp")

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

_server = Server("finetune-mcp")
_config = McpConfig.from_env()
_client = PlatformClient(_config)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_TOOLS: list[Tool] = [
    # ----- Read tools -----
    Tool(
        name="list_datasets",
        description="List all datasets in the current organization.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_dataset",
        description="Get detailed information about a dataset.",
        inputSchema={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "Dataset UUID"},
            },
            "required": ["dataset_id"],
        },
    ),
    Tool(
        name="query_data",
        description=(
            "Run a read-only data query against a dataset. "
            "Supported query_type: annotation-stats, sample-slice, "
            "metadata-histogram, recent-annotations, prediction-summary."
        ),
        inputSchema={
            "type": "object",
            "properties": {
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
                "params": {"type": "object", "description": "Query-specific parameters"},
            },
            "required": ["dataset_id", "query_type"],
        },
    ),
    Tool(
        name="list_jobs",
        description="List training jobs.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_job",
        description="Get detailed information about a training job.",
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Training job UUID"},
            },
            "required": ["job_id"],
        },
    ),
    Tool(
        name="list_presets",
        description="List available training presets with their names and IDs.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="list_models",
        description="List trained model artifacts. Optionally filter by dataset_id.",
        inputSchema={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "Filter by dataset UUID"},
            },
        },
    ),
    Tool(
        name="list_prediction_jobs",
        description="List prediction/inference jobs.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="list_schedules",
        description="List cron-based training schedules.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    # ----- Write tools -----
    Tool(
        name="create_dataset",
        description=(
            "Create a new dataset. Requires a name. "
            "Optionally provide task_spec with label_space."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human-readable dataset name"},
                "task_spec": {
                    "type": "object",
                    "description": "Task specification with label_space",
                    "properties": {
                        "label_space": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of valid label names",
                        },
                    },
                },
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="create_job",
        description=(
            "Start a training job on a dataset with a preset."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "Dataset UUID"},
                "preset_id": {"type": "string", "description": "Training preset UUID"},
            },
            "required": ["dataset_id", "preset_id"],
        },
    ),
    Tool(
        name="cancel_job",
        description="Cancel a running training job.",
        inputSchema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Training job UUID"},
            },
            "required": ["job_id"],
        },
    ),
    Tool(
        name="run_predictions",
        description="Run model predictions on a dataset.",
        inputSchema={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "Dataset UUID"},
                "model_id": {"type": "string", "description": "Model UUID"},
                "target": {"type": "string", "description": "Prediction target (default: image_classification)"},
            },
            "required": ["dataset_id", "model_id"],
        },
    ),
    Tool(
        name="create_schedule",
        description="Create a cron-based training schedule.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "flow_name": {"type": "string", "description": "Prefect flow name (e.g. 'train-job')"},
                "cron": {"type": "string", "description": "Cron expression (e.g. '0 2 * * *')"},
                "parameters": {"type": "object", "description": "Flow parameters"},
                "description": {"type": "string"},
            },
            "required": ["name", "flow_name", "cron"],
        },
    ),
    Tool(
        name="delete_schedule",
        description="Delete a schedule by ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "schedule_id": {"type": "string", "description": "Schedule UUID"},
            },
            "required": ["schedule_id"],
        },
    ),
    # ----- Agent tools -----
    Tool(
        name="agent_chat",
        description=(
            "Send a message to the platform's global AI agent and receive its "
            "response. The agent is context-aware, has full platform knowledge, "
            "and can perform read/write operations (list datasets, start training, "
            "run predictions, manage schedules, etc.). Pass a session_id to "
            "maintain conversation continuity across multiple messages."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to send to the agent",
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "Session ID for conversation continuity. "
                        "Reuse the same ID across messages to maintain context."
                    ),
                },
                "context": {
                    "type": "object",
                    "description": (
                        "Optional navigation context to make the agent "
                        "aware of the user's current page/resource."
                    ),
                    "properties": {
                        "route": {
                            "type": "string",
                            "description": "Current page route (e.g. '/datasets', '/classify/uuid')",
                        },
                        "dataset_id": {
                            "type": "string",
                            "description": "Active dataset UUID, if on a dataset-specific page",
                        },
                    },
                },
            },
            "required": ["message"],
        },
    ),
    # ----- Surface tools -----
    Tool(
        name="get_surface_state",
        description="Read the current sidebar panel state for a session.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "surface_id": {"type": "string", "default": "classify-sidebar"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="set_panel",
        description=(
            "Add or replace a panel on the sidebar display surface. "
            "Panel descriptor includes id, component, title, data, config, order, size."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "surface_id": {"type": "string", "default": "classify-sidebar"},
                "panel": {
                    "type": "object",
                    "description": "Panel descriptor",
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
                        "data": {"type": "object"},
                        "config": {"type": "object"},
                        "order": {"type": "integer", "minimum": 0},
                        "size": {"type": "string", "enum": ["compact", "normal", "large"]},
                        "ephemeral": {"type": "boolean"},
                    },
                    "required": ["id", "component", "title"],
                },
            },
            "required": ["session_id", "panel"],
        },
    ),
    Tool(
        name="remove_panel",
        description="Remove a panel from the sidebar by its panel ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "surface_id": {"type": "string", "default": "classify-sidebar"},
                "panel_id": {"type": "string"},
            },
            "required": ["session_id", "panel_id"],
        },
    ),
    Tool(
        name="export_surface",
        description="Export the full surface state document (panels, layout, metadata).",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "surface_id": {"type": "string", "default": "classify-sidebar"},
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="import_surface",
        description="Import a surface state document, replacing all current panels.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "surface_id": {"type": "string", "default": "classify-sidebar"},
                "document": {
                    "type": "object",
                    "description": "SurfaceStateDocument JSON",
                },
            },
            "required": ["session_id", "document"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@_server.list_tools()
async def list_tools() -> list[Tool]:
    return _TOOLS


@_server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls to the platform API client."""
    try:
        result = _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as exc:
        _logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]


def _dispatch(name: str, args: dict[str, Any]) -> Any:
    """Route a tool call to the appropriate client method."""
    # ----- Read tools -----
    if name == "list_datasets":
        return _client.list_datasets()

    elif name == "get_dataset":
        return _client.get_dataset(args["dataset_id"])

    elif name == "query_data":
        return _client.query_data(
            dataset_id=args["dataset_id"],
            query_type=args["query_type"],
            params=args.get("params"),
        )

    elif name == "list_jobs":
        return _client.list_jobs()

    elif name == "get_job":
        return _client.get_job(args["job_id"])

    elif name == "list_presets":
        return _client.list_presets()

    elif name == "list_models":
        return _client.list_models(dataset_id=args.get("dataset_id"))

    elif name == "list_prediction_jobs":
        return _client.list_prediction_jobs()

    elif name == "list_schedules":
        return _client.list_schedules()

    # ----- Write tools -----
    elif name == "create_dataset":
        body: dict[str, Any] = {"name": args["name"]}
        if "task_spec" in args:
            body["task_spec"] = args["task_spec"]
        return _client.create_dataset(body)

    elif name == "create_job":
        return _client.create_job({
            "dataset_id": args["dataset_id"],
            "preset_id": args["preset_id"],
        })

    elif name == "cancel_job":
        return _client.cancel_job(args["job_id"])

    elif name == "run_predictions":
        body_pred: dict[str, Any] = {
            "dataset_id": args["dataset_id"],
            "model_id": args["model_id"],
        }
        if "target" in args:
            body_pred["target"] = args["target"]
        return _client.run_predictions(body_pred)

    elif name == "create_schedule":
        body_sched: dict[str, Any] = {
            "name": args["name"],
            "flow_name": args["flow_name"],
            "cron": args["cron"],
        }
        if "parameters" in args:
            body_sched["parameters"] = args["parameters"]
        if "description" in args:
            body_sched["description"] = args["description"]
        return _client.create_schedule(body_sched)

    elif name == "delete_schedule":
        return _client.delete_schedule(args["schedule_id"])

    # ----- Agent tools -----
    elif name == "agent_chat":
        return _client.agent_chat(
            message=args["message"],
            session_id=args.get("session_id"),
            context=args.get("context"),
        )

    # ----- Surface tools -----
    elif name == "get_surface_state":
        return _client.get_surface_state(
            session_id=args["session_id"],
            surface_id=args.get("surface_id", "classify-sidebar"),
        )

    elif name == "set_panel":
        return _client.set_panel(
            session_id=args["session_id"],
            surface_id=args.get("surface_id", "classify-sidebar"),
            panel=args["panel"],
        )

    elif name == "remove_panel":
        return _client.remove_panel(
            session_id=args["session_id"],
            surface_id=args.get("surface_id", "classify-sidebar"),
            panel_id=args["panel_id"],
        )

    elif name == "export_surface":
        return _client.export_surface(
            session_id=args["session_id"],
            surface_id=args.get("surface_id", "classify-sidebar"),
        )

    elif name == "import_surface":
        return _client.import_surface(
            session_id=args["session_id"],
            surface_id=args.get("surface_id", "classify-sidebar"),
            document=args["document"],
        )

    else:
        return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server on stdio transport."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    _logger.info(
        "Starting finetune-mcp server (api=%s)", _config.api_base_url
    )

    import asyncio
    asyncio.run(_run_stdio())


async def _run_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await _server.run(
            read_stream,
            write_stream,
            _server.create_initialization_options(),
        )


if __name__ == "__main__":
    main()
