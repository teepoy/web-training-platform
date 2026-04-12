"""MCP server exposing finetune platform tools.

Tools:
  - list_datasets        — enumerate datasets in the org
  - get_dataset          — fetch dataset details
  - query_data           — run structured data queries
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
