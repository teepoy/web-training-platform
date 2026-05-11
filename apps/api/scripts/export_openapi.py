"""Export FastAPI OpenAPI schema to a JSON file for the frontend api-contract package."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Force test profile so we don't need a running DB / Label Studio
import os

os.environ.setdefault("APP_CONFIG_PROFILE", "test")


def _export() -> None:
    from app.main import app as fastapi_app

    schema = fastapi_app.openapi()
    output_path = (
        Path(__file__).resolve().parents[3] / "libs" / "api-contract" / "openapi.json"
    )
    output_path.write_text(json.dumps(schema, indent=2))
    print(f"OpenAPI schema written to {output_path}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _export()
