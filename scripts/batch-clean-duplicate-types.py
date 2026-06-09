#!/usr/bin/env python3
"""
Batch script to clean up duplicate types in the web frontend.

Strategy:
1. Delete hand-written type definitions from shared/api/types.ts and ui-helpers.ts
2. For every .ts/.vue file, scan all import type { ... } blocks.
   If the import source resolves to the old types file, remove the old type names
   from the import and add corresponding orval imports.
3. Update shared/index.ts barrel exports.

Run with: python3 scripts/batch-clean-duplicate-types.py
"""

import re
import os

SRC = "apps/web/src"
TYPES_FILE = f"{SRC}/shared/api/types.ts"
UI_HELPERS_FILE = f"{SRC}/shared/api/ui-helpers.ts"
SHARED_INDEX = f"{SRC}/shared/index.ts"

# =============================================================================
# Configuration
# =============================================================================

# Exact name matches: types.ts name == orval/models name
EXACT_MATCHES = {
    "Annotation": "annotation",
    "Dataset": "dataset",
    "LatestAnnotation": "latestAnnotation",
    "Sample": "sample",
    "SampleWithLabels": "sampleWithLabels",
    "SyncPredictionCollectionResponse": "syncPredictionCollectionResponse",
}

# Suffix matches: old_name -> (orval_name, alias)
SUFFIX_MATCHES = {
    "AnnotationVersion": ("AnnotationVersionResponse", "AnnotationVersion"),
    "Model": ("ModelResponse", "Model"),
    "ModelUploadTemplate": ("ModelUploadTemplateResponse", "ModelUploadTemplate"),
    "PredictionCollection": ("PredictionCollectionResponse", "PredictionCollection"),
    "PredictionEvent": ("PredictionEventResponse", "PredictionEvent"),
    "PredictionJob": ("PredictionJobResponse", "PredictionJob"),
    "PredictionResult": ("PredictionResultResponse", "PredictionResult"),
    "ReviewAction": ("ReviewActionResponse", "ReviewAction"),
    "RunLog": ("RunLogResponse", "RunLog"),
    "Schedule": ("ScheduleResponse", "Schedule"),
    "SensorDefinition": ("SensorDefinitionResponse", "SensorDefinition"),
    "SensorSubscription": ("SensorSubscriptionResponse", "SensorSubscription"),
    "TaskTrackerDetail": ("TaskTrackerDetailResponse", "TaskTrackerDetail"),
    "TaskTrackerSummary": ("TaskTrackerSummaryResponse", "TaskTrackerSummary"),
    "User": ("UserResponse", "User"),
    "UserWithOrgs": ("UserWithOrgsResponse", "UserWithOrgs"),
}

# From ui-helpers.ts
UI_HELPER_MATCHES = {
    "ExportFormat": ("ExportFormatResponse", "ExportFormat"),
}

# Build master map: old_name -> (orval_name, alias_or_None)
OLD_IMPORTS = {}
for name in set(EXACT_MATCHES):
    OLD_IMPORTS[name] = (name, None)  # same name in orval, no alias
for name, (orv, alias) in SUFFIX_MATCHES.items():
    OLD_IMPORTS[name] = (orv, alias)
for name, (orv, alias) in UI_HELPER_MATCHES.items():
    OLD_IMPORTS[name] = (orv, alias)

ALL_NAMES = set(OLD_IMPORTS)
ALL_EXACT = set(EXACT_MATCHES)
ALL_SUFFIX = set(SUFFIX_MATCHES)
ALL_UI = set(UI_HELPER_MATCHES)

# Source path patterns that are (or re-export from) the old types file
OLD_SOURCE_PATTERNS = [
    re.compile(r"^['\"]@/shared/api/types['\"]$"),
    re.compile(r"^['\"]@/shared/api['\"]$"),
    re.compile(r"^['\"]@/shared['\"]$"),
    re.compile(r"^['\"]\./types['\"]$"),
    re.compile(r"^['\"]\.\./types['\"]$"),
    re.compile(r"^['\"]\./api/types['\"]$"),
    re.compile(r"^['\"]\.\./api/types['\"]$"),
    re.compile(r"^['\"]\./api['\"]$"),
    re.compile(r"^['\"]\.\./api['\"]$"),
    re.compile(r"^['\"]\.\./\.\./api['\"]$"),
    re.compile(r"^['\"]\.\./\.\./\.\./api['\"]$"),
    re.compile(r"^['\"]\./api/ui-helpers['\"]$"),
    re.compile(r"^['\"]\.\./api/ui-helpers['\"]$"),
]


def is_old_source(from_clause):
    """Check if a 'from' clause points to the old types file."""
    from_clause = from_clause.strip()
    if from_clause.endswith(";"):
        from_clause = from_clause[:-1].strip()
    # Extract just the path: "from './types'" -> "'./types'"
    path = from_clause
    if path.lower().startswith("from "):
        path = path[5:].strip()
    if path.startswith('"') or path.startswith("'"):
        pass  # already a quoted path
    for pat in OLD_SOURCE_PATTERNS:
        if pat.match(path):
            return True
    return False


def remove_type_definitions(filepath, names_to_remove):
    """Remove type/interface definitions from the old types file."""
    with open(filepath) as f:
        lines = f.read().split("\n")

    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        matching = None
        for name in names_to_remove:
            if re.match(rf"^export\s+(interface|type)\s+{re.escape(name)}\b", stripped):
                matching = name
                break
            if re.match(
                rf"^export\s+interface\s+{re.escape(name)}\s+extends", stripped
            ):
                matching = name
                break

        if matching:
            depth = 0
            if "{" in line:
                depth += line.count("{") - line.count("}")
            i += 1
            while i < len(lines):
                curr = lines[i]
                if "{" in curr:
                    depth += curr.count("{") - curr.count("}")
                if "}" in curr:
                    depth += curr.count("{") - curr.count("}")
                end_condition = (
                    depth <= 0 and "}" in curr and curr.strip().endswith("}")
                )
                if end_condition:
                    new_lines.append("")
                    i += 1
                    break
                if depth <= 0 and curr.strip().endswith(";"):
                    new_lines.append("")
                    i += 1
                    break
                i += 1
            # Skip trailing blanks
            skipped = 0
            while i < len(lines) and lines[i].strip() == "" and skipped < 2:
                i += 1
                skipped += 1
            continue

        new_lines.append(line)
        i += 1

    # Collapse blank lines
    cleaned = []
    prev = False
    for line in new_lines:
        empty = line.strip() == ""
        if empty and prev:
            continue
        cleaned.append(line)
        prev = empty

    with open(filepath, "w") as f:
        f.write("\n".join(cleaned).rstrip("\n") + "\n")


def extract_import_block(lines, start_idx):
    """
    Given the full file lines and an index of the start of an 'import type {'
    line, return (block_lines, from_clause, imported_names_list, end_idx).

    imported_names_list is a list of tuples (full_text, base_name, as_alias).
    """
    block_lines = [lines[start_idx]]
    block_text = lines[start_idx]
    i = start_idx + 1

    # If it's a single-line import
    if "}" in lines[start_idx] and "from" in lines[start_idx]:
        pass  # already complete
    else:
        while i < len(lines):
            block_lines.append(lines[i])
            block_text += " " + lines[i]
            if "}" in lines[i] and "from" in lines[i]:
                i += 1
                break
            i += 1

    # Extract from-clause
    m_from = re.search(r"}\s*(from\s+[^;]+;?)", block_text)
    if not m_from:
        return None, None, [], i

    from_clause = m_from.group(1)

    # Extract names in braces
    m_brace = re.search(r"\{([^}]*)\}", block_text)
    if not m_brace:
        return None, from_clause, [], i

    names_raw = m_brace.group(1)
    names_list = []
    for part in names_raw.split(","):
        part = part.strip()
        if not part:
            continue
        if " as " in part:
            base, alias = part.split(" as ", 1)
            names_list.append((part, base.strip(), alias.strip()))
        else:
            names_list.append((part, part, None))

    return block_lines, from_clause, names_list, i


def process_file(filepath):
    """Process a file: redirect outdated imports to orval models."""
    if "/generated/" in filepath:
        return False

    with open(filepath) as f:
        content = f.read()

    lines = content.split("\n")
    orval_additions = []  # [(orval_name, alias_or_none)]
    new_lines = []
    i = 0
    modified = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect import type {
        if re.match(r"^import\s+type\s+\{", stripped):
            block, from_cl, names_list, end_i = extract_import_block(lines, i)

            if from_cl is None or not is_old_source(from_cl.strip()):
                new_lines.extend(lines[i:end_i])
                i = end_i
                continue

            # This import is from old types source
            kept = []
            for full, base, alias in names_list:
                if base in OLD_IMPORTS:
                    orv_name, orv_alias = OLD_IMPORTS[base]
                    if (orv_name, orv_alias) not in orval_additions:
                        orval_additions.append((orv_name, orv_alias))
                    modified = True
                else:
                    kept.append(full)

            if kept:
                # Rebuild import line keeping non-old names
                new_lines.append(
                    f"import type {{ {', '.join(kept)} }} {from_cl.strip()}"
                )
            # else: entire import was old types - omit

            i = end_i
            continue

        new_lines.append(line)
        i += 1

    if not orval_additions:
        return modified

    # Insert orval import
    orv_parts = []
    for orv_name, alias in orval_additions:
        if alias and alias != orv_name:
            orv_parts.append(f"{orv_name} as {alias}")
        else:
            orv_parts.append(orv_name)
    orv_line = (
        f'import type {{ {", ".join(orv_parts)} }} from "@/generated/orval/models";'
    )

    # Find insertion point: scan from TOP to find where imports live
    insert_at = -1
    # 1) After the FIRST top-level orval/models import (not inline import() expressions)
    for idx in range(len(new_lines)):
        line = new_lines[idx].strip()
        if "@/generated/orval/models" in line and "import(" not in line:
            insert_at = idx + 1
            break
    # 2) After the FIRST top-level orval import at all
    if insert_at < 0:
        for idx in range(len(new_lines)):
            line = new_lines[idx].strip()
            if "@/generated/orval" in line and "import(" not in line:
                insert_at = idx + 1
                break
    # 3) After the LAST import closing line
    if insert_at < 0:
        for idx in range(len(new_lines) - 1, -1, -1):
            if re.search(r'\}\s*from\s+[\'"]', new_lines[idx]):
                insert_at = idx + 1
                break
    # 4) Insert at top of file
    if insert_at < 0:
        insert_at = 0

    new_lines.insert(insert_at, orv_line)

    # Collapse blanks
    cleaned = []
    prev = False
    for line in new_lines:
        empty = line.strip() == ""
        if empty and prev:
            continue
        cleaned.append(line)
        prev = empty

    with open(filepath, "w") as f:
        f.write("\n".join(cleaned).rstrip("\n") + "\n")

    return True


def patch_shared_index():
    """Remove old type re-exports from shared/index.ts."""
    with open(SHARED_INDEX) as f:
        lines = f.read().split("\n")

    new_lines = []
    for line in lines:
        m = re.match(
            r'export\s+type\s+\{([^}]+)\}\s+from\s+[\'"]\./api/(types|ui-helpers)[\'"]',
            line.strip(),
        )
        if m:
            names = [n.strip().split(" as ")[0].strip() for n in m.group(1).split(",")]
            keep = [n for n in names if n not in OLD_IMPORTS]
            if keep:
                new_lines.append(
                    f'export type {{ {", ".join(keep)} }} from "./api/{m.group(2)}";'
                )
            continue
        new_lines.append(line)

    with open(SHARED_INDEX, "w") as f:
        f.write("\n".join(new_lines))


def main():
    print("=" * 60)
    print("Batch Clean Duplicate Types v2")
    print("=" * 60)

    # Step 1: Remove old type definitions
    print("\n[1/3] Removing old type definitions...")
    remove_type_definitions(TYPES_FILE, ALL_EXACT | ALL_SUFFIX)
    print(f"  types.ts - removed {len(ALL_EXACT | ALL_SUFFIX)} types")
    remove_type_definitions(UI_HELPERS_FILE, ALL_UI)
    print(f"  ui-helpers.ts - removed {len(ALL_UI)} types")

    # Step 2: Patch all .ts/.vue files
    print("\n[2/3] Patching imports...")
    all_files = []
    for root, dirs, fnames in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist")]
        for fname in fnames:
            if fname.endswith((".ts", ".vue")):
                all_files.append(os.path.join(root, fname))

    patched = 0
    for f in sorted(all_files):
        if process_file(f):
            patched += 1
            print(f"  Patched: {f}")

    print(f"  Total patched: {patched}")

    # Step 3: Update barrel
    print("\n[3/3] Updating shared/index.ts...")
    patch_shared_index()
    print("  Done")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
