# Test, benchmark, smoke, regression, and end-to-end targets.

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

.PHONY: test-seed-tools
test-seed-tools: ## Run repository seed-tool unit tests
	PYTHONPATH=devtools $(UV_RUN_INSTALLED) python -m pytest devtools/seedmaker/tests/test_sc_simulator.py
	PYTHONPATH=devtools $(UV_RUN_INSTALLED) --package sc-upstream python -m pytest devtools/seedmaker/tests/test_legacy_sc_sqlite.py

.PHONY: benchmark-sc-prediction
benchmark-sc-prediction: ## Require >3000 samples/s for bounded SC prediction preprocessing
	$(UV_RUN_INSTALLED) --package ml-library python libs/ml/benchmarks/sc_prediction_stream_throughput.py --minimum-samples-per-second 3000

.PHONY: benchmark-image-stream-receipt
benchmark-image-stream-receipt: ## Gate 300k warm-cache ZIP parsing through Python receipt at >=3000 samples/s
	cd services/image-parser && SC_IMAGE_STREAM_ACCEPTANCE=1 GOCACHE=/tmp/web-training-platform-go-cache go test ./internal/service -run '^TestPredictionImageStreamWarmCache300KToPython$$' -count=1 -v

.PHONY: benchmark-sc-runtime-data-paths
benchmark-sc-runtime-data-paths: ## Benchmark real SC train/predict data paths with fake GPU kernels
	$(DEV_API_HOST_ENV) \
		SC_PATCH_S3_ENDPOINT=$(MINIO_ENDPOINT_HOST) \
		SC_PATCH_S3_ACCESS_KEY=minioadmin \
		SC_PATCH_S3_SECRET_KEY=minioadmin \
		SC_PATCH_S3_BUCKET=$(SC_PATCH_ZIP_BUCKET) \
		LITELLM_LOCAL_MODEL_COST_MAP=True \
		$(UV_RUN_INSTALLED) --package finetune-api python -m devtools.benchmarks.sc_runtime_data_paths \
			--source-dataset-name '$(SC_RUNTIME_BENCHMARK_SOURCE_DATASET_NAME)' \
			--samples $(SC_RUNTIME_BENCHMARK_SAMPLES) $(if $(SC_RUNTIME_BENCHMARK_MIN_TRAIN_SPS),--minimum-training-samples-per-second $(SC_RUNTIME_BENCHMARK_MIN_TRAIN_SPS),) $(if $(SC_RUNTIME_BENCHMARK_MIN_PREDICT_SPS),--minimum-prediction-samples-per-second $(SC_RUNTIME_BENCHMARK_MIN_PREDICT_SPS),)

.PHONY: benchmark-sc-prediction-export
benchmark-sc-prediction-export: ## Benchmark 300k-row SC export generation plus MinIO upload (ARGS may override format/version)
	cd $(API_DIR) && $(DEV_API_HOST_ENV) $(UV_RUN_INSTALLED) python scripts/benchmark_sc_prediction_export.py --samples 300000 $(ARGS)

.PHONY: test-release-contract
test-release-contract: ## Validate immutable release image environment generation
	python3 -m unittest discover -s scripts/tests -p 'test_write_release_image_env.py'

.PHONY: test-e2e
test-e2e: ## Run frontend mock e2e tests (Playwright, no live stack required)
	cd $(WEB_DIR) && pnpm test:e2e

.PHONY: full-test
full-test: ## Run all tests and checks (API + web unit + e2e + build + lint)
	$(MAKE) test-api && \
	$(MAKE) test-web && \
	$(MAKE) test-e2e && \
	$(MAKE) build-web && \
	ruff check apps/api && \
	$(UV_RUN_INSTALLED) --directory apps/api pyright .

.PHONY: check-openapi-sync
check-openapi-sync: ## Check FastAPI route schema against openapi/openapi.yaml
	cd $(API_DIR) && APP_CONFIG_PROFILE=test $(UV_RUN_INSTALLED) python ../../scripts/check_openapi_sync.py

.PHONY: test-graphify-federation
test-graphify-federation: ## Test the repeatable Graphify federation tooling
	python3 -m unittest discover -s scripts/tests -p 'test_graphify_federation.py'

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
