.DEFAULT_GOAL := help
SHELL := /bin/bash

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
API_DIR     := apps/api
WEB_DIR     := apps/web
SDK_DIR     := libs/python-sdk
COMPOSE     := infra/compose/docker-compose.yaml
OPENAPI_SPEC := openapi/openapi.yaml
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
	@if command -v timeout >/dev/null 2>&1; then \
		timeout --foreground --signal=TERM --kill-after=10s $(TEST_TIMEOUT)s bash -lc 'cd $(API_DIR) && uv run --extra dev pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
	elif command -v gtimeout >/dev/null 2>&1; then \
		gtimeout --foreground --signal=TERM --kill-after=10s $(TEST_TIMEOUT)s bash -lc 'cd $(API_DIR) && uv run --extra dev pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
	else \
		python3 scripts/run_with_timeout.py --timeout $(TEST_TIMEOUT) -- bash -lc 'cd $(API_DIR) && uv run --extra dev pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
	fi

.PHONY: build-web
build-web: ## Build frontend for production
	cd $(WEB_DIR) && pnpm build

.PHONY: generate-api-models
generate-api-models: ## Generate backend transport models from openapi/openapi.yaml
	cd $(API_DIR) && uv run --extra dev datamodel-codegen --input ../../$(OPENAPI_SPEC) --input-file-type openapi --output-datetime-class datetime --output app/shared/generated/openapi_models.py

.PHONY: generate-web-types
generate-web-types: ## Generate frontend transport types from openapi/openapi.yaml
	cd $(WEB_DIR) && pnpm generate:openapi-types

.PHONY: generate-openapi-artifacts
generate-openapi-artifacts: generate-api-models generate-web-types ## Generate backend/frontend transport artifacts

.PHONY: check-openapi-sync
check-openapi-sync: ## Check FastAPI route schema against openapi/openapi.yaml
	cd $(API_DIR) && APP_CONFIG_PROFILE=test uv run python ../../scripts/check_openapi_sync.py

.PHONY: docs-build
docs-build: ## Build the MkDocs documentation site
	uv run mkdocs build --strict

.PHONY: docs-serve
docs-serve: ## Serve the MkDocs documentation site locally
	uv run mkdocs serve

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
seed: ## Run unified seed CLI (usage: make seed ARGS="mock-multi-image --max-samples 1000")
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run python scripts/seed.py --api-url $(API_URL) --compose-file $(COMPOSE) $(ARGS)

.PHONY: seed-imagenet-mock
seed-imagenet-mock: ## Seed ImageNet-1K mock data with 1000 offline synthetic samples (delegates to unified CLI)
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	$(MAKE) seed ARGS="imagenet-mock $(ARGS)"

.PHONY: imagenet-mock
imagenet-mock: seed-imagenet-mock ## Alias for seed-imagenet-mock

.PHONY: seed-imagenet-poc
seed-imagenet-poc: ## Seed ImageNet-1K proof-of-concept with 64 real dev-bucket samples (delegates to unified CLI)
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	$(MAKE) seed ARGS="imagenet-real --max-samples 64 $(ARGS)"

.PHONY: imagenet-poc
imagenet-poc: seed-imagenet-poc ## Alias for seed-imagenet-poc

.PHONY: seed-imagenet-full
seed-imagenet-full: ## Seed ImageNet-1K full real dataset from the real bucket/source (delegates to unified CLI)
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	$(MAKE) seed ARGS="imagenet-real $(ARGS)"

.PHONY: imagenet-full
imagenet-full: seed-imagenet-full ## Alias for seed-imagenet-full

.PHONY: seed-multi-image-scatter
seed-multi-image-scatter: ## Seed multi-image samples with scatter coordinates (delegates to unified CLI)
	$(MAKE) seed ARGS="multi-image-scatter $(ARGS)"

.PHONY: multi-image-scatter
multi-image-scatter: seed-multi-image-scatter ## Alias for seed-multi-image-scatter

.PHONY: seed-wafer-demo
seed-wafer-demo: ## Seed deterministic Wafer Demo data (delegates to unified CLI)
	$(MAKE) seed ARGS="wafer-demo $(ARGS)"

.PHONY: wafer-demo
wafer-demo: seed-wafer-demo ## Alias for seed-wafer-demo

.PHONY: seed-mock-multi-image
seed-mock-multi-image: ## Seed 100K-sample multi-image mock dataset (delegates to unified CLI)
	$(MAKE) seed ARGS="mock-multi-image $(ARGS)"

.PHONY: mock-multi-image
mock-multi-image: seed-mock-multi-image ## Alias for seed-mock-multi-image

.PHONY: seed-imagenet-100-rchannel
seed-imagenet-100-rchannel: ## Seed ImageNet-100 R-Channel dataset with 10K multi-image samples (delegates to unified CLI)
	$(MAKE) seed ARGS="imagenet-100-rchannel $(ARGS)"

.PHONY: imagenet-100-rchannel
imagenet-100-rchannel: seed-imagenet-100-rchannel ## Alias for seed-imagenet-100-rchannel

.PHONY: smoke-dev-batch
smoke-dev-batch: ## Run batch dev smoke test against seeded local stack
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run python scripts/smoke_dev_batch.py $(ARGS)

.PHONY: smoke-dev-training
smoke-dev-training: ## Run training dev smoke test against local stack
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run python scripts/smoke_dev_training.py $(ARGS)

.PHONY: smoke-dev-prediction
smoke-dev-prediction: ## Run prediction dev smoke test against local stack
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run python scripts/smoke_dev_prediction.py $(ARGS)

.PHONY: smoke-dev-runtime
smoke-dev-runtime: smoke-dev-training smoke-dev-prediction ## Run core runtime smoke tests against local stack

# ──────────────────────────────────────────────
# Regression tests
# ──────────────────────────────────────────────

.PHONY: test-regression
test-regression: ## Run pytest-native seed regression tests (SQLite, no Docker needed)
	cd $(API_DIR) && uv run --extra dev pytest tests/test_seed_regression_*.py -v

.PHONY: smoke-regression
smoke-regression: ## Run live-stack smoke regression (needs Docker Compose)
	@curl -s --fail --show-error $(API_URL)/health > /dev/null 2>&1 || (echo "ERROR: API not healthy at $(API_URL)" && exit 1)
	python scripts/smoke_runner.py --all

.PHONY: regression
regression: test-regression ## Run fast regression then live-stack smoke
	@echo "--- Running live-stack smoke regression ---"
	$(MAKE) smoke-regression

# ──────────────────────────────────────────────
# Live-stack Playwright E2E
# ──────────────────────────────────────────────

WEB_URL ?= http://localhost:5173

.PHONY: e2e-live
e2e-live: ## Run live-stack Playwright browser tests (needs Docker Compose)
	@curl -s --fail --show-error $(API_URL)/health > /dev/null 2>&1 || (echo "ERROR: API not healthy at $(API_URL)" && exit 1)
	cd $(WEB_DIR) && WEB_URL=$(WEB_URL) API_URL=$(API_URL) pnpm test:e2e-live

.PHONY: e2e-live-ui
e2e-live-ui: ## Run live-stack Playwright tests in headed mode (debugging)
	cd $(WEB_DIR) && WEB_URL=$(WEB_URL) API_URL=$(API_URL) pnpm exec playwright test --config e2e-live/playwright.config.ts --headed

.PHONY: e2e-live-report
e2e-live-report: ## Open Playwright HTML report
	cd $(WEB_DIR) && pnpm exec playwright show-report e2e-live/playwright-report-live


# ──────────────────────────────────────────────
# Docker / Infra
# ──────────────────────────────────────────────
.PHONY: build
build:
	docker compose -f $(COMPOSE) build

.PHONY: export-bundle
export-bundle: ## Export source snapshot and docker images to a tar bundle
	bash scripts/export_bundle.sh $(ARGS)

.PHONY: up
up: ## Start full Compose stack (dev profile, detached)
	docker compose -f $(COMPOSE) up -d

.PHONY: up-stack
up-stack: ## Start compose stack without the baked web container
	docker compose -f $(COMPOSE) up -d --scale web=0

.PHONY: wait-api
wait-api: ## Wait for API health endpoint to respond
	@python3 scripts/run_with_timeout.py --timeout 120 -- bash -lc 'until curl --fail --silent --show-error "$(API_URL)/health" >/dev/null; do sleep 2; done'

.PHONY: ensure-mock-datasets
ensure-mock-datasets: wait-api ## Ensure default mock datasets exist for dev mode
	$(MAKE) seed-imagenet-mock ARGS="--no-model"

.PHONY: ensure-sandbox-datasets
ensure-sandbox-datasets: wait-api ## Seed demo datasets for the /sandbox dev route
	$(MAKE) seed ARGS="wafer-demo --samples 2000 $(ARGS)"
	$(MAKE) seed ARGS="multi-image-scatter --samples 18 $(ARGS)"
	$(MAKE) seed ARGS="imagenet-100-rchannel --max-samples 200 --no-model $(ARGS)"

.PHONY: updev
updev: ## Start compose backend + local Vite frontend with hot reload
	@trap 'kill 0' EXIT; \
	$(MAKE) up-stack && \
	$(MAKE) ensure-mock-datasets && \
	$(MAKE) ensure-sandbox-datasets && \
	$(MAKE) dev-web & \
	wait

.PHONY: db-migrate-compose
db-migrate-compose: ## Run Alembic migrations inside Compose API container
	docker compose -f $(COMPOSE) run --rm api /bin/sh -lc 'cd /app/apps/api && /app/.venv/bin/alembic upgrade head'

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
help: ## Show this help message
	@printf '\nUsage: make \033[36m<target>\033[0m [VAR=value]\n\n'
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nVariables:\n'
	@printf '  \033[36m%-16s\033[0m %s\n' "API_PORT" "API server port (default: 8000)"
	@printf '  \033[36m%-16s\033[0m %s\n' "API_URL" "API base URL used by seed targets (default: http://localhost:API_PORT)"
	@printf '  \033[36m%-16s\033[0m %s\n' "WEB_PORT" "Web dev server port (default: 5173)"
	@printf '  \033[36m%-16s\033[0m %s\n' "TEST_TIMEOUT" "Hard timeout for test targets in seconds (default: 300)"
	@printf '  \033[36m%-16s\033[0m %s\n' "PYTEST_FAULTHANDLER_TIMEOUT" "Per-test stuck timeout for stack dumps in seconds (default: 60)"
	@printf '  \033[36m%-16s\033[0m %s\n' "ARGS" "Extra args passed to test/ftctl/logs"
	@printf '  \033[36m%-16s\033[0m %s\n' "MSG" "Alembic revision message"
	@echo
