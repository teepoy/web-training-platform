"""Label Studio client wrapper for annotation management.

This module provides :class:`LabelStudioClient` — an async wrapper around the
``label-studio-sdk`` library for managing annotation projects, tasks, and
annotations in Label Studio.

Label Studio is always required.  There is no null/disabled mode.

Error mapping
-------------
- SDK connection errors  → ``LabelStudioConnectionError``
- SDK 404 errors         → ``LabelStudioNotFoundError``
- All other SDK errors   → ``LabelStudioError``

Format converters
-----------------
Module-level helpers convert between the platform's flat label representation
and Label Studio's structured annotation JSON format.
"""
from __future__ import annotations

import asyncio
from typing import Any


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LabelStudioError(Exception):
    """Base error for Label Studio client failures."""


class LabelStudioConnectionError(LabelStudioError):
    """Raised when the Label Studio server is unreachable."""


class LabelStudioNotFoundError(LabelStudioError):
    """Raised when a requested Label Studio resource does not exist (404)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_dict(obj: Any) -> dict:
    """Convert a label-studio-sdk Pydantic model to a plain dict.

    The SDK returns Pydantic v2 model instances.  We normalise them to plain
    ``dict`` objects so callers don't need to know which SDK version is in use.
    If the object already is a dict (e.g. from a mock) it is returned as-is.
    """
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    # Fallback: try __dict__ (strips private attrs)
    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


def _wrap_sdk_error(exc: Exception) -> LabelStudioError:
    """Map a label-studio-sdk exception to our error hierarchy."""
    # Import lazily to avoid hard dependency at module load time
    try:
        from label_studio_sdk.core.api_error import ApiError  # type: ignore[import]

        if isinstance(exc, ApiError):
            if exc.status_code == 404:
                return LabelStudioNotFoundError(str(exc))
            return LabelStudioError(str(exc))
    except ImportError:
        pass

    msg = str(exc).lower()
    if any(word in msg for word in ("connect", "connection", "unreachable", "refused")):
        return LabelStudioConnectionError(str(exc))
    return LabelStudioError(str(exc))


# ---------------------------------------------------------------------------
# Real client
# ---------------------------------------------------------------------------


class LabelStudioClient:
    """Async wrapper around the ``label-studio-sdk`` synchronous client.

    All SDK calls are offloaded to a thread via :func:`asyncio.to_thread` so
    the FastAPI event loop is never blocked.

    Parameters
    ----------
    url:
        Base URL of the Label Studio instance, e.g. ``http://localhost:8080``.
    api_key:
        Label Studio API key (found in Account → Access Token).
    """

    def __init__(self, url: str, api_key: str) -> None:
        from label_studio_sdk import LabelStudio  # type: ignore[import]

        self._client = LabelStudio(base_url=url, api_key=api_key)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def create_project(self, name: str, label_config: str) -> dict:
        """Create a new Label Studio project.

        Parameters
        ----------
        name:
            Human-readable project title.
        label_config:
            XML labeling configuration string.

        Returns
        -------
        dict
            Project object with at least ``id`` and ``title`` keys.
        """
        try:
            result = await asyncio.to_thread(
                self._client.projects.create,
                title=name,
                label_config=label_config,
            )
            return _to_dict(result)
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    async def get_project(self, project_id: int) -> dict:
        """Fetch a single project by ID.

        Parameters
        ----------
        project_id:
            Numeric Label Studio project ID.

        Returns
        -------
        dict
            Project object.
        """
        try:
            result = await asyncio.to_thread(
                self._client.projects.get, id=project_id
            )
            return _to_dict(result)
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    async def list_projects(self) -> list[dict]:
        """List all projects accessible to the authenticated user.

        Returns
        -------
        list[dict]
            List of project objects.
        """
        try:
            pager = await asyncio.to_thread(self._client.projects.list)
            return [_to_dict(p) for p in pager]
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    async def create_task(self, project_id: int, data: dict) -> dict:
        """Create a single task in a project.

        Parameters
        ----------
        project_id:
            Target project ID.
        data:
            Task data payload, e.g. ``{"image": "http://..."}``.

        Returns
        -------
        dict
            Created task object with at least an ``id`` key.
        """
        try:
            result = await asyncio.to_thread(
                self._client.tasks.create,
                project=project_id,
                data=data,
            )
            return _to_dict(result)
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    async def list_tasks(
        self, project_id: int, page: int = 1, page_size: int = 50
    ) -> tuple[list[dict], int]:
        """List tasks for a project with pagination.

        Parameters
        ----------
        project_id:
            Project ID to filter by.
        page:
            1-based page number.
        page_size:
            Number of tasks per page.

        Returns
        -------
        tuple[list[dict], int]
            ``(tasks, total_count)`` where *total_count* is the number of tasks
            in the project (not just the current page).
        """
        try:
            pager = await asyncio.to_thread(
                self._client.tasks.list,
                project=project_id,
                page=page,
                page_size=page_size,
            )
            # SyncPagerExt wraps a SyncPager whose ``response`` is a
            # PaginatedRoleBasedTaskList with a ``total`` field.
            tasks = [_to_dict(t) for t in pager]
            total: int = 0
            if hasattr(pager, "response") and pager.response is not None:
                resp = pager.response
                total_val = (
                    resp.get("total") if isinstance(resp, dict)
                    else getattr(resp, "total", None)
                )
                if total_val is not None:
                    total = int(total_val)
            if total == 0:
                total = len(tasks)
            return tasks, total
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    async def get_task(self, task_id: int) -> dict:
        """Fetch a single task by ID.

        Parameters
        ----------
        task_id:
            Numeric task ID.

        Returns
        -------
        dict
            Task object.
        """
        try:
            result = await asyncio.to_thread(
                self._client.tasks.get, id=str(task_id)
            )
            return _to_dict(result)
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    # ------------------------------------------------------------------
    # Annotations
    # ------------------------------------------------------------------

    async def create_annotation(
        self, task_id: int, result: list[dict]
    ) -> dict:
        """Create an annotation on a task.

        Parameters
        ----------
        task_id:
            ID of the task to annotate.
        result:
            List of annotation result objects in Label Studio format.

        Returns
        -------
        dict
            Created annotation object.
        """
        try:
            annotation = await asyncio.to_thread(
                self._client.annotations.create,
                id=task_id,
                result=result,
            )
            return _to_dict(annotation)
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    async def list_annotations(self, task_id: int) -> list[dict]:
        """List all annotations for a task.

        Parameters
        ----------
        task_id:
            ID of the task.

        Returns
        -------
        list[dict]
            List of annotation objects.
        """
        try:
            annotations = await asyncio.to_thread(
                self._client.annotations.list, id=task_id
            )
            return [_to_dict(a) for a in annotations]
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    async def export_project(self, project_id: int) -> list[dict]:
        """Export all tasks with their annotations from a project.

        Parameters
        ----------
        project_id:
            ID of the project to export.

        Returns
        -------
        list[dict]
            List of task dicts, each including an ``annotations`` key.
        """
        try:
            data = await asyncio.to_thread(
                self._client.projects.exports.as_json,
                project_id=project_id,
            )
            if isinstance(data, list):
                return [_to_dict(item) if not isinstance(item, dict) else item for item in data]
            return []
        except Exception as exc:
            raise _wrap_sdk_error(exc) from exc

    # ------------------------------------------------------------------
    # Config generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_image_classification_config(label_space: list[str]) -> str:
        """Generate a Label Studio XML config for image classification.

        Parameters
        ----------
        label_space:
            List of class labels, e.g. ``["cat", "dog"]``.

        Returns
        -------
        str
            XML labeling configuration string.
        """
        choices_xml = "\n".join(
            f'      <Choice value="{label}"/>' for label in label_space
        )
        return (
            "<View>\n"
            '  <Image name="image" value="$image"/>\n'
            '  <Choices name="classification" toName="image">\n'
            f"{choices_xml}\n"
            "  </Choices>\n"
            "</View>"
        )


# ---------------------------------------------------------------------------
# Format conversion helpers
# ---------------------------------------------------------------------------


def platform_annotation_to_ls(
    label: str, label_config_info: dict | None = None
) -> list[dict]:
    """Convert a platform label string to a Label Studio annotation result.

    Parameters
    ----------
    label:
        The classification label from the platform, e.g. ``"cat"``.
    label_config_info:
        Optional hint dict (reserved for future use; currently unused).

    Returns
    -------
    list[dict]
        List with a single LS ``choices`` result object.
    """
    return [
        {
            "from_name": "classification",
            "to_name": "image",
            "type": "choices",
            "value": {"choices": [label]},
        }
    ]


def ls_annotation_to_platform(result: list[dict]) -> str:
    """Extract the first choice label from a Label Studio annotation result.

    Parameters
    ----------
    result:
        List of LS result objects from an annotation's ``result`` field.

    Returns
    -------
    str
        The first choice label found, or ``""`` if none is present.
    """
    for item in result:
        if item.get("type") == "choices":
            choices = item.get("value", {}).get("choices", [])
            if choices:
                return choices[0]
    return ""
