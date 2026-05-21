"""Shared agent event models used by classify and global agent runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentMessage:
    """Text response from the agent."""

    content: str


@dataclass
class AgentAction:
    """Agent performed a tool call."""

    tool: str
    summary: str
    result: dict[str, Any] | None = None


@dataclass
class AgentSidebarUpdate:
    """Sidebar state changed."""

    surface_id: str
    panels: list[dict[str, Any]]


@dataclass
class AgentDone:
    """Agent finished processing this turn."""

    pass


AgentEvent = AgentMessage | AgentAction | AgentSidebarUpdate | AgentDone
