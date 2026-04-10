#!/usr/bin/env bash
#
# dev-init.sh - Initialize development environment with seed data
#
# This script:
# 1. Waits for services to be ready (API, Label Studio)
# 2. Creates/ensures admin user exists
# 3. Seeds Oxford Flowers dataset (limited samples for dev)
# 4. Seeds YOLO classification training presets
#
# Usage:
#   ./scripts/dev-init.sh                    # Default: 100 samples
#   ./scripts/dev-init.sh --max-samples 500  # Custom sample limit
#   ./scripts/dev-init.sh --full             # All ~8k samples
#
# Prerequisites:
#   - Docker Compose stack running: make up
#   - Or local dev servers: make dev
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/infra/compose/docker-compose.yaml"

# Default configuration
API_URL="${API_URL:-http://localhost:8000}"
LS_URL="${LS_URL:-http://localhost:8080}"
MAX_SAMPLES="${MAX_SAMPLES:-100}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-120}"

# Admin credentials (matches migration-seeded admin)
ADMIN_EMAIL="admin@localhost"
ADMIN_PASSWORD="admin"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --max-samples)
            MAX_SAMPLES="$2"
            shift 2
            ;;
        --full)
            MAX_SAMPLES=0
            shift
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --max-samples N   Limit Oxford Flowers samples (default: 100)"
            echo "  --full            Use all ~8k samples"
            echo "  --api-url URL     API base URL (default: http://localhost:8000)"
            echo "  --compose-file F  Docker compose file path"
            echo "  -h, --help        Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ============================================================
# Step 1: Wait for services to be ready
# ============================================================
wait_for_service() {
    local name="$1"
    local url="$2"
    local endpoint="${3:-/}"
    local elapsed=0

    log_info "Waiting for $name at $url$endpoint ..."
    
    while [ $elapsed -lt $WAIT_TIMEOUT ]; do
        if curl -sf "$url$endpoint" > /dev/null 2>&1; then
            log_success "$name is ready"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        echo -n "."
    done
    
    echo ""
    log_error "$name not ready after ${WAIT_TIMEOUT}s"
    return 1
}

echo ""
echo "========================================"
echo "  Development Environment Initializer"
echo "========================================"
echo ""
log_info "Configuration:"
echo "  API URL:      $API_URL"
echo "  LS URL:       $LS_URL"
echo "  Max Samples:  $MAX_SAMPLES (0 = all)"
echo ""

wait_for_service "API" "$API_URL" "/api/v1/health"
wait_for_service "Label Studio" "$LS_URL" "/health"

# ============================================================
# Step 2: Verify/create admin user
# ============================================================
echo ""
log_info "Step 1: Verifying admin user..."

# Try to login with default admin credentials
LOGIN_RESP=$(curl -sf -X POST "$API_URL/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$ADMIN_EMAIL\", \"password\": \"$ADMIN_PASSWORD\"}" 2>&1) || true

if echo "$LOGIN_RESP" | grep -q "access_token"; then
    log_success "Admin user verified: $ADMIN_EMAIL"
    ADMIN_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
else
    log_warn "Default admin login failed, attempting to create via docker exec..."
    
    # Try to create superadmin via docker compose exec
    if docker compose -f "$COMPOSE_FILE" exec -T api \
        uv run python -m app.cli create-superadmin \
        --email="$ADMIN_EMAIL" \
        --password="$ADMIN_PASSWORD" \
        --name="Admin" 2>/dev/null; then
        log_success "Admin user created"
    else
        log_warn "Could not create admin via docker exec (may already exist or not using compose)"
    fi
    
    # Retry login
    LOGIN_RESP=$(curl -sf -X POST "$API_URL/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$ADMIN_EMAIL\", \"password\": \"$ADMIN_PASSWORD\"}")
    
    if echo "$LOGIN_RESP" | grep -q "access_token"; then
        log_success "Admin user verified after creation"
        ADMIN_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
    else
        log_error "Could not authenticate as admin"
        exit 1
    fi
fi

echo ""
echo "----------------------------------------"
echo "  Admin Credentials"
echo "----------------------------------------"
echo "  Email:    $ADMIN_EMAIL"
echo "  Password: $ADMIN_PASSWORD"
echo "----------------------------------------"
echo ""

# ============================================================
# Step 3: Seed training presets
# ============================================================
log_info "Step 2: Seeding training presets..."

cd "$REPO_ROOT"

# Use uv to run the seed script
if command -v uv &> /dev/null; then
    uv run python scripts/seed_presets.py \
        --api-url "$API_URL" \
        --compose-file "$COMPOSE_FILE" \
        --no-promote
else
    python scripts/seed_presets.py \
        --api-url "$API_URL" \
        --compose-file "$COMPOSE_FILE" \
        --no-promote
fi

log_success "Training presets seeded"

# ============================================================
# Step 4: Seed Oxford Flowers dataset
# ============================================================
echo ""
log_info "Step 3: Seeding Oxford Flowers dataset..."

FLOWERS_ARGS="--api-url $API_URL --compose-file $COMPOSE_FILE --no-promote"
if [ "$MAX_SAMPLES" -gt 0 ]; then
    FLOWERS_ARGS="$FLOWERS_ARGS --max-samples $MAX_SAMPLES"
fi

if command -v uv &> /dev/null; then
    uv run python scripts/seed_oxford_flowers.py $FLOWERS_ARGS
else
    python scripts/seed_oxford_flowers.py $FLOWERS_ARGS
fi

log_success "Oxford Flowers dataset seeded"

# ============================================================
# Summary
# ============================================================
echo ""
echo "========================================"
echo "  Initialization Complete!"
echo "========================================"
echo ""
echo "Services:"
echo "  Web App:       http://localhost:3000"
echo "  API:           $API_URL"
echo "  Label Studio:  $LS_URL"
echo "  pgAdmin:       http://localhost:5050"
echo "  MinIO Console: http://localhost:9001"
echo "  Prefect:       http://localhost:4200"
echo ""
echo "Credentials:"
echo "  Platform:      $ADMIN_EMAIL / $ADMIN_PASSWORD"
echo "  Label Studio:  admin@example.com / admin123"
echo "  pgAdmin:       admin@example.com / admin123"
echo "  MinIO:         minioadmin / minioadmin"
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:3000 in your browser"
echo "  2. Login with admin credentials"
echo "  3. Explore the Oxford Flowers dataset"
echo "  4. Create a training job using YOLO presets"
echo ""
