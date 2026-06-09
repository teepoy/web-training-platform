from __future__ import annotations

import json
from pathlib import Path

from app.shared.sse.events import SSEEvent  # pyright: ignore[reportMissingImports]


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "openapi" / "sse-events.schema.json"


def main() -> int:
    schema = SSEEvent.model_json_schema()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
