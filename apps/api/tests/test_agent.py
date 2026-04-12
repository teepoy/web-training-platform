"""Tests for the agent module: surface store, metadata inference, assembler, routes."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, container


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_SPEC = {"task_type": "classification", "label_space": ["cat", "dog"]}


def _create_dataset(c: TestClient, name: str = "agent-test-ds") -> str:
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


def _create_annotation(
    c: TestClient, sample_id: str, label: str, created_by: str = "tester"
) -> str:
    r = c.post(
        "/api/v1/annotations",
        json={"sample_id": sample_id, "label": label, "created_by": created_by},
    )
    assert r.status_code == 200
    return r.json()["id"]


# ===================================================================
# 1. Surface store routes
# ===================================================================


class TestSurfaceRoutes:
    """Test the surface state CRUD endpoints."""

    def test_get_empty_surface(self) -> None:
        with TestClient(app) as c:
            r = c.get("/api/v1/sessions/test-sess/surfaces/sidebar")
            assert r.status_code == 200
            body = r.json()
            assert body["surface_id"] == "sidebar"
            assert body["panels"] == []
            assert body["version"] == 1

    def test_set_and_get_panel(self) -> None:
        with TestClient(app) as c:
            panel = {
                "id": "test-panel",
                "component": "metric-cards",
                "title": "Test Metrics",
                "order": 10,
                "data": {"inline": {"metrics": [{"label": "Count", "value": "42"}]}},
            }
            r = c.post(
                "/api/v1/sessions/test-sess/surfaces/sidebar/panels",
                json={"panel": panel},
            )
            assert r.status_code == 200
            body = r.json()
            assert len(body["panels"]) == 1
            assert body["panels"][0]["id"] == "test-panel"
            assert body["panels"][0]["title"] == "Test Metrics"

            # GET should return the same
            r2 = c.get("/api/v1/sessions/test-sess/surfaces/sidebar")
            assert r2.status_code == 200
            assert len(r2.json()["panels"]) == 1

    def test_replace_panel(self) -> None:
        with TestClient(app) as c:
            panel_v1 = {
                "id": "replace-me",
                "component": "metric-cards",
                "title": "Version 1",
            }
            c.post(
                "/api/v1/sessions/test-sess-replace/surfaces/sidebar/panels",
                json={"panel": panel_v1},
            )

            panel_v2 = {
                "id": "replace-me",
                "component": "data-table",
                "title": "Version 2",
            }
            r = c.post(
                "/api/v1/sessions/test-sess-replace/surfaces/sidebar/panels",
                json={"panel": panel_v2},
            )
            assert r.status_code == 200
            panels = r.json()["panels"]
            assert len(panels) == 1
            assert panels[0]["component"] == "data-table"
            assert panels[0]["title"] == "Version 2"

    def test_remove_panel(self) -> None:
        with TestClient(app) as c:
            panel = {
                "id": "to-remove",
                "component": "markdown-log",
                "title": "Removable",
            }
            c.post(
                "/api/v1/sessions/test-sess-rm/surfaces/sidebar/panels",
                json={"panel": panel},
            )

            r = c.delete(
                "/api/v1/sessions/test-sess-rm/surfaces/sidebar/panels/to-remove"
            )
            assert r.status_code == 200
            assert len(r.json()["panels"]) == 0

    def test_remove_nonexistent_panel_404(self) -> None:
        with TestClient(app) as c:
            r = c.delete(
                "/api/v1/sessions/test-sess-404/surfaces/sidebar/panels/ghost"
            )
            assert r.status_code == 404

    def test_panel_ordering(self) -> None:
        with TestClient(app) as c:
            for pid, order in [("c-panel", 30), ("a-panel", 10), ("b-panel", 20)]:
                c.post(
                    "/api/v1/sessions/test-sess-order/surfaces/sidebar/panels",
                    json={
                        "panel": {
                            "id": pid,
                            "component": "metric-cards",
                            "title": pid,
                            "order": order,
                        }
                    },
                )

            r = c.get("/api/v1/sessions/test-sess-order/surfaces/sidebar")
            panels = r.json()["panels"]
            assert [p["id"] for p in panels] == ["a-panel", "b-panel", "c-panel"]

    def test_import_export_surface(self) -> None:
        with TestClient(app) as c:
            # Set up a panel first
            c.post(
                "/api/v1/sessions/test-sess-ie/surfaces/sidebar/panels",
                json={
                    "panel": {
                        "id": "exported-panel",
                        "component": "data-table",
                        "title": "Export Me",
                    }
                },
            )

            # Export
            exp = c.get("/api/v1/sessions/test-sess-ie/surfaces/sidebar/export")
            assert exp.status_code == 200
            exported = exp.json()
            assert exported["exported_at"] is not None
            assert len(exported["panels"]) == 1

            # Import into a new session
            imp = c.post(
                "/api/v1/sessions/test-sess-ie-2/surfaces/sidebar/import",
                json=exported,
            )
            assert imp.status_code == 200
            assert len(imp.json()["panels"]) == 1
            assert imp.json()["panels"][0]["id"] == "exported-panel"


# ===================================================================
# 2. Metadata inference (unit tests — no HTTP)
# ===================================================================


class TestMetadataInference:
    """Test scan_metadata_types and build_metadata_block."""

    def test_scan_empty(self) -> None:
        from app.agent.metadata_inference import scan_metadata_types

        result = scan_metadata_types([])
        assert result == {}

    def test_scan_pure_python_string_keys(self) -> None:
        from app.agent.metadata_inference import scan_metadata_types

        data = [
            {"source": "imagenet", "label_name": "cat"},
            {"source": "imagenet", "label_name": "dog"},
            {"source": "custom", "label_name": "bird"},
        ]

        # Force pure-Python path by temporarily hiding polars
        with patch.dict("sys.modules", {"polars": None}):
            result = scan_metadata_types(data)

        assert "source" in result
        assert "label_name" in result
        assert result["source"].type == "str"
        assert result["source"].n_unique == 2
        assert result["label_name"].n_unique == 3

    def test_scan_pure_python_numeric_keys(self) -> None:
        from app.agent.metadata_inference import scan_metadata_types

        data = [
            {"score": 0.9, "index": 1},
            {"score": 0.5, "index": 2},
            {"score": 0.1, "index": 3},
        ]

        with patch.dict("sys.modules", {"polars": None}):
            result = scan_metadata_types(data)

        assert result["score"].type == "float"
        assert result["score"].min == 0.1
        assert result["score"].max == 0.9
        assert result["index"].type == "int"
        assert result["index"].min == 1
        assert result["index"].max == 3

    def test_scan_pure_python_nulls(self) -> None:
        from app.agent.metadata_inference import scan_metadata_types

        data = [
            {"key": "a"},
            {"key": None},
            {"key": "b"},
        ]

        with patch.dict("sys.modules", {"polars": None}):
            result = scan_metadata_types(data)

        assert result["key"].null_count == 1
        assert result["key"].n_unique == 2

    def test_build_metadata_block_empty(self) -> None:
        from app.agent.metadata_inference import build_metadata_block

        result = build_metadata_block(None, None)
        assert "no metadata" in result.lower()

    def test_build_metadata_block_inferred_only(self) -> None:
        from app.agent.metadata_inference import build_metadata_block
        from app.api.schemas import MetadataKeyInfo

        inferred = {
            "source": MetadataKeyInfo(
                type="str", n_unique=2, sample_values=["imagenet", "custom"]
            ),
        }
        result = build_metadata_block(None, inferred)
        assert "`source`" in result
        assert "inferred" in result.lower()

    def test_build_metadata_block_declared(self) -> None:
        from app.agent.metadata_inference import build_metadata_block
        from app.api.schemas import DeclaredMetadataKey, MetadataKeyInfo

        declared = {
            "label_name": DeclaredMetadataKey(type="string", description="ImageNet class name"),
        }
        inferred = {
            "label_name": MetadataKeyInfo(
                type="str", n_unique=10, sample_values=["cat", "dog", "bird"]
            ),
        }
        result = build_metadata_block(declared, inferred)
        assert "`label_name`" in result
        assert "ImageNet class name" in result
        assert "declared" in result.lower()


# ===================================================================
# 3. Prompt assembler (unit test)
# ===================================================================


class TestPromptAssembler:
    """Test assemble_prompt fills the template correctly."""

    def test_assemble_basic(self) -> None:
        from app.agent.assembler import assemble_prompt

        prompt = assemble_prompt(
            dataset_name="Test DS",
            dataset_type="image_classification",
            sample_count=100,
            label_space=["cat", "dog"],
            annotation_stats={
                "total_samples": 100,
                "annotated_samples": 50,
                "unlabeled_samples": 50,
                "label_counts": {"cat": 30, "dog": 20},
            },
            metadata_dicts=[],
            declared_metadata=None,
            has_predictions=False,
            has_embeddings=False,
        )

        assert "Test DS" in prompt
        assert "image_classification" in prompt
        assert "cat, dog" in prompt
        assert "100" in prompt
        assert "50" in prompt

    def test_assemble_with_metadata(self) -> None:
        from app.agent.assembler import assemble_prompt

        metadata_dicts = [
            {"source": "imagenet", "label_index": 0},
            {"source": "imagenet", "label_index": 5},
        ]

        with patch.dict("sys.modules", {"polars": None}):
            prompt = assemble_prompt(
                dataset_name="Meta DS",
                dataset_type="image_classification",
                sample_count=200,
                label_space=["a", "b"],
                annotation_stats={
                    "total_samples": 200,
                    "annotated_samples": 0,
                    "unlabeled_samples": 200,
                    "label_counts": {},
                },
                metadata_dicts=metadata_dicts,
                declared_metadata=None,
                has_predictions=True,
                has_embeddings=False,
            )

        assert "`source`" in prompt
        assert "`label_index`" in prompt
        assert "true" in prompt  # has_predictions
        assert "false" in prompt  # has_embeddings

    def test_assemble_with_declared_metadata(self) -> None:
        from app.agent.assembler import assemble_prompt

        prompt = assemble_prompt(
            dataset_name="Declared DS",
            dataset_type="image_vqa",
            sample_count=50,
            label_space=[],
            annotation_stats={
                "total_samples": 50,
                "annotated_samples": 10,
                "unlabeled_samples": 40,
                "label_counts": {},
            },
            metadata_dicts=[{"question": "What is this?"}],
            declared_metadata={
                "question": {"type": "string", "description": "VQA question text"},
            },
            has_predictions=False,
            has_embeddings=False,
        )

        assert "VQA question text" in prompt
        assert "declared" in prompt.lower()


# ===================================================================
# 4. Query data route
# ===================================================================


class TestQueryDataRoute:
    """Test POST /api/v1/datasets/{id}/query."""

    def test_annotation_stats_query(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="query-stats-ds")
            s1 = _create_sample(c, dataset_id)
            _create_sample(c, dataset_id)
            _create_annotation(c, s1, "cat")

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "annotation-stats"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total_samples"] == 2
            assert body["annotated_samples"] == 1
            assert body["label_counts"]["cat"] == 1

    def test_sample_slice_query(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="query-slice-ds")
            for _ in range(5):
                _create_sample(c, dataset_id)

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "sample-slice",
                    "params": {"offset": 0, "limit": 3},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert len(body["items"]) == 3
            assert body["total"] == 5

    def test_metadata_histogram_query(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="query-hist-ds")
            _create_sample(c, dataset_id, metadata={"source": "train"})
            _create_sample(c, dataset_id, metadata={"source": "train"})
            _create_sample(c, dataset_id, metadata={"source": "val"})

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "metadata-histogram",
                    "params": {"key": "source"},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert body["key"] == "source"
            # Should have histogram entries
            hist = {h["value"]: h["count"] for h in body["histogram"]}
            assert hist["train"] == 2
            assert hist["val"] == 1

    def test_metadata_histogram_missing_key_param(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="query-hist-nokey-ds")
            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "metadata-histogram"},
            )
            assert r.status_code == 200
            body = r.json()
            assert "error" in body

    def test_recent_annotations_query(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="query-recent-ds")
            s1 = _create_sample(c, dataset_id)
            s2 = _create_sample(c, dataset_id)
            _create_annotation(c, s1, "cat")
            _create_annotation(c, s2, "dog")

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={
                    "query_type": "recent-annotations",
                    "params": {"limit": 10},
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert "entries" in body
            assert len(body["entries"]) == 2

    def test_prediction_summary_query(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="query-pred-ds")
            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "prediction-summary"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total_predictions"] == 0

    def test_unknown_query_type(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="query-unknown-ds")
            r = c.post(
                f"/api/v1/datasets/{dataset_id}/query",
                json={"query_type": "not-a-real-query"},
            )
            assert r.status_code == 200
            body = r.json()
            assert "error" in body

    def test_query_nonexistent_dataset_404(self) -> None:
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/datasets/nonexistent-ds-id/query",
                json={"query_type": "annotation-stats"},
            )
            assert r.status_code == 404


# ===================================================================
# 5. Agent chat endpoint (LLM mocked)
# ===================================================================


class TestAgentChat:
    """Test POST /api/v1/datasets/{id}/agent/chat (SSE)."""

    def test_chat_llm_not_configured(self) -> None:
        """When llm.base_url or llm.api_key is missing, return 503."""
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="chat-no-llm-ds")

            r = c.post(
                f"/api/v1/datasets/{dataset_id}/agent/chat",
                json={"message": "Hello"},
            )
            # test config has no llm.base_url/api_key → 503
            assert r.status_code == 503
            assert "LLM not configured" in r.json()["detail"]

    def test_chat_nonexistent_dataset_404(self) -> None:
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/datasets/nonexistent-ds-id/agent/chat",
                json={"message": "Hello"},
            )
            assert r.status_code == 404

    def test_chat_streams_sse_events(self) -> None:
        """Mock the LLM and verify we get proper SSE events back."""
        # Prepare a mock LLM response — simple text reply, no tool calls
        mock_llm_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello! I can see your dataset has 2 samples.",
                    },
                    "finish_reason": "stop",
                }
            ]
        }

        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="chat-sse-ds")
            _create_sample(c, dataset_id)
            _create_sample(c, dataset_id)

            # Patch both the config check AND the LLM call
            cfg = container.config()
            original_base_url = cfg.llm.base_url
            original_api_key = cfg.llm.api_key

            try:
                # Temporarily set LLM config so the endpoint doesn't 503
                cfg.llm.base_url = "http://fake-llm:8080/v1"
                cfg.llm.api_key = "fake-key"

                with patch("app.agent.runtime._call_llm", return_value=mock_llm_response):
                    r = c.post(
                        f"/api/v1/datasets/{dataset_id}/agent/chat",
                        json={"message": "What does this dataset look like?"},
                    )
                    assert r.status_code == 200
                    assert r.headers["content-type"].startswith("text/event-stream")

                    # Parse SSE events
                    events = _parse_sse(r.text)
                    event_types = [e["event"] for e in events]

                    assert "agent-message" in event_types
                    assert "done" in event_types

                    # Check message content
                    msg_event = next(e for e in events if e["event"] == "agent-message")
                    data = json.loads(msg_event["data"])
                    assert "Hello" in data["content"]
            finally:
                cfg.llm.base_url = original_base_url
                cfg.llm.api_key = original_api_key

    def test_chat_with_tool_call(self) -> None:
        """Mock the LLM doing a tool call and verify action + sidebar events."""
        # First response: tool call to set_panel
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
                                        "id": "test-chart",
                                        "component": "metric-cards",
                                        "title": "Overview",
                                        "data": {"inline": {"metrics": [{"label": "Samples", "value": "2"}]}},
                                    }),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

        # Second response: text reply after tool call
        text_response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I've added a metrics panel to the sidebar.",
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
            dataset_id = _create_dataset(c, name="chat-tool-ds")
            _create_sample(c, dataset_id)

            cfg = container.config()
            original_base_url = cfg.llm.base_url
            original_api_key = cfg.llm.api_key

            try:
                cfg.llm.base_url = "http://fake-llm:8080/v1"
                cfg.llm.api_key = "fake-key"

                with patch("app.agent.runtime._call_llm", side_effect=_mock_call_llm):
                    r = c.post(
                        f"/api/v1/datasets/{dataset_id}/agent/chat",
                        json={"message": "Show me an overview"},
                    )
                    assert r.status_code == 200

                    events = _parse_sse(r.text)
                    event_types = [e["event"] for e in events]

                    # Should have: action, sidebar-update, message, done
                    assert "agent-action" in event_types
                    assert "sidebar-update" in event_types
                    assert "agent-message" in event_types
                    assert "done" in event_types

                    # Check action event
                    action_evt = next(e for e in events if e["event"] == "agent-action")
                    action_data = json.loads(action_evt["data"])
                    assert action_data["tool"] == "set_panel"

                    # Check sidebar update
                    sidebar_evt = next(e for e in events if e["event"] == "sidebar-update")
                    sidebar_data = json.loads(sidebar_evt["data"])
                    assert len(sidebar_data["panels"]) == 1
                    assert sidebar_data["panels"][0]["id"] == "test-chart"
            finally:
                cfg.llm.base_url = original_base_url
                cfg.llm.api_key = original_api_key

    def test_chat_empty_message_rejected(self) -> None:
        with TestClient(app) as c:
            dataset_id = _create_dataset(c, name="chat-empty-msg-ds")
            r = c.post(
                f"/api/v1/datasets/{dataset_id}/agent/chat",
                json={"message": ""},
            )
            assert r.status_code == 422  # validation error


# ===================================================================
# 6. Surface store unit tests (async)
# ===================================================================


class TestSurfaceStoreUnit:
    """Direct unit tests for SurfaceStore class."""

    def test_clear_ephemeral(self) -> None:
        import asyncio
        from app.agent.surface_store import SurfaceStore
        from app.api.schemas import AgentPanelDescriptor

        store = SurfaceStore()

        async def _run():
            p1 = AgentPanelDescriptor(
                id="persistent", component="metric-cards", title="Keep Me"
            )
            p2 = AgentPanelDescriptor(
                id="temp", component="metric-cards", title="Remove Me", ephemeral=True
            )
            await store.set_panel("s1", "surf", p1)
            await store.set_panel("s1", "surf", p2)

            state = await store.get_state("s1", "surf")
            assert len(state.panels) == 2

            state = await store.clear_ephemeral("s1", "surf")
            assert len(state.panels) == 1
            assert state.panels[0].id == "persistent"

        asyncio.run(_run())

    def test_clear_session(self) -> None:
        import asyncio
        from app.agent.surface_store import SurfaceStore
        from app.api.schemas import AgentPanelDescriptor

        store = SurfaceStore()

        async def _run():
            p = AgentPanelDescriptor(
                id="panel", component="metric-cards", title="Panel"
            )
            await store.set_panel("s1", "surf", p)
            state = await store.get_state("s1", "surf")
            assert len(state.panels) == 1

            await store.clear_session("s1")
            state = await store.get_state("s1", "surf")
            assert len(state.panels) == 0

        asyncio.run(_run())

    def test_max_panel_enforcement(self) -> None:
        """Test that tool implementation enforces MAX_PANELS=8."""
        import asyncio
        from app.agent.surface_store import SurfaceStore
        from app.agent.tools import execute_set_panel

        store = SurfaceStore()

        async def _run():
            # Add 8 panels (max)
            for i in range(8):
                result = await execute_set_panel(
                    session_id="s1",
                    surface_id="surf",
                    surface_store=store,
                    id=f"panel-{i}",
                    component="metric-cards",
                    title=f"Panel {i}",
                )
                assert result.get("ok") is True

            # 9th panel should fail
            result = await execute_set_panel(
                session_id="s1",
                surface_id="surf",
                surface_store=store,
                id="panel-overflow",
                component="metric-cards",
                title="Too Many",
            )
            assert "error" in result
            assert "Maximum" in result["error"]

        asyncio.run(_run())


# ===================================================================
# 7. Tool execution unit tests
# ===================================================================


class TestToolExecution:
    """Test tool implementations directly."""

    def test_execute_get_surface_state(self) -> None:
        import asyncio
        from app.agent.surface_store import SurfaceStore
        from app.agent.tools import execute_get_surface_state

        store = SurfaceStore()

        async def _run():
            result = await execute_get_surface_state(
                session_id="s1", surface_id="surf", surface_store=store
            )
            assert result["surface_id"] == "surf"
            assert result["panels"] == []

        asyncio.run(_run())

    def test_execute_remove_nonexistent_panel(self) -> None:
        import asyncio
        from app.agent.surface_store import SurfaceStore
        from app.agent.tools import execute_remove_panel

        store = SurfaceStore()

        async def _run():
            result = await execute_remove_panel(
                session_id="s1",
                surface_id="surf",
                surface_store=store,
                panel_id="ghost",
            )
            assert "error" in result

        asyncio.run(_run())

    def test_execute_query_data_unknown_type(self) -> None:
        import asyncio
        from app.agent.tools import execute_query_data

        async def _run():
            result = await execute_query_data(
                query_type="foobar",
                params=None,
                dataset_id="ds1",
                repository=MagicMock(),
            )
            assert "error" in result

        asyncio.run(_run())

    def test_data_size_limit(self) -> None:
        """Inline data > 50KB should be rejected."""
        import asyncio
        from app.agent.surface_store import SurfaceStore
        from app.agent.tools import execute_set_panel

        store = SurfaceStore()

        async def _run():
            big_data = {"inline": {"payload": "x" * 60000}}
            result = await execute_set_panel(
                session_id="s1",
                surface_id="surf",
                surface_store=store,
                id="big-panel",
                component="data-table",
                title="Big",
                data=big_data,
            )
            assert "error" in result
            assert "50KB" in result["error"]

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# SSE parsing helper
# ---------------------------------------------------------------------------


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
