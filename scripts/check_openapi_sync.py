from __future__ import annotations

import difflib
import json
import os
import sys
from pathlib import Path

import yaml
from fastapi.openapi.utils import get_openapi


REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "apps" / "api"
OPENAPI_SPEC = REPO_ROOT / "openapi" / "openapi.yaml"


def _normalize(document: object) -> object:
    return json.loads(json.dumps(document, sort_keys=True))


def _load_canonical() -> object:
    return yaml.safe_load(OPENAPI_SPEC.read_text(encoding="utf-8"))


def _build_live() -> object:
    os.environ.setdefault("APP_CONFIG_PROFILE", "test")
    sys.path.insert(0, str(API_DIR))
    from app.main import app

    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    _fix_uploadfile_binary_format(schema)
    return schema


def _fix_uploadfile_binary_format(schema: object) -> None:
    """Match export_openapi_spec.py's UploadFile normalization."""
    if not isinstance(schema, dict):
        return
    schemas = schema.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        return
    for obj in schemas.values():
        if not isinstance(obj, dict):
            continue
        for prop_schema in obj.get("properties", {}).values():
            if (
                isinstance(prop_schema, dict)
                and "contentMediaType" in prop_schema
                and "format" not in prop_schema
            ):
                prop_schema["format"] = "binary"


def main() -> int:
    canonical = _normalize(_load_canonical())
    live = _normalize(_build_live())
    if canonical == live:
        print("OpenAPI spec is in sync.")
        return 0

    canonical_text = json.dumps(canonical, indent=2, sort_keys=True).splitlines()
    live_text = json.dumps(live, indent=2, sort_keys=True).splitlines()
    diff = "\n".join(
        difflib.unified_diff(
            canonical_text,
            live_text,
            fromfile=str(OPENAPI_SPEC),
            tofile="live-fastapi-schema",
            lineterm="",
        )
    )
    print(diff)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
