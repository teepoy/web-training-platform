# Learnings

## [2026-05-22] Session ses_1b53171aeffex6dvdUWcuerYdM - Codebase exploration

### Key structural changes since plan was written

1. **DI pattern (clean-di DONE)**: `AppContainer` dataclass in `apps/api/app/composition.py` is the new DI root. Route deps use `request.app.state.container`. No more `dependency-injector` container.

2. **Dataset types are now top-level modules**:
   - `apps/api/app/modules/dataset_classification/domain/schema.py` ← classification SCHEMA (NOT the old path)
   - `apps/api/app/modules/dataset_vqa/domain/schema.py` ← VQA SCHEMA
   - `apps/api/app/modules/dataset_detection/domain/schema.py` ← detection SCHEMA
   - OLD paths like `apps/api/app/modules/datasets/domain/schemas/image_classification.py` are GONE
   - `DatasetSchema` dataclass still lives at `apps/api/app/modules/datasets/domain/entities/dataset_schema.py` (unchanged)
   - Schema registry still at `apps/api/app/modules/datasets/domain/entities/schema_registry.py`

3. **Domain tests in backend**: Tests now live inside each module at `apps/api/app/modules/<module>/tests/test_*.py`. No longer in `apps/api/tests/`. (The top-level `apps/api/tests/` only has integration/smoke tests).

4. **Preset split**:
   - `apps/api/app/modules/presets/` still has shared presets (resnet50_cls_v1.py, clip_zero_shot_v1.py, dspy_vqa_v1.py, _registry.py)
   - `apps/api/app/modules/dataset_classification/presets/` has (clip_zero_shot_v1.py, resnet50_cls_v1.py) - may be copies or the same
   - `apps/api/app/modules/dataset_vqa/presets/dspy.py` - VQA preset

### Plan Reference Corrections

The plan mentions `apps/api/app/modules/datasets/domain/schemas/image_classification.py` etc. - THESE PATHS ARE WRONG NOW.

Correct paths for schema declarations:
- Classification: `apps/api/app/modules/dataset_classification/domain/schema.py`
- VQA: `apps/api/app/modules/dataset_vqa/domain/schema.py`
- Detection: `apps/api/app/modules/dataset_detection/domain/schema.py`

New tests should go inside the appropriate module under:
- `apps/api/app/modules/datasets/tests/` (for dataset infrastructure)
- Or create a new `apps/api/app/modules/datasets/tests/test_view_contract*.py`

View contract module likely best placed at:
- `apps/api/app/modules/datasets/domain/entities/view_contracts.py` (alongside dataset_schema.py)

Trainer/predictor spec registries could go in:
- `apps/api/app/modules/presets/` (alongside _registry.py) since they shadow presets
- Or in a new `apps/api/app/modules/runtime/` (separate module)

## Task 2: View Contract Backlog Documentation
- Established a clear Phase 2+ roadmap for the View Contract system.
- Documented 11 deferred items with rationales and prerequisites.
- Explicitly defined the boundaries between current JSON/Pydantic control-plane and future high-performance lanes (Arrow/gRPC).
- Ensured consistency with the storage mode architecture (file_shard_sparse).

## [2026-05-22] T1 view contract foundation

- Added `app.modules.datasets.domain.entities.view_contracts` as a runtime-internal foundation only; no route contracts, preview constructors, or shared runtime contexts were changed.
- View row classes keep `VIEW_TYPE` as `ClassVar[Literal[...]]`, so row serialization via `model_dump()` omits `view_type`.
- Initial model literals are `resnet_cls_v1`, `clip_emb_v1`, and `dspy_vqa_v1`; these intentionally live beside view contracts rather than in preset decorators.
- Verification note: `make test` currently fails in `tests/test_api_flows.py::test_events_history_pagination` because the endpoint returns 3 items while `total` is 2; focused rerun reproduces the same failure and appears unrelated to view contract code.

## [2026-05-22] T3 runtime specs registry

- Added `app.modules.datasets.domain.entities.runtime_specs` as an internal in-memory catalog only; it mirrors the preset registry shape but does not participate in execution.
- `TrainerSpec.input_views` is a `frozenset[ViewType]` so trainers can declare multiple required views; `PredictorSpec.input_view` stays singular because predictors consume one view type.
- The registry API is intentionally minimal: `register_*`, `list_*`, and `get_*` helpers only, with module-level dict storage and no persistence layer.
- Smoke import and preset-registry-unchanged checks passed; repository `make test` still fails on the pre-existing `test_events_history_pagination` mismatch, unrelated to this change.

## [2026-05-22] T4 view-contract/spec tests

- Added `app/modules/datasets/tests/test_view_contract_specs.py` with pure unit coverage for view literals, dataclass-backed `model_dump()` output, and runtime spec registry helpers.
- Used unique IDs per registry test so module-level trainer/predictor dicts do not collide across tests.
- `make test-api ARGS="-k 'view_contract or runtime_spec' -v"` passed; full `make test` still fails in the pre-existing `tests/test_api_flows.py::test_events_history_pagination` assertion mismatch.

## [2026-05-22] Task 5 - DatasetSchema view metadata

- Added optional `provided_views` and `runtime_policy` fields to `DatasetSchema` without breaking existing constructors.
- Added `RuntimeFilterPolicy` with empty deny-set defaults; empty policy means allow all.
- Verified schema registry still loads all three dataset types: classification, detection, VQA.

## [2026-05-22] T10 runtime preservation tests

- Added a pure unit test file for runtime preservation that exercises preset imports, registry listing, runtime dataclass field names, and compatibility validators without touching DB/LS/workers.
- `list_presets()` ordering is registry-dependent; asserting the exact set plus count is more robust than relying on insertion order.
- `PresetSpec.model` expects a `ModelSource`, not a raw dict, in local test fixtures.

## [2026-05-22] F1 evidence refresh

- Created missing evidence files for T13-T15 under `.sisyphus/evidence/` using the already-verified results; no source code or plan file was modified.
- Evidence files now exist for targeted tests, type/lint, full test run, and API Docker build.
- Plan audit conclusion: T1-T16 are satisfied from the plan/evidence perspective: T1-T12 previously verified, T13 targeted tests passed, T14 pyright/ruff clean and `make test` recorded the unrelated pre-existing failure, T15 API Docker build succeeded, and T16 backlog doc covers Regex, Arrow, gRPC, frontend, sparse, and preset migration.
