from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import BinaryIO

from app.modules.storage.domain.storage_agg import DatasetStorageAgg
from app.shared.api.schemas import Dataset


ANNOTATION_TRANSFER_FORMAT = "platform.annotations.jsonl"
ANNOTATION_TRANSFER_VERSION = 1


@dataclass(frozen=True)
class AnnotationImportResult:
    imported: int
    cleared: int


async def export_annotations_jsonl(
    dataset: Dataset,
    storage: DatasetStorageAgg,
    *,
    page_rows: int,
) -> AsyncIterator[bytes]:
    header = {
        "format": ANNOTATION_TRANSFER_FORMAT,
        "version": ANNOTATION_TRANSFER_VERSION,
        "identity": "sample_id",
        "mode": "replace_provided",
        "dataset_contract": {
            "dataset_type": dataset.dataset_type,
            "task_type": dataset.task_spec.task_type,
            "label_space": list(dataset.task_spec.label_space),
        },
    }
    yield _jsonl_line(header)
    offset = 0
    while True:
        rows, total = await storage.list_samples(
            offset=offset,
            limit=page_rows,
            with_labels=True,
            order_by="id",
        )
        for row in rows:
            if row.latest_label is not None:
                yield _jsonl_line(
                    {"sample_id": str(row.sample_id), "label": str(row.latest_label)}
                )
        offset += len(rows)
        if offset >= total:
            return
        if not rows:
            raise RuntimeError(
                "Dataset storage returned an empty annotation export page before total"
            )


async def import_annotations_jsonl(
    dataset: Dataset,
    storage: DatasetStorageAgg,
    file: BinaryIO,
    *,
    actor_id: str,
    max_bytes: int,
    max_records: int,
    batch_rows: int,
) -> AnnotationImportResult:
    consumed = 0

    async def read_line() -> bytes:
        nonlocal consumed
        line = await asyncio.to_thread(file.readline, max_bytes - consumed + 1)
        consumed += len(line)
        if consumed > max_bytes:
            raise ValueError("Annotation import exceeds the configured byte limit")
        return line

    first = await read_line()
    if not first:
        raise ValueError("Annotation import file is empty")
    header = _parse_object(first, line_number=1)
    if (
        header.get("format") != ANNOTATION_TRANSFER_FORMAT
        or header.get("version") != ANNOTATION_TRANSFER_VERSION
        or header.get("identity") != "sample_id"
        or header.get("mode") != "replace_provided"
    ):
        raise ValueError("Unsupported annotation transfer header")

    expected_contract = {
        "dataset_type": dataset.dataset_type,
        "task_type": dataset.task_spec.task_type,
        "label_space": list(dataset.task_spec.label_space),
    }
    if header.get("dataset_contract") != expected_contract:
        raise ValueError(
            "Annotation transfer Dataset contract does not match the target"
        )

    labels = set(dataset.task_spec.label_space)
    records: dict[str, str | None] = {}
    line_number = 1
    while True:
        raw = await read_line()
        if not raw:
            break
        line_number += 1
        if not raw.strip():
            continue
        item = _parse_object(raw, line_number=line_number)
        sample_id = item.get("sample_id")
        label = item.get("label")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError(
                f"Line {line_number}: sample_id must be a non-empty string"
            )
        if label is not None and (not isinstance(label, str) or label not in labels):
            raise ValueError(
                f"Line {line_number}: label is not in the Dataset label space"
            )
        if sample_id in records:
            raise ValueError(f"Line {line_number}: duplicate sample_id {sample_id!r}")
        records[sample_id] = label
        if len(records) > max_records:
            raise ValueError("Annotation import exceeds the configured record limit")

    ordered_ids = list(records)
    existing: set[str] = set()
    for offset in range(0, len(ordered_ids), batch_rows):
        existing.update(
            await storage.existing_sample_ids(
                set(ordered_ids[offset : offset + batch_rows])
            )
        )
    unknown = set(records) - existing
    if unknown:
        preview = ", ".join(sorted(unknown)[:5])
        raise ValueError(
            f"Annotation import references {len(unknown)} unknown sample IDs: {preview}"
        )

    imported = 0
    cleared = 0
    items = list(records.items())
    for offset in range(0, len(items), batch_rows):
        batch = items[offset : offset + batch_rows]
        imported += await storage.replace_annotations_for_samples(
            batch, created_by=actor_id
        )
        cleared += sum(1 for _, label in batch if label is None)
    return AnnotationImportResult(imported=imported, cleared=cleared)


def _parse_object(raw: bytes, *, line_number: int) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Line {line_number}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Line {line_number}: expected a JSON object")
    return value


def _jsonl_line(value: dict[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()
