# OpenAPI, SSE, protobuf, and Graphify generation targets.

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
	pnpm dlx json-schema-to-typescript@15.0.4 openapi/sse-events.schema.json --output $(WEB_DIR)/src/generated/sse-types.ts

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

.PHONY: graphify-list
graphify-list: ## List bounded Graphify contexts and source counts (ARGS="--files")
	python3 scripts/graphify_federation.py list $(ARGS)

.PHONY: graphify-check
graphify-check: ## Validate Graphify context boundaries, overlays, and pinned tool version
	python3 scripts/graphify_federation.py check $(ARGS)

.PHONY: graphify-build
graphify-build: ## Rebuild Graphify contexts (ARGS="--context sc-domain")
	python3 scripts/graphify_federation.py build --max-workers $(GRAPHIFY_MAX_WORKERS) $(ARGS)

.PHONY: graphify-query
graphify-query: ## Query one graph (CONTEXT=, QUESTION= are required)
	@test -n "$(CONTEXT)" || (echo "CONTEXT is required" >&2 && exit 2)
	@test -n "$(QUESTION)" || (echo "QUESTION is required" >&2 && exit 2)
	python3 scripts/graphify_federation.py query --context "$(CONTEXT)" $(ARGS) "$(QUESTION)"
