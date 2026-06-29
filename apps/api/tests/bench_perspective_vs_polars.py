"""Benchmark perspective-py vs polars on ~500k defect sample rows.

Operations:
  1. Rectangle selection (spatial bounding box)
  2. Filter by class / prediction
  3. Filter by defect_ids (IN selection)
  4. Rectangle filter -> offset 10 take 10 -> to_dicts (trigger lazy eval)
  5. Class filter -> sample 10 -> to_dicts (trigger lazy eval)
"""

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_CONFIG_PROFILE", "test")

import polars as pl  # noqa: E402
from perspective import Server  # noqa: E402

from app.modules.sc.wafer_data_gen import build_patch_sample  # noqa: E402


NUM_SAMPLES = 500_000
RANDOM_SEED = 42
WAFER_RADIUS_NM = 150_000_000
NUM_WARMUP = 2
NUM_ITER = 10


def _row_from_sample(sample) -> dict:
    return {
        "defect_id": sample.defect_id,
        "wafer_x": sample.wafer_x,
        "wafer_y": sample.wafer_y,
        "class_number": sample.class_number,
        "rough_bin": sample.rough_bin,
        "wafer_key": sample.wafer_key,
    }


def generate_data(n: int) -> tuple[pl.DataFrame, list[str]]:
    print(f"Generating {n:,} sample rows ...", flush=True)
    t0 = time.perf_counter()
    rows = [
        _row_from_sample(build_patch_sample(i))
        for i in range(n)
    ]
    gen_elapsed = time.perf_counter() - t0
    print(f"  generated in {gen_elapsed:.2f}s ({n / gen_elapsed:,.0f} rows/s)", flush=True)

    df = pl.DataFrame(rows, infer_schema_length=n)
    print(f"  DataFrame shape: {df.shape}", flush=True)
    print(f"  columns: {df.columns}", flush=True)
    print(f"  memory: {df.estimated_size('mb'):.1f} MB", flush=True)

    defect_ids = df["defect_id"].to_list()
    return df, defect_ids


def bench_rectangle_selection(df: pl.DataFrame, psp_table) -> None:
    """Rectangle selection: select points in a bounding box."""
    print("\n─── Rectangle Selection ───", flush=True)

    # Pick a rectangle in the center 25% area
    half = WAFER_RADIUS_NM // 2
    rect = {
        "min_x": -half,
        "max_x": half,
        "min_y": -half,
        "max_y": half,
    }
    print(f"  bbox: x=[{rect['min_x']:,}, {rect['max_x']:,}]  y=[{rect['min_y']:,}, {rect['max_y']:,}]", flush=True)

    # ── polars ──
    for _ in range(NUM_WARMUP):
        _ = df.filter(
            pl.col("wafer_x").is_between(rect["min_x"], rect["max_x"])
            & pl.col("wafer_y").is_between(rect["min_y"], rect["max_y"])
        )
    pl_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        result = df.filter(
            pl.col("wafer_x").is_between(rect["min_x"], rect["max_x"])
            & pl.col("wafer_y").is_between(rect["min_y"], rect["max_y"])
        )
        elapsed = time.perf_counter() - t0
        pl_times.append(elapsed)
        if i == 0:
            print(f"  polars matched {result.height:,} rows (first iter)", flush=True)

    pl_avg = sum(pl_times) / len(pl_times)
    pl_min = min(pl_times)
    print(f"  polars: avg={pl_avg*1000:.3f}ms  min={pl_min*1000:.3f}ms (n={NUM_ITER})", flush=True)

    # ── perspective ──
    for _ in range(NUM_WARMUP):
        v = psp_table.view(filter=[
            ["wafer_x", ">=", rect["min_x"]],
            ["wafer_x", "<=", rect["max_x"]],
            ["wafer_y", ">=", rect["min_y"]],
            ["wafer_y", "<=", rect["max_y"]],
        ])
        v.delete()

    psp_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        v = psp_table.view(filter=[
            ["wafer_x", ">=", rect["min_x"]],
            ["wafer_x", "<=", rect["max_x"]],
            ["wafer_y", ">=", rect["min_y"]],
            ["wafer_y", "<=", rect["max_y"]],
        ])
        row_count = v.num_rows()
        elapsed = time.perf_counter() - t0
        v.delete()
        psp_times.append(elapsed)
        if i == 0:
            print(f"  perspective matched {row_count:,} rows (first iter)", flush=True)

    psp_avg = sum(psp_times) / len(psp_times)
    psp_min = min(psp_times)
    ratio = psp_avg / pl_avg if pl_avg > 0 else float("inf")
    print(f"  perspective: avg={psp_avg*1000:.3f}ms  min={psp_min*1000:.3f}ms (n={NUM_ITER})", flush=True)
    print(f"  >>> polars {pl_avg*1000:.2f}ms vs perspective {psp_avg*1000:.2f}ms  (polars is {ratio:.1f}x faster)", flush=True)


def bench_class_filter(df: pl.DataFrame, psp_table) -> None:
    """Filter by class_number."""
    print("\n─── Filter by Class ───", flush=True)

    target_cls = 42
    print(f"  class_number == {target_cls}", flush=True)

    # ── polars ──
    for _ in range(NUM_WARMUP):
        _ = df.filter(pl.col("class_number") == target_cls)
    pl_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        result = df.filter(pl.col("class_number") == target_cls)
        elapsed = time.perf_counter() - t0
        pl_times.append(elapsed)
        if i == 0:
            print(f"  polars matched {result.height:,} rows (first iter)", flush=True)

    pl_avg = sum(pl_times) / len(pl_times)
    pl_min = min(pl_times)
    print(f"  polars: avg={pl_avg*1000:.3f}ms  min={pl_min*1000:.3f}ms (n={NUM_ITER})", flush=True)

    # ── perspective ──
    for _ in range(NUM_WARMUP):
        v = psp_table.view(filter=[["class_number", "==", target_cls]])
        v.delete()

    psp_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        v = psp_table.view(filter=[["class_number", "==", target_cls]])
        row_count = v.num_rows()
        elapsed = time.perf_counter() - t0
        v.delete()
        psp_times.append(elapsed)
        if i == 0:
            print(f"  perspective matched {row_count:,} rows (first iter)", flush=True)

    psp_avg = sum(psp_times) / len(psp_times)
    psp_min = min(psp_times)
    ratio = psp_avg / pl_avg if pl_avg > 0 else float("inf")
    print(f"  perspective: avg={psp_avg*1000:.3f}ms  min={psp_min*1000:.3f}ms (n={NUM_ITER})", flush=True)
    print(f"  >>> polars {pl_avg*1000:.2f}ms vs perspective {psp_avg*1000:.2f}ms  (polars is {ratio:.1f}x faster)", flush=True)


def bench_defect_id_in_selection(df: pl.DataFrame, psp_table, all_defect_ids: list[str]) -> None:
    """Filter by defect_ids IN selection."""
    print("\n─── Filter by defect_ids (IN selection) ───", flush=True)

    rng = random.Random(RANDOM_SEED)
    target_ids = rng.sample(all_defect_ids, 1000)
    print(f"  {len(target_ids):,} defect_ids", flush=True)

    # ── polars ──
    for _ in range(NUM_WARMUP):
        _ = df.filter(pl.col("defect_id").is_in(target_ids))
    pl_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        result = df.filter(pl.col("defect_id").is_in(target_ids))
        elapsed = time.perf_counter() - t0
        pl_times.append(elapsed)
        if i == 0:
            print(f"  polars matched {result.height:,} rows (first iter)", flush=True)

    pl_avg = sum(pl_times) / len(pl_times)
    pl_min = min(pl_times)
    print(f"  polars: avg={pl_avg*1000:.3f}ms  min={pl_min*1000:.3f}ms (n={NUM_ITER})", flush=True)

    # ── perspective ──
    for _ in range(NUM_WARMUP):
        v = psp_table.view(filter=[["defect_id", "in", target_ids]])
        v.delete()

    psp_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        v = psp_table.view(filter=[["defect_id", "in", target_ids]])
        row_count = v.num_rows()
        elapsed = time.perf_counter() - t0
        v.delete()
        psp_times.append(elapsed)
        if i == 0:
            print(f"  perspective matched {row_count:,} rows (first iter)", flush=True)

    psp_avg = sum(psp_times) / len(psp_times)
    psp_min = min(psp_times)
    ratio = psp_avg / pl_avg if pl_avg > 0 else float("inf")
    print(f"  perspective: avg={psp_avg*1000:.3f}ms  min={psp_min*1000:.3f}ms (n={NUM_ITER})", flush=True)
    print(f"  >>> polars {pl_avg*1000:.2f}ms vs perspective {psp_avg*1000:.2f}ms  (polars is {ratio:.1f}x faster)", flush=True)


def bench_filter_offset_take_to_dicts(df: pl.DataFrame, psp_table) -> None:
    """Rectangle filter -> offset 10 take 10 -> to_dicts (triggers lazy eval)."""
    print("\n─── Rectangle Filter → Offset 10 Take 10 → to_dicts ───", flush=True)

    half = WAFER_RADIUS_NM // 2
    rect = {"min_x": -half, "max_x": half, "min_y": -half, "max_y": half}
    print(f"  bbox: x=[{rect['min_x']:,}, {rect['max_x']:,}]  y=[{rect['min_y']:,}, {rect['max_y']:,}]", flush=True)
    print("  paginate: offset=10, length=10", flush=True)

    # ── polars (lazy: filter + slice + collect -> to_dicts) ──
    lazy_df = df.lazy()
    for _ in range(NUM_WARMUP):
        _ = (
            lazy_df
            .filter(
                pl.col("wafer_x").is_between(rect["min_x"], rect["max_x"])
                & pl.col("wafer_y").is_between(rect["min_y"], rect["max_y"])
            )
            .slice(10, 10)
            .collect()
            .to_dicts()
        )
    pl_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        result = (
            lazy_df
            .filter(
                pl.col("wafer_x").is_between(rect["min_x"], rect["max_x"])
                & pl.col("wafer_y").is_between(rect["min_y"], rect["max_y"])
            )
            .slice(10, 10)
            .collect()
            .to_dicts()
        )
        elapsed = time.perf_counter() - t0
        pl_times.append(elapsed)
        if i == 0:
            print(f"  polars returned {len(result)} dicts (first iter)", flush=True)

    pl_avg = sum(pl_times) / len(pl_times)
    pl_min = min(pl_times)
    print(f"  polars: avg={pl_avg*1000:.3f}ms  min={pl_min*1000:.3f}ms (n={NUM_ITER})", flush=True)

    # ── perspective (must get ALL filtered rows, then slice in python) ──
    for _ in range(NUM_WARMUP):
        v = psp_table.view(filter=[
            ["wafer_x", ">=", rect["min_x"]],
            ["wafer_x", "<=", rect["max_x"]],
            ["wafer_y", ">=", rect["min_y"]],
            ["wafer_y", "<=", rect["max_y"]],
        ])
        _ = v.to_columns()
        v.delete()

    psp_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        v = psp_table.view(filter=[
            ["wafer_x", ">=", rect["min_x"]],
            ["wafer_x", "<=", rect["max_x"]],
            ["wafer_y", ">=", rect["min_y"]],
            ["wafer_y", "<=", rect["max_y"]],
        ])
        columns = v.to_columns()
        # Manual offset + take in Python
        keys = list(columns.keys())
        rows = [{k: columns[k][j] for k in keys} for j in range(10, min(20, len(columns[keys[0]])))]
        elapsed = time.perf_counter() - t0
        v.delete()
        psp_times.append(elapsed)
        if i == 0:
            print(f"  perspective: to_columns()={len(columns[keys[0]]):,} rows, sliced to {len(rows)} dicts (first iter)", flush=True)

    psp_avg = sum(psp_times) / len(psp_times)
    psp_min = min(psp_times)
    ratio = psp_avg / pl_avg if pl_avg > 0 else float("inf")
    print(f"  perspective: avg={psp_avg*1000:.3f}ms  min={psp_min*1000:.3f}ms (n={NUM_ITER})", flush=True)
    print(f"  >>> polars {pl_avg*1000:.2f}ms vs perspective {psp_avg*1000:.2f}ms  (polars is {ratio:.1f}x faster)", flush=True)


def bench_filter_sample_to_dicts(df: pl.DataFrame, psp_table) -> None:
    """Class filter -> sample 10 -> to_dicts (triggers eval)."""
    print("\n─── Class Filter → Sample 10 → to_dicts ───", flush=True)

    target_cls = 42
    print(f"  class_number == {target_cls}, sample n=10", flush=True)

    # ── polars (eager filter + sample + to_dicts; LazyFrame has no .sample()) ──
    for _ in range(NUM_WARMUP):
        _ = (
            df
            .filter(pl.col("class_number") == target_cls)
            .sample(n=10, seed=RANDOM_SEED)
            .to_dicts()
        )
    pl_times = []
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        result = (
            df
            .filter(pl.col("class_number") == target_cls)
            .sample(n=10, seed=RANDOM_SEED)
            .to_dicts()
        )
        elapsed = time.perf_counter() - t0
        pl_times.append(elapsed)
        if i == 0:
            print(f"  polars returned {len(result)} dicts (first iter)", flush=True)

    pl_avg = sum(pl_times) / len(pl_times)
    pl_min = min(pl_times)
    print(f"  polars: avg={pl_avg*1000:.3f}ms  min={pl_min*1000:.3f}ms (n={NUM_ITER})", flush=True)

    # ── perspective (must get ALL filtered rows, then sample in python) ──
    for _ in range(NUM_WARMUP):
        v = psp_table.view(filter=[["class_number", "==", target_cls]])
        _ = v.to_columns()
        v.delete()

    psp_times = []
    rng = random.Random(RANDOM_SEED)
    for i in range(NUM_ITER):
        t0 = time.perf_counter()
        v = psp_table.view(filter=[["class_number", "==", target_cls]])
        columns = v.to_columns()
        # Manual sample in Python
        keys = list(columns.keys())
        n_total = len(columns[keys[0]])
        indices = rng.sample(range(n_total), min(10, n_total))
        rows = [{k: columns[k][j] for k in keys} for j in indices]
        elapsed = time.perf_counter() - t0
        v.delete()
        psp_times.append(elapsed)
        if i == 0:
            print(f"  perspective: to_columns()={n_total:,} rows, sampled to {len(rows)} dicts (first iter)", flush=True)

    psp_avg = sum(psp_times) / len(psp_times)
    psp_min = min(psp_times)
    ratio = psp_avg / pl_avg if pl_avg > 0 else float("inf")
    print(f"  perspective: avg={psp_avg*1000:.3f}ms  min={psp_min*1000:.3f}ms (n={NUM_ITER})", flush=True)
    print(f"  >>> polars {pl_avg*1000:.2f}ms vs perspective {psp_avg*1000:.2f}ms  (polars is {ratio:.1f}x faster)", flush=True)


def main() -> None:
    print(f"=== perspective-py vs polars benchmark ({NUM_SAMPLES:,} rows) ===\n", flush=True)

    df, all_defect_ids = generate_data(NUM_SAMPLES)

    print("\nBuilding perspective Table from polars DataFrame ...", flush=True)
    t0 = time.perf_counter()
    server = Server()
    client = server.new_local_client()
    table = client.table(df, name="bench_table", index="defect_id")
    build_elapsed = time.perf_counter() - t0
    print(f"  built in {build_elapsed:.2f}s", flush=True)
    print(f"  table size: {table.size():,} rows", flush=True)

    bench_rectangle_selection(df, table)
    bench_class_filter(df, table)
    bench_defect_id_in_selection(df, table, all_defect_ids)
    bench_filter_offset_take_to_dicts(df, table)
    bench_filter_sample_to_dicts(df, table)

    print("\n=== Done ===", flush=True)


if __name__ == "__main__":
    main()
