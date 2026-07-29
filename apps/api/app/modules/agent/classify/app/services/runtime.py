"""Classify workspace agent runtime."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, AsyncIterator

from litellm.types.llms.openai import AllMessageValues, ChatCompletionToolMessage

from app.modules.agent.classify.adapter.tools.tools import (
    TOOL_DEFINITIONS,
    execute_get_surface_state,
    execute_query_data,
    execute_remove_panel,
    execute_set_panel,
)
from app.shared.infrastructure.agent_runtime import (
    AgentAction,
    AgentDone,
    AgentEvent,
    AgentMessage,
    AgentSidebarUpdate,
)
from app.shared.infrastructure.llm.client import call_llm as _call_llm
from app.shared.infrastructure.surface_store import SurfaceStore

if TYPE_CHECKING:
    from app.modules.storage.port.local import DatasetStorageFactoryPort

_logger = logging.getLogger(__name__)


class ClassifyAgent:
    """Stateful agent session for a dataset classification workflow."""

    def __init__(
        self,
        *,
        system_prompt: str,
        llm_base_url: str,
        llm_api_key: str,
        llm_model: str,
        dataset_id: str,
        session_id: str,
        surface_id: str,
        surface_store: SurfaceStore,
        dataset_storage_factory: DatasetStorageFactoryPort | None = None,
        org_id: str = "",
    ) -> None:
        self._system_prompt = system_prompt
        self._llm_base_url = llm_base_url
        self._llm_api_key = llm_api_key
        self._llm_model = llm_model
        self._dataset_id = dataset_id
        self._session_id = session_id
        self._surface_id = surface_id
        self._surface_store = surface_store
        self._dataset_storage_factory = dataset_storage_factory
        self._org_id = org_id
        self._messages: list[AllMessageValues] = []

    async def handle_message(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """Process a user message and yield events."""
        self._messages.append({"role": "user", "content": user_message})

        await self._surface_store.clear_ephemeral(self._session_id, self._surface_id)

        max_iterations = 10
        for _ in range(max_iterations):
            try:
                response = await _call_llm(
                    base_url=self._llm_base_url,
                    api_key=self._llm_api_key,
                    model=self._llm_model,
                    system_prompt=self._system_prompt,
                    messages=self._messages,
                    tools=TOOL_DEFINITIONS,
                )
            except Exception as e:
                _logger.exception("LLM call failed")
                yield AgentMessage(
                    content=f"Sorry, I encountered an error communicating with the AI model: {e}"
                )
                break

            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            self._messages.append(message)

            tool_calls = message.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}

                    result = await self._execute_tool(tool_name, args)
                    summary = self._summarise_tool_call(tool_name, args, result)
                    yield AgentAction(tool=tool_name, summary=summary, result=result)

                    if tool_name in ("set_panel", "remove_panel"):
                        state = await self._surface_store.get_state(
                            self._session_id, self._surface_id
                        )
                        yield AgentSidebarUpdate(
                            surface_id=self._surface_id,
                            panels=[p.model_dump(mode="json") for p in state.panels],
                        )

                    tool_msg: ChatCompletionToolMessage = {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(result, default=str),
                    }
                    self._messages.append(tool_msg)
            else:
                content = message.get("content", "")
                if content:
                    yield AgentMessage(content=content)
                break

        yield AgentDone()

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call to its implementation."""
        try:
            if name == "query_data":
                if self._dataset_storage_factory is None:
                    return {"error": "DatasetStorageFactory not configured"}
                return await execute_query_data(
                    query_type=args.get("query_type", ""),
                    params=args.get("params"),
                    dataset_id=self._dataset_id,
                    factory=self._dataset_storage_factory,
                    org_id=self._org_id,
                )
            if name == "set_panel":
                return await execute_set_panel(
                    session_id=self._session_id,
                    surface_id=self._surface_id,
                    surface_store=self._surface_store,
                    **args,
                )
            if name == "remove_panel":
                return await execute_remove_panel(
                    session_id=self._session_id,
                    surface_id=self._surface_id,
                    surface_store=self._surface_store,
                    panel_id=args.get("panel_id", ""),
                )
            if name == "get_surface_state":
                return await execute_get_surface_state(
                    session_id=self._session_id,
                    surface_id=self._surface_id,
                    surface_store=self._surface_store,
                )
            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            _logger.exception("Tool execution failed: %s", name)
            return {"error": str(e)}

    def _summarise_tool_call(
        self, name: str, args: dict[str, Any], result: dict[str, Any]
    ) -> str:
        """Generate a human-readable summary of what the tool did."""
        if name == "query_data":
            qt = args.get("query_type", "?")
            params = args.get("params", {})
            extra = f" key={params['key']}" if "key" in params else ""
            return f"Queried {qt}{extra}"
        if name == "set_panel":
            return f'Added panel "{args.get("id", "?")}" ({args.get("component", "?")})'
        if name == "remove_panel":
            return f'Removed panel "{args.get("panel_id", "?")}"'
        if name == "get_surface_state":
            n = len(result.get("panels", []))
            return f"Read sidebar state ({n} panels)"
        return f"Called {name}"
