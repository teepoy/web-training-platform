# Pre-release, production release, and local acceptance targets.

# Deployed pre-release identity, environment files, and optional profiles.
PRE_RELEASE_NETWORK           ?= finetune-pre-release
PRE_RELEASE_PROJECT           ?= finetune-pre-release
PRE_RELEASE_STATEFUL_ENV      ?= /srv/finetune-pre-release/stateful/.env
PRE_RELEASE_PLATFORM_ENV      ?= /srv/finetune-pre-release/platform/.env
PRE_RELEASE_IMAGE_ENV         ?=
PRE_RELEASE_OBSERVABILITY_ENV ?= /srv/finetune-pre-release/observability/.env
PRE_RELEASE_PROFILES          ?=

# Production release identity, environment files, and optional profiles.
RELEASE_NETWORK           ?= finetune-prod
RELEASE_PROJECT           ?= finetune
RELEASE_STATEFUL_ENV      ?= /srv/finetune/stateful/.env
RELEASE_PLATFORM_ENV      ?= /srv/finetune/platform/.env
RELEASE_IMAGE_ENV         ?=
RELEASE_OBSERVABILITY_ENV ?= /srv/finetune/observability/.env
RELEASE_PROFILES          ?=

# Shared deployable split-stack manifests.
COMPOSE_RELEASE_STATEFUL      := infra/compose/production/compose.stateful.yaml
COMPOSE_RELEASE_PLATFORM      := infra/compose/production/compose.platform.yaml
COMPOSE_RELEASE_OPS           := infra/compose/production/compose.ops.yaml
COMPOSE_RELEASE_OBSERVABILITY := infra/compose/production/compose.observability.yaml

# Internal inputs used by the shared deployed-stack recipes.
DEPLOY_RUNTIME_ENV        = APP_CONFIG_PROFILE=$(DEPLOY_PROFILE) PLATFORM_NETWORK_NAME=$(DEPLOY_NETWORK)
DEPLOY_PLATFORM_ENV_FILES = --env-file $(DEPLOY_PLATFORM_ENV) $(if $(strip $(DEPLOY_IMAGE_ENV)),--env-file $(DEPLOY_IMAGE_ENV))
PRE_RELEASE_DEPLOY_ARGS   = DEPLOY_PROFILE=pre-release DEPLOY_NETWORK=$(PRE_RELEASE_NETWORK) DEPLOY_PROJECT=$(PRE_RELEASE_PROJECT) DEPLOY_STATEFUL_ENV=$(PRE_RELEASE_STATEFUL_ENV) DEPLOY_PLATFORM_ENV=$(PRE_RELEASE_PLATFORM_ENV) DEPLOY_IMAGE_ENV=$(PRE_RELEASE_IMAGE_ENV) DEPLOY_OBSERVABILITY_ENV=$(PRE_RELEASE_OBSERVABILITY_ENV)
RELEASE_DEPLOY_ARGS       = DEPLOY_PROFILE=prod DEPLOY_NETWORK=$(RELEASE_NETWORK) DEPLOY_PROJECT=$(RELEASE_PROJECT) DEPLOY_STATEFUL_ENV=$(RELEASE_STATEFUL_ENV) DEPLOY_PLATFORM_ENV=$(RELEASE_PLATFORM_ENV) DEPLOY_IMAGE_ENV=$(RELEASE_IMAGE_ENV) DEPLOY_OBSERVABILITY_ENV=$(RELEASE_OBSERVABILITY_ENV)

# Local pre-release identity and routing.
PRE_RELEASE_LOCAL_ENV          ?= infra/compose/pre-release/.env
PRE_RELEASE_LOCAL_NETWORK      ?= finetune-pre-release-local
PRE_RELEASE_LOCAL_PROJECT      ?= finetune-pre-release-local
PRE_RELEASE_LOCAL_TAG          ?= $(shell git describe --always --dirty 2>/dev/null)
PRE_RELEASE_LOCAL_IMAGE_PREFIX ?= web-training-platform
PRE_RELEASE_LOCAL_PROFILES     ?=
PRE_RELEASE_LOCAL_BIND_HOST    ?= 127.0.0.1

# Local pre-release host ports keep the acceptance stack separate from dev.
PRE_RELEASE_LOCAL_POSTGRES_PORT          ?= 15432
PRE_RELEASE_LOCAL_MINIO_PORT             ?= 19000
PRE_RELEASE_LOCAL_MINIO_CONSOLE_PORT     ?= 19001
PRE_RELEASE_LOCAL_REDIS_PORT             ?= 16379
PRE_RELEASE_LOCAL_LABEL_STUDIO_PORT      ?= 18080
PRE_RELEASE_LOCAL_PREFECT_PORT           ?= 14200
PRE_RELEASE_LOCAL_API_PORT               ?= 18000
PRE_RELEASE_LOCAL_SC_DATA_PROVIDER_PORT  ?= 18001
PRE_RELEASE_LOCAL_WEB_PORT               ?= 15173
PRE_RELEASE_LOCAL_SC_GRPC_PORT           ?= 19091
PRE_RELEASE_LOCAL_SC_FLIGHT_PORT         ?= 19093
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

# ──────────────────────────────────────────────
# Shared deployed stack recipes
# ──────────────────────────────────────────────

.PHONY: require-deploy-config
require-deploy-config:
	@case "$(DEPLOY_PROFILE)" in pre-release|prod) ;; *) echo "ERROR: DEPLOY_PROFILE must be pre-release or prod" >&2; exit 1 ;; esac
	@test -f "$(DEPLOY_STATEFUL_ENV)" || { echo "ERROR: missing $(DEPLOY_STATEFUL_ENV)" >&2; exit 1; }
	@test -f "$(DEPLOY_PLATFORM_ENV)" || { echo "ERROR: missing $(DEPLOY_PLATFORM_ENV)" >&2; exit 1; }
	@if [ -n "$(DEPLOY_IMAGE_ENV)" ] && [ ! -f "$(DEPLOY_IMAGE_ENV)" ]; then echo "ERROR: missing $(DEPLOY_IMAGE_ENV)" >&2; exit 1; fi
	@test -f "$(DEPLOY_OBSERVABILITY_ENV)" || { echo "ERROR: missing $(DEPLOY_OBSERVABILITY_ENV)" >&2; exit 1; }

.PHONY: create-deploy-network
create-deploy-network: require-deploy-config
	@docker network inspect $(DEPLOY_NETWORK) >/dev/null 2>&1 || docker network create $(DEPLOY_NETWORK)

.PHONY: check-deploy-config
check-deploy-config: require-deploy-config
	$(DEPLOY_RUNTIME_ENV) docker compose --env-file $(DEPLOY_STATEFUL_ENV) -p $(DEPLOY_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) config --quiet
	$(DEPLOY_RUNTIME_ENV) docker compose $(DEPLOY_PLATFORM_ENV_FILES) -p $(DEPLOY_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) --profile '*' config --quiet
	$(DEPLOY_RUNTIME_ENV) docker compose $(DEPLOY_PLATFORM_ENV_FILES) -p $(DEPLOY_PROJECT)-ops -f $(COMPOSE_RELEASE_OPS) --profile ops config --quiet
	$(DEPLOY_RUNTIME_ENV) docker compose --env-file $(DEPLOY_OBSERVABILITY_ENV) -p $(DEPLOY_PROJECT)-observability -f $(COMPOSE_RELEASE_OBSERVABILITY) --profile '*' config --quiet

.PHONY: up-deploy-stateful
up-deploy-stateful: create-deploy-network
	$(DEPLOY_RUNTIME_ENV) docker compose --env-file $(DEPLOY_STATEFUL_ENV) -p $(DEPLOY_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) up -d --wait --wait-timeout 300

.PHONY: prepare-deploy-platform
prepare-deploy-platform: create-deploy-network
	$(DEPLOY_RUNTIME_ENV) docker compose $(DEPLOY_PLATFORM_ENV_FILES) -p $(DEPLOY_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) up -d --wait --wait-timeout 180 prefect-server
	$(DEPLOY_RUNTIME_ENV) docker compose $(DEPLOY_PLATFORM_ENV_FILES) -p $(DEPLOY_PROJECT)-ops -f $(COMPOSE_RELEASE_OPS) --profile ops run --rm prepare-platform

.PHONY: up-deploy-platform
up-deploy-platform: create-deploy-network
	$(DEPLOY_RUNTIME_ENV) docker compose $(DEPLOY_PLATFORM_ENV_FILES) -p $(DEPLOY_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) $(DEPLOY_PROFILES) up -d --wait --wait-timeout 300 $(ARGS)

.PHONY: up-deploy-observability
up-deploy-observability: create-deploy-network
	$(DEPLOY_RUNTIME_ENV) docker compose --env-file $(DEPLOY_OBSERVABILITY_ENV) -p $(DEPLOY_PROJECT)-observability -f $(COMPOSE_RELEASE_OBSERVABILITY) $(DEPLOY_PROFILES) up -d

.PHONY: up-deploy
up-deploy: require-deploy-config
	$(MAKE) check-deploy-config
	$(MAKE) up-deploy-stateful
	$(MAKE) prepare-deploy-platform
	$(MAKE) up-deploy-platform ARGS="$(ARGS)"
	$(MAKE) up-deploy-observability

.PHONY: ps-deploy
ps-deploy: require-deploy-config
	$(DEPLOY_RUNTIME_ENV) docker compose --env-file $(DEPLOY_STATEFUL_ENV) -p $(DEPLOY_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) ps
	$(DEPLOY_RUNTIME_ENV) docker compose $(DEPLOY_PLATFORM_ENV_FILES) -p $(DEPLOY_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) $(DEPLOY_PROFILES) ps
	$(DEPLOY_RUNTIME_ENV) docker compose --env-file $(DEPLOY_OBSERVABILITY_ENV) -p $(DEPLOY_PROJECT)-observability -f $(COMPOSE_RELEASE_OBSERVABILITY) $(DEPLOY_PROFILES) ps

.PHONY: logs-deploy
logs-deploy: require-deploy-config
	$(DEPLOY_RUNTIME_ENV) docker compose $(DEPLOY_PLATFORM_ENV_FILES) -p $(DEPLOY_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) $(DEPLOY_PROFILES) logs -f $(ARGS)

.PHONY: down-deploy
down-deploy: require-deploy-config
	@$(DEPLOY_RUNTIME_ENV) docker compose --env-file $(DEPLOY_OBSERVABILITY_ENV) -p $(DEPLOY_PROJECT)-observability -f $(COMPOSE_RELEASE_OBSERVABILITY) $(DEPLOY_PROFILES) down --remove-orphans
	@$(DEPLOY_RUNTIME_ENV) docker compose $(DEPLOY_PLATFORM_ENV_FILES) -p $(DEPLOY_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) $(DEPLOY_PROFILES) down --remove-orphans
	@$(DEPLOY_RUNTIME_ENV) docker compose --env-file $(DEPLOY_STATEFUL_ENV) -p $(DEPLOY_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) down --remove-orphans

# ──────────────────────────────────────────────
# Deployed pre-release and production release
# ──────────────────────────────────────────────

.PHONY: check-pre-release-config
check-pre-release-config: ## Render the deployed pre-release configuration
	$(MAKE) check-deploy-config $(PRE_RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(PRE_RELEASE_PROFILES)"

.PHONY: up-pre-release
up-pre-release: ## Deploy pre-release
	$(MAKE) up-deploy $(PRE_RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(PRE_RELEASE_PROFILES)" ARGS="$(ARGS)"

.PHONY: ps-pre-release
ps-pre-release: ## Show deployed pre-release services
	$(MAKE) ps-deploy $(PRE_RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(PRE_RELEASE_PROFILES)"

.PHONY: logs-pre-release
logs-pre-release: ## Tail deployed pre-release platform logs (ARGS="api")
	$(MAKE) logs-deploy $(PRE_RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(PRE_RELEASE_PROFILES)" ARGS="$(ARGS)"

.PHONY: down-pre-release
down-pre-release: ## Stop deployed pre-release services without deleting data
	$(MAKE) down-deploy $(PRE_RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(PRE_RELEASE_PROFILES)"

.PHONY: check-release-config
check-release-config: ## Render the production configuration used by releases
	$(MAKE) check-deploy-config $(RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(RELEASE_PROFILES)"

.PHONY: up-release
up-release: ## Deploy the release to prod
	$(MAKE) up-deploy $(RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(RELEASE_PROFILES)" ARGS="$(ARGS)"

.PHONY: ps-release
ps-release: ## Show prod release services
	$(MAKE) ps-deploy $(RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(RELEASE_PROFILES)"

.PHONY: logs-release
logs-release: ## Tail prod release platform logs (ARGS="api")
	$(MAKE) logs-deploy $(RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(RELEASE_PROFILES)" ARGS="$(ARGS)"

.PHONY: down-release
down-release: ## Stop prod release services without deleting data
	$(MAKE) down-deploy $(RELEASE_DEPLOY_ARGS) DEPLOY_PROFILES="$(RELEASE_PROFILES)"

# ──────────────────────────────────────────────
# Local pre-release acceptance
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
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-ops -f $(COMPOSE_RELEASE_OPS) --profile ops config --quiet

.PHONY: build-pre-release-local
build-pre-release-local: require-pre-release-local-env
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) build $(ARGS)

.PHONY: up-pre-release-local
up-pre-release-local: require-pre-release-local-env create-pre-release-local-network ## Build and start loopback-only pre-release acceptance
	$(MAKE) check-pre-release-local-config
	$(MAKE) build-pre-release-local
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) up -d --wait --wait-timeout 180
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) up -d --no-build --wait --wait-timeout 180 prefect-server
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-ops -f $(COMPOSE_RELEASE_OPS) --profile ops run --rm prepare-platform
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) up -d --no-build --wait --wait-timeout 300 $(ARGS)
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
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) ps
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) ps

.PHONY: logs-pre-release-local
logs-pre-release-local: require-pre-release-local-env
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) logs -f $(ARGS)

.PHONY: down-pre-release-local
down-pre-release-local: require-pre-release-local-env
	@$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) down --remove-orphans
	@$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file $(PRE_RELEASE_LOCAL_ENV) -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) down --remove-orphans
