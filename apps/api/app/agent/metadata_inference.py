"""Metadata schema inference using Polars.

Two tiers:
  1. Declared schema — read from ``task_spec.metadata_schema`` (preferred).
  2. Polars scan — sample N rows, load into a Polars DataFrame, read the
     inferred schema.  Purely mechanical: no LLM, no heuristics.
"""
from __future__ import annotations

from typing import Any

from app.api.schemas import DeclaredMetadataKey, MetadataKeyInfo


def scan_metadata_types(
    metadata_dicts: list[dict[str, Any]],
) -> dict[str, MetadataKeyInfo]:
    """Scan a list of metadata dicts and return per-key type info.

    Uses Polars for deterministic type inference when available, falls
    back to a pure-Python scan when Polars is not installed.
    """
    if not metadata_dicts:
        return {}

    try:
        return _scan_with_polars(metadata_dicts)
    except ImportError:
        return _scan_pure_python(metadata_dicts)


def _scan_with_polars(
    metadata_dicts: list[dict[str, Any]],
) -> dict[str, MetadataKeyInfo]:
    """Use ``polars.DataFrame`` for fast, exact type inference."""
    import polars as pl

    df = pl.DataFrame(metadata_dicts)
    result: dict[str, MetadataKeyInfo] = {}

    for col_name in df.columns:
        dtype = df.schema[col_name]
        col = df[col_name]
        info = MetadataKeyInfo(
            type=str(dtype),
            null_count=col.null_count(),
            n_unique=col.n_unique(),
            sample_values=col.drop_nulls().unique().head(5).to_list(),
        )
        if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                     pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                     pl.Float32, pl.Float64):
            info.min = col.min()
            info.max = col.max()
        result[col_name] = info

    return result


def _scan_pure_python(
    metadata_dicts: list[dict[str, Any]],
) -> dict[str, MetadataKeyInfo]:
    """Fallback when Polars is not available.  Slower but dependency-free."""
    keys: dict[str, list[Any]] = {}
    for md in metadata_dicts:
        for k, v in md.items():
            keys.setdefault(k, []).append(v)

    result: dict[str, MetadataKeyInfo] = {}
    for k, values in keys.items():
        non_null = [v for v in values if v is not None]
        type_set = {type(v).__name__ for v in non_null}
        dominant = type_set.pop() if len(type_set) == 1 else "mixed"

        distinct = list({repr(v): v for v in non_null}.values())
        info = MetadataKeyInfo(
            type=dominant,
            null_count=sum(1 for v in values if v is None),
            n_unique=len(distinct),
            sample_values=distinct[:5],
        )
        if dominant in ("int", "float"):
            nums = [v for v in non_null if isinstance(v, (int, float))]
            if nums:
                info.min = min(nums)
                info.max = max(nums)
        result[k] = info

    return result


def build_metadata_block(
    declared: dict[str, DeclaredMetadataKey] | None,
    inferred: dict[str, MetadataKeyInfo] | None,
) -> str:
    """Build the metadata section of the agent prompt.

    Declared schema wins when present — it has human descriptions.
    Inferred fills in for undeclared datasets.
    """
    if not declared and not inferred:
        return "  (no metadata keys found)"

    lines: list[str] = []

    # Use declared keys as primary source
    if declared:
        for key, decl in declared.items():
            inf = inferred.get(key) if inferred else None
            type_str = decl.type
            if inf:
                extra = f", {inf.n_unique} distinct"
                if inf.min is not None:
                    extra += f", range {inf.min}–{inf.max}"
                type_str += extra
            desc = decl.description or "(no description)"
            lines.append(f"  - `{key}` ({type_str}) — {desc}")

        # Append any inferred keys not in declared
        if inferred:
            for key, info in inferred.items():
                if key not in declared:
                    examples = ", ".join(repr(v) for v in info.sample_values[:3])
                    lines.append(f"  - `{key}` ({info.type}, {info.n_unique} distinct) — e.g. {examples}")
        lines.append("  (Schema declared by dataset creator)")
    elif inferred:
        for key, info in inferred.items():
            desc = f"{info.type}, {info.n_unique} distinct"
            if info.min is not None:
                desc += f", range {info.min}–{info.max}"
            examples = ", ".join(repr(v) for v in info.sample_values[:3])
            lines.append(f"  - `{key}` ({desc}) — e.g. {examples}")
        lines.append("  (Schema inferred from sample scan — no descriptions available)")

    return "\n".join(lines)
