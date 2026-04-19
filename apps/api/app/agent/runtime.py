"""Agent runtime — tool-calling loop that drives the LLM.

The ``ClassifyAgent`` manages a conversation session.  Each user message
triggers a loop: call the LLM, execute any tool calls, feed results back,
repeat until the LLM produces a final text response with no tool calls.

Events are yielded as they happen so the caller can stream them over SSE.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agent.assembler import assemble_prompt
from app.agent.surface_store import SurfaceStore
from app.agent.tools import (
    TOOL_DEFINITIONS,
    execute_get_surface_state,
    execute_query_data,
    execute_remove_panel,
    execute_set_panel,
)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event types yielded by the agent
# ---------------------------------------------------------------------------


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
    """Sidebar state changed — surface_store was mutated."""
    surface_id: str
    panels: list[dict[str, Any]]


@dataclass
class AgentDone:
    """Agent finished processing this turn."""
    pass


AgentEvent = AgentMessage | AgentAction | AgentSidebarUpdate | AgentDone


# ---------------------------------------------------------------------------
# LLM client wrapper
# ---------------------------------------------------------------------------

# Re-export so existing test patches against ``app.agent.runtime._call_llm``
# continue to work without changes.
from app.services.llm import call_llm as _call_llm  # noqa: F401


# ---------------------------------------------------------------------------
# Classify Agent
# ---------------------------------------------------------------------------


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
        repository: Any,
    ) -> None:
        self._system_prompt = system_prompt
        self._llm_base_url = llm_base_url
        self._llm_api_key = llm_api_key
        self._llm_model = llm_model
        self._dataset_id = dataset_id
        self._session_id = session_id
        self._surface_id = surface_id
        self._surface_store = surface_store
        self._repository = repository
        self._messages: list[dict[str, Any]] = []

    async def handle_message(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """Process a user message and yield events."""
        self._messages.append({"role": "user", "content": user_message})

        # Clear ephemeral panels from previous turn
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
                yield AgentMessage(content=f"Sorry, I encountered an error communicating with the AI model: {e}")
                break

            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")

            # Append the assistant message to history
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

                    # Execute the tool
                    result = await self._execute_tool(tool_name, args)

                    summary = self._summarise_tool_call(tool_name, args, result)
                    yield AgentAction(tool=tool_name, summary=summary, result=result)

                    # If it was a surface mutation, emit sidebar update
                    if tool_name in ("set_panel", "remove_panel"):
                        state = await self._surface_store.get_state(
                            self._session_id, self._surface_id
                        )
                        yield AgentSidebarUpdate(
                            surface_id=self._surface_id,
                            panels=[p.model_dump(mode="json") for p in state.panels],
                        )

                    # Feed tool result back into conversation
                    self._messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(result, default=str),
                    })
            else:
                # No tool calls — agent is done
                content = message.get("content", "")
                if content:
                    yield AgentMessage(content=content)
                break

        yield AgentDone()

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call to its implementation."""
        try:
            if name == "query_data":
                return await execute_query_data(
                    query_type=args.get("query_type", ""),
                    params=args.get("params"),
                    dataset_id=self._dataset_id,
                    repository=self._repository,
                )
            elif name == "set_panel":
                return await execute_set_panel(
                    session_id=self._session_id,
                    surface_id=self._surface_id,
                    surface_store=self._surface_store,
                    **args,
                )
            elif name == "remove_panel":
                return await execute_remove_panel(
                    session_id=self._session_id,
                    surface_id=self._surface_id,
                    surface_store=self._surface_store,
                    panel_id=args.get("panel_id", ""),
                )
            elif name == "get_surface_state":
                return await execute_get_surface_state(
                    session_id=self._session_id,
                    surface_id=self._surface_id,
                    surface_store=self._surface_store,
                )
            else:
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
        elif name == "set_panel":
            return f"Added panel \"{args.get('id', '?')}\" ({args.get('component', '?')})"
        elif name == "remove_panel":
            return f"Removed panel \"{args.get('panel_id', '?')}\""
        elif name == "get_surface_state":
            n = len(result.get("panels", []))
            return f"Read sidebar state ({n} panels)"
        return f"Called {name}"
