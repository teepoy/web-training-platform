.DEFAULT_GOAL := help
SHELL := /bin/bash

# Repository layout
# Internal paths shared by target modules; callers normally do not override them.
API_DIR      := apps/api
WEB_DIR      := apps/web
COMPOSE      := infra/compose/docker-compose.yaml
COMPOSE_DEV  := infra/compose/docker-compose.yaml -f infra/compose/docker-compose.dev.yaml
DATA_DIR     := infra/compose/data
OPENAPI_SPEC := openapi/openapi.yaml
PROTO_DIR    := protos
SC_PROTO     := $(PROTO_DIR)/sc/v1/sample.proto

# Development endpoints and host tooling
# Override these when host services or helper binaries use non-default locations.
API_PORT                         ?= 8000
API_URL                          ?= http://localhost:$(API_PORT)
WEB_PORT                         ?= 5173
WEB_URL                          ?= http://localhost:$(WEB_PORT)
IMAGE_PARSER_GRPC_ADDR_HOST      ?= 127.0.0.1:9092
ARTIFACTS_DIR                    ?= $(CURDIR)/artifacts
HOST_BIN_DIR                     := $(ARTIFACTS_DIR)/bin
MINIO_ENDPOINT_HOST              ?= localhost:9000
UV_RUN_INSTALLED                 := uv run --no-sync --offline
LITELLM_LOCAL_MODEL_COST_MAP="True"

# Host API environment
# Keeps host-run API, worker, seed, and benchmark targets aligned with dev Compose.
DEV_API_HOST_ENV := \
	APP_CONFIG_PROFILE=dev \
	FRONTEND_URL=$(WEB_URL) \
	JWT_SECRET_KEY=local-development-jwt-secret-not-for-shared-host \
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
	REDIS_HOST=localhost \
	SC_UPSTREAM_ADDR=127.0.0.1:9091 \
	SC_UPSTREAM_FLIGHT_ADDR=grpc://127.0.0.1:9093 \
	UPSTREAM_MOCK_URL=http://127.0.0.1:8094 \
	UPSTREAM_MOCK_TOKEN=local-development-upstream-mock-token \
	UPSTREAM_MOCK_TIMEOUT_SECONDS=300 \
	IMAGE_PARSER_GRPC_ADDR=$(IMAGE_PARSER_GRPC_ADDR_HOST) \
	SC_DATA_PROVIDER_CACHE_DIR=/tmp/sc-data-provider \
	SC_DATA_PROVIDER_CACHE_NAMESPACE=sc-data-provider

# Development seed data
# Controls the repeatable SC inspection and showcase datasets created by seed targets.
SC_WAFER_MOCK_DEFECTS            ?= 2500
SC_WAFER_MOCK_INSPECTION_TIME    ?= 2026-08-01T04:00:00+08:00
DEV_SEED_CLASSIFICATION_SAMPLES  ?= 180
DEV_SEED_REVIEW_SAMPLES          ?= 96
DEV_SEED_SC_ANNOTATIONS          ?= 96

# Tests and benchmarks
# Sets timeout diagnostics and acceptance thresholds for test and SC benchmark targets.
TEST_TIMEOUT                ?= 300
PYTEST_FAULTHANDLER_TIMEOUT ?= 120
SC_RUNTIME_BENCHMARK_SOURCE_DATASET_NAME ?= Dev SC Inspection - Sparse
SC_RUNTIME_BENCHMARK_SAMPLES             ?= 300000
SC_RUNTIME_BENCHMARK_MIN_TRAIN_SPS       ?=
SC_RUNTIME_BENCHMARK_MIN_PREDICT_SPS     ?= 3000

# Schema generation and Graphify
# Pins repository-managed generators and controls Graphify build parallelism.
GRAPHIFY_MAX_WORKERS          ?= 1
BUF_VERSION                   ?= 1.70.0
PROTOC_GEN_GO_VERSION         ?= v1.36.11
PROTOC_GEN_GO_GRPC_VERSION    ?= v1.6.0
# Locked module sums are checked after building with the unavailable public checksum DB disabled.
PROTOC_GEN_GO_MODULE_SUM      := h1:fV6ZwhNocDyBLK0dj+fg8ektcVegBBuEolpbTQyBNVE=
PROTOC_GEN_GO_GRPC_MODULE_SUM := h1:6Al3kEFFP9VJhRz3DID6quisgPnTeZVr4lep9kkxdPA=
PROTOC_GEN_GO_GRPC_PROTO_SUM  := h1:AYd7cD/uASjIL6Q9LiTjz8JLcrh/88q5UObnmY3aOOE=
PROTO_TOOLS_HOST_OS           ?= $(shell uname -s | tr '[:upper:]' '[:lower:]')
PROTO_TOOLS_HOST_ARCH         ?= $(shell uname -m | sed -e 's/^x86_64$$/amd64/' -e 's/^aarch64$$/arm64/')
PROTO_TOOLS_TARGETS           ?= darwin/amd64 darwin/arm64 linux/amd64 linux/arm64
PROTO_TOOLS_GO_PROXY_URL      ?= https://proxy.golang.org
PROTO_TOOLS_DIR               ?= $(ARTIFACTS_DIR)/protobuf-tools
PROTO_GO_TOOLS_BIN            := $(PROTO_TOOLS_DIR)/$(PROTO_TOOLS_HOST_OS)/$(PROTO_TOOLS_HOST_ARCH)/bin
PROTO_BUF_BIN                 := $(PROTO_GO_TOOLS_BIN)/buf
PROTO_ES_BIN                  := $(CURDIR)/$(WEB_DIR)/node_modules/.bin/protoc-gen-es
PROTO_PRETTIER_BIN            := $(CURDIR)/$(WEB_DIR)/node_modules/.bin/prettier
PROTO_MYPY_BIN                := $(CURDIR)/.venv/bin/protoc-gen-mypy
PROTO_PYTHON_BIN              := $(CURDIR)/.venv/bin/python

# Target modules
include make/build.mk
include make/test.mk
include make/lint.mk
include make/docker.mk
include make/generate.mk
include make/release.mk

.PHONY: help
help: ## Show this help message
	@printf '\nUsage: make \033[36m<target>\033[0m [VAR=value]\n\n'
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nVariables (override with VAR=value):\n'
	@printf '\n  Common target arguments\n'
	@printf '    \033[36m%-43s\033[0m %s\n' "ARGS" "Extra arguments forwarded by supported test, seed, build, and log targets"
	@printf '    \033[36m%-43s\033[0m %s\n' "MSG" "Alembic revision message used by db-revision"
	@printf '    \033[36m%-43s\033[0m %s\n' "EMAIL / PASSWORD / NAME" "Super-admin credentials used by create-superadmin"
	@printf '    \033[36m%-43s\033[0m %s\n' "CONTEXT / QUESTION" "Graph context and query text used by graphify-query"
	@printf '\n  Development endpoints and host helpers\n'
	@printf '    \033[36m%-43s\033[0m %s\n' "API_PORT" "Host API port (default: 8000)"
	@printf '    \033[36m%-43s\033[0m %s\n' "API_URL" "API base URL used by seed, smoke, and live E2E targets (default: http://localhost:API_PORT)"
	@printf '    \033[36m%-43s\033[0m %s\n' "WEB_PORT" "Frontend development port convention (default: 5173)"
	@printf '    \033[36m%-43s\033[0m %s\n' "WEB_URL" "Frontend base URL used by live E2E targets (default: http://localhost:5173)"
	@printf '    \033[36m%-43s\033[0m %s\n' "IMAGE_PARSER_GRPC_ADDR_HOST" "Host image-parser gRPC address injected into host API and workers"
	@printf '    \033[36m%-43s\033[0m %s\n' "ARTIFACTS_DIR" "Repository-local directory for generated host build artifacts"
	@printf '    \033[36m%-43s\033[0m %s\n' "MINIO_ENDPOINT_HOST" "Host MinIO endpoint used by host API and benchmark targets"
	@printf '\n  Development seed data\n'
	@printf '    \033[36m%-43s\033[0m %s\n' "SC_WAFER_MOCK_DEFECTS" "Number of defects in the repeatable mock SC inspection (default: 2500)"
	@printf '    \033[36m%-43s\033[0m %s\n' "SC_WAFER_MOCK_INSPECTION_TIME" "Stable inspection timestamp used to make seed runs reusable"
	@printf '    \033[36m%-43s\033[0m %s\n' "DEV_SEED_CLASSIFICATION_SAMPLES" "Classification showcase sample count (default: 180)"
	@printf '    \033[36m%-43s\033[0m %s\n' "DEV_SEED_REVIEW_SAMPLES" "Review showcase sample count (default: 96)"
	@printf '    \033[36m%-43s\033[0m %s\n' "DEV_SEED_SC_ANNOTATIONS" "SC annotation count created by seed-dev (default: 96)"
	@printf '\n  Tests and SC runtime benchmarks\n'
	@printf '    \033[36m%-43s\033[0m %s\n' "TEST_TIMEOUT" "Hard timeout for API test execution in seconds (default: 300)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PYTEST_FAULTHANDLER_TIMEOUT" "Per-test stack-dump timeout in seconds (default: 120)"
	@printf '    \033[36m%-43s\033[0m %s\n' "SC_RUNTIME_BENCHMARK_SOURCE_DATASET_NAME" "Dataset consumed by the SC runtime data-path benchmark"
	@printf '    \033[36m%-43s\033[0m %s\n' "SC_RUNTIME_BENCHMARK_SAMPLES" "Sample count processed by the SC runtime benchmark (default: 300000)"
	@printf '    \033[36m%-43s\033[0m %s\n' "SC_RUNTIME_BENCHMARK_MIN_TRAIN_SPS" "Optional minimum accepted training throughput"
	@printf '    \033[36m%-43s\033[0m %s\n' "SC_RUNTIME_BENCHMARK_MIN_PREDICT_SPS" "Minimum accepted prediction throughput (default: 3000)"
	@printf '\n  Schema generation and Graphify\n'
	@printf '    \033[36m%-43s\033[0m %s\n' "GRAPHIFY_MAX_WORKERS" "Maximum parallel Graphify context builds (default: 1)"
	@printf '    \033[36m%-43s\033[0m %s\n' "BUF_VERSION" "Pinned Buf CLI version packaged for offline protobuf generation"
	@printf '    \033[36m%-43s\033[0m %s\n' "PROTOC_GEN_GO_VERSION" "Pinned protoc-gen-go version"
	@printf '    \033[36m%-43s\033[0m %s\n' "PROTOC_GEN_GO_GRPC_VERSION" "Pinned protoc-gen-go-grpc version"
	@printf '    \033[36m%-43s\033[0m %s\n' "PROTO_TOOLS_HOST_OS / PROTO_TOOLS_HOST_ARCH" "Host platform route used to select offline protobuf executables"
	@printf '    \033[36m%-43s\033[0m %s\n' "PROTO_TOOLS_TARGETS" "OS/architecture routes built by protobuf-tools-artifacts"
	@printf '    \033[36m%-43s\033[0m %s\n' "PROTO_TOOLS_GO_PROXY_URL" "Go module proxy URL used only while building the connected-host bundle"
	@printf '    \033[36m%-43s\033[0m %s\n' "PROTO_TOOLS_DIR" "Platform-routed protobuf executable artifacts directory"
	@printf '\n  Deployed pre-release defaults\n'
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_NETWORK" "External Docker network for deployed pre-release"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_PROJECT" "Compose project-name prefix for deployed pre-release"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_STATEFUL_ENV" "Deployed pre-release stateful-services environment file"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_PLATFORM_ENV" "Deployed pre-release platform environment file"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_IMAGE_ENV" "Optional image-digest environment file loaded after platform config"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_OBSERVABILITY_ENV" "Deployed pre-release observability environment file"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_PROFILES" "Optional Compose profile flags for deployed pre-release"
	@printf '\n  Production release defaults\n'
	@printf '    \033[36m%-43s\033[0m %s\n' "RELEASE_NETWORK" "External Docker network for prod releases"
	@printf '    \033[36m%-43s\033[0m %s\n' "RELEASE_PROJECT" "Compose project-name prefix for prod releases"
	@printf '    \033[36m%-43s\033[0m %s\n' "RELEASE_STATEFUL_ENV" "Prod release stateful-services environment file"
	@printf '    \033[36m%-43s\033[0m %s\n' "RELEASE_PLATFORM_ENV" "Prod release platform environment file"
	@printf '    \033[36m%-43s\033[0m %s\n' "RELEASE_IMAGE_ENV" "Optional image-digest environment file loaded after platform config"
	@printf '    \033[36m%-43s\033[0m %s\n' "RELEASE_OBSERVABILITY_ENV" "Prod release observability environment file"
	@printf '    \033[36m%-43s\033[0m %s\n' "RELEASE_PROFILES" "Optional Compose profile flags for prod releases"
	@printf '\n  Local pre-release acceptance\n'
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_ENV" "Local acceptance environment file"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_NETWORK" "Isolated Docker network for local acceptance"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_PROJECT" "Compose project-name prefix for local acceptance"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_TAG" "Image tag built for local acceptance (default: current Git description)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_IMAGE_PREFIX" "Image repository prefix for locally built release images"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_PROFILES" "Optional Compose profile flags for local acceptance"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_BIND_HOST" "Loopback bind host for local acceptance (default: 127.0.0.1)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_POSTGRES_PORT" "Host PostgreSQL port (default: 15432)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_MINIO_PORT" "Host MinIO API port (default: 19000)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_MINIO_CONSOLE_PORT" "Host MinIO console port (default: 19001)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_REDIS_PORT" "Host Redis port (default: 16379)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_LABEL_STUDIO_PORT" "Host Label Studio port (default: 18080)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_PREFECT_PORT" "Host Prefect port (default: 14200)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_API_PORT" "Host platform API port (default: 18000)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_SC_DATA_PROVIDER_PORT" "Host SC data-provider port (default: 18001)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_WEB_PORT" "Host frontend port (default: 15173)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_SC_GRPC_PORT" "Host SC upstream gRPC port (default: 19091)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_SC_FLIGHT_PORT" "Host SC Arrow Flight port (default: 19093)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_IMAGE_PARSER_HTTP_PORT" "Host image-parser HTTP port (default: 18090)"
	@printf '    \033[36m%-43s\033[0m %s\n' "PRE_RELEASE_LOCAL_IMAGE_PARSER_GRPC_PORT" "Host image-parser gRPC port (default: 19092)"
	@echo
