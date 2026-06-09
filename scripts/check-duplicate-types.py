#!/usr/bin/env python3
"""Check for duplicate types between shared/api/types{,ui-helpers} and generated/orval/models.

Reports any type defined in shared/api/types.ts or shared/api/ui-helpers.ts that
has a corresponding (exact or suffix-matched) type in generated/orval/models.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_SRC = ROOT / "apps" / "web" / "src"

TYPES_FILE = WEB_SRC / "shared" / "api" / "types.ts"
UI_HELPERS_FILE = WEB_SRC / "shared" / "api" / "ui-helpers.ts"
ORVAL_INDEX = WEB_SRC / "generated" / "orval" / "models" / "index.ts"

# Types in types.ts that are legitimately frontend-only (not API DTOs)
FRONTEND_ONLY_TYPES: set[str] = {
    "TaskType",
    "DatasetType",
    "ModelFramework",
    "ModelFormat",
    "OrgRole",
    "ViewRowV1",
    "ViewPaginatedResponse",
    "PaginatedResponse",
}


def filename_to_type(name: str) -> str:
    """Convert a filename base to its exported PascalCase type name.

    Orval names each file after the type name (e.g. 'sensorSubscriptionResponse.ts'
    exports 'SensorSubscriptionResponse'), so we just uppercase the first character.
    """
    return name[0].upper() + name[1:]


def extract_orval_types(index_path: Path) -> set[str]:
    """Extract exported type names from orval models index.ts.

    Each line looks like: export * from './someTypeName';
    """
    content = index_path.read_text()
    types: set[str] = set()
    for line in content.splitlines():
        m = re.search(r"from\s+['\"]\./([^'\"]+)['\"]", line)
        if m:
            name = m.group(1)
            if name not in ("index",):
                types.add(filename_to_type(name))
    return types


def extract_handwritten_type_names(file_path: Path) -> set[str]:
    """Extract exported type/interface names from a .ts file."""
    content = file_path.read_text()
    names: set[str] = set()
    for m in re.finditer(r"export\s+(interface|type)\s+(\w+)", content):
        kind = m.group(1)
        name = m.group(2)
        if kind == "type" and name in FRONTEND_ONLY_TYPES:
            continue
        names.add(name)
    return names


def find_overlaps(
    handwritten: set[str],
    orval: set[str],
    source_file: str,
) -> list[str]:
    """Find handwritten types that overlap with orval types."""
    problems: list[str] = []
    for name in sorted(handwritten):
        reasons: list[str] = []

        if name in orval:
            reasons.append(f"exact name match: orval/models already exports `{name}`")

        response_name = name + "Response"
        if response_name in orval:
            reasons.append(
                f"suffix match: types.ts `{name}` → orval/models `{response_name}`"
            )

        if reasons:
            problems.append(
                f"  {name} in {source_file}:\n"
                + "\n".join(f"    - {r}" for r in reasons)
            )

    return problems


def main() -> int:
    if not ORVAL_INDEX.exists():
        print(f"Error: orval index not found: {ORVAL_INDEX}", file=sys.stderr)
        return 1

    orval_types = extract_orval_types(ORVAL_INDEX)

    all_problems: list[str] = []

    for file_path, label in [
        (TYPES_FILE, "types.ts"),
        (UI_HELPERS_FILE, "ui-helpers.ts"),
    ]:
        if not file_path.exists():
            print(f"[warn] File not found, skipping: {file_path}", file=sys.stderr)
            continue
        handwritten = extract_handwritten_type_names(file_path)
        problems = find_overlaps(handwritten, orval_types, f"shared/api/{label}")
        all_problems.extend(problems)

    if all_problems:
        print(
            f"[error] {len(all_problems)} type(s) in shared/api types "
            f"already exist in orval/models:\n"
        )
        for p in all_problems:
            print(p)
        return 1

    print("[ok] No duplicate types found between shared/api and orval/models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
