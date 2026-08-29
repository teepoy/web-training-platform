# Local Compose, image, export, and Kubernetes targets.

.PHONY: build-image-parser-vendor
build-image-parser-vendor: ## Build amd64 vendor/tooling image for image-parser offline builds
	docker build --platform linux/amd64 -f services/image-parser/Dockerfile.vendor -t image-parser-vendor:local .

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
check-config: ## Render dev, pre-release, and prod configurations
	docker compose -f $(COMPOSE_DEV) config --quiet
	docker compose --env-file infra/compose/production/env-stateful.example -f $(COMPOSE_RELEASE_STATEFUL) config --quiet
	APP_CONFIG_PROFILE=pre-release docker compose --env-file infra/compose/production/env-platform.example -f $(COMPOSE_RELEASE_PLATFORM) config --quiet
	APP_CONFIG_PROFILE=prod docker compose --env-file infra/compose/production/env-platform.example -f $(COMPOSE_RELEASE_PLATFORM) config --quiet
	APP_CONFIG_PROFILE=prod docker compose --env-file infra/compose/production/env-platform.example -f $(COMPOSE_RELEASE_OPS) --profile ops config --quiet
	docker compose --env-file infra/compose/production/env-observability.example -f $(COMPOSE_RELEASE_OBSERVABILITY) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file infra/compose/pre-release/env.example -p $(PRE_RELEASE_LOCAL_PROJECT)-stateful -f $(COMPOSE_RELEASE_STATEFUL) -f $(COMPOSE_PRE_RELEASE_STATEFUL) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file infra/compose/pre-release/env.example -p $(PRE_RELEASE_LOCAL_PROJECT)-platform -f $(COMPOSE_RELEASE_PLATFORM) -f $(COMPOSE_PRE_RELEASE_BUILD) -f $(COMPOSE_PRE_RELEASE_PLATFORM) $(PRE_RELEASE_LOCAL_PROFILES) config --quiet
	$(PRE_RELEASE_LOCAL_RUNTIME_ENV) docker compose --env-file infra/compose/pre-release/env.example -p $(PRE_RELEASE_LOCAL_PROJECT)-ops -f $(COMPOSE_RELEASE_OPS) --profile ops config --quiet
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
		infra/compose/init-scripts/create-prefect-db.sql \
		infra/compose/init-scripts/03-create-sc-simulator.sql; \
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
