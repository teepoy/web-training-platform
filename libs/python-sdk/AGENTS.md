# SDK KNOWLEDGE BASE

## OVERVIEW
Python SDK and CLI package (`ftsdk`) for simple platform operations: list datasets/jobs, inspect job status, stream job events, and expose agent-friendly wrappers.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Packaging / CLI entry | `pyproject.toml` | `ftctl = "ftsdk.cli:app"` |
| CLI commands | `ftsdk/cli.py` | `jobs ls/status/watch`, `datasets ls` |
| HTTP client | `ftsdk/client.py` | Sync `httpx` wrapper |
| Agent wrappers | `ftsdk/agent_tools.py` | Thin helpers around `FinetuneClient` |
| Public export | `ftsdk/__init__.py` | Re-exports `FinetuneClient` |

## CONVENTIONS
- Run via `uv run ftctl ...` or `uv run python -m ftsdk.cli ...`.
- `FinetuneClient` is synchronous and defaults to `http://localhost:8000/api/v1`.
- Bearer auth is optional and only attached when `token` is passed to `FinetuneClient`.
- `AgentTools.start_training()` defaults `created_by="agent"`; raw client defaults to `sdk-user`.

## ANTI-PATTERNS
- Don’t assume async compatibility; SDK calls block because they use `httpx.Client`.
- Don’t depend on built-in retry/backoff; none exists.
- Don’t hardcode more localhost assumptions without adding a config/env override path.
- Don’t treat CLI SSE streaming as a full SSE client; `jobs watch` only echoes `data:` lines.

## COMMANDS
```bash
uv run ftctl jobs ls
uv run ftctl jobs status --job-id <job-id>
uv run ftctl jobs watch --job-id <job-id>
uv run ftctl datasets ls
uv run python -m ftsdk.cli jobs ls
```

## GOTCHAS
- Standard client requests use a 15s timeout.
- HTTP errors raise directly via `resp.raise_for_status()`; catch `httpx` exceptions in callers.
- There are no SDK-specific tests yet.
