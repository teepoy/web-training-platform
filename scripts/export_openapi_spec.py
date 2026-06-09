from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from fastapi.openapi.utils import get_openapi


REPO_ROOT = Path(__file__).resolve().parents[1]
API_DIR = REPO_ROOT / "apps" / "api"
OUTPUT_PATH = REPO_ROOT / "openapi" / "openapi.yaml"


def _build_live() -> object:
    os.environ.setdefault("APP_CONFIG_PROFILE", "test")
    sys.path.insert(0, str(API_DIR))
    from app.main import app

    return get_openapi(title=app.title, version=app.version, routes=app.routes)


def _fix_uploadfile_binary_format(schema: object) -> None:
    """Add ``format: binary`` to multipart-body schema props where FastAPI
    emits only ``contentMediaType``.  Without ``format: binary``, Orval
    generates ``string`` instead of ``File`` for the upload body model."""
    if not isinstance(schema, dict):
        return
    schemas = schema.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict):
        return
    for _name, obj in schemas.items():
        if not isinstance(obj, dict):
            continue
        for _prop, prop_schema in obj.get("properties", {}).items():
            if (
                isinstance(prop_schema, dict)
                and "contentMediaType" in prop_schema
                and "format" not in prop_schema
            ):
                prop_schema["format"] = "binary"


def main() -> int:
    schema = _build_live()
    _fix_uploadfile_binary_format(schema)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        yaml.dump(
            schema, sort_keys=False, allow_unicode=True, default_flow_style=False
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
