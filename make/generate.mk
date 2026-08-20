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
	cd $(WEB_DIR) && pnpm exec orval --config orval.config.ts
	"$(PROTO_PYTHON_BIN)" scripts/normalize_generated_text.py $(WEB_DIR)/src/generated/orval --suffix .ts

.PHONY: generate-sse-types
generate-sse-types: ## Generate SSE JSON schema and frontend TypeScript types
	mkdir -p openapi $(WEB_DIR)/src/generated
	uv run --directory $(API_DIR) python ../../scripts/export_sse_schema.py
	pnpm dlx json-schema-to-typescript@15.0.4 openapi/sse-events.schema.json --output $(WEB_DIR)/src/generated/sse-types.ts

.PHONY: generate-openapi-artifacts
generate-openapi-artifacts: generate-openapi-spec generate-api-models generate-orval generate-sse-types ## Generate backend/frontend transport artifacts

.PHONY: generate-protos
generate-protos: generate-protos-check-deps ## Generate protobuf stubs using only preinstalled tools (network-free)
	mkdir -p libs/protos/src/proto_stubs/sc/v1 $(WEB_DIR)/src/features/sc/generated/proto
	cd $(PROTO_DIR) && PATH="$(PROTO_GO_TOOLS_BIN):$$PATH" "$(PROTO_BUF_BIN)" generate . --template buf.gen.yaml
	"$(PROTO_PRETTIER_BIN)" --write $(WEB_DIR)/src/features/sc/generated/proto
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

.PHONY: generate-protos-deps
generate-protos-deps: ## Install locked proto generators (requires network; not part of generation)
	uv sync --frozen --inexact
	pnpm install --frozen-lockfile
	$(MAKE) protobuf-tools-artifacts PROTO_TOOLS_TARGETS="$(PROTO_TOOLS_HOST_OS)/$(PROTO_TOOLS_HOST_ARCH)"
	$(MAKE) generate-protos-check-deps

.PHONY: generate-protos-check-deps
generate-protos-check-deps: ## Check protobuf generators without installing or accessing the network
	@test -x "$(PROTO_BUF_BIN)"
	@test -x "$(PROTO_ES_BIN)"
	@test -x "$(PROTO_PRETTIER_BIN)"
	@test -x "$(PROTO_MYPY_BIN)"
	@test -x "$(PROTO_PYTHON_BIN)"
	@test -x "$(PROTO_GO_TOOLS_BIN)/protoc-gen-go"
	@test -x "$(PROTO_GO_TOOLS_BIN)/protoc-gen-go-grpc"
	@echo "Proto generators ready: buf=$$("$(PROTO_BUF_BIN)" --version), protoc-gen-es=$$("$(PROTO_ES_BIN)" --version), mypy-protobuf=$$("$(PROTO_MYPY_BIN)" --version), grpcio-tools=$$("$(PROTO_PYTHON_BIN)" -m grpc_tools.protoc --version), protoc-gen-go=$$("$(PROTO_GO_TOOLS_BIN)/protoc-gen-go" --version), protoc-gen-go-grpc=$$("$(PROTO_GO_TOOLS_BIN)/protoc-gen-go-grpc" --version)"

.PHONY: protobuf-tools-artifacts
protobuf-tools-artifacts: ## Package Buf and Go protobuf generators by OS/architecture (requires network)
	@set -euo pipefail; \
	tmp_dir=$$(mktemp -d); \
	trap 'rm -rf "$$tmp_dir"' EXIT; \
	go_path="$$tmp_dir/go"; \
	mkdir -p "$$go_path/pkg/mod"; \
	download_module() { \
		module_url="$$1"; module_archive="$$2"; module_sum="$$3"; \
		curl --fail --location --silent --show-error "$$module_url" --output "$$module_archive"; \
		env GO111MODULE=off GOTOOLCHAIN=local GOWORK=off GOPROXY=off go run scripts/protobuf-tools/hash_module_zip.go "$$module_archive" "$$module_sum"; \
		unzip -q "$$module_archive" -d "$$go_path/pkg/mod"; \
	}; \
	download_module "$(PROTO_TOOLS_GO_PROXY_URL)/google.golang.org/protobuf/@v/$(PROTOC_GEN_GO_VERSION).zip" \
		"$$tmp_dir/protobuf-$(PROTOC_GEN_GO_VERSION).zip" '$(PROTOC_GEN_GO_MODULE_SUM)'; \
	download_module "$(PROTO_TOOLS_GO_PROXY_URL)/google.golang.org/protobuf/@v/v1.36.10.zip" \
		"$$tmp_dir/protobuf-v1.36.10.zip" '$(PROTOC_GEN_GO_GRPC_PROTO_SUM)'; \
	download_module "$(PROTO_TOOLS_GO_PROXY_URL)/google.golang.org/grpc/cmd/protoc-gen-go-grpc/@v/$(PROTOC_GEN_GO_GRPC_VERSION).zip" \
		"$$tmp_dir/protoc-gen-go-grpc-$(PROTOC_GEN_GO_GRPC_VERSION).zip" '$(PROTOC_GEN_GO_GRPC_MODULE_SUM)'; \
	protoc_gen_go_source="$$go_path/pkg/mod/google.golang.org/protobuf@$(PROTOC_GEN_GO_VERSION)/cmd/protoc-gen-go"; \
	protoc_gen_go_grpc_source="$$go_path/pkg/mod/google.golang.org/grpc/cmd/protoc-gen-go-grpc@$(PROTOC_GEN_GO_GRPC_VERSION)"; \
	grpc_modfile="$$tmp_dir/protoc-gen-go-grpc.mod"; \
	cp scripts/protobuf-tools/protoc-gen-go-grpc.mod "$$grpc_modfile"; \
	cp scripts/protobuf-tools/protoc-gen-go-grpc.sum "$${grpc_modfile%.mod}.sum"; \
	(cd "$$protoc_gen_go_grpc_source" && env GOTOOLCHAIN=local GOWORK=off GOPROXY=off go mod edit -modfile="$$grpc_modfile" \
		-replace="google.golang.org/protobuf=$$go_path/pkg/mod/google.golang.org/protobuf@v1.36.10"); \
	for target in $(PROTO_TOOLS_TARGETS); do \
		case "$$target" in \
			darwin/amd64) buf_package=buf-darwin-x64; buf_integrity='sucV3lQXVuOqYs3+ToulkUh2tZuMnl286DKb44imp3PnexVhAVOP7d3ybYe98HNGwysEdjNP2WIOGb0uKuRCIQ==' ;; \
			darwin/arm64) buf_package=buf-darwin-arm64; buf_integrity='c7owUswBbMmwfHPH9JRBEJu09mrXYGC33V2JQCgraWCBm74Z95AOkhDua50qiBrQnysvJkJ0p/z4MWxJqcpnIA==' ;; \
			linux/amd64) buf_package=buf-linux-x64; buf_integrity='5WHGUIb5iLFXcnqV33TDejqaPgx0CWFaYW7b4wh12wT0w3DR+ghFq6S6RmYyZLbTuhS4ZFsf+xyk5m+HViKxrA==' ;; \
			linux/arm64) buf_package=buf-linux-aarch64; buf_integrity='4viSYqbhIusd6LR+JayDex8S1rLUL+hTUMYUgSPl75EC93FpJM4vkk2RhoAhyjQqWF/JQLcyWV8kjRRiIwygdg==' ;; \
			*) echo "Unsupported PROTO_TOOLS_TARGETS route: $$target" >&2; exit 2 ;; \
		esac; \
		target_os=$${target%/*}; \
		target_arch=$${target#*/}; \
		out_dir="$(PROTO_TOOLS_DIR)/$$target_os/$$target_arch/bin"; \
		mkdir -p "$$out_dir"; \
		(cd "$$protoc_gen_go_source" && env GOTOOLCHAIN=local GOWORK=off GOPROXY=off GOSUMDB=off CGO_ENABLED=0 GOOS="$$target_os" GOARCH="$$target_arch" GOPATH="$$go_path" \
			go build -trimpath -o "$$out_dir/protoc-gen-go" .); \
		(cd "$$protoc_gen_go_grpc_source" && env GOTOOLCHAIN=local GOWORK=off GOPROXY=off GOSUMDB=off CGO_ENABLED=0 GOOS="$$target_os" GOARCH="$$target_arch" GOPATH="$$go_path" \
			go build -trimpath -mod=readonly -modfile="$$grpc_modfile" -o "$$out_dir/protoc-gen-go-grpc" .); \
		go version -m "$$out_dir/protoc-gen-go" | grep -F "GOOS=$$target_os" >/dev/null; \
		go version -m "$$out_dir/protoc-gen-go" | grep -F "GOARCH=$$target_arch" >/dev/null; \
		go version -m "$$out_dir/protoc-gen-go-grpc" | grep -F "GOOS=$$target_os" >/dev/null; \
		go version -m "$$out_dir/protoc-gen-go-grpc" | grep -F "GOARCH=$$target_arch" >/dev/null; \
		buf_archive="$$tmp_dir/$$buf_package.tgz"; \
		buf_extract_dir="$$tmp_dir/$$buf_package"; \
		curl --fail --location --silent --show-error \
			"https://registry.npmjs.org/@bufbuild/$$buf_package/-/$$buf_package-$(BUF_VERSION).tgz" \
			--output "$$buf_archive"; \
		actual_buf_integrity=$$(openssl dgst -sha512 -binary "$$buf_archive" | openssl base64 -A); \
		[[ "$$actual_buf_integrity" == "$$buf_integrity" ]] || { echo "Buf integrity mismatch for $$target" >&2; exit 1; }; \
		mkdir -p "$$buf_extract_dir"; \
		tar -xzf "$$buf_archive" -C "$$buf_extract_dir" package/bin/buf; \
		install -m 0755 "$$buf_extract_dir/package/bin/buf" "$$out_dir/buf"; \
		echo "Packaged protobuf tools for $$target"; \
	done; \
	if command -v sha256sum >/dev/null 2>&1; then \
		(cd "$(PROTO_TOOLS_DIR)" && find . -path '*/bin/*' -type f -print | LC_ALL=C sort | xargs sha256sum) > "$(PROTO_TOOLS_DIR)/SHA256SUMS"; \
	else \
		(cd "$(PROTO_TOOLS_DIR)" && find . -path '*/bin/*' -type f -print | LC_ALL=C sort | xargs shasum -a 256) > "$(PROTO_TOOLS_DIR)/SHA256SUMS"; \
	fi; \
	printf 'buf=%s\nprotoc-gen-go=%s\nprotoc-gen-go-grpc=%s\ngo=%s\n' \
		'$(BUF_VERSION)' '$(PROTOC_GEN_GO_VERSION)' '$(PROTOC_GEN_GO_GRPC_VERSION)' "$$(go env GOVERSION)" \
		> "$(PROTO_TOOLS_DIR)/VERSIONS"

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
