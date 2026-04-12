"""MCP server configuration.

Reads environment variables for platform connectivity.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class McpConfig:
    """Connection settings for the finetune platform API."""

    api_base_url: str
    api_token: str | None
    default_org_id: str | None

    @classmethod
    def from_env(cls) -> McpConfig:
        return cls(
            api_base_url=os.environ.get("FINETUNE_API_URL", "http://localhost:8000/api/v1"),
            api_token=os.environ.get("FINETUNE_API_TOKEN"),
            default_org_id=os.environ.get("FINETUNE_ORG_ID"),
        )
