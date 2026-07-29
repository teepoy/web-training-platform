from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.shared.api.schemas import Sample
from app.shared.db.registry import SampleORM

_SAMPLES_COLUMNS = "id, dataset_id, image_uris, metadata_json, ls_task_id"


class ScBatchReader:
    """Reads sample batches via raw async SQL for speed.

    All public methods are async — they use the async engine directly,
    avoiding the asyncio.to_thread / MissingGreenlet trap.
    """

    def __init__(self, async_engine: AsyncEngine) -> None:
        self._engine = async_engine

    async def _read(self, query: str, params: dict[str, Any] | None = None) -> Any:
        async with self._engine.connect() as conn:
            result = await conn.execute(text(query), params or {})
            return result.fetchall()

    async def list_all_samples(self, dataset_id: str) -> list[Sample]:
        """Return every sample for *dataset_id*."""
        rows = await self._read(
            f"SELECT {_SAMPLES_COLUMNS} FROM samples WHERE dataset_id = :dataset_id",
            params={"dataset_id": dataset_id},
        )
        return _rows_to_samples(rows)

    async def list_all_sample_ids_meta(
        self, dataset_id: str
    ) -> list[dict[str, object]]:
        """Return (id, metadata_json) for every sample in *dataset_id*."""
        rows = await self._read(
            "SELECT id, metadata_json FROM samples WHERE dataset_id = :dataset_id",
            params={"dataset_id": dataset_id},
        )
        return _rows_to_dicts(rows)

    async def map_defect_ids_to_sample_ids(
        self,
        dataset_id: str,
        defect_ids: set[str],
    ) -> dict[str, str]:
        """Resolve SC defect identities with one database query."""
        if not defect_ids:
            return {}

        defect_id_expr = SampleORM.metadata_json["defect_id"].as_string()
        stmt = (
            select(SampleORM.id, defect_id_expr.label("defect_id"))
            .where(
                SampleORM.dataset_id == dataset_id,
                defect_id_expr.in_(defect_ids),
            )
            .order_by(SampleORM.id)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).all()
        return {
            str(row.defect_id): str(row.id) for row in rows if row.defect_id is not None
        }

    async def list_samples_paginated(
        self, dataset_id: str, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[Sample], int]:
        """Paginated sample list — total count + page rows."""
        count_rows = await self._read(
            "SELECT COUNT(*) AS total FROM samples WHERE dataset_id = :dataset_id",
            params={"dataset_id": dataset_id},
        )
        total: int = count_rows[0][0] if count_rows else 0

        if total == 0:
            return [], 0

        rows = await self._read(
            f"SELECT {_SAMPLES_COLUMNS} FROM samples WHERE dataset_id = :dataset_id "
            "ORDER BY id LIMIT :limit OFFSET :offset",
            params={"dataset_id": dataset_id, "limit": limit, "offset": offset},
        )
        return _rows_to_samples(rows), total


def _row_to_dict(row: Any) -> dict[str, object]:
    """Convert a SQLAlchemy Row to a plain dict."""
    return dict(row._mapping)


def _rows_to_dicts(rows: Any) -> list[dict[str, object]]:
    """Convert SQLAlchemy Row results to list[dict] with JSON columns parsed."""
    result: list[dict[str, object]] = []
    for row in rows:
        parsed: dict[str, object] = {}
        for k, v in _row_to_dict(row).items():
            if k in ("metadata_json", "image_uris") and isinstance(v, str):
                try:
                    parsed[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    parsed[k] = v
            else:
                parsed[k] = v
        result.append(parsed)
    return result


def _dict_to_sample(row: dict[str, object]) -> Sample:
    """Build a ``Sample`` from a raw row dict (JSON strings already parsed)."""
    image_uris_raw = row.get("image_uris", [])
    metadata_raw = row.get("metadata_json", {})
    ls_task_id_raw = row.get("ls_task_id")
    return Sample(
        id=str(row.get("id", "")),
        dataset_id=str(row.get("dataset_id", "")),
        image_uris=image_uris_raw if isinstance(image_uris_raw, list) else [],
        metadata=metadata_raw if isinstance(metadata_raw, dict) else {},
        ls_task_id=int(str(ls_task_id_raw)) if ls_task_id_raw is not None else None,
    )


def _rows_to_samples(rows: Any) -> list[Sample]:
    return [_dict_to_sample(d) for d in _rows_to_dicts(rows)]
