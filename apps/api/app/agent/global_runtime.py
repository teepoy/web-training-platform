"""Global agent runtime — platform-wide tool-calling loop.

The ``GlobalAgent`` extends the agent pattern established by
``ClassifyAgent`` to the entire platform.  Key differences:

- **Session persistence** via :class:`SessionStore` (multi-turn memory
  survives across HTTP requests for the same ``session_id``).
- **Context-aware tool set** — sidebar tools are only available on the
  classify page; read/write tools are always available.
- **Write-operation dispatch** — can create datasets, start training,
  run predictions, manage schedules (all with confirmation rules in the
  system prompt).

Events are yielded as they happen so the caller can stream them over SSE.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from app.agent.global_assembler import assemble_global_prompt
from app.agent.global_tools import (
    get_tool_definitions,
    # Read tool executors
    execute_list_datasets,
    execute_get_dataset,
    execute_list_training_jobs,
    execute_get_training_job,
    execute_list_presets,
    execute_list_models,
    execute_list_prediction_jobs,
    execute_list_schedules,
    execute_get_dashboard,
    execute_query_data,
    # Write tool executors
    execute_create_dataset,
    execute_start_training_job,
    execute_run_predictions,
    execute_create_schedule,
    execute_cancel_training_job,
    # Sidebar tool executors
    execute_set_panel,
    execute_remove_panel,
    execute_get_surface_state,
)
from app.agent.runtime import (
    AgentAction,
    AgentDone,
    AgentEvent,
    AgentMessage,
    AgentSidebarUpdate,
)
from app.agent.session_store import SessionStore
from app.agent.surface_store import SurfaceStore
from app.api.schemas import AgentContext

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM client wrapper (shared with ClassifyAgent pattern)
# ---------------------------------------------------------------------------

# Re-export so existing test patches against ``app.agent.global_runtime._call_llm``
# continue to work without changes.
from app.services.llm import call_llm as _call_llm  # noqa: F401


# ---------------------------------------------------------------------------
# Global Agent
# ---------------------------------------------------------------------------


class GlobalAgent:
    """Platform-wide agent with multi-turn memory and expanded tool set.

    Parameters
    ----------
    llm_base_url / llm_api_key / llm_model:
        LLM connection settings.
    session_store:
        Persistent conversation memory.
    surface_store:
        In-memory sidebar panel state (for classify page).
    repository:
        SQL repository for data access.
    orchestrator:
        Training job orchestrator.
    prediction_orchestrator:
        Prediction job orchestrator.
    scheduler_service:
        Schedule CRUD.
    model_service:
        Model listing.
    preset_registry:
        Preset listing/lookup.
    label_studio_client:
        Label Studio project creation (needed for create_dataset).
    """

    def __init__(
        self,
        *,
        llm_base_url: str,
        llm_api_key: str,
        llm_model: str,
        session_store: SessionStore,
        surface_store: SurfaceStore,
        repository: Any,
        orchestrator: Any,
        prediction_orchestrator: Any,
        scheduler_service: Any,
        model_service: Any,
        preset_registry: Any,
        label_studio_client: Any,
    ) -> None:
        self._llm_base_url = llm_base_url
        self._llm_api_key = llm_api_key
        self._llm_model = llm_model
        self._session_store = session_store
        self._surface_store = surface_store
        self._repository = repository
        self._orchestrator = orchestrator
        self._prediction_orchestrator = prediction_orchestrator
        self._scheduler_service = scheduler_service
        self._model_service = model_service
        self._preset_registry = preset_registry
        self._label_studio_client = label_studio_client

    async def handle_message(
        self,
        *,
        session_id: str,
        user_id: str,
        user_email: str,
        org_id: str,
        org_name: str,
        context: AgentContext,
        user_message: str,
    ) -> AsyncIterator[AgentEvent]:
        """Process a user message and yield SSE-compatible events.

        The conversation history is loaded from ``session_store``, appended
        to, and persisted back after each LLM turn.
        """
        # Ensure session exists
        session = await self._session_store.get_or_create(session_id, user_id)

        # Build system prompt with platform context
        dataset_info: dict[str, Any] | None = None
        if context.dataset_id:
            try:
                from app.agent.global_tools import execute_get_dataset as _get_ds
                dataset_info = await _get_ds(
                    dataset_id=context.dataset_id,
                    repository=self._repository,
                    org_id=org_id,
                )
                if dataset_info and "error" in dataset_info:
                    dataset_info = None
            except Exception:
                _logger.debug("Failed to enrich dataset context", exc_info=True)

        platform_stats: dict[str, Any] | None = None
        try:
            from app.agent.global_tools import execute_get_dashboard as _get_dash
            platform_stats = await _get_dash(repository=self._repository, org_id=org_id)
        except Exception:
            _logger.debug("Failed to get platform stats", exc_info=True)

        system_prompt = await assemble_global_prompt(
            context=context,
            user_email=user_email,
            org_id=org_id,
            org_name=org_name,
            dataset_info=dataset_info,
            platform_stats=platform_stats,
        )

        # Load existing conversation and append the new user message
        messages = await self._session_store.get_messages(session_id)
        messages.append({"role": "user", "content": user_message})

        # Get the context-appropriate tools
        tools = get_tool_definitions(context)

        # Derive surface_id for sidebar operations
        surface_id = f"classify-{context.dataset_id}" if context.dataset_id else ""

        # Clear ephemeral panels if on classify page
        if surface_id and context.page and "/classify" in context.page:
            await self._surface_store.clear_ephemeral(session_id, surface_id)

        # Collect new messages produced this turn for later persistence
        new_messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

        max_iterations = 10
        for _ in range(max_iterations):
            try:
                response = await _call_llm(
                    base_url=self._llm_base_url,
                    api_key=self._llm_api_key,
                    model=self._llm_model,
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=tools,
                )
            except Exception as e:
                _logger.exception("LLM call failed")
                error_msg = f"Sorry, I encountered an error communicating with the AI model: {e}"
                yield AgentMessage(content=error_msg)
                new_messages.append({"role": "assistant", "content": error_msg})
                break

            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})

            # Append assistant message to the running conversation
            messages.append(message)
            new_messages.append(message)

            tool_calls = message.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}

                    # Execute the tool
                    result = await self._execute_tool(
                        tool_name, args,
                        session_id=session_id,
                        surface_id=surface_id,
                        org_id=org_id,
                        user_id=user_id,
                    )

                    summary = self._summarise_tool_call(tool_name, args, result)
                    yield AgentAction(tool=tool_name, summary=summary, result=result)

                    # If sidebar mutation, emit update
                    if tool_name in ("set_panel", "remove_panel") and surface_id:
                        state = await self._surface_store.get_state(session_id, surface_id)
                        yield AgentSidebarUpdate(
                            surface_id=surface_id,
                            panels=[p.model_dump(mode="json") for p in state.panels],
                        )

                    # Feed tool result back
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(result, default=str),
                    }
                    messages.append(tool_msg)
                    new_messages.append(tool_msg)
            else:
                # No tool calls — agent is done
                content = message.get("content", "")
                if content:
                    yield AgentMessage(content=content)
                break

        # Persist new messages to the session store
        await self._session_store.append_messages(session_id, new_messages)

        yield AgentDone()

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        session_id: str,
        surface_id: str,
        org_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Dispatch a tool call to its implementation."""
        try:
            # -- Read tools --
            if name == "list_datasets":
                return await execute_list_datasets(
                    repository=self._repository, org_id=org_id,
                )
            if name == "get_dataset":
                return await execute_get_dataset(
                    dataset_id=args.get("dataset_id", ""),
                    repository=self._repository,
                    org_id=org_id,
                )
            if name == "list_training_jobs":
                return await execute_list_training_jobs(
                    repository=self._repository,
                    org_id=org_id,
                    dataset_id=args.get("dataset_id"),
                    status=args.get("status"),
                )
            if name == "get_training_job":
                return await execute_get_training_job(
                    job_id=args.get("job_id", ""),
                    repository=self._repository,
                    org_id=org_id,
                )
            if name == "list_presets":
                return await execute_list_presets(
                    preset_registry=self._preset_registry,
                )
            if name == "list_models":
                return await execute_list_models(
                    model_service=self._model_service,
                    org_id=org_id,
                    dataset_id=args.get("dataset_id"),
                )
            if name == "list_prediction_jobs":
                return await execute_list_prediction_jobs(
                    repository=self._repository,
                    org_id=org_id,
                )
            if name == "list_schedules":
                return await execute_list_schedules(
                    scheduler_service=self._scheduler_service,
                    org_id=org_id,
                )
            if name == "get_dashboard":
                return await execute_get_dashboard(
                    repository=self._repository,
                    org_id=org_id,
                )
            if name == "query_data":
                return await execute_query_data(
                    dataset_id=args.get("dataset_id", ""),
                    query_type=args.get("query_type", ""),
                    params=args.get("params"),
                    repository=self._repository,
                    org_id=org_id,
                )

            # -- Write tools --
            if name == "create_dataset":
                return await execute_create_dataset(
                    name=args.get("name", ""),
                    label_space=args.get("label_space", []),
                    task_type=args.get("task_type"),
                    repository=self._repository,
                    org_id=org_id,
                    label_studio_client=self._label_studio_client,
                    user_id=user_id,
                )
            if name == "start_training_job":
                return await execute_start_training_job(
                    dataset_id=args.get("dataset_id", ""),
                    preset_id=args.get("preset_id", ""),
                    repository=self._repository,
                    org_id=org_id,
                    orchestrator=self._orchestrator,
                    preset_registry=self._preset_registry,
                    user_id=user_id,
                )
            if name == "run_predictions":
                return await execute_run_predictions(
                    dataset_id=args.get("dataset_id", ""),
                    model_id=args.get("model_id", ""),
                    target=args.get("target"),
                    repository=self._repository,
                    org_id=org_id,
                    prediction_orchestrator=self._prediction_orchestrator,
                    user_id=user_id,
                )
            if name == "create_schedule":
                return await execute_create_schedule(
                    name=args.get("name", ""),
                    flow_name=args.get("flow_name", ""),
                    cron=args.get("cron", ""),
                    parameters=args.get("parameters"),
                    description=args.get("description"),
                    scheduler_service=self._scheduler_service,
                    org_id=org_id,
                    user_id=user_id,
                )
            if name == "cancel_training_job":
                return await execute_cancel_training_job(
                    job_id=args.get("job_id", ""),
                    orchestrator=self._orchestrator,
                    repository=self._repository,
                    org_id=org_id,
                )

            # -- Sidebar tools --
            if name == "set_panel":
                return await execute_set_panel(
                    session_id=session_id,
                    surface_id=surface_id,
                    surface_store=self._surface_store,
                    **args,
                )
            if name == "remove_panel":
                return await execute_remove_panel(
                    session_id=session_id,
                    surface_id=surface_id,
                    surface_store=self._surface_store,
                    panel_id=args.get("panel_id", ""),
                )
            if name == "get_surface_state":
                return await execute_get_surface_state(
                    session_id=session_id,
                    surface_id=surface_id,
                    surface_store=self._surface_store,
                )

            return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            _logger.exception("Tool execution failed: %s", name)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Summarisation helpers
    # ------------------------------------------------------------------

    def _summarise_tool_call(
        self, name: str, args: dict[str, Any], result: dict[str, Any]
    ) -> str:
        """Generate a human-readable summary of what the tool did."""
        if "error" in result:
            return f"{name} failed: {result['error'][:80]}"

        # Read tools
        if name == "list_datasets":
            return f"Listed {result.get('count', '?')} datasets"
        if name == "get_dataset":
            return f"Got dataset \"{result.get('name', '?')}\""
        if name == "list_training_jobs":
            return f"Listed {result.get('count', '?')} training jobs"
        if name == "get_training_job":
            return f"Got job {result.get('id', '?')[:8]}… ({result.get('status', '?')})"
        if name == "list_presets":
            return f"Listed {result.get('count', '?')} presets"
        if name == "list_models":
            return f"Listed {result.get('count', '?')} models"
        if name == "list_prediction_jobs":
            return f"Listed {result.get('count', '?')} prediction jobs"
        if name == "list_schedules":
            return f"Listed {result.get('count', '?')} schedules"
        if name == "get_dashboard":
            return (
                f"Dashboard: {result.get('dataset_count', '?')} datasets, "
                f"{result.get('job_count', '?')} jobs"
            )
        if name == "query_data":
            qt = args.get("query_type", "?")
            return f"Queried {qt}"

        # Write tools
        if name == "create_dataset":
            return f"Created dataset \"{result.get('name', '?')}\" ({result.get('id', '?')[:8]}…)"
        if name == "start_training_job":
            return f"Started training job {result.get('id', '?')[:8]}…"
        if name == "run_predictions":
            return f"Started prediction job {result.get('id', '?')[:8]}…"
        if name == "create_schedule":
            return f"Created schedule \"{result.get('name', '?')}\""
        if name == "cancel_training_job":
            return f"Cancelled job {result.get('id', '?')[:8]}…"

        # Sidebar tools
        if name == "set_panel":
            return f"Added panel \"{args.get('id', '?')}\" ({args.get('component', '?')})"
        if name == "remove_panel":
            return f"Removed panel \"{args.get('panel_id', '?')}\""
        if name == "get_surface_state":
            n = len(result.get("panels", []))
            return f"Read sidebar state ({n} panels)"

        return f"Called {name}"
