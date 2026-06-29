from __future__ import annotations

import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import polars as pl
from perspective import Server


def builtin_duration(label: str, start: float) -> float:
    elapsed = time.monotonic() - start
    print(f"  {label}: {elapsed:.3f}s")
    return elapsed


def main() -> None:
    N = 300_000
    print(f"Generating {N:,} rows ...")
    df = pl.DataFrame(
        {
            "defect_id": list(range(1, N + 1)),
            "wafer_x": [i % 1000 for i in range(N)],
            "wafer_y": [i // 1000 for i in range(N)],
            "class_number": [i % 10 for i in range(N)],
            "rough_bin": [i % 5 for i in range(N)],
            "map_in_selection": [0] * N,
            "table_in_selection": [0] * N,
        }
    )

    print("Starting Perspective Server ...")
    server = Server()
    client = server.new_local_client()

    t0 = time.monotonic()
    table = client.table(
        df.to_dict(as_series=False),
        name="samples",
        index="defect_id",
    )
    builtin_duration("table created", t0)
    print(f"  size={table.size()}")

    # Test 1: update all rows at once
    print(f"\n--- Test 1: update all {N:,} rows at once ---")
    t0 = time.monotonic()
    table.update(
        {
            "defect_id": list(range(1, N + 1)),
            "map_in_selection": [1] * N,
        }
    )
    builtin_duration("update all rows", t0)
    table.update({"defect_id": list(range(1, N + 1)), "map_in_selection": [0] * N})

    # Test 2: chunked update (current approach)
    chunk_sizes = [1_000, 5_000, 10_000, 20_000, 50_000]
    for chunk_size in chunk_sizes:
        print(f"\n--- Test 2: chunked update, chunk_size={chunk_size:,} ---")
        t0 = time.monotonic()
        for start in range(0, N, chunk_size):
            end = min(start + chunk_size, N)
            chunk = list(range(start + 1, end + 1))
            table.update(
                {
                    "defect_id": chunk,
                    "map_in_selection": [1] * len(chunk),
                }
            )
        builtin_duration(f"chunked update ({len(range(0, N, chunk_size))} chunks)", t0)

        # Reset for next iteration
        table.update(
            {
                "defect_id": list(range(1, N + 1)),
                "map_in_selection": [0] * N,
            }
        )

    # Test 3: view extraction then single update
    print("\n--- Test 3: extract all IDs then single update ---")
    t0 = time.monotonic()
    view = table.view(columns=["defect_id"])
    ids_col = view.to_columns()
    all_ids = list(ids_col["defect_id"])
    builtin_duration("extract all IDs via view", t0)

    t0 = time.monotonic()
    table.update({"defect_id": all_ids, "map_in_selection": [1] * len(all_ids)})
    builtin_duration("single update with all IDs", t0)

    print("\nDone.")
    client.clear()


if __name__ == "__main__":
    main()
