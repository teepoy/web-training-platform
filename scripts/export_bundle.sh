#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/infra/compose/docker-compose.yaml"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DEFAULT_OUTPUT="$REPO_ROOT/artifacts/online-finetune-platform-bundle-$TIMESTAMP.tar"

OUTPUT_PATH="$DEFAULT_OUTPUT"
PULL_MISSING=0

usage() {
    cat <<'EOF'
Usage: scripts/export_bundle.sh [OPTIONS]

Create a portable tar bundle containing:
- a source snapshot of this repository
- a docker image archive with the images referenced by this repo
- manifest files listing discovered, saved, and missing images

Options:
  --output PATH     Final tar path (default: artifacts/online-finetune-platform-bundle-<timestamp>.tar)
  --pull-missing    Pull missing images before saving them
  -h, --help        Show this help

Notes:
- Source snapshot uses git-tracked and untracked, non-ignored files when available.
- LICENSE and docs/ are included in the source snapshot.
- Locally built project images must already exist unless you build them first.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            OUTPUT_PATH="$2"
            shift 2
            ;;
        --pull-missing)
            PULL_MISSING=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown option: %s\n\n' "$1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    printf 'docker is required to export image archives\n' >&2
    exit 1
fi

if ! command -v tar >/dev/null 2>&1; then
    printf 'tar is required to build the bundle\n' >&2
    exit 1
fi

if ! command -v rg >/dev/null 2>&1; then
    printf 'rg is required to discover image references\n' >&2
    exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

WORK_DIR="$(mktemp -d)"
BUNDLE_NAME="online-finetune-platform-bundle-$TIMESTAMP"
BUNDLE_DIR="$WORK_DIR/$BUNDLE_NAME"
mkdir -p "$BUNDLE_DIR/manifests"

cleanup() {
    rm -rf "$WORK_DIR"
}

trap cleanup EXIT

IMAGE_LIST_FILE="$WORK_DIR/images.txt"
AVAILABLE_LIST_FILE="$WORK_DIR/images-available.txt"
MISSING_LIST_FILE="$WORK_DIR/images-missing.txt"
FILE_LIST_FILE="$WORK_DIR/source-files.txt"

touch "$IMAGE_LIST_FILE" "$AVAILABLE_LIST_FILE" "$MISSING_LIST_FILE" "$FILE_LIST_FILE"

append_images() {
    local source_file="$1"
    if [[ -r "$source_file" ]]; then
        cat "$source_file" >> "$IMAGE_LIST_FILE"
    fi
}

yaml_image_refs() {
    rg --no-filename --only-matching --replace '$1' '^[[:space:]]*image:[[:space:]]*["'"'"']?([^"'"'"'[:space:]]+)' "$@" || true
}

dockerfile_from_refs() {
    rg --no-filename --only-matching --replace '$1' '^FROM[[:space:]]+([^[:space:]]+)' "$@" || true
}

compose_config_refs() {
    if [[ -f "$COMPOSE_FILE" ]] && docker compose version >/dev/null 2>&1; then
        docker compose -f "$COMPOSE_FILE" config --images 2>/dev/null || true
    fi
}

PROJECT_IMAGE_CANDIDATES=$(cat <<'EOF'
finetune-api:latest
finetune-worker:latest
finetune-embedding:latest
finetune-inference:latest
finetune-web:latest
ghcr.io/astral-sh/uv:latest
EOF
)

append_images <(yaml_image_refs "$REPO_ROOT/infra/compose/docker-compose.yaml" "$REPO_ROOT/infra/k8s"/*.yaml "$REPO_ROOT/apps/api/config/base.yaml")
append_images <(dockerfile_from_refs "$REPO_ROOT/apps/api/Dockerfile" "$REPO_ROOT/apps/worker/Dockerfile" "$REPO_ROOT/apps/embedding/Dockerfile" "$REPO_ROOT/apps/inference/Dockerfile" "$REPO_ROOT/apps/web/Dockerfile")
append_images <(compose_config_refs)
append_images <(printf '%s\n' "$PROJECT_IMAGE_CANDIDATES")

sort -u "$IMAGE_LIST_FILE" -o "$IMAGE_LIST_FILE"

if [[ ! -s "$IMAGE_LIST_FILE" ]]; then
    printf 'No docker image references were discovered\n' >&2
    exit 1
fi

while IFS= read -r image_ref; do
    [[ -z "$image_ref" ]] && continue

    if docker image inspect "$image_ref" >/dev/null 2>&1; then
        printf '%s\n' "$image_ref" >> "$AVAILABLE_LIST_FILE"
        continue
    fi

    if [[ "$PULL_MISSING" -eq 1 ]]; then
        if docker pull "$image_ref"; then
            printf '%s\n' "$image_ref" >> "$AVAILABLE_LIST_FILE"
            continue
        fi
    fi

    printf '%s\n' "$image_ref" >> "$MISSING_LIST_FILE"
done < "$IMAGE_LIST_FILE"

sort -u "$AVAILABLE_LIST_FILE" -o "$AVAILABLE_LIST_FILE"
sort -u "$MISSING_LIST_FILE" -o "$MISSING_LIST_FILE"

cp "$IMAGE_LIST_FILE" "$BUNDLE_DIR/manifests/images-discovered.txt"
cp "$AVAILABLE_LIST_FILE" "$BUNDLE_DIR/manifests/images-saved.txt"
cp "$MISSING_LIST_FILE" "$BUNDLE_DIR/manifests/images-missing.txt"

if [[ -s "$AVAILABLE_LIST_FILE" ]]; then
    available_images=()
    while IFS= read -r image_ref; do
        [[ -z "$image_ref" ]] && continue
        available_images+=("$image_ref")
    done < "$AVAILABLE_LIST_FILE"
    docker save -o "$BUNDLE_DIR/docker-images.tar" "${available_images[@]}"
else
    tar --create --file "$BUNDLE_DIR/docker-images.tar" --files-from /dev/null
fi

if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$REPO_ROOT" ls-files --cached --others --exclude-standard -z > "$FILE_LIST_FILE"
else
    printf 'apps\0docs\0infra\0libs\0scripts\0AGENTS.md\0LICENSE\0Makefile\0README.md\0package.json\0pnpm-lock.yaml\0pnpm-workspace.yaml\0pyproject.toml\0uv.lock\0' > "$FILE_LIST_FILE"
fi

if [[ -f "$REPO_ROOT/LICENSE" ]]; then
    printf 'LICENSE\0' >> "$FILE_LIST_FILE"
fi

if [[ -d "$REPO_ROOT/docs" ]]; then
    printf 'docs\0' >> "$FILE_LIST_FILE"
fi

python3 - <<'PY' "$FILE_LIST_FILE"
from __future__ import annotations

import pathlib
import sys

path = pathlib.Path(sys.argv[1])
items = [item for item in path.read_bytes().split(b"\0") if item]
unique_items = []
seen = set()
for item in items:
    if item in seen:
        continue
    seen.add(item)
    unique_items.append(item)
path.write_bytes(b"\0".join(unique_items) + (b"\0" if unique_items else b""))
PY

tar --create --gzip --file "$BUNDLE_DIR/source-code.tar.gz" --directory "$REPO_ROOT" --null --files-from "$FILE_LIST_FILE"

cat > "$BUNDLE_DIR/README.txt" <<EOF
Bundle contents:
- source-code.tar.gz: repository snapshot including docs/ and LICENSE
- docker-images.tar: saved local docker images discovered from compose, k8s, config, and Dockerfiles
- manifests/images-discovered.txt: all discovered image references
- manifests/images-saved.txt: image references included in docker-images.tar
- manifests/images-missing.txt: discovered image references not available locally${PULL_MISSING:+ after pull attempts}
EOF

tar --create --file "$OUTPUT_PATH" --directory "$WORK_DIR" "$BUNDLE_NAME"

printf 'Created bundle: %s\n' "$OUTPUT_PATH"
if [[ -s "$MISSING_LIST_FILE" ]]; then
    printf 'Some images were not saved; see manifests/images-missing.txt inside the bundle\n'
fi
