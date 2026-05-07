from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Any, Callable

from mcp.types import Tool

_logger = logging.getLogger(__name__)


ToolHandler = Callable[[dict[str, Any]], Any]


def load_plugin_tools() -> tuple[list[Tool], dict[str, ToolHandler]]:
    """Load additional MCP tools from finetune_mcp.plugins modules."""
    tools: list[Tool] = []
    handlers: dict[str, ToolHandler] = {}

    package_name = "finetune_mcp.plugins"
    package = importlib.import_module(package_name)

    for module_info in pkgutil.iter_modules(package.__path__):
        module_name = module_info.name
        if module_name.startswith("_") or module_name == "loader":
            continue

        full_name = f"{package_name}.{module_name}"
        try:
            module = importlib.import_module(full_name)
        except Exception as exc:
            _logger.exception(
                "Failed to import MCP plugin module %s: %s", full_name, exc
            )
            continue

        module_tools = getattr(module, "TOOLS", None)
        module_handlers = getattr(module, "HANDLERS", None)

        if not isinstance(module_tools, list) or not isinstance(module_handlers, dict):
            _logger.warning(
                "Skipping MCP plugin module %s: expected TOOLS(list) and HANDLERS(dict)",
                full_name,
            )
            continue

        for tool in module_tools:
            if not isinstance(tool, Tool):
                continue
            if tool.name in handlers:
                _logger.warning(
                    "Skipping duplicate MCP plugin tool name: %s", tool.name
                )
                continue
            handler = module_handlers.get(tool.name)
            if not callable(handler):
                _logger.warning(
                    "Skipping MCP plugin tool %s from %s: missing callable handler",
                    tool.name,
                    full_name,
                )
                continue
            tools.append(tool)
            handlers[tool.name] = handler

        _logger.info(
            "Loaded MCP plugin module: %s (%d tools)", full_name, len(module_tools)
        )

    return tools, handlers
