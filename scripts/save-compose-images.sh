#!/usr/bin/env bash
#
# save-compose-images.sh - Save all Docker images used by the compose stack
# as .tar archives for backup or offline transfer.
#
# Usage:
#   ./scripts/save-compose-images.sh                    # Save to ./docker-images/
#   ./scripts/save-compose-images.sh -o /path/to/output
#   ./scripts/save-compose-images.sh --include-built
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_BASE="$REPO_ROOT/infra/compose/docker-compose.yaml"
COMPOSE_DEV="$REPO_ROOT/infra/compose/docker-compose.dev.yaml"

OUTPUT_DIR="${OUTPUT_DIR:-./docker-images}"
INCLUDE_BUILT=false

while [[ $# -gt 0 ]]; do
  case $1 in
    -o|--output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --include-built)
      INCLUDE_BUILT=true
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [-o|--output DIR] [--include-built]"
      echo ""
      echo "Options:"
      echo "  -o, --output DIR    Output directory (default: ./docker-images)"
      echo "  --include-built     Also save locally built images (api, web, workers)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# ── Collect images from compose files ──────────────────────────
IMAGES=()

# Pulled images from docker-compose.yaml (base services)
while IFS= read -r line; do
  IMAGES+=("$line")
done < <(grep -rh '^\s*image:\s' "$COMPOSE_BASE" "$COMPOSE_DEV" 2>/dev/null \
  | sed 's/.*image:\s*//' | sed 's/"//g' | sort -u)

# Built images — resolve actual image names from running compose stack
if $INCLUDE_BUILT; then
  if docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" images -q 2>/dev/null | grep -q .; then
    while IFS= read -r repotag; do
      IMAGES+=("$repotag")
    done < <(docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_DEV" images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
      | grep -v ':<none>$' || true)
  else
    echo "[WARN] Compose stack not running; cannot resolve built images. Start it first or skip --include-built." >&2
  fi
fi

# Deduplicate
mapfile -t IMAGES < <(printf '%s\n' "${IMAGES[@]}" | sort -u)

if [ ${#IMAGES[@]} -eq 0 ]; then
  echo "[ERROR] No images found in compose files."
  exit 1
fi

echo "Found ${#IMAGES[@]} images to save:"
printf '  %s\n' "${IMAGES[@]}"
echo ""

# ── Save each image ────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
MANIFEST="$OUTPUT_DIR/manifest_$TIMESTAMP.txt"
echo "Output: $OUTPUT_DIR/"
echo ""

FAILED=0
for img in "${IMAGES[@]}"; do
  # Sanitize image name for filename
  safe_name="$(echo "$img" | sed 's|/|_|g; s|:|_|g')"
  tarball="$OUTPUT_DIR/${safe_name}.tar"

  if [ -f "$tarball" ]; then
    echo "[SKIP] $img → $tarball (already exists)"
    continue
  fi

  echo "[SAVE] $img → $tarball ..."
  if docker save "$img" -o "$tarball"; then
    echo "  done ($(du -h "$tarball" | cut -f1))"
    echo "$img → $tarball" >> "$MANIFEST"
  else
    echo "  FAILED — image not found locally" >&2
    FAILED=$((FAILED + 1))
  fi
done

# ── Summary ────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Save Complete"
echo "========================================"
echo "  Images attempted: ${#IMAGES[@]}"
echo "  Failed:           $FAILED"
echo "  Output:           $(cd "$OUTPUT_DIR" && pwd)"
echo "  Manifest:         $MANIFEST"
echo ""
if [ "$FAILED" -gt 0 ]; then
  echo "Note: Some images may need to be pulled first:"
  echo "  docker compose -f infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml pull"
fi
