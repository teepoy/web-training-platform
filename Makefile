.DEFAULT_GOAL := help
SHELL := /bin/bash

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
API_DIR     := apps/api
WEB_DIR     := apps/web
COMPOSE     := infra/compose/docker-compose.yaml
OPENAPI_SPEC := openapi/openapi.yaml
PROTO_DIR    := protos
SC_PROTO     := $(PROTO_DIR)/sc/v1/sample.proto
API_PORT    ?= 8000
API_URL     ?= http://localhost:$(API_PORT)
WEB_PORT    ?= 5173
COMPOSE_DEV  := infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml
DATA_DIR     := infra/compose/data
IMAGE_PARSER_GRPC_ADDR_HOST ?= 127.0.0.1:9092
MINIO_ENDPOINT_HOST ?= localhost:9000
SC_WAFER_MOCK_DEFECTS ?= 2500
SC_WAFER_MOCK_INSPECTION_TIME ?= 2026-08-01T04:00:00
DEV_SEED_CLASSIFICATION_SAMPLES ?= 180
DEV_SEED_REVIEW_SAMPLES ?= 96
DEV_SEED_SC_ANNOTATIONS ?= 96
SC_PATCH_ZIP_BUCKET ?= sc-patch-images
SC_PATCH_ZIP_S3_ENDPOINT ?= http://localhost:9000

DEV_API_HOST_ENV := \
	APP_CONFIG_PROFILE=dev \
	DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/finetune \
	PREFECT_API_URL=http://localhost:4200/api \
	PREFECT_UI_URL=http://localhost:4200 \
	LABEL_STUDIO_URL=http://localhost:8080 \
	LABEL_STUDIO_EXTERNAL_URL=http://localhost:8080 \
	LABEL_STUDIO_API_KEY=ls-smoke-token-for-local-dev \
	LABEL_STUDIO_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/labelstudio \
	MINIO_ENDPOINT=$(MINIO_ENDPOINT_HOST) \
	MINIO_ACCESS_KEY=minioadmin \
	MINIO_SECRET_KEY=minioadmin \
	MINIO_BUCKET=finetune-artifacts \
	REDIS_HOST=localhost \
	REDIS_PORT=6379 \
	SC_UPSTREAM_ADDR=127.0.0.1:9091 \
	SC_UPSTREAM_FLIGHT_ADDR=grpc://127.0.0.1:9093 \
	IMAGE_PARSER_GRPC_ADDR=$(IMAGE_PARSER_GRPC_ADDR_HOST)

# ──────────────────────────────────────────────
# Canonical deployed release stack (infra/compose/production/)
# ──────────────────────────────────────────────
PROD_NETWORK                ?= finetune-prod
PROD_STATEFUL_ENV           ?= /srv/finetune/stateful/.env
PROD_PLATFORM_ENV           ?= /srv/finetune/platform/.env
PROD_OBSERVABILITY_ENV      ?= /srv/finetune/observability/.env
PRE_RELEASE_NETWORK         ?= finetune-pre-release
PRE_RELEASE_PROJECT         ?= finetune-pre-release
PRE_RELEASE_STATEFUL_ENV    ?= /srv/finetune-pre-release/stateful/.env
PRE_RELEASE_PLATFORM_ENV    ?= /srv/finetune-pre-release/platform/.env
PRE_RELEASE_OBSERVABILITY_ENV ?= /srv/finetune-pre-release/observability/.env
PRE_RELEASE_PROFILES        ?=

RELEASE_PROFILE             ?= prod
RELEASE_NETWORK             ?= $(PROD_NETWORK)
RELEASE_PROJECT             ?= finetune
RELEASE_STATEFUL_ENV        ?= $(PROD_STATEFUL_ENV)
RELEASE_PLATFORM_ENV        ?= $(PROD_PLATFORM_ENV)
RELEASE_OBSERVABILITY_ENV   ?= $(PROD_OBSERVABILITY_ENV)
RELEASE_PROFILES            ?=
RELEASE_RUNTIME_ENV         := APP_CONFIG_PROFILE=$(RELEASE_PROFILE) PLATFORM_NETWORK_NAME=$(RELEASE_NETWORK)

COMPOSE_PROD_STATEFUL       := infra/compose/production/compose.stateful.yaml
COMPOSE_PROD_PLATFORM       := infra/compose/production/compose.platform.yaml
COMPOSE_PROD_OPS            := infra/compose/production/compose.ops.yaml
COMPOSE_PROD_OBSERVABILITY  := infra/compose/production/compose.observability.yaml

# Local pre-release acceptance stack. It reuses the production manifests,
# builds production Docker targets, and keeps projects/network/volumes isolated.
PRE_RELEASE_LOCAL_ENV        ?= infra/compose/pre-release/.env
PRE_RELEASE_LOCAL_NETWORK    ?= finetune-pre-release-local
PRE_RELEASE_LOCAL_PROJECT    ?= finetune-pre-release-local
PRE_RELEASE_LOCAL_TAG        ?= $(shell git describe --always --dirty 2>/dev/null)
PRE_RELEASE_LOCAL_IMAGE_PREFIX ?= web-training-platform
PRE_RELEASE_LOCAL_PROFILES   ?=
PRE_RELEASE_LOCAL_BIND_HOST  ?= 127.0.0.1
PRE_RELEASE_LOCAL_POSTGRES_PORT ?= 15432
PRE_RELEASE_LOCAL_MINIO_PORT ?= 19000
PRE_RELEASE_LOCAL_MINIO_CONSOLE_PORT ?= 19001
PRE_RELEASE_LOCAL_REDIS_PORT ?= 16379
PRE_RELEASE_LOCAL_LABEL_STUDIO_PORT ?= 18080
PRE_RELEASE_LOCAL_PREFECT_PORT ?= 14200
PRE_RELEASE_LOCAL_API_PORT   ?= 18000
PRE_RELEASE_LOCAL_SC_DATA_PROVIDER_PORT ?= 18001
PRE_RELEASE_LOCAL_WEB_PORT   ?= 15173
PRE_RELEASE_LOCAL_SC_GRPC_PORT ?= 19091
PRE_RELEASE_LOCAL_SC_FLIGHT_PORT ?= 19093
PRE_RELEASE_LOCAL_IMAGE_PARSER_HTTP_PORT ?= 18090
PRE_RELEASE_LOCAL_IMAGE_PARSER_GRPC_PORT ?= 19092
COMPOSE_PRE_RELEASE_BUILD    := infra/compose/pre-release/compose.build.yaml
COMPOSE_PRE_RELEASE_STATEFUL := infra/compose/pre-release/compose.stateful.yaml
COMPOSE_PRE_RELEASE_PLATFORM := infra/compose/pre-release/compose.platform.yaml
PRE_RELEASE_LOCAL_RUNTIME_ENV := \
	APP_CONFIG_PROFILE=pre-release \
	PLATFORM_NETWORK_NAME=$(PRE_RELEASE_LOCAL_NETWORK) \
	FRONTEND_URL=http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_WEB_PORT) \
	PREFECT_UI_URL=http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_PREFECT_PORT) \
	LABEL_STUDIO_EXTERNAL_URL=http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_LABEL_STUDIO_PORT) \
	PRE_RELEASE_BIND_HOST=$(PRE_RELEASE_LOCAL_BIND_HOST) \
	PRE_RELEASE_POSTGRES_PORT=$(PRE_RELEASE_LOCAL_POSTGRES_PORT) \
	PRE_RELEASE_MINIO_PORT=$(PRE_RELEASE_LOCAL_MINIO_PORT) \
	PRE_RELEASE_MINIO_CONSOLE_PORT=$(PRE_RELEASE_LOCAL_MINIO_CONSOLE_PORT) \
	PRE_RELEASE_REDIS_PORT=$(PRE_RELEASE_LOCAL_REDIS_PORT) \
	PRE_RELEASE_LABEL_STUDIO_PORT=$(PRE_RELEASE_LOCAL_LABEL_STUDIO_PORT) \
	PRE_RELEASE_PREFECT_PORT=$(PRE_RELEASE_LOCAL_PREFECT_PORT) \
	PRE_RELEASE_API_PORT=$(PRE_RELEASE_LOCAL_API_PORT) \
	PRE_RELEASE_SC_DATA_PROVIDER_PORT=$(PRE_RELEASE_LOCAL_SC_DATA_PROVIDER_PORT) \
	PRE_RELEASE_WEB_PORT=$(PRE_RELEASE_LOCAL_WEB_PORT) \
	PRE_RELEASE_SC_GRPC_PORT=$(PRE_RELEASE_LOCAL_SC_GRPC_PORT) \
	PRE_RELEASE_SC_FLIGHT_PORT=$(PRE_RELEASE_LOCAL_SC_FLIGHT_PORT) \
	PRE_RELEASE_IMAGE_PARSER_HTTP_PORT=$(PRE_RELEASE_LOCAL_IMAGE_PARSER_HTTP_PORT) \
	PRE_RELEASE_IMAGE_PARSER_GRPC_PORT=$(PRE_RELEASE_LOCAL_IMAGE_PARSER_GRPC_PORT) \
	FINETUNE_API_IMAGE=$(PRE_RELEASE_LOCAL_IMAGE_PREFIX)/api:$(PRE_RELEASE_LOCAL_TAG) \
	FINETUNE_WEB_IMAGE=$(PRE_RELEASE_LOCAL_IMAGE_PREFIX)/web:$(PRE_RELEASE_LOCAL_TAG) \
	FINETUNE_CPU_WORKER_IMAGE=$(PRE_RELEASE_LOCAL_IMAGE_PREFIX)/cpu-worker:$(PRE_RELEASE_LOCAL_TAG) \
	FINETUNE_GPU_WORKER_IMAGE=$(PRE_RELEASE_LOCAL_IMAGE_PREFIX)/gpu-worker:$(PRE_RELEASE_LOCAL_TAG) \
	SC_UPSTREAM_IMAGE=$(PRE_RELEASE_LOCAL_IMAGE_PREFIX)/sc-upstream:$(PRE_RELEASE_LOCAL_TAG) \
	IMAGE_PARSER_IMAGE=$(PRE_RELEASE_LOCAL_IMAGE_PREFIX)/image-parser:$(PRE_RELEASE_LOCAL_TAG)
TEST_TIMEOUT ?= 300
PYTEST_FAULTHANDLER_TIMEOUT ?= 120
UV_RUN_INSTALLED := uv run --no-sync --offline
LITELLM_LOCAL_MODEL_COST_MAP="True"
PROTOC_GEN_GO_VERSION ?= v1.36.11
PROTOC_GEN_GO_GRPC_VERSION ?= v1.6.0
PROTO_TOOLS_DIR ?= $(CURDIR)/.cache/protobuf-tools
PROTO_GO_TOOLS_BIN := $(PROTO_TOOLS_DIR)/bin
PROTO_BUF_BIN := $(CURDIR)/node_modules/.bin/buf
PROTO_ES_BIN := $(CURDIR)/$(WEB_DIR)/node_modules/.bin/protoc-gen-es
PROTO_MYPY_BIN := $(CURDIR)/.venv/bin/protoc-gen-mypy
PROTO_PYTHON_BIN := $(CURDIR)/.venv/bin/python

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
	cd apps/api && uv sync --group sc-runtime && \
	uv run python -m prefect init --profile local --no-prompt && \
	$(DEV_API_HOST_ENV) \
	PLATFORM_API_URL=http://localhost:8000 \
	LITELLM_LOCAL_MODEL_COST_MAP="True" uv run python -m prefect worker start --pool default-gpu

# ──────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────

.PHONY: db-migrate
db-migrate: ## Run Alembic migrations (upgrade head)
	cd $(API_DIR) && uv run --no-dev --frozen alembic upgrade head

.PHONY: db-revision
db-revision: ## Create a new Alembic revision (usage: make db-revision MSG="add users table")
	cd $(API_DIR) && uv run --no-dev --frozen alembic revision --autogenerate -m "$(MSG)"

# ──────────────────────────────────────────────
# Tests & checks
# ──────────────────────────────────────────────

.PHONY: test
test: test-api check-openapi-sync ## Run all tests

.PHONY: test-api
test-api: ## Run API tests
	@if command -v timeout >/dev/null 2>&1; then \
		timeout --foreground --signal=TERM --kill-after=10s $(TEST_TIMEOUT)s bash -lc 'cd $(API_DIR) && $(UV_RUN_INSTALLED) --extra dev python -m pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
	elif command -v gtimeout >/dev/null 2>&1; then \
		gtimeout --foreground --signal=TERM --kill-after=10s $(TEST_TIMEOUT)s bash -lc 'cd $(API_DIR) && $(UV_RUN_INSTALLED) --extra dev python -m pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
	else \
		python3 scripts/run_with_timeout.py --timeout $(TEST_TIMEOUT) -- bash -lc 'cd $(API_DIR) && $(UV_RUN_INSTALLED) --extra dev python -m pytest -o faulthandler_timeout=$(PYTEST_FAULTHANDLER_TIMEOUT) $(ARGS)'; \
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
lint: ## Run fast lint on git diff files (ruff + prettier)
	@CHANGED=$$(git diff --name-only --diff-filter=ACMR HEAD 2>/dev/null || true); \
	if [ -z "$$CHANGED" ]; then \
		echo "No changed files found."; \
		exit 0; \
	fi; \
	PY_FILES=$$(echo "$$CHANGED" | grep '\.py$$' || true); \
	if [ -n "$$PY_FILES" ]; then \
		echo "--- ruff check (Python) ---"; \
		echo "$$PY_FILES" | xargs ruff check; \
	fi; \
	WEB_FILES=$$(echo "$$CHANGED" | grep -E '\.(vue|ts|tsx|js|jsx|css|scss|json|yaml|yml|md)$$' | grep -v /node_modules/ | grep -v /dist/ | grep -v /generated/ || true); \
	if [ -n "$$WEB_FILES" ]; then \
		echo "--- prettier check (Web) ---"; \
		echo "$$WEB_FILES" | xargs pnpm exec prettier --check; \
	fi; \
	echo "--- lint done ---"

.PHONY: full-test
full-test: ## Run all tests and checks (API + web unit + e2e + build + lint)
	$(MAKE) test-api && \
	$(MAKE) test-web && \
	$(MAKE) test-e2e && \
	$(MAKE) build-web && \
	ruff check apps/api && \
	$(UV_RUN_INSTALLED) --directory apps/api pyright .

.PHONY: build-web
build-web: ## Build frontend for production
	cd $(WEB_DIR) && pnpm build

.PHONY: build-image-parser-vendor
build-image-parser-vendor: ## Build amd64 Debian vendor/tooling image for image-parser offline builds
	docker build --platform linux/amd64 -f services/image-parser/Dockerfile.vendor -t image-parser-vendor:local .

.PHONY: generate
generate: generate-openapi-spec generate-openapi-artifacts generate-protos ## Regenerate all schema artifacts (OpenAPI, SSE, Orval, proto)

.PHONY: generate-openapi-spec
generate-openapi-spec: ## Export OpenAPI spec from FastAPI routes to openapi/openapi.yaml
	cd $(API_DIR) && APP_CONFIG_PROFILE=test uv run python ../../scripts/export_openapi_spec.py

.PHONY: generate-api-models
generate-api-models: ## Generate backend transport models from openapi/openapi.yaml
	cd $(API_DIR) && uv run --extra dev python -m datamodel_code_generator --input ../../$(OPENAPI_SPEC) --input-file-type openapi --output app/shared/generated/openapi_models.py

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
generate-protos: generate-protos-deps ## Generate protobuf Python, TypeScript, and Go stubs from protos/
	mkdir -p libs/protos/src/proto_stubs/sc/v1 $(WEB_DIR)/src/features/sc/generated/proto
	cd $(PROTO_DIR) && "$(PROTO_BUF_BIN)" generate . --template buf.gen.yaml
	cd $(WEB_DIR) && pnpm exec prettier --write src/features/sc/generated/proto
	"$(PROTO_PYTHON_BIN)" scripts/normalize_generated_text.py $(WEB_DIR)/src/features/sc/generated/proto --suffix .ts
	"$(PROTO_PYTHON_BIN)" -m grpc_tools.protoc \
		--proto_path=$(PROTO_DIR) \
		--python_out=libs/protos/src/proto_stubs \
		$(PROTO_DIR)/imageparser/v1/service.proto \
		$(PROTO_DIR)/sc/v1/sample.proto \
		$(PROTO_DIR)/sc/v1/upstream.proto
	"$(PROTO_PYTHON_BIN)" -m grpc_tools.protoc \
		--proto_path=$(PROTO_DIR) \
		--grpc_python_out=libs/protos/src/proto_stubs \
		$(PROTO_DIR)/imageparser/v1/service.proto \
		$(PROTO_DIR)/sc/v1/upstream.proto
	"$(PROTO_PYTHON_BIN)" scripts/fix_python_grpc_imports.py libs/protos/src/proto_stubs
	cd services/image-parser && go mod tidy

.PHONY: generate-protos-deps
generate-protos-deps: ## Install locked proto generators into repository-managed environments
	uv sync --frozen --inexact
	pnpm install --frozen-lockfile
	mkdir -p "$(PROTO_GO_TOOLS_BIN)"
	GOBIN="$(PROTO_GO_TOOLS_BIN)" go install google.golang.org/protobuf/cmd/protoc-gen-go@$(PROTOC_GEN_GO_VERSION)
	GOBIN="$(PROTO_GO_TOOLS_BIN)" go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@$(PROTOC_GEN_GO_GRPC_VERSION)
	@test -x "$(PROTO_BUF_BIN)"
	@test -x "$(PROTO_ES_BIN)"
	@test -x "$(PROTO_MYPY_BIN)"
	@test -x "$(PROTO_PYTHON_BIN)"
	@test -x "$(PROTO_GO_TOOLS_BIN)/protoc-gen-go"
	@test -x "$(PROTO_GO_TOOLS_BIN)/protoc-gen-go-grpc"
	@echo "Proto generators ready: buf=$$("$(PROTO_BUF_BIN)" --version), protoc-gen-es=$$("$(PROTO_ES_BIN)" --version), mypy-protobuf=$$("$(PROTO_MYPY_BIN)" --version), grpcio-tools=$$("$(PROTO_PYTHON_BIN)" -m grpc_tools.protoc --version), protoc-gen-go=$$("$(PROTO_GO_TOOLS_BIN)/protoc-gen-go" --version), protoc-gen-go-grpc=$$("$(PROTO_GO_TOOLS_BIN)/protoc-gen-go-grpc" --version)"

.PHONY: check-openapi-sync
check-openapi-sync: ## Check FastAPI route schema against openapi/openapi.yaml
	cd $(API_DIR) && APP_CONFIG_PROFILE=test $(UV_RUN_INSTALLED) python ../../scripts/check_openapi_sync.py

.PHONY: docs-build
docs-build: ## Build the MkDocs documentation site
	uv run mkdocs build --strict

.PHONY: docs-serve
docs-serve: ## Serve the MkDocs documentation site locally
	uv run mkdocs serve

.PHONY: create-superadmin
create-superadmin: ## Create or promote a super admin user (EMAIL=, PASSWORD=, NAME= required)
	cd $(API_DIR) && APP_CONFIG_PROFILE=dev BOOTSTRAP_SUPERADMIN_EMAIL='$(EMAIL)' BOOTSTRAP_SUPERADMIN_PASSWORD='$(PASSWORD)' BOOTSTRAP_SUPERADMIN_NAME='$(NAME)' uv run python scripts/create_superadmin.py

.PHONY: reset-dev-database
reset-dev-database: ## Destructively reset the dev database through Alembic
	cd $(API_DIR) && APP_CONFIG_PROFILE=dev ALLOW_RESET_APP_DATA=1 uv run python scripts/reset_dev_database.py


# ──────────────────────────────────────────────
# Seed data
# ──────────────────────────────────────────────

.PHONY: seed
seed: ## Run unified seed CLI (usage: make seed ARGS="mock-multi-image --max-samples 1000")
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run scripts/seed.py --api-url $(API_URL) --compose-file $(COMPOSE) $(ARGS)

.PHONY: seed-dev
seed-dev: seed-wafer-mock seed-wafer-patch-zips ## Seed moderate, repeatable data for dataset/model/job/schedule/sensor pages
	$(DEV_API_HOST_ENV) $(MAKE) seed ARGS="dev-showcase --no-promote --org-slug dev-no-auth --org-name 'Dev No Auth' --classification-samples $(DEV_SEED_CLASSIFICATION_SAMPLES) --review-samples $(DEV_SEED_REVIEW_SAMPLES) --sc-samples $(SC_WAFER_MOCK_DEFECTS) --sc-annotations $(DEV_SEED_SC_ANNOTATIONS) --sc-inspection-time $(SC_WAFER_MOCK_INSPECTION_TIME)"

.PHONY: seed-wafer-mock
seed-wafer-mock: ## Seed mock wafer inspection SQLite database
	cd services/sc-upstream && uv run python -m sc_upstream.seed mass \
		--db-url "sqlite:///$(CURDIR)/$(DATA_DIR)/wafer_inspection.db" \
		--defects "$(SC_WAFER_MOCK_DEFECTS)" --imaged 100 --images-per 5 \
		--inspection-time "$(SC_WAFER_MOCK_INSPECTION_TIME)" --reuse-matching

.PHONY: seed-wafer-patch-zips
seed-wafer-patch-zips: ## Seed mock SC patch zips into MinIO and inspection_zips.db
	uv run python infra/compose/seed_patch_zips.py \
		--s3-endpoint "$(SC_PATCH_ZIP_S3_ENDPOINT)" \
		--bucket "$(SC_PATCH_ZIP_BUCKET)" \
		--inspection-db-url "sqlite:///$(CURDIR)/$(DATA_DIR)/wafer_inspection.db" \
		--zips-db-url "sqlite:///$(CURDIR)/$(DATA_DIR)/inspection_zips.db" \
		--upstream-cache-dir "$(CURDIR)/$(DATA_DIR)/cache" \
		--total-defects "$(SC_WAFER_MOCK_DEFECTS)"

.PHONY: seed-wafer-mock-1m
seed-wafer-mock-1m: ## Seed mock wafer inspection SQLite database (1M defects)
	cd services/sc-upstream && uv run python -m sc_upstream.seed mass \
		--db-url "sqlite:///$(CURDIR)/$(DATA_DIR)/wafer_inspection_1m.db" \
		--defects 1000000 --imaged 200 --images-per 5 \
		--batch 50000 --reset

.PHONY: smoke-tests
smoke-tests: ## Run all smoke tests (requires: make up-dev)
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
# 	uv run python scripts/smoke_dev_batch.py $(ARGS)
# 	uv run python scripts/smoke_dev_training.py $(ARGS)
# 	uv run python scripts/smoke_dev_prediction.py $(ARGS)
	uv run python scripts/smoke_wafer_e2e.py $(ARGS)
#  Config overrides: ARGS="--wafer-db-url /custom/path.db --trainer-id yolo-sc-v1"

.PHONY: smoke-wafer-train-predict
smoke-wafer-train-predict: ## Run seedmaker wafer images through live train -> predict
	@curl --fail --silent --show-error "$(API_URL)/health" >/dev/null || (printf 'API health check failed: %s\n' "$(API_URL)/health" && exit 1)
	uv run --directory apps/api python ../../scripts/smoke_wafer_train_predict.py $(ARGS)

# ──────────────────────────────────────────────
# Regression tests
# ──────────────────────────────────────────────

.PHONY: test-regression
test-regression: ## Run pytest-native seed regression tests (SQLite, no Docker needed)
	cd $(API_DIR) && uv run --extra dev python -m pytest tests/test_seed_regression_*.py -v

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
	cd $(WEB_DIR) && WEB_URL=$(WEB_URL) API_URL=$(API_URL) pnpm test:e2e:live

.PHONY: e2e-live-ui
e2e-live-ui: ## Run live-stack Playwright tests in headed mode (debugging)
	cd $(WEB_DIR) && WEB_URL=$(WEB_URL) API_URL=$(API_URL) pnpm test:e2e:live:ui

.PHONY: e2e-live-report
e2e-live-report: ## Open Playwright HTML report
	cd $(WEB_DIR) && pnpm test:e2e:live:report


# ──────────────────────────────────────────────
# Docker / Infra
# ──────────────────────────────────────────────

.PHONY: up-dev
up-dev: ensure-fixtures ## Start compose dev stack (volume mounts, hot reload)
	docker compose -f $(COMPOSE_DEV) up -d postgres minio redis label-studio prefect-server sc-upstream image-parser
	docker compose -f $(COMPOSE_DEV) --profile ops run --rm prepare-platform
	docker compose -f $(COMPOSE_DEV) up -d $(ARGS)

.PHONY: up-dev-host-api
up-dev-host-api: ensure-fixtures ## Start compose dev dependencies without Docker API/Web
	docker compose -f $(COMPOSE_DEV) up -d --scale api=0 --scale web=0 $(ARGS)

.PHONY: build-dev
build-dev: ## Build all dev-target Docker images
	docker compose -f $(COMPOSE_DEV) build $(ARGS)

.PHONY: check-config
check-config: ## Render dev, local pre-release, deployed pre-release, and production configurations
	docker compose -f $(COMPOSE_DEV) config --quiet
	docker compose --env-file infra/compose/production/env-stateful.example -f $(COMPOSE_PROD_STATEFUL) config --quiet
	APP_CONFIG_PROFILE=pre-release docker compose --env-file infra/compose/production/env-platform.example -f $(COMPOSE_PROD_PLATFORM) config --quiet
	APP_CONFIG_PROFILE=prod docker compose --env-file infra/compose/production/env-platform.example -f $(COMPOSE_PROD_PLATFORM) config --quiet
	APP_CONFIG_PROFILE=prod docker compose --env-file infra/compose/production/env-platform.example -f $(COMPOSE_PROD_OPS) --profile ops config --quiet
	docker compose --env-file infra/compose/production/env-observability.example -f $(COMPOSE_PROD_OBSERVABILITY) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file infra/compose/pre-release/env.example -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file infra/compose/pre-release/env.example -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file infra/compose/pre-release/env.example -p $(PRE_RELEASE_LOCAL_PROJECT)-ops -f $(COMPOSE_PROD_OPS) --profile ops config --quiet
	python3 scripts/check_compose_parity.py

.PHONY: logs-dev
logs-dev: ## Tail dev compose logs (usage: make logs-dev ARGS="api")
	docker compose -f $(COMPOSE_DEV) logs -f $(ARGS)

.PHONY: export-bundle
export-bundle: ## Export source snapshot and docker images to a tar bundle
	bash scripts/export_bundle.sh $(ARGS)

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
	@echo "Prune complete. Run 'make up-dev' to start fresh (bind-mount fixtures auto-recreated)."

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

.PHONY: db-migrate-compose
db-migrate-compose: ## Run Alembic migrations inside Compose API container (dev mode)
	docker compose -f $(COMPOSE_DEV) run --rm api /bin/sh -lc 'cd /app/apps/api && /app/.venv/bin/alembic upgrade head'

.PHONY: down
down: ## Stop dev compose stack only
	@docker compose -f $(COMPOSE_DEV) down --remove-orphans 2>/dev/null || true

# ──────────────────────────────────────────────
# Canonical deployed release targets. Pre-release and prod use these exact
# commands and production manifests; only RELEASE_* environment inputs differ.
# ──────────────────────────────────────────────

.PHONY: require-release-config
require-release-config:
	@case "$(RELEASE_PROFILE)" in pre-release|prod) ;; *) echo "ERROR: RELEASE_PROFILE must be pre-release or prod" >&2; exit 1 ;; esac
	@test -f "$(RELEASE_STATEFUL_ENV)" || { echo "ERROR: missing $(RELEASE_STATEFUL_ENV)" >&2; exit 1; }
	@test -f "$(RELEASE_PLATFORM_ENV)" || { echo "ERROR: missing $(RELEASE_PLATFORM_ENV)" >&2; exit 1; }
	@test -f "$(RELEASE_OBSERVABILITY_ENV)" || { echo "ERROR: missing $(RELEASE_OBSERVABILITY_ENV)" >&2; exit 1; }

.PHONY: create-release-network
create-release-network: require-release-config ## Create the selected release network
	@docker network inspect $(RELEASE_NETWORK) >/dev/null 2>&1 || docker network create $(RELEASE_NETWORK)

.PHONY: check-release-config
check-release-config: require-release-config ## Render one deployed release from canonical manifests
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_STATEFUL_ENV) -p $(RELEASE_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) config --quiet
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_PLATFORM_ENV) -p $(RELEASE_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) --profile '*' config --quiet
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_PLATFORM_ENV) -p $(RELEASE_PROJECT)-ops -f $(COMPOSE_PROD_OPS) --profile ops config --quiet
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_OBSERVABILITY_ENV) -p $(RELEASE_PROJECT)-observability -f $(COMPOSE_PROD_OBSERVABILITY) --profile '*' config --quiet

.PHONY: up-release-stateful
up-release-stateful: create-release-network ## Start and wait for deployed stateful services
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_STATEFUL_ENV) -p $(RELEASE_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) up -d --wait --wait-timeout 300

.PHONY: prepare-release-platform
prepare-release-platform: create-release-network ## Prepare database, MinIO, and Prefect
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_PLATFORM_ENV) -p $(RELEASE_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) up -d --wait --wait-timeout 180 prefect-server
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_PLATFORM_ENV) -p $(RELEASE_PROJECT)-ops -f $(COMPOSE_PROD_OPS) --profile ops run --rm prepare-platform

.PHONY: up-release-platform
up-release-platform: create-release-network ## Start and wait for deployed application services
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_PLATFORM_ENV) -p $(RELEASE_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) $(RELEASE_PROFILES) up -d --wait --wait-timeout 300 $(ARGS)

.PHONY: up-release-observability
up-release-observability: create-release-network ## Start deployed observability services
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_OBSERVABILITY_ENV) -p $(RELEASE_PROJECT)-observability -f $(COMPOSE_PROD_OBSERVABILITY) $(RELEASE_PROFILES) up -d

.PHONY: up-release
up-release: require-release-config ## Start a canonical pre-release or production deployment
	$(MAKE) check-release-config
	$(MAKE) up-release-stateful
	$(MAKE) prepare-release-platform
	$(MAKE) up-release-platform
	$(MAKE) up-release-observability

.PHONY: ps-release
ps-release: require-release-config ## Show all projects for the selected release
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_STATEFUL_ENV) -p $(RELEASE_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) ps
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_PLATFORM_ENV) -p $(RELEASE_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) $(RELEASE_PROFILES) ps
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_OBSERVABILITY_ENV) -p $(RELEASE_PROJECT)-observability -f $(COMPOSE_PROD_OBSERVABILITY) $(RELEASE_PROFILES) ps

.PHONY: logs-release
logs-release: require-release-config ## Tail selected release platform logs (ARGS="api")
	$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_PLATFORM_ENV) -p $(RELEASE_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) $(RELEASE_PROFILES) logs -f $(ARGS)

.PHONY: down-release
down-release: require-release-config ## Stop all selected release projects without deleting data
	@$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_OBSERVABILITY_ENV) -p $(RELEASE_PROJECT)-observability -f $(COMPOSE_PROD_OBSERVABILITY) $(RELEASE_PROFILES) down --remove-orphans
	@$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_PLATFORM_ENV) -p $(RELEASE_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) $(RELEASE_PROFILES) down --remove-orphans
	@$(RELEASE_RUNTIME_ENV) docker compose --env-file $(RELEASE_STATEFUL_ENV) -p $(RELEASE_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) down --remove-orphans

PRE_RELEASE_DEPLOY_ARGS := RELEASE_PROFILE=pre-release RELEASE_NETWORK=$(PRE_RELEASE_NETWORK) RELEASE_PROJECT=$(PRE_RELEASE_PROJECT) RELEASE_STATEFUL_ENV=$(PRE_RELEASE_STATEFUL_ENV) RELEASE_PLATFORM_ENV=$(PRE_RELEASE_PLATFORM_ENV) RELEASE_OBSERVABILITY_ENV=$(PRE_RELEASE_OBSERVABILITY_ENV)
PROD_RELEASE_ARGS := RELEASE_PROFILE=prod RELEASE_NETWORK=$(PROD_NETWORK) RELEASE_PROJECT=finetune RELEASE_STATEFUL_ENV=$(PROD_STATEFUL_ENV) RELEASE_PLATFORM_ENV=$(PROD_PLATFORM_ENV) RELEASE_OBSERVABILITY_ENV=$(PROD_OBSERVABILITY_ENV)

.PHONY: check-pre-release-config
check-pre-release-config: ## Render deployed pre-release using production manifests
	$(MAKE) check-release-config $(PRE_RELEASE_DEPLOY_ARGS) RELEASE_PROFILES="$(PRE_RELEASE_PROFILES)"

.PHONY: up-pre-release
up-pre-release: ## Deploy pre-release from the same immutable images/manifests as prod
	$(MAKE) up-release $(PRE_RELEASE_DEPLOY_ARGS) RELEASE_PROFILES="$(PRE_RELEASE_PROFILES)" ARGS="$(ARGS)"

.PHONY: ps-pre-release
ps-pre-release:
	$(MAKE) ps-release $(PRE_RELEASE_DEPLOY_ARGS) RELEASE_PROFILES="$(PRE_RELEASE_PROFILES)"

.PHONY: logs-pre-release
logs-pre-release:
	$(MAKE) logs-release $(PRE_RELEASE_DEPLOY_ARGS) RELEASE_PROFILES="$(PRE_RELEASE_PROFILES)" ARGS="$(ARGS)"

.PHONY: down-pre-release
down-pre-release:
	$(MAKE) down-release $(PRE_RELEASE_DEPLOY_ARGS) RELEASE_PROFILES="$(PRE_RELEASE_PROFILES)"

.PHONY: create-prod-network
create-prod-network:
	$(MAKE) create-release-network $(PROD_RELEASE_ARGS)

.PHONY: up-prod-stateful
up-prod-stateful:
	$(MAKE) up-release-stateful $(PROD_RELEASE_ARGS)

.PHONY: prepare-platform-prod
prepare-platform-prod:
	$(MAKE) prepare-release-platform $(PROD_RELEASE_ARGS)

.PHONY: up-prod-platform
up-prod-platform:
	$(MAKE) up-release-platform $(PROD_RELEASE_ARGS) RELEASE_PROFILES="$(PROFILES)" ARGS="$(ARGS)"

.PHONY: up-prod-observability
up-prod-observability:
	$(MAKE) up-release-observability $(PROD_RELEASE_ARGS) RELEASE_PROFILES="$(PROFILES)"

.PHONY: up-prod-all
up-prod-all: ## Deploy prod through the canonical release workflow
	$(MAKE) up-release $(PROD_RELEASE_ARGS) RELEASE_PROFILES="$(PROFILES)" ARGS="$(ARGS)"

.PHONY: ps-prod
ps-prod:
	$(MAKE) ps-release $(PROD_RELEASE_ARGS) RELEASE_PROFILES="$(PROFILES)"

.PHONY: logs-prod-platform
logs-prod-platform:
	$(MAKE) logs-release $(PROD_RELEASE_ARGS) RELEASE_PROFILES="$(PROFILES)" ARGS="$(ARGS)"

.PHONY: down-prod-all
down-prod-all:
	$(MAKE) down-release $(PROD_RELEASE_ARGS) RELEASE_PROFILES="$(PROFILES)"

# Local workstation acceptance. These overlays are intentionally excluded from
# deployed pre-release and production.
# ──────────────────────────────────────────────

.PHONY: init-pre-release-local-env
init-pre-release-local-env:
	@test ! -e $(PRE_RELEASE_LOCAL_ENV) || { echo "ERROR: $(PRE_RELEASE_LOCAL_ENV) already exists"; exit 1; }
	cp infra/compose/pre-release/env.example $(PRE_RELEASE_LOCAL_ENV)
	@echo "Created $(PRE_RELEASE_LOCAL_ENV) for loopback-only local acceptance."

.PHONY: require-pre-release-local-env
require-pre-release-local-env:
	@test -f $(PRE_RELEASE_LOCAL_ENV) || { echo "ERROR: missing $(PRE_RELEASE_LOCAL_ENV); run 'make init-pre-release-local-env'"; exit 1; }

.PHONY: create-pre-release-local-network
create-pre-release-local-network:
	@docker network inspect $(PRE_RELEASE_LOCAL_NETWORK) >/dev/null 2>&1 || docker network create $(PRE_RELEASE_LOCAL_NETWORK)

.PHONY: check-pre-release-local-config
check-pre-release-local-config: require-pre-release-local-env
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-ops -f $(COMPOSE_PROD_OPS) --profile ops config --quiet

.PHONY: build-pre-release-local
build-pre-release-local: require-pre-release-local-env
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) build $(ARGS)

.PHONY: up-pre-release-local
up-pre-release-local: require-pre-release-local-env create-pre-release-local-network ## Build and start loopback-only local acceptance
	$(MAKE) check-pre-release-local-config
	$(MAKE) build-pre-release-local
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) up -d --wait --wait-timeout 180
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) up -d --no-build --wait --wait-timeout 180 prefect-server
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-ops -f $(COMPOSE_PROD_OPS) --profile ops run --rm prepare-platform
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) up -d --no-build --wait --wait-timeout 300 $(ARGS)
	$(MAKE) verify-pre-release-local

.PHONY: verify-pre-release-local
verify-pre-release-local:
	curl --fail --show-error --silent http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_WEB_PORT)/ >/dev/null
	curl --fail --show-error --silent http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_API_PORT)/ready >/dev/null
	curl --fail --show-error --silent http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_PREFECT_PORT)/api/health >/dev/null
	curl --fail --show-error --silent http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_LABEL_STUDIO_PORT)/health >/dev/null
	curl --fail --show-error --silent http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_MINIO_PORT)/minio/health/live >/dev/null
	curl --fail --show-error --silent http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_IMAGE_PARSER_HTTP_PORT)/health >/dev/null
	@echo "Local pre-release is healthy: http://$(PRE_RELEASE_LOCAL_BIND_HOST):$(PRE_RELEASE_LOCAL_WEB_PORT)"

.PHONY: ps-pre-release-local
ps-pre-release-local: require-pre-release-local-env
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) ps
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) ps

.PHONY: logs-pre-release-local
logs-pre-release-local: require-pre-release-local-env
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) logs -f $(ARGS)

.PHONY: down-pre-release-local
down-pre-release-local: require-pre-release-local-env
	@$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_PROD_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) down --remove-orphans
	@$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_PROD_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) down --remove-orphans

.PHONY: save-images
save-images: ## Save all compose Docker images as .tar archives
	bash scripts/save-compose-images.sh $(ARGS)

.PHONY: image-parser-export
image-parser-export: ## Build and export image-parser as offline loadable tar.gz
	@echo "Building image-parser ..."
	docker build --platform linux/amd64 -t image-parser:local -f services/image-parser/Dockerfile .
	@mkdir -p dist
	@echo "Saving image-parser:local -> dist/image-parser.tar.gz"
	docker save image-parser:local | gzip > dist/image-parser.tar.gz
	@echo "Done: dist/image-parser.tar.gz ($(shell du -h dist/image-parser.tar.gz | cut -f1))"

.PHONY: k8s-prepare
k8s-prepare: ## Run the Kubernetes platform preparation Job and wait for it
	-kubectl delete job finetune-platform-prepare -n finetune --ignore-not-found
	kubectl create -f infra/k8s/platform-prepare-job.yaml
	kubectl wait --for=condition=complete job/finetune-platform-prepare -n finetune --timeout=10m

.PHONY: k8s-apply
k8s-apply: ## Apply dependencies, prepare the platform, then apply API/runtime workloads
	kubectl apply -f infra/k8s/namespace.yaml -f infra/k8s/rbac.yaml -f infra/k8s/configmap.yaml
	kubectl apply -f infra/k8s/postgres.yaml -f infra/k8s/minio.yaml -f infra/k8s/redis.yaml -f infra/k8s/prefect-server.yaml -f infra/k8s/label-studio.yaml
	kubectl rollout status deployment/postgres -n finetune --timeout=10m
	kubectl rollout status deployment/minio -n finetune --timeout=10m
	kubectl rollout status deployment/redis -n finetune --timeout=10m
	kubectl rollout status deployment/prefect-server -n finetune --timeout=10m
	kubectl rollout status deployment/label-studio -n finetune --timeout=10m
	$(MAKE) k8s-prepare
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
	@printf '  \033[36m%-16s\033[0m %s\n' "ARGS" "Extra args passed to test/seed/logs"
	@printf '  \033[36m%-16s\033[0m %s\n' "MSG" "Alembic revision message"
	@printf '  \033[36m%-16s\033[0m %s\n' "PROD_NETWORK" "Shared Docker network for production split stack (default: finetune-prod)"
	@printf '  \033[36m%-16s\033[0m %s\n' "PROD_STATEFUL_ENV" "Path to stateful .env file (default: /srv/finetune/stateful/.env)"
	@printf '  \033[36m%-16s\033[0m %s\n' "PROD_PLATFORM_ENV" "Path to platform .env file (default: /srv/finetune/platform/.env)"
	@printf '  \033[36m%-16s\033[0m %s\n' "PROD_OBSERVABILITY_ENV" "Path to observability .env file (default: /srv/finetune/observability/.env)"
	@printf '  \033[36m%-16s\033[0m %s\n' "PRE_RELEASE_STATEFUL_ENV" "Deployed pre-release stateful env file"
	@printf '  \033[36m%-16s\033[0m %s\n' "PRE_RELEASE_PLATFORM_ENV" "Deployed pre-release platform env file"
	@printf '  \033[36m%-16s\033[0m %s\n' "PRE_RELEASE_OBSERVABILITY_ENV" "Deployed pre-release observability env file"
	@printf '  \033[36m%-16s\033[0m %s\n' "PRE_RELEASE_PROFILES" "Optional deployed pre-release Compose profiles"
	@printf '  \033[36m%-16s\033[0m %s\n' "PRE_RELEASE_LOCAL_PROFILES" "Optional local acceptance Compose profiles"
	@echo
