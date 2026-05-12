# MCP Server (Archived Feature)

> **Status**: Extracted from monorepo. Previously at `libs/mcp-server/`.
> **Purpose**: Exposed platform tools (datasets, jobs, schedules, samples, agent chat) via the Model Context Protocol for external AI agent access.

## Architecture (historical)

```
libs/mcp-server/
├── finetune_mcp/
│   ├── server.py       # MCP server with 18 tools (read/write/agent/surface)
│   ├── client.py       # HTTP client wrapper for the MCP server
│   ├── config.py       # Server configuration
│   └── plugins/
│       ├── loader.py   # Auto-discovers tool modules with TOOLS + dispatch()
│       └── core_tools.py  # Placeholder (0 tools at time of extraction)
└── pyproject.toml
```

## Tools Provided

The MCP server exposed these tool categories:
- **Read tools**: list datasets, samples, jobs, schedules; get details
- **Write tools**: create datasets, start training jobs, update labels
- **Agent tools**: send agent messages, get conversation state
- **Surface tools**: inject sidebar panels, update dashboard state

## Why Extracted

- Zero integration with the main platform at runtime
- No Docker Compose or deployment manifest references
- No test coverage
- The LLM agent integration is handled directly via the frontend SSE agent chat system
- Added unnecessary dependency complexity (`mcp>=1.0.0`, `httpx`, `pydantic`)

## Migration Path

If MCP-based external agent access is needed in the future, the server can be:
1. Re-implemented as a standalone service that consumes the platform's REST API
2. Deployed alongside the platform as a sidecar container
3. Maintained in a separate repository
