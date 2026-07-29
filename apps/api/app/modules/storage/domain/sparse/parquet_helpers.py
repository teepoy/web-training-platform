"""Runtime parquet write/read helpers for materialized dataset shards.

Embeds manifest metadata in the parquet schema and validates
schema-version on read so that cross-deployment schema drift is caught
early.
"""

from __future__ import annotations

import hashlib
import io
import json

import pyarrow as pa
import pyarrow.parquet as pq

_METADATA_KEY = "runtime_manifest"


def write_runtime_parquet(
    rows: list[dict],
    schema_version: str,
    *,
    row_group_size: int = 1024,
    metadata: dict | None = None,
) -> bytes:
    """Write rows as a single parquet blob with embedded manifest metadata.

    Parameters
    ----------
    rows:
        List of row dicts.  Keys are column names; binary values are
        stored as ``pyarrow.binary``.
    schema_version:
        Schema version string embedded in the parquet metadata so readers
        can detect drift.
    row_group_size:
        Maximum number of rows per row group (passed to
        ``pq.write_table``).
    metadata:
        Optional manifest dict (purpose, job_id, view_id, …) merged into
        the embedded metadata.

    Returns
    -------
    bytes
        Raw parquet bytes suitable for in-memory I/O or object-storage
        upload.
    """
    column_data: dict[str, list] = _build_column_data(rows)

    manifest: dict[str, object] = dict(metadata) if metadata else {}
    manifest["schema_version"] = schema_version

    table = pa.Table.from_pydict(column_data)
    table = _embed_manifest(table, manifest)

    buf = io.BytesIO()
    pq.write_table(table, buf, row_group_size=row_group_size)
    raw = buf.getvalue()

    # Compute size / checksum from the written bytes, then re-embed.
    manifest["byte_size"] = len(raw)
    manifest["checksum_sha256"] = hashlib.sha256(raw).hexdigest()

    table = _embed_manifest(table, manifest)
    buf = io.BytesIO()
    pq.write_table(table, buf, row_group_size=row_group_size)
    return buf.getvalue()


def read_runtime_parquet(
    data: bytes,
    *,
    expected_schema_version: str | None = None,
) -> tuple[list[dict], dict]:
    """Read a runtime parquet blob and return (rows, manifest_metadata).

    Parameters
    ----------
    data:
        Parquet bytes produced by :func:`write_runtime_parquet`.
    expected_schema_version:
        When set, the embedded ``schema_version`` must match exactly;
        otherwise a ``ValueError`` is raised.

    Returns
    -------
    tuple[list[dict], dict]
        A 2-tuple of ``(rows, metadata)`` where *rows* is a list of
        per-row dicts and *metadata* is the embedded manifest dict.
    """
    table = pq.read_table(io.BytesIO(data))
    manifest = _extract_manifest(table)

    embedded_version = manifest.get("schema_version")
    if (
        expected_schema_version is not None
        and embedded_version != expected_schema_version
    ):
        raise ValueError(
            f"Schema version mismatch: expected {expected_schema_version!r}, "
            f"got {embedded_version!r}"
        )

    rows = _table_to_row_dicts(table)
    return rows, manifest


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _build_column_data(rows: list[dict]) -> dict[str, list]:
    """Build columnar dict from a list of per-row dicts.

    Collects all unique keys across rows so that sparse / partial rows
    are represented with ``None`` values rather than triggering a
    pyarrow schema error.
    """
    if not rows:
        return {}

    all_keys: list[str] = list(dict.fromkeys(k for row in rows for k in row))
    return {key: [row.get(key) for row in rows] for key in all_keys}


def _embed_manifest(table: pa.Table, manifest: dict[str, object]) -> pa.Table:
    """Replace the table's schema metadata with a single JSON-encoded key."""
    raw = json.dumps(manifest, default=str)
    return table.replace_schema_metadata({_METADATA_KEY: raw.encode("utf-8")})


def _extract_manifest(table: pa.Table) -> dict:
    """Decode the ``runtime_manifest`` JSON blob from schema metadata."""
    schema_metadata = table.schema.metadata
    if schema_metadata is None:
        return {}
    encoded = schema_metadata.get(_METADATA_KEY.encode("utf-8"))
    if encoded is None:
        return {}
    return json.loads(encoded)


def _table_to_row_dicts(table: pa.Table) -> list[dict]:
    """Convert a pyarrow ``Table`` to a list of per-row dicts."""
    col_data = table.to_pydict()
    if not col_data:
        return []
    col_names = list(col_data.keys())
    result: list[dict] = []
    for i in range(table.num_rows):
        result.append({name: col_data[name][i] for name in col_names})
    return result
