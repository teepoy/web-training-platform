.DEFAULT_GOAL := help
SHELL := /bin/bash

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
API_DIR     := apps/api
WEB_DIR     := apps/web
RUNTIME_DIR    := libs/platform-runtime
COMPOSE     := infra/compose/docker-compose.yaml
OPENAPI_SPEC := openapi/openapi.yaml
PROTO_DIR    := protos
SC_PROTO     := $(PROTO_DIR)/sc/v1/sample.proto
API_PORT    ?= 8000
API_URL     ?= http://localhost:$(API_PORT)
WEB_PORT    ?= 5173
COMPOSE_DEV  := infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml
COMPOSE_PROD := infra/compose/docker-compose.yaml -f infra/compose/docker-compose.prod.yaml
TEST_TIMEOUT ?= 300
PYTEST_FAULTHANDLER_TIMEOUT ?= 120
LITELLM_LOCAL_MODEL_COST_MAP="True"

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
dev: ## [DEPRECATED] Use `make up-dev` instead. Redirects to compose dev mode.
	@echo "⚠️  'make dev' is deprecated. Use 'make up-dev' for compose dev mode." >&2
	@$(MAKE) up-dev

.PHONY: dev-api
dev-api: ## Start API dev server (default: 8000)
	cd $(API_DIR) && uv run uvicorn app.main:app --reload --port $(API_PORT)

.PHONY: dev-web
dev-web: ## Start frontend dev server (default: 5173)
	cd $(WEB_DIR) && pnpm dev

# GPU worker (host) — only ONE of this OR compose --profile gpu should run at a time
.PHONY: prefect-worker-gpu-host
prefect-worker-gpu-host: ## Start a host-side GPU Prefect worker (DO NOT run concurrently with compose --profile gpu)
	cd apps/api && uv sync --extra gpu && \
	uvx prefect init --profile local --no-prompt && \
	PREFECT_API_URL=http://localhost:4200/api \
	PLATFORM_API_URL=http://localhost:8000 \
	LITELLM_LOCAL_MODEL_COST_MAP="True" uv run prefect worker start --pool default-gpu

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
test: test-api check-openapi-sync ## Run all tests

.PHONY: test-api
test-api: ## Run API tests
	@if command -v timeout >/dev/null 2>&1; then \
		timeout --foreground --signal=TERM --kill-after=10s $(TEST_TIMEOUT)s bash -lc 'cd $(API_DIR) && uv run --extra dev pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
	elif command -v gtimeout >/dev/null 2>&1; then \
		gtimeout --foreground --signal=TERM --kill-after=10s $(TEST_TIMEOUT)s bash -lc 'cd $(API_DIR) && uv run --extra dev pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
	else \
		python3 scripts/run_with_timeout.py --timeout $(TEST_TIMEOUT) -- bash -lc 'cd $(API_DIR) && uv run --extra dev pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
	fi

.PHONY: test-web
test-web: ## Run frontend unit tests (vitest)
	cd $(WEB_DIR) && pnpm test:unit

.PHONY: test-e2e
test-e2e: ## Run frontend mock e2e tests (Playwright, no live stack required)
	cd $(WEB_DIR) && pnpm test:e2e

.PHONY: check-duplicate-types
check-duplicate-types: ## Check for duplicate types between shared/api and generated/orval
	python3 scripts/check-duplicate-types.py

.PHONY: lint
lint: ## Run static checks (ruff, pyright, tsc)
	ruff check apps/api && \
	uv run --directory apps/api pyright . && \
	python3 scripts/check-duplicate-types.py && \
	cd $(WEB_DIR) && pnpm vue-tsc -b
	sg scan

.PHONY: full-test
full-test: ## Run all tests and checks (API + web unit + e2e + build + lint)
	$(MAKE) test-api && \
	$(MAKE) test-web && \
	$(MAKE) test-e2e && \
	$(MAKE) build-web && \
	ruff check apps/api && \
	uv run --directory apps/api pyright .

.PHONY: build-web
build-web: ## Build frontend for production
	cd $(WEB_DIR) && pnpm build

.PHONY: generate
generate: generate-openapi-spec generate-openapi-artifacts generate-protos ## Regenerate all schema artifacts (OpenAPI, SSE, Orval, proto)

.PHONY: generate-openapi-spec
generate-openapi-spec: ## Export OpenAPI spec from FastAPI routes to openapi/openapi.yaml
	cd $(API_DIR) && APP_CONFIG_PROFILE=test uv run python ../../scripts/export_openapi_spec.py

.PHONY: generate-api-models
generate-api-models: ## Generate backend transport models from openapi/openapi.yaml
	cd $(API_DIR) && uv run --extra dev datamodel-codegen --input ../../$(OPENAPI_SPEC) --input-file-type openapi --output app/shared/generated/openapi_models.py

.PHONY: generate-web-types
generate-web-types: ## Generate frontend transport types from openapi/openapi.yaml
	cd $(WEB_DIR) && pnpm generate:openapi-types

.PHONY: generate-orval
generate-orval: ## Generate frontend Orval artifacts from openapi/openapi.yaml
	cd apps/web && pnpm orval

.PHONY: generate-sse-types
generate-sse-types: ## Generate SSE JSON schema and frontend TypeScript types
	mkdir -p openapi $(WEB_DIR)/src/generated
	uv run --directory $(API_DIR) python ../../scripts/export_sse_schema.py
	npx json-schema-to-typescript openapi/sse-events.schema.json --output $(WEB_DIR)/src/generated/sse-types.ts

.PHONY: generate-openapi-artifacts
generate-openapi-artifacts: generate-openapi-spec generate-api-models generate-orval generate-sse-types ## Generate backend/frontend transport artifacts

.PHONY: generate-protos
generate-protos: ## Generate SC protobuf Python and TypeScript stubs from protos/ (buf v1)
	mkdir -p libs/protos/src/proto_stubs/sc/v1 $(WEB_DIR)/src/features/sc/generated/proto
	export PATH="$(CURDIR)/.venv/bin:$(CURDIR)/$(WEB_DIR)/node_modules/.bin:$$PATH" && cd $(PROTO_DIR) && npx buf generate

.PHONY: generate-protos-deps
generate-protos-deps: ## Verify buf CLI, protoc, and protoc-gen-mypy are available
	@echo "Checking protoc (>= 29.x for proto edition compatibility with buf)..."
	@if ! command -v protoc >/dev/null 2>&1; then \
		echo "protoc-29.3.0 not found. Install via: brew install protobuf@29"; \
		exit 1; \
	fi
	@echo "Proto dependencies ready protoc: $$(which protoc)"

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
	cd $(RUNTIME_DIR) && uv run ftctl $(ARGS)

# ──────────────────────────────────────────────
# Seed data
# ──────────────────────────────────────────────

.PHONY: seed
seed: ## Run unified seed CLI (usage: make seed ARGS="mock-multi-image --max-samples 1000")
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run scripts/seed.py --api-url $(API_URL) --compose-file $(COMPOSE) $(ARGS)

.PHONY: seed-dev
seed-dev: seed-wafer-mock ## Seed dev demo data (wafer-demo + mock SQLite, dev-no-auth org)
	$(MAKE) seed ARGS="wafer-demo --no-promote --org-slug dev-no-auth --org-name 'Dev No Auth'"

.PHONY: seed-wafer-mock
seed-wafer-mock: ## Seed mock wafer inspection SQLite database (100K defects)
	cd apps/api && uv run python -m app.modules.sc.adapter._wafer_mock.seed mass \
		--db-url "sqlite:///wafer_inspection.db" \
		--defects 100000 --imaged 100 --images-per 5 --reset

.PHONY: seed-wafer-mock-1m
seed-wafer-mock-1m: ## Seed mock wafer inspection SQLite database (1M defects)
	cd apps/api && uv run python -m app.modules.sc.adapter._wafer_mock.seed mass \
		--db-url "sqlite:///wafer_inspection_1m.db" \
		--defects 1000000 --imaged 200 --images-per 5 \
		--batch 50000 --reset

.PHONY: smoke-tests
smoke-tests: ## Run all smoke tests (requires: make up-dev)
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
# 	uv run python scripts/smoke_dev_batch.py $(ARGS)
# 	uv run python scripts/smoke_dev_training.py $(ARGS)
# 	uv run python scripts/smoke_dev_prediction.py $(ARGS)
	uv run python scripts/smoke_wafer_e2e.py $(ARGS)
#  Config overrides: ARGS="--wafer-db-url /custom/path.db --trainer-id resnet50-sc-v1"

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

.PHONY: up-dev
up-dev: ensure-fixtures ## Start compose dev stack (volume mounts, hot reload)
	docker compose -f $(COMPOSE_DEV) up -d

.PHONY: up-prod
up-prod: ## Start compose prod stack (no mounts, uvicorn --workers, nginx serve)
	docker compose -f $(COMPOSE_PROD) up -d

.PHONY: build-dev
build-dev: ## Build all dev-target Docker images
	docker compose -f $(COMPOSE_DEV) build

.PHONY: build-prod
build-prod: ## Build all prod-target Docker images
	docker compose -f $(COMPOSE_PROD) build

.PHONY: logs-dev
logs-dev: ## Tail dev compose logs (usage: make logs-dev ARGS="api")
	docker compose -f $(COMPOSE_DEV) logs -f $(ARGS)

.PHONY: logs-prod
logs-prod: ## Tail prod compose logs (usage: make logs-prod ARGS="api")
	docker compose -f $(COMPOSE_PROD) logs -f $(ARGS)

.PHONY: build
build: ## Build all dev-target Docker images (use build-dev/build-prod explicitly)
	docker compose -f $(COMPOSE_DEV) build

.PHONY: prod
prod: ## [DEPRECATED] Use `make up-prod` instead. Redirects to prod mode.
	@echo "⚠️  'make prod' is deprecated. Use 'make up-prod' instead." >&2
	@$(MAKE) up-prod

.PHONY: export-bundle
export-bundle: ## Export source snapshot and docker images to a tar bundle
	bash scripts/export_bundle.sh $(ARGS)

.PHONY: up
up: ensure-fixtures ## [DEPRECATED] Use `make up-dev` instead. Redirects to dev mode.
	@echo "⚠️  'make up' is deprecated. Use 'make up-dev' for development or 'make up-prod' for production." >&2
	@echo "⏳ Redirecting to 'make up-dev'..." >&2
	@docker compose -f $(COMPOSE_DEV) up -d

.PHONY: ensure-fixtures
ensure-fixtures: ## Ensure host-side bind-mount fixture files exist (idempotent; safe to run anytime)
	@for f in \
		infra/compose/pgadmin-servers.json \
		infra/compose/pgadmin-pgpass \
		infra/compose/prefect.yaml \
		infra/compose/init-scripts/create-labelstudio-db.sql \
		infra/compose/init-scripts/create-prefect-db.sql; \
	do \
		if [ ! -f "$$f" ]; then \
			echo "⚠️  Missing optional fixture: $$f" >&2; \
		fi; \
	done

.PHONY: up-stack
up-stack: ensure-fixtures ## [DEPRECATED] Use `make up-dev --scale web=0`. Redirects to dev mode without web.
	@echo "⚠️  'make up-stack' is deprecated. Use 'make up-dev --scale web=0' instead." >&2
	@echo "⏳ Redirecting to 'make up-dev --scale web=0'..." >&2
	@docker compose -f $(COMPOSE_DEV) up -d --scale web=0

.PHONY: prune-dev
prune-dev: ## Wipe ALL dev data: compose volumes (postgres, minio, label-studio, prometheus, grafana) + local SQLite files
	@echo "WARNING: This will destroy ALL local dev data (databases, S3 buckets, SQLite files, observability state)."
	@echo "Press Ctrl-C within 5 seconds to abort..."
	@sleep 5
	@echo "Stopping compose stack ..."
	@docker compose -f $(COMPOSE_DEV) down -v --remove-orphans 2>&1 | tail -20 || true
	@echo "Removing named volumes (in case any survived) ..."
	@for vol in compose_pgdata compose_minio-data compose_ls-data compose_prometheus_data compose_grafana_data; do \
		docker volume rm -f $$vol 2>/dev/null || true; \
	done
	@echo "Deleting local SQLite files ..."
	@find . -maxdepth 4 -name "*.db" \
		-not -path "*/node_modules/*" \
		-not -path "*/.git/*" \
		-not -path "*/.venv/*" \
		-not -path "*/dist/*" \
		-print -delete 2>/dev/null || true
	@echo "Prune complete. Run 'make up-dev' or 'make updev' to start fresh (bind-mount fixtures auto-recreated)."

.PHONY: reset-db-compose
reset-db-compose: ## Reset the compose database (drops and recreates finetune DB) — requires postgres running (dev mode)
	@echo "Resetting compose database ..."
	@docker compose -f $(COMPOSE_DEV) exec -T postgres psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'finetune' AND pid <> pg_backend_pid();" 2>/dev/null || true
	@docker compose -f $(COMPOSE_DEV) exec -T postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS finetune;" 2>/dev/null || true
	@docker compose -f $(COMPOSE_DEV) exec -T postgres psql -U postgres -d postgres -c "CREATE DATABASE finetune;" 2>/dev/null
	@echo "Database reset complete. Restarting API ..."
	@docker compose -f $(COMPOSE_DEV) restart api 2>/dev/null || true

.PHONY: wait-api
wait-api: ## Wait for API health endpoint to respond
	@python3 scripts/run_with_timeout.py --timeout 120 -- bash -lc 'until curl --fail --silent --show-error "$(API_URL)/health" >/dev/null; do sleep 2; done'

.PHONY: ensure-mock-datasets
ensure-mock-datasets: wait-api ## Ensure default mock datasets exist for dev mode
	$(MAKE) seed ARGS="imagenet-mock --no-model $(ARGS)"

.PHONY: ensure-sandbox-datasets
ensure-sandbox-datasets: wait-api ## Seed demo datasets for the /sandbox dev route
	$(MAKE) seed ARGS="wafer-demo --samples 2000 $(ARGS)"
	$(MAKE) seed ARGS="multi-image-scatter --samples 18 $(ARGS)"
	$(MAKE) seed ARGS="imagenet-100-rchannel --max-samples 200 --no-model $(ARGS)"

.PHONY: updev
updev: ## Start compose backend + local Vite frontend with hot reload + wafer-demo seed
	@trap 'kill 0' EXIT; \
	$(MAKE) up-dev --scale web=0 && \
	$(MAKE) wait-api && \
	$(MAKE) seed-dev && \
	$(MAKE) dev-web & \
	wait

.PHONY: db-migrate-compose
db-migrate-compose: ## Run Alembic migrations inside Compose API container (dev mode)
	docker compose -f $(COMPOSE_DEV) run --rm api /bin/sh -lc 'cd /app/apps/api && /app/.venv/bin/alembic upgrade head'

.PHONY: down
down: ## Stop all compose stacks (dev + prod)
	@docker compose -f $(COMPOSE_DEV) down --remove-orphans 2>/dev/null || true
	@docker compose -f $(COMPOSE_PROD) down --remove-orphans 2>/dev/null || true

.PHONY: logs
logs: ## Tail dev compose logs (use logs-dev/logs-prod explicitly)
	docker compose -f $(COMPOSE_DEV) logs -f $(ARGS) -n 1000

.PHONY: save-images
save-images: ## Save all compose Docker images as .tar archives
	bash scripts/save-compose-images.sh $(ARGS)

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
