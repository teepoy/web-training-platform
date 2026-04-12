# Agent Display Protocol

The agent display protocol defines how an AI agent controls dynamic UI panels on a **display surface** (e.g. the classify sidebar).

## Architecture

```
                       +-------------------+
                       |  Agent Chat UI    |  (AgentChatDrawer.vue)
                       |  Floating drawer  |
                       +--------+----------+
                                |
                   POST /datasets/{id}/agent/chat
                       (SSE response stream)
                                |
                       +--------v----------+
                       |  ClassifyAgent    |  (runtime.py)
                       |  Tool-calling     |
                       |  loop             |
                       +--------+----------+
                                |
              +-----------------+-----------------+
              |                                   |
    +---------v---------+              +----------v---------+
    |  query_data       |              |  set_panel         |
    |  (read-only DB)   |              |  remove_panel      |
    +-------------------+              |  get_surface_state |
                                       +----------+---------+
                                                  |
                                       +----------v---------+
                                       |  SurfaceStore      |
                                       |  (in-memory)       |
                                       +----------+---------+
                                                  |
                                         SSE: sidebar-update
                                                  |
                                       +----------v---------+
                                       |  ClassifySidebar   |
                                       |  (Vue component)   |
                                       +--------------------+
```

## Concepts

### Display Surface
A named rendering area where the agent places panels. Currently there is one:
- `classify-sidebar` — the right sidebar on the classify page

The pattern is generic and can be reused for other surfaces (job detail, dashboard, etc.).

### Panel Descriptor
Each panel on a surface is described by an `AgentPanelDescriptor`:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique lowercase-kebab-case identifier |
| `component` | string | Widget type key (see below) |
| `title` | string | Human-readable header |
| `order` | int | Sort priority (lower = higher, default 50) |
| `size` | string | `compact`, `normal`, or `large` |
| `data` | object | Inline data: `{inline: <payload>}` |
| `data_source` | object | Reference to API or context data source |
| `config` | object | Widget-specific config props |
| `ephemeral` | bool | Auto-remove on next agent turn if not re-sent |
| `ttl` | int | Auto-remove after N seconds |

### Surface State Document
The complete state of a surface is a `SurfaceStateDocument`:
```json
{
  "version": 1,
  "surface_id": "classify-sidebar",
  "panels": [ ...AgentPanelDescriptor[] ],
  "layout": { "width": 280, "position": "right" },
  "exported_at": null,
  "metadata": {}
}
```

## Data Binding

Panels support two data binding modes:

1. **Inline data** — Data embedded directly in the panel descriptor:
   ```json
   { "data": { "inline": { "metrics": [{"label": "Count", "value": "42"}] } } }
   ```

2. **Data source reference** — Points to an API endpoint or Vue context:
   ```json
   { "data_source": { "kind": "api", "endpoint": "/datasets/{id}/query", "params": {"query_type": "annotation-stats"} } }
   ```

## Widget Types

| Key | Renders | Data Shape |
|-----|---------|------------|
| `echarts-generic` | Any ECharts chart | Full `EChartsOption` object |
| `markdown-log` | Scrollable timestamped log | `{entries: [{ts, level, message}]}` |
| `data-table` | Sortable table | `{columns: string[], rows: any[][]}` |
| `metric-cards` | KPI card grid | `{metrics: [{label, value, color?}]}` |
| `sample-viewer` | Sample image grid/list | `{sampleIds: string[], mode: "grid"\|"list"}` |

## API Endpoints

### Surface CRUD

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sessions/{sid}/surfaces/{surf}` | Get current surface state |
| POST | `/sessions/{sid}/surfaces/{surf}/panels` | Add or replace a panel |
| DELETE | `/sessions/{sid}/surfaces/{surf}/panels/{pid}` | Remove a panel |
| GET | `/sessions/{sid}/surfaces/{surf}/export` | Export state document |
| POST | `/sessions/{sid}/surfaces/{surf}/import` | Import state document |

### Data Query

| Method | Path | Description |
|--------|------|-------------|
| POST | `/datasets/{id}/query` | Run a structured data query |

Supported `query_type` values:
- `annotation-stats` — aggregate counts and label distribution
- `sample-slice` — fetch N samples with latest labels
- `metadata-histogram` — value counts for one metadata key
- `recent-annotations` — latest annotations with sample info
- `prediction-summary` — prediction counts by model and label

### Agent Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/datasets/{id}/agent/chat` | Send message, receive SSE stream |

Request body: `{"message": "string"}`

SSE event types in the response stream:
- `agent-message` — `{"content": "text response"}`
- `agent-action` — `{"tool": "tool_name", "summary": "description"}`
- `sidebar-update` — `{"surface_id": "...", "panels": [...]}`
- `done` — `{}`

## Agent Runtime

The `ClassifyAgent` (in `app/agent/runtime.py`) implements a tool-calling loop:

1. User message arrives via POST
2. System prompt is assembled from dataset context (name, type, label space, annotation stats, metadata schema)
3. LLM is called with the conversation history + tool definitions
4. If LLM returns tool calls, they are executed and results fed back
5. Steps 3-4 repeat until LLM returns a text response (max 10 iterations)
6. Events are yielded as SSE frames throughout the loop

### Metadata Discovery

Two tiers:
1. **Declared schema** — Human-written key descriptions in `task_spec.metadata_schema`
2. **Inferred schema** — Polars-based (or pure-Python fallback) type scanning from sampled rows

The metadata block is assembled at session start and included in the system prompt.

## MCP Server

The `libs/mcp-server/` package exposes the same tools via the Model Context Protocol for external agent access:

```bash
FINETUNE_API_URL=http://localhost:8000/api/v1 finetune-mcp
```

Tools: `list_datasets`, `get_dataset`, `query_data`, `get_surface_state`, `set_panel`, `remove_panel`, `export_surface`, `import_surface`.

## Constraints

- Max 8 panels per surface
- Inline data must be < 50KB
- Panel IDs: lowercase-kebab-case, max 80 chars
- Ephemeral panels auto-remove on next agent turn
- Surface state is in-memory (lost on API restart); use export/import for persistence
