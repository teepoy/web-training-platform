# Build, setup, development, data, and housekeeping targets.

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

.PHONY: dev-api
dev-api: ## Start API dev server (default: 8000)
	cd $(API_DIR) && $(DEV_API_HOST_ENV) uv run --no-dev --frozen uvicorn app.main:app --reload --port $(API_PORT) --timeout-keep-alive $${UVICORN_TIMEOUT_KEEP_ALIVE:-120} --timeout-graceful-shutdown $${UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-600} --timeout-worker-healthcheck $${UVICORN_TIMEOUT_WORKER_HEALTHCHECK:-60}

.PHONY: dev-api-host
dev-api-host: up-dev-host-api ## Start compose dependencies, then run API on host
	cd $(API_DIR) && $(DEV_API_HOST_ENV) uv run --no-dev --frozen python scripts/prepare_platform.py && $(DEV_API_HOST_ENV) uv run --no-dev --frozen uvicorn app.main:app --reload --port $(API_PORT) --timeout-keep-alive $${UVICORN_TIMEOUT_KEEP_ALIVE:-120} --timeout-graceful-shutdown $${UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-600} --timeout-worker-healthcheck $${UVICORN_TIMEOUT_WORKER_HEALTHCHECK:-60}

.PHONY: dev-web
dev-web: ## Start frontend dev server (default: 5173)
	cd $(WEB_DIR) && pnpm dev

# GPU worker (host) — only ONE of this OR compose --profile gpu should run at a time
.PHONY: prefect-worker-gpu-host
prefect-worker-gpu-host: ## Start a host-side GPU Prefect worker (DO NOT run concurrently with compose --profile gpu)
	cd apps/api && $(UV_RUN_INSTALLED) python -m prefect init --profile local --no-prompt && \
	$(DEV_API_HOST_ENV) \
	PLATFORM_API_URL=$(API_URL) \
	LITELLM_LOCAL_MODEL_COST_MAP="True" $(UV_RUN_INSTALLED) python -m prefect worker start --pool default-gpu

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────

.PHONY: db-migrate
db-migrate: ## Run Alembic migrations (upgrade head)
	cd $(API_DIR) && $(DEV_API_HOST_ENV) uv run --no-dev --frozen alembic upgrade head

.PHONY: db-revision
db-revision: ## Create a new Alembic revision (usage: make db-revision MSG="add users table")
	cd $(API_DIR) && $(DEV_API_HOST_ENV) uv run --no-dev --frozen alembic revision --autogenerate -m "$(MSG)"

.PHONY: build-web
build-web: ## Build the frontend bundle
	cd $(WEB_DIR) && pnpm build

.PHONY: docs-build
docs-build: ## Build the MkDocs documentation site
	uv run mkdocs build --strict

.PHONY: docs-serve
docs-serve: ## Serve the MkDocs documentation site locally
	uv run mkdocs serve

.PHONY: create-superadmin
create-superadmin: ## Create or promote a super admin user (EMAIL=, PASSWORD=, NAME= required)
	cd $(API_DIR) && $(DEV_API_HOST_ENV) BOOTSTRAP_SUPERADMIN_EMAIL='$(EMAIL)' BOOTSTRAP_SUPERADMIN_PASSWORD='$(PASSWORD)' BOOTSTRAP_SUPERADMIN_NAME='$(NAME)' uv run python scripts/create_superadmin.py

.PHONY: reset-dev-database
reset-dev-database: ## Destructively reset the dev database through Alembic
	cd $(API_DIR) && $(DEV_API_HOST_ENV) ALLOW_RESET_APP_DATA=1 uv run python scripts/reset_dev_database.py


# ──────────────────────────────────────────────
# Seed data
# ──────────────────────────────────────────────

.PHONY: seed
seed: ## Run unified seed CLI (usage: make seed ARGS="mock-multi-image --max-samples 1000")
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run scripts/seed.py --api-url $(API_URL) --compose-file $(COMPOSE) $(ARGS)

.PHONY: seed-dev
seed-dev: ## Seed moderate, repeatable Library/model/automation showcase data
	$(DEV_API_HOST_ENV) $(MAKE) seed ARGS="dev-showcase --no-promote --org-slug dev-no-auth --org-name 'Dev No Auth' --classification-samples $(DEV_SEED_CLASSIFICATION_SAMPLES) --review-samples $(DEV_SEED_REVIEW_SAMPLES) --sc-samples $(SC_WAFER_MOCK_DEFECTS) --sc-annotations $(DEV_SEED_SC_ANNOTATIONS) --sc-inspection-time $(SC_WAFER_MOCK_INSPECTION_TIME)"

# ──────────────────────────────────────────────
# Housekeeping
# ──────────────────────────────────────────────

.PHONY: clean
clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(WEB_DIR)/dist
