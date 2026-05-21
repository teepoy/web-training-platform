"""Metadata schema inference using Polars."""

from __future__ import annotations

from typing import Any

from app.shared.api.schemas import DeclaredMetadataKey, MetadataKeyInfo


def scan_metadata_types(
    metadata_dicts: list[dict[str, Any]],
) -> dict[str, MetadataKeyInfo]:
    if not metadata_dicts:
        return {}

    try:
        return _scan_with_polars(metadata_dicts)
    except ImportError:
        return _scan_pure_python(metadata_dicts)


def _scan_with_polars(
    metadata_dicts: list[dict[str, Any]],
) -> dict[str, MetadataKeyInfo]:
    import polars as pl  # pyright: ignore[reportMissingImports]

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
        if dtype in (
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
            pl.Float32,
            pl.Float64,
        ):
            info.min = col.min()
            info.max = col.max()
        result[col_name] = info

    return result


def _scan_pure_python(
    metadata_dicts: list[dict[str, Any]],
) -> dict[str, MetadataKeyInfo]:
    keys: dict[str, list[Any]] = {}
    for md in metadata_dicts:
        for key, value in md.items():
            keys.setdefault(key, []).append(value)

    result: dict[str, MetadataKeyInfo] = {}
    for key, values in keys.items():
        non_null = [value for value in values if value is not None]
        type_set = {type(value).__name__ for value in non_null}
        dominant = type_set.pop() if len(type_set) == 1 else "mixed"

        distinct = list({repr(value): value for value in non_null}.values())
        info = MetadataKeyInfo(
            type=dominant,
            null_count=sum(1 for value in values if value is None),
            n_unique=len(distinct),
            sample_values=distinct[:5],
        )
        if dominant in ("int", "float"):
            nums = [value for value in non_null if isinstance(value, (int, float))]
            if nums:
                info.min = min(nums)
                info.max = max(nums)
        result[key] = info

    return result


def build_metadata_block(
    declared: dict[str, DeclaredMetadataKey] | None,
    inferred: dict[str, MetadataKeyInfo] | None,
) -> str:
    if not declared and not inferred:
        return "  (no metadata keys found)"

    lines: list[str] = []

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

        if inferred:
            for key, info in inferred.items():
                if key not in declared:
                    examples = ", ".join(repr(v) for v in info.sample_values[:3])
                    lines.append(
                        f"  - `{key}` ({info.type}, {info.n_unique} distinct) — e.g. {examples}"
                    )
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
