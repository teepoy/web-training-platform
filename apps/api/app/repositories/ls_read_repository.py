"""Read-only repository for Label Studio Postgres database.

Queries the Label Studio ``task`` and ``task_completion`` tables directly
to retrieve annotations without going through the LS REST API.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class LsReadRepository:
    """Read-only repository for Label Studio's Postgres database."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_annotations_for_tasks(
        self, task_ids: list[int]
    ) -> dict[int, list[dict[str, Any]]]:
        """Return annotations grouped by task ID.

        Parameters
        ----------
        task_ids:
            List of Label Studio task IDs to fetch annotations for.

        Returns
        -------
        dict[int, list[dict]]
            Mapping from task_id to list of annotation dicts, each with
            ``id``, ``result``, ``completed_by_id``, ``created_at``, and
            ``was_cancelled`` keys.
        """
        if not task_ids:
            return {}

        async with self._session_factory() as session:
            # Use ANY() to pass the list as a parameter
            rows = (
                await session.execute(
                    text(
                        "SELECT id, task_id, result, completed_by_id, created_at, was_cancelled "
                        "FROM task_completion "
                        "WHERE task_id = ANY(:task_ids) "
                        "ORDER BY created_at ASC"
                    ),
                    {"task_ids": task_ids},
                )
            ).fetchall()

        result: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            tid = row[1]
            result.setdefault(tid, []).append(
                {
                    "id": row[0],
                    "task_id": tid,
                    "result": row[2],
                    "completed_by_id": row[3],
                    "created_at": str(row[4]) if row[4] else None,
                    "was_cancelled": row[5],
                }
            )
        return result

    async def get_tasks_for_project(
        self, project_id: int
    ) -> list[dict[str, Any]]:
        """Return all tasks for a Label Studio project.

        Parameters
        ----------
        project_id:
            Label Studio project ID.

        Returns
        -------
        list[dict]
            List of task dicts with ``id``, ``data``, ``total_annotations``,
            ``is_labeled``, ``created_at`` keys.
        """
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT id, data, total_annotations, is_labeled, created_at "
                        "FROM task "
                        "WHERE project_id = :project_id "
                        "ORDER BY id ASC"
                    ),
                    {"project_id": project_id},
                )
            ).fetchall()

        return [
            {
                "id": row[0],
                "data": row[1],
                "total_annotations": row[2],
                "is_labeled": row[3],
                "created_at": str(row[4]) if row[4] else None,
            }
            for row in rows
        ]
