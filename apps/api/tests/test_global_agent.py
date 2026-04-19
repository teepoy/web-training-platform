"""Tests for the global agent: session store, global tools, runtime, and route."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, container


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _create_dataset(c: TestClient, name: str = "global-agent-ds") -> str:
    ds = c.post(
        "/api/v1/datasets",
        json={"name": name, "dataset_type": "image_classification", "task_spec": _TASK_SPEC},
    )
    assert ds.status_code == 200
    return ds.json()["id"]


def _create_sample(
    c: TestClient,
    dataset_id: str,
    metadata: dict | None = None,
) -> str:
    body: dict = {"image_uris": []}
    if metadata is not None:
        body["metadata"] = metadata
    sample = c.post(f"/api/v1/datasets/{dataset_id}/samples", json=body)
    assert sample.status_code == 200
    return sample.json()["id"]


def _parse_sse(text: str) -> list[dict[str, str]]:
    """Parse SSE text into a list of {event, data} dicts."""
    events: list[dict[str, str]] = []
    current_event = ""
    current_data = ""

    for line in text.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            current_data = line[6:]
        elif line == "" and current_event:
            events.append({"event": current_event, "data": current_data})
            current_event = ""
            current_data = ""

    return events


# ===================================================================
# 1. Session store unit tests
# ===================================================================


class TestSessionStore:
    """Direct unit tests for SessionStore."""

    def test_create_and_retrieve_session(self) -> None:
        from app.agent.session_store import SessionStore

        store = SessionStore()

        async def _run():
            s = await store.get_or_create("sess-1", "user-1")
            assert s.session_id == "sess-1"
            assert s.user_id == "user-1"
            assert s.messages == []

            # Retrieve again — same session
            s2 = await store.get_or_create("sess-1", "user-1")
            assert s2 is s

        asyncio.run(_run())

    def test_append_and_get_messages(self) -> None:
        from app.agent.session_store import SessionStore

        store = SessionStore()

        async def _run():
            await store.get_or_create("sess-2", "user-1")
            await store.append_messages("sess-2", [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ])
            msgs = await store.get_messages("sess-2")
            assert len(msgs) == 2
            assert msgs[0]["content"] == "hello"
            assert msgs[1]["content"] == "hi there"

        asyncio.run(_run())

    def test_truncation(self) -> None:
        from app.agent.session_store import SessionStore

        store = SessionStore(max_messages_per_session=5)

        async def _run():
            await store.get_or_create("sess-3", "user-1")
            await store.append_messages("sess-3", [
                {"role": "user", "content": f"msg-{i}"} for i in range(10)
            ])
            msgs = await store.get_messages("sess-3")
            assert len(msgs) == 5
            # Should keep the last 5
            assert msgs[0]["content"] == "msg-5"

        asyncio.run(_run())

    def test_clear_session(self) -> None:
        from app.agent.session_store import SessionStore

        store = SessionStore()

        async def _run():
            await store.get_or_create("sess-4", "user-1")
            await store.append_messages("sess-4", [{"role": "user", "content": "hi"}])
            await store.clear_session("sess-4")

            s = await store.get("sess-4")
            assert s is None

            msgs = await store.get_messages("sess-4")
            assert msgs == []

        asyncio.run(_run())

    def test_ttl_eviction(self) -> None:
        import time
        from app.agent.session_store import SessionStore

        store = SessionStore(ttl_seconds=0)

        async def _run():
            await store.get_or_create("sess-ttl", "user-1")
            # Wait a tiny bit to ensure monotonic time advances
            time.sleep(0.01)
            s = await store.get("sess-ttl")
            assert s is None

        asyncio.run(_run())

    def test_max_sessions_cap(self) -> None:
        from app.agent.session_store import SessionStore

        store = SessionStore(max_sessions=3)

        async def _run():
            await store.get_or_create("s1", "u1")
            await store.get_or_create("s2", "u1")
            await store.get_or_create("s3", "u1")
            await store.get_or_create("s4", "u1")
            count = await store.session_count()
            assert count == 3

        asyncio.run(_run())


# ===================================================================
# 2. Global tool definitions
# ===================================================================


class TestGlobalToolDefinitions:
    """Test that get_tool_definitions returns the right tools for context."""

    def test_tools_without_classify_context(self) -> None:
        from app.agent.global_tools import get_tool_definitions
        from app.api.schemas import AgentContext

        ctx = AgentContext(page="/datasets")
        tools = get_tool_definitions(ctx)
        tool_names = {t["function"]["name"] for t in tools}

        # Should have read + write tools but NOT sidebar tools
        assert "list_datasets" in tool_names
        assert "create_dataset" in tool_names
        assert "start_training_job" in tool_names
        assert "set_panel" not in tool_names
        assert "remove_panel" not in tool_names
        assert "get_surface_state" not in tool_names

    def test_tools_with_classify_context(self) -> None:
        from app.agent.global_tools import get_tool_definitions
        from app.api.schemas import AgentContext

        ctx = AgentContext(page="/datasets/abc/classify", dataset_id="abc")
        tools = get_tool_definitions(ctx)
        tool_names = {t["function"]["name"] for t in tools}

        # Should have everything including sidebar tools
        assert "list_datasets" in tool_names
        assert "create_dataset" in tool_names
        assert "set_panel" in tool_names
        assert "remove_panel" in tool_names
        assert "get_surface_state" in tool_names

    def test_read_tool_count(self) -> None:
        from app.agent.global_tools import READ_TOOLS
        assert len(READ_TOOLS) == 10

    def test_write_tool_count(self) -> None:
        from app.agent.global_tools import WRITE_TOOLS
        assert len(WRITE_TOOLS) == 5

    def test_sidebar_tool_count(self) -> None:
        from app.agent.global_tools import SIDEBAR_TOOLS
        assert len(SIDEBAR_TOOLS) == 3


# ===================================================================
# 3. Global assembler
# ===================================================================


class TestGlobalAssembler:
    """Test the global prompt assembler."""

    def test_basic_assembly(self) -> None:
        from app.agent.global_assembler import assemble_global_prompt
        from app.api.schemas import AgentContext

        async def _run():
            ctx = AgentContext(page="/datasets")
            prompt = await assemble_global_prompt(
                context=ctx,
                user_email="test@example.com",
                org_id="org-1",
                org_name="TestOrg",
            )
            assert "test@example.com" in prompt
            assert "TestOrg" in prompt
            assert "Sidebar tools are NOT available" in prompt

        asyncio.run(_run())

    def test_assembly_with_classify_page(self) -> None:
        from app.agent.global_assembler import assemble_global_prompt
        from app.api.schemas import AgentContext

        async def _run():
            ctx = AgentContext(page="/datasets/abc/classify", dataset_id="abc")
            prompt = await assemble_global_prompt(
                context=ctx,
                user_email="test@example.com",
                org_id="org-1",
                org_name="TestOrg",
                dataset_info={"name": "Test DS", "dataset_type": "image_classification", "sample_count": 100},
            )
            assert "Sidebar tools are AVAILABLE" in prompt
            assert "Test DS" in prompt
            assert "abc" in prompt

        asyncio.run(_run())

    def test_assembly_with_platform_stats(self) -> None:
        from app.agent.global_assembler import assemble_global_prompt
        from app.api.schemas import AgentContext

        async def _run():
            ctx = AgentContext(page="/")
            prompt = await assemble_global_prompt(
                context=ctx,
                user_email="test@example.com",
                org_id="org-1",
                org_name="TestOrg",
                platform_stats={"dataset_count": 5, "job_count": 10, "model_count": 3, "preset_count": 2},
            )
            assert "Datasets: 5" in prompt
            assert "Training jobs: 10" in prompt

        asyncio.run(_run())


# ===================================================================
# 4. Global agent route
# ===================================================================


class TestGlobalAgentChat:
    """Test POST /api/v1/agent/chat (SSE)."""

    def test_chat_llm_not_configured(self) -> None:
        """When llm.base_url or llm.api_key is missing, return 503."""
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/agent/chat",
                json={"message": "Hello", "context": {"page": "/datasets"}},
            )
            # test config has no llm.base_url/api_key → 503
            assert r.status_code == 503
            assert "LLM not configured" in r.json()["detail"]

    def test_chat_streams_sse_events(self) -> None:
        """Mock the LLM and verify we get proper SSE events back."""
        mock_llm_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello! I'm your platform assistant.",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

        with TestClient(app) as c:
            cfg = container.config()
            original_base_url = cfg.llm.base_url
            original_api_key = cfg.llm.api_key

            try:
                cfg.llm.base_url = "http://fake-llm:8080/v1"
                cfg.llm.api_key = "fake-key"

                with patch("app.agent.global_runtime._call_llm", return_value=mock_llm_response):
                    r = c.post(
                        "/api/v1/agent/chat",
                        json={
                            "message": "What can you do?",
                            "context": {"page": "/datasets"},
                        },
                    )
                    assert r.status_code == 200
                    assert r.headers["content-type"].startswith("text/event-stream")

                    events = _parse_sse(r.text)
                    event_types = [e["event"] for e in events]

                    assert "agent-message" in event_types
                    assert "done" in event_types

                    msg_event = next(e for e in events if e["event"] == "agent-message")
                    data = json.loads(msg_event["data"])
                    assert "Hello" in data["content"]
            finally:
                cfg.llm.base_url = original_base_url
                cfg.llm.api_key = original_api_key

    def test_chat_with_read_tool_call(self) -> None:
        """Mock the LLM calling list_datasets tool."""
        tool_call_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "list_datasets",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

        text_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "You have 1 dataset.",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

        call_count = 0

        async def _mock_call_llm(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_call_response
            return text_response

        with TestClient(app) as c:
            _create_dataset(c, name="global-chat-ds-1")

            cfg = container.config()
            original_base_url = cfg.llm.base_url
            original_api_key = cfg.llm.api_key

            try:
                cfg.llm.base_url = "http://fake-llm:8080/v1"
                cfg.llm.api_key = "fake-key"

                with patch("app.agent.global_runtime._call_llm", side_effect=_mock_call_llm):
                    r = c.post(
                        "/api/v1/agent/chat",
                        json={
                            "message": "List my datasets",
                            "context": {"page": "/datasets"},
                        },
                    )
                    assert r.status_code == 200

                    events = _parse_sse(r.text)
                    event_types = [e["event"] for e in events]

                    assert "agent-action" in event_types
                    assert "agent-message" in event_types
                    assert "done" in event_types

                    action_evt = next(e for e in events if e["event"] == "agent-action")
                    action_data = json.loads(action_evt["data"])
                    assert action_data["tool"] == "list_datasets"
                    assert "dataset" in action_data["summary"].lower()
            finally:
                cfg.llm.base_url = original_base_url
                cfg.llm.api_key = original_api_key

    def test_chat_with_sidebar_tool_on_classify(self) -> None:
        """When on classify page, sidebar tools should work."""
        tool_call_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "set_panel",
                                    "arguments": json.dumps({
                                        "id": "overview-chart",
                                        "component": "metric-cards",
                                        "title": "Overview",
                                        "data": {"inline": {"metrics": [{"label": "Count", "value": "5"}]}},
                                    }),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

        text_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I've added an overview panel.",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

        call_count = 0

        async def _mock_call_llm(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_call_response
            return text_response

        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="global-classify-ds")

            cfg = container.config()
            original_base_url = cfg.llm.base_url
            original_api_key = cfg.llm.api_key

            try:
                cfg.llm.base_url = "http://fake-llm:8080/v1"
                cfg.llm.api_key = "fake-key"

                with patch("app.agent.global_runtime._call_llm", side_effect=_mock_call_llm):
                    r = c.post(
                        "/api/v1/agent/chat",
                        json={
                            "message": "Show me an overview",
                            "context": {
                                "page": f"/datasets/{dataset_id}/classify",
                                "dataset_id": dataset_id,
                            },
                        },
                    )
                    assert r.status_code == 200

                    events = _parse_sse(r.text)
                    event_types = [e["event"] for e in events]

                    assert "agent-action" in event_types
                    assert "sidebar-update" in event_types
                    assert "agent-message" in event_types
                    assert "done" in event_types

                    action_evt = next(e for e in events if e["event"] == "agent-action")
                    action_data = json.loads(action_evt["data"])
                    assert action_data["tool"] == "set_panel"

                    sidebar_evt = next(e for e in events if e["event"] == "sidebar-update")
                    sidebar_data = json.loads(sidebar_evt["data"])
                    assert len(sidebar_data["panels"]) == 1
                    assert sidebar_data["panels"][0]["id"] == "overview-chart"
            finally:
                cfg.llm.base_url = original_base_url
                cfg.llm.api_key = original_api_key

    def test_chat_session_persistence(self) -> None:
        """Multiple messages to the same session should accumulate history."""
        mock_llm_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Got it.",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

        with TestClient(app) as c:
            cfg = container.config()
            original_base_url = cfg.llm.base_url
            original_api_key = cfg.llm.api_key

            try:
                cfg.llm.base_url = "http://fake-llm:8080/v1"
                cfg.llm.api_key = "fake-key"

                with patch("app.agent.global_runtime._call_llm", return_value=mock_llm_response):
                    # First message
                    r1 = c.post(
                        "/api/v1/agent/chat",
                        json={
                            "message": "Hello",
                            "context": {"page": "/"},
                            "session_id": "persist-test-session",
                        },
                    )
                    assert r1.status_code == 200

                    # Second message to same session
                    r2 = c.post(
                        "/api/v1/agent/chat",
                        json={
                            "message": "What did I say before?",
                            "context": {"page": "/"},
                            "session_id": "persist-test-session",
                        },
                    )
                    assert r2.status_code == 200

                    # Verify session store has accumulated messages
                    session_store = container.session_store()

                    async def _check():
                        msgs = await session_store.get_messages("persist-test-session")
                        # Each turn: user + assistant = 2 messages per turn
                        # 2 turns = 4 messages
                        assert len(msgs) == 4
                        assert msgs[0]["role"] == "user"
                        assert msgs[0]["content"] == "Hello"
                        assert msgs[1]["role"] == "assistant"
                        assert msgs[2]["role"] == "user"
                        assert msgs[2]["content"] == "What did I say before?"

                    asyncio.run(_check())
            finally:
                cfg.llm.base_url = original_base_url
                cfg.llm.api_key = original_api_key

    def test_chat_empty_message_rejected(self) -> None:
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/agent/chat",
                json={"message": "", "context": {"page": "/"}},
            )
            assert r.status_code == 422  # validation error

    def test_chat_with_context_defaults(self) -> None:
        """When context is not provided, it should use defaults."""
        mock_llm_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hi!",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

        with TestClient(app) as c:
            cfg = container.config()
            original_base_url = cfg.llm.base_url
            original_api_key = cfg.llm.api_key

            try:
                cfg.llm.base_url = "http://fake-llm:8080/v1"
                cfg.llm.api_key = "fake-key"

                with patch("app.agent.global_runtime._call_llm", return_value=mock_llm_response):
                    r = c.post(
                        "/api/v1/agent/chat",
                        json={"message": "Hi"},
                    )
                    assert r.status_code == 200
                    events = _parse_sse(r.text)
                    assert any(e["event"] == "agent-message" for e in events)
            finally:
                cfg.llm.base_url = original_base_url
                cfg.llm.api_key = original_api_key

    def test_chat_llm_error_handled(self) -> None:
        """When LLM call raises an exception, agent should return error message."""
        async def _failing_llm(**kwargs):
            raise RuntimeError("LLM is down")

        with TestClient(app) as c:
            cfg = container.config()
            original_base_url = cfg.llm.base_url
            original_api_key = cfg.llm.api_key

            try:
                cfg.llm.base_url = "http://fake-llm:8080/v1"
                cfg.llm.api_key = "fake-key"

                with patch("app.agent.global_runtime._call_llm", side_effect=_failing_llm):
                    r = c.post(
                        "/api/v1/agent/chat",
                        json={
                            "message": "Hello",
                            "context": {"page": "/"},
                        },
                    )
                    assert r.status_code == 200

                    events = _parse_sse(r.text)
                    msg_event = next(e for e in events if e["event"] == "agent-message")
                    data = json.loads(msg_event["data"])
                    assert "error" in data["content"].lower()
                    assert "done" in [e["event"] for e in events]
            finally:
                cfg.llm.base_url = original_base_url
                cfg.llm.api_key = original_api_key


# ===================================================================
# 5. Global tool execution unit tests
# ===================================================================


class TestGlobalToolExecution:
    """Unit tests for global tool execute_* functions."""

    def test_execute_list_datasets(self) -> None:
        from app.agent.global_tools import execute_list_datasets

        async def _run():
            mock_repo = MagicMock()
            ds = MagicMock()
            ds.id = "ds-1"
            ds.name = "Test"
            ds.dataset_type = "image_classification"
            ds.created_at = None
            mock_repo.list_datasets = AsyncMock(return_value=[ds])

            result = await execute_list_datasets(repository=mock_repo, org_id="org-1")
            assert result["count"] == 1
            assert result["datasets"][0]["id"] == "ds-1"

        asyncio.run(_run())

    def test_execute_get_dataset_not_found(self) -> None:
        from app.agent.global_tools import execute_get_dataset

        async def _run():
            mock_repo = MagicMock()
            mock_repo.get_dataset = AsyncMock(return_value=None)

            result = await execute_get_dataset(
                dataset_id="nonexistent", repository=mock_repo, org_id="org-1"
            )
            assert "error" in result

        asyncio.run(_run())

    def test_execute_list_presets(self) -> None:
        from app.agent.global_tools import execute_list_presets

        async def _run():
            mock_registry = MagicMock()
            p = MagicMock()
            p.id = "preset-1"
            p.name = "ResNet50"
            p.trainable = True
            mock_registry.list_presets.return_value = [p]

            result = await execute_list_presets(preset_registry=mock_registry)
            assert result["count"] == 1
            assert result["presets"][0]["name"] == "ResNet50"

        asyncio.run(_run())

    def test_execute_get_dashboard(self) -> None:
        from app.agent.global_tools import execute_get_dashboard

        async def _run():
            mock_repo = MagicMock()
            mock_repo.list_datasets = AsyncMock(return_value=[MagicMock(), MagicMock()])
            job1 = MagicMock()
            job1.status = "running"
            job2 = MagicMock()
            job2.status = "completed"
            mock_repo.list_jobs = AsyncMock(return_value=[job1, job2])

            result = await execute_get_dashboard(repository=mock_repo, org_id="org-1")
            assert result["dataset_count"] == 2
            assert result["job_count"] == 2
            assert result["jobs_running"] == 1
            assert result["jobs_completed"] == 1

        asyncio.run(_run())

    def test_execute_cancel_training_job_not_found(self) -> None:
        from app.agent.global_tools import execute_cancel_training_job

        async def _run():
            mock_repo = MagicMock()
            mock_repo.get_job = AsyncMock(return_value=None)
            mock_orch = MagicMock()

            result = await execute_cancel_training_job(
                job_id="nonexistent", orchestrator=mock_orch, repository=mock_repo, org_id="org-1"
            )
            assert "error" in result

        asyncio.run(_run())

    def test_execute_list_schedules(self) -> None:
        from app.agent.global_tools import execute_list_schedules

        async def _run():
            mock_svc = MagicMock()
            mock_svc.list_schedules = AsyncMock(return_value=[
                {"id": "s1", "name": "nightly", "cron": "0 2 * * *", "paused": False},
            ])

            result = await execute_list_schedules(scheduler_service=mock_svc, org_id="org-1")
            assert result["count"] == 1
            assert result["schedules"][0]["name"] == "nightly"

        asyncio.run(_run())


# ===================================================================
# 6. GlobalAgent runtime unit tests
# ===================================================================


class TestGlobalAgentRuntime:
    """Unit tests for GlobalAgent class directly."""

    def test_summarise_tool_call_read(self) -> None:
        from app.agent.global_runtime import GlobalAgent
        from app.agent.session_store import SessionStore
        from app.agent.surface_store import SurfaceStore

        agent = GlobalAgent(
            llm_base_url="http://fake:8080/v1",
            llm_api_key="fake",
            llm_model="test",
            session_store=SessionStore(),
            surface_store=SurfaceStore(),
            repository=MagicMock(),
            orchestrator=MagicMock(),
            prediction_orchestrator=MagicMock(),
            scheduler_service=MagicMock(),
            model_service=MagicMock(),
            preset_registry=MagicMock(),
            label_studio_client=MagicMock(),
        )

        assert "2" in agent._summarise_tool_call("list_datasets", {}, {"count": 2, "datasets": []})
        assert "failed" in agent._summarise_tool_call("list_datasets", {}, {"error": "fail"}).lower()
        assert "Created" in agent._summarise_tool_call("create_dataset", {}, {"name": "X", "id": "abc12345"})
        assert "Cancelled" in agent._summarise_tool_call("cancel_training_job", {}, {"id": "abc12345", "status": "cancelled"})
