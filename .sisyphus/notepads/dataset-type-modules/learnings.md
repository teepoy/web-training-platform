## dataset_detection module scaffold
- For backend module scaffolding, create only the requested DDD subdirs and keep `__init__.py` files minimal with `from __future__ import annotations`.
- `uv run python -c "import app.modules.<module>"` is a quick validation for package importability after adding new module skeletons.

## dataset_vqa module scaffold
- Created the empty `app.modules.dataset_vqa` package with `domain/`, `presets/`, `runtime/`, `mocks/`, and `data/` subpackages.
- Kept every `__init__.py` minimal and import-safe with `from __future__ import annotations`.
- Verified importability with `uv run python -c "import app.modules.dataset_vqa; print('ok')"`.
## 2026-05-21
- Scaffolded `apps/web/src/modules/dataset-detection/` with the empty `views/` directory plus `index.ts` and `registrations.ts` placeholder exports.
- Verified the module skeleton matches the existing dataset-classification pattern.
- Scaffolded apps/web/src/modules/dataset-vqa with empty views/ plus export-only index.ts and registrations.ts.
- Verified the new module directory with lsp diagnostics and vue-tsc --noEmit.
- Copied dataset detection schema and shim files into the new module layout without changing behavior.
- FE copies needed import path normalization to absolute @/features references for moved registry/schema links.
## 2026-05-21 storybook shims
- Added Storybook stories for the classification and VQA dataset shims using the detection story as the template.
- Kept story-local mock data aligned to each schema's sample factory shape (`label` for classification, `question` for VQA).
- Verified the frontend Storybook build with `pnpm --dir apps/web build-storybook 2>&1 | tail -10`.
