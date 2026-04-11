from __future__ import annotations

import argparse
import math
import time

from label_studio_sdk import LabelStudio

LS_URL = "http://localhost:8080"
LS_API_KEY = "ls-smoke-token-for-local-dev"

LABEL_CONFIG = """
<View>
  <Image name="image" value="$image"/>
  <Choices name="label" toName="image" choice="single">
    <Choice value="cat"/>
    <Choice value="dog"/>
  </Choices>
</View>
""".strip()


def build_batch(start: int, count: int) -> list[dict[str, str]]:
    return [
        {"image": f"http://example.local/mock-images/{idx}.jpg"}
        for idx in range(start, start + count)
    ]


def benchmark(total_tasks: int, batch_size: int, return_task_ids: bool) -> None:
    client = LabelStudio(base_url=LS_URL, api_key=LS_API_KEY)
    project = client.projects.create(
        title=f"bench-import-{int(time.time())}",
        label_config=LABEL_CONFIG,
    )
    project_id = int(project.id)

    try:
        batches = math.ceil(total_tasks / batch_size)
        started = time.perf_counter()
        imported = 0

        for batch_index in range(batches):
            remaining = total_tasks - imported
            current_batch_size = min(batch_size, remaining)
            payload = build_batch(imported, current_batch_size)
            batch_started = time.perf_counter()
            response = client.projects.import_tasks(
                id=project_id,
                request=payload,
                return_task_ids=return_task_ids,
            )
            batch_elapsed = time.perf_counter() - batch_started
            imported += current_batch_size
            print(
                f"batch={batch_index + 1}/{batches} imported={current_batch_size} "
                f"elapsed_seconds={batch_elapsed:.3f} response={response}"
            )

        elapsed = time.perf_counter() - started
        rate = imported / elapsed if elapsed > 0 else 0.0
        projected_100k_seconds = 100_000 / rate if rate > 0 else float("inf")

        print(f"project_id={project_id}")
        print(f"tasks_imported={imported}")
        print(f"elapsed_seconds={elapsed:.3f}")
        print(f"tasks_per_second={rate:.2f}")
        print(f"projected_100k_seconds={projected_100k_seconds:.2f}")
        print(f"projected_100k_minutes={projected_100k_seconds / 60.0:.2f}")
    finally:
        try:
            client.projects.delete(id=project_id)
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark Label Studio bulk task import")
    parser.add_argument("--tasks", type=int, default=10000, help="Number of tasks to import")
    parser.add_argument("--batch-size", type=int, default=1000, help="Tasks per import request")
    parser.add_argument("--return-task-ids", action="store_true", help="Request created task IDs in the import response")
    args = parser.parse_args()
    benchmark(total_tasks=args.tasks, batch_size=args.batch_size, return_task_ids=args.return_task_ids)
