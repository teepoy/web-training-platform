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
WEB_PORT    ?= 5173

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
	cd $(API_DIR) && uv run --extra dev pytest $(ARGS)

.PHONY: build-web
build-web: ## Build frontend for production
	cd $(WEB_DIR) && pnpm build

.PHONY: create-superadmin
create-superadmin: ## Create or promote a super admin user (EMAIL=, PASSWORD=, NAME= required)
	cd $(API_DIR) && APP_CONFIG_PROFILE=local-smoke uv run python -m app.cli create-superadmin --email=$(EMAIL) --password=$(PASSWORD) --name=$(NAME)

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
	uv run scripts/seed_oxford_flowers.py --compose-file $(COMPOSE) $(ARGS)

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
	docker compose -f $(COMPOSE) down

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
	@printf '  \033[36m%-16s\033[0m %s\n' "WEB_PORT" "Web dev server port (default: 5173)"
	@printf '  \033[36m%-16s\033[0m %s\n' "ARGS" "Extra args passed to test/ftctl/logs"
	@printf '  \033[36m%-16s\033[0m %s\n' "MSG" "Alembic revision message"
	@echo
