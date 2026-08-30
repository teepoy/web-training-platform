# Fast static checks for changed files and generated type boundaries.

.PHONY: check-duplicate-types
check-duplicate-types: ## Check for duplicate types between shared/api and generated/orval
	python3 scripts/check-duplicate-types.py

.PHONY: check-web-i18n
check-web-i18n: ## Reject static English copy in localized production UI scopes
	python3 scripts/check-web-i18n-literals.py

.PHONY: lint
lint: check-web-i18n ## Run fast lint on git diff files (ruff + prettier)
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
	WEB_FILES=$$(echo "$$CHANGED" | grep -E '\.(vue|ts|tsx|js|jsx|css|scss|json|yaml|yml|md)$$' | grep -v '^devtools/' | grep -v /node_modules/ | grep -v /dist/ | grep -v /generated/ || true); \
	if [ -n "$$WEB_FILES" ]; then \
		echo "--- prettier check (Web) ---"; \
		echo "$$WEB_FILES" | xargs ./node_modules/.bin/prettier --check; \
	fi; \
	echo "--- lint done ---"
