.DEFAULT_GOAL := help
SHELL := /bin/bash

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
API_DIR     := apps/api
WEB_DIR     := apps/web
SDK_DIR     := libs/python-sdk
COMPOSE     := infra/compose/docker-compose.yaml
API_PORT    ?= 8000
API_URL     ?= http://localhost:$(API_PORT)
WEB_PORT    ?= 5173
TEST_TIMEOUT ?= 300
PYTEST_FAULTHANDLER_TIMEOUT ?= 60

# ──────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────

.PHONY: install
install: install-api install-web ## Install all dependencies

.PHONY: install-api
install-api: ## Install Python (uv) dependencies
	uv sync

.PHONY: install-web
install-web: ## Install frontend (pnpm) dependencies
	pnpm --filter web install

# ──────────────────────────────────────────────
# Dev servers
# ──────────────────────────────────────────────

.PHONY: dev
dev: ## Start API + Web dev servers (parallel, Ctrl-C stops both)
	@trap 'kill 0' EXIT; \
	$(MAKE) dev-api & \
	$(MAKE) dev-web & \
	wait

.PHONY: dev-api
dev-api: ## Start API dev server (default: 8000)
	cd $(API_DIR) && uv run uvicorn app.main:app --reload --port $(API_PORT)

.PHONY: dev-web
dev-web: ## Start frontend dev server (default: 5173)
	cd $(WEB_DIR) && pnpm dev

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────

.PHONY: db-migrate
db-migrate: ## Run Alembic migrations (upgrade head)
	cd $(API_DIR) && uv run alembic upgrade head

.PHONY: db-revision
db-revision: ## Create a new Alembic revision (usage: make db-revision MSG="add users table")
	cd $(API_DIR) && uv run alembic revision --autogenerate -m "$(MSG)"

# ──────────────────────────────────────────────
# Tests & checks
# ──────────────────────────────────────────────

.PHONY: test
test: test-api ## Run all tests

.PHONY: test-api
test-api: ## Run API tests
	timeout --foreground --signal=TERM --kill-after=10s $(TEST_TIMEOUT)s bash -lc 'cd $(API_DIR) && uv run --extra dev pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'

.PHONY: build-web
build-web: ## Build frontend for production
	cd $(WEB_DIR) && pnpm build

.PHONY: create-superadmin
create-superadmin: ## Create or promote a super admin user (EMAIL=, PASSWORD=, NAME= required)
	cd $(API_DIR) && APP_CONFIG_PROFILE=dev uv run python -m app.cli create-superadmin --email=$(EMAIL) --password=$(PASSWORD) --name=$(NAME)

.PHONY: reset-app-data
reset-app-data: ## Drop and recreate all application tables
	cd $(API_DIR) && APP_CONFIG_PROFILE=dev uv run python -m app.cli reset-app-data
	

# ──────────────────────────────────────────────
# SDK / CLI
# ──────────────────────────────────────────────

.PHONY: ftctl
ftctl: ## Run ftctl CLI (usage: make ftctl ARGS="jobs ls")
	cd $(SDK_DIR) && uv run ftctl $(ARGS)

# ──────────────────────────────────────────────
# Seed data
# ──────────────────────────────────────────────

.PHONY: seed
seed: ## Seed Oxford Flowers 102 dataset (requires running compose stack)
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run scripts/seed_oxford_flowers.py --api-url $(API_URL) --compose-file $(COMPOSE) $(ARGS)

.PHONY: seed-imagenet-dev
seed-imagenet-dev: ## Seed ImageNet-1K with synthetic samples + fake model (no extra deps)
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run python scripts/seed_imagenet_dev.py --api-url $(API_URL) --compose-file $(COMPOSE) $(ARGS)

.PHONY: seed-imagenet-real
seed-imagenet-real: ## Seed ImageNet-1K with real HF images + pretrained ResNet-50
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run python scripts/seed_imagenet_real.py --api-url $(API_URL) --compose-file $(COMPOSE) $(ARGS)

.PHONY: smoke-dev-batch
smoke-dev-batch: ## Run batch dev smoke test against seeded local stack
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run python scripts/smoke_dev_batch.py $(ARGS)


# ──────────────────────────────────────────────
# Docker / Infra
# ──────────────────────────────────────────────
.PHONY: build
build:
	docker compose -f $(COMPOSE) build

.PHONY: up
up: ## Start Compose stack (Postgres + MinIO + API)
	docker compose -f $(COMPOSE) up -d

.PHONY: down
down: ## Stop Compose stack
	docker compose -f $(COMPOSE) down --remove-orphans

.PHONY: logs
logs: ## Tail Compose logs (usage: make logs ARGS="api")
	docker compose -f $(COMPOSE) logs -f $(ARGS)

.PHONY: k8s-apply
k8s-apply: ## Apply Kubernetes manifests
	kubectl apply -k infra/k8s

# ──────────────────────────────────────────────
# Housekeeping
# ──────────────────────────────────────────────

.PHONY: clean
clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(WEB_DIR)/dist

.PHONY: help
help: ## Show this help
	@printf '\nUsage: make \033[36m<target>\033[0m [VAR=value]\n\n'
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nVariables:\n'
	@printf '  \033[36m%-16s\033[0m %s\n' "API_PORT" "API server port (default: 8000)"
	@printf '  \033[36m%-16s\033[0m %s\n' "API_URL" "API base URL used by seed targets (default: http://localhost:API_PORT)"
	@printf '  \033[36m%-16s\033[0m %s\n' "WEB_PORT" "Web dev server port (default: 5173)"
	@printf '  \033[36m%-16s\033[0m %s\n' "TEST_TIMEOUT" "Hard timeout for test targets in seconds (default: 300)"
	@printf '  \033[36m%-16s\033[0m %s\n' "PYTEST_FAULTHANDLER_TIMEOUT" "Per-test stuck timeout for stack dumps in seconds (default: 60)"
	@printf '  \033[36m%-16s\033[0m %s\n' "ARGS" "Extra args passed to test/ftctl/logs"
	@printf '  \033[36m%-16s\033[0m %s\n' "MSG" "Alembic revision message"
	@echo
