# Agent Display Protocol

The agent display protocol defines how an AI agent controls dynamic UI panels on a **display surface** (e.g. the classify sidebar).

## Architecture

There are two agent runtimes:

1. **ClassifyAgent** (Phase 1) — A classify-page-specific agent that controls the sidebar and answers data queries. Accessed via `POST /datasets/{id}/agent/chat`.
2. **GlobalAgent** (Phase 2) — A platform-wide agent available on every authenticated page. Has full read/write access to the platform (datasets, jobs, predictions, schedules) plus sidebar control when on the classify page. Accessed via `POST /api/v1/agent/chat`.

```
                       +-------------------+
                       |  Agent Chat UI    |  (AgentChatDrawer.vue in App.vue)
                       |  Floating drawer  |
                       +--------+----------+
                                |
                   POST /api/v1/agent/chat
                       (SSE response stream)
                                |
                       +--------v----------+
                       |  GlobalAgent      |  (global_runtime.py)
                       |  Tool-calling     |
                       |  loop             |
                       +--------+----------+
                                |
          +----------+----------+----------+---------+
          |          |          |          |         |
  +-------v--+ +----v----+ +--v---+ +----v---+ +---v--------+
  |list_*    | |create_* | |query | |sidebar | |cancel_*   |
  |get_*     | |start_*  | |_data | |tools   | |delete_*   |
  |(read)    | |run_*    | |      | |        | |            |
  +----------+ |(write)  | +------+ +---+----+ +------------+
               +---------+              |
                                +-------v--------+
                                |  SurfaceStore  |
                                |  (in-memory)   |
                                +-------+--------+
                                        |
                                  SSE: sidebar-update
                                        |
                                +-------v--------+
                                | ClassifySidebar|
                                | (Vue component)|
                                +----------------+
```

### Session Persistence

The GlobalAgent uses a `SessionStore` (in-memory, TTL-based) to persist conversation history across requests within a session. Sessions are keyed by `session_id` (derived from user ID on the frontend). The classify-page ClassifyAgent does not persist sessions across requests.

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
| POST | `/datasets/{id}/agent/chat` | Classify agent — send message, receive SSE stream |
| POST | `/api/v1/agent/chat` | Global agent — send message with context, receive SSE stream |

Classify agent request body: `{"message": "string"}`

Global agent request body:
```json
{
  "message": "string",
  "context": {
    "page": "/datasets/abc/classify",
    "dataset_id": "abc",
    "job_id": null,
    "schedule_id": null
  },
  "session_id": "global-user123"
}
```

SSE event types in the response stream (same for both agents):
- `agent-message` — `{"content": "text response"}`
- `agent-action` — `{"tool": "tool_name", "summary": "description"}`
- `sidebar-update` — `{"surface_id": "...", "panels": [...]}`
- `done` — `{}`

## Agent Runtime

### ClassifyAgent (Phase 1)

The `ClassifyAgent` (in `app/agent/runtime.py`) implements a tool-calling loop:

1. User message arrives via POST
2. System prompt is assembled from dataset context (name, type, label space, annotation stats, metadata schema)
3. LLM is called with the conversation history + tool definitions
4. If LLM returns tool calls, they are executed and results fed back
5. Steps 3-4 repeat until LLM returns a text response (max 10 iterations)
6. Events are yielded as SSE frames throughout the loop

### GlobalAgent (Phase 2)

The `GlobalAgent` (in `app/agent/global_runtime.py`) extends the pattern:

1. User message arrives via `POST /api/v1/agent/chat` with context (page, dataset_id, job_id, etc.)
2. Session history is loaded from `SessionStore` (or created fresh)
3. System prompt is assembled from global context (available resources, current page, entity details)
4. LLM is called with conversation history + 18 tool definitions (10 read + 5 write + 3 sidebar when on classify)
5. Tool calls are executed with full service access (repository, orchestrator, prediction_orchestrator, scheduler_service, etc.)
6. Steps 4-5 repeat until text response (max 10 iterations)
7. Session history is persisted back to `SessionStore`
8. Events yielded as SSE frames

#### Global Agent Tools

**Read tools** (always available):
`list_datasets`, `get_dataset`, `list_training_jobs`, `get_training_job`, `list_presets`, `list_models`, `list_prediction_jobs`, `list_schedules`, `get_dashboard`, `query_data`

**Write tools** (always available, with user confirmation in system prompt):
`create_dataset`, `start_training_job`, `run_predictions`, `create_schedule`, `cancel_training_job`

**Sidebar tools** (only on classify page):
`set_panel`, `remove_panel`, `get_surface_state`

### Metadata Discovery

Two tiers:
1. **Declared schema** — Human-written key descriptions in `task_spec.metadata_schema`
2. **Inferred schema** — Polars-based (or pure-Python fallback) type scanning from sampled rows

The metadata block is assembled at session start and included in the system prompt.

## MCP Server

The `libs/mcp-server/` package exposes platform tools via the Model Context Protocol for external agent access:

```bash
FINETUNE_API_URL=http://localhost:8000/api/v1 finetune-mcp
```

**Read tools:** `list_datasets`, `get_dataset`, `query_data`, `list_jobs`, `get_job`, `list_presets`, `list_models`, `list_prediction_jobs`, `list_schedules`

**Write tools:** `create_dataset`, `create_job`, `cancel_job`, `run_predictions`, `create_schedule`, `delete_schedule`

**Agent tools:** `agent_chat` — send a message to the platform's built-in global AI agent and receive its response. Supports `session_id` for conversation continuity and `context` for page-aware responses.

**Surface tools:** `get_surface_state`, `set_panel`, `remove_panel`, `export_surface`, `import_surface`

## Constraints

- Max 8 panels per surface
- Inline data must be < 50KB
- Panel IDs: lowercase-kebab-case, max 80 chars
- Ephemeral panels auto-remove on next agent turn
- Surface state is in-memory (lost on API restart); use export/import for persistence
