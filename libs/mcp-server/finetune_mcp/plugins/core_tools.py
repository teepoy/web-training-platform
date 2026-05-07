"""Built-in MCP core tools placeholder.

This module exists to keep the plugins package structure explicit.
Built-in tools currently remain in finetune_mcp.server.
"""

from __future__ import annotations

from typing import Any, Callable

from mcp.types import Tool

TOOLS: list[Tool] = []
HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {}
