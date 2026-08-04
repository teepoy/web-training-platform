# fix → main Diff Document

> **Branch**: `fix` | **Base**: `main` | **Squashed**: 1 commit, 109 files, +11755 / -7985

---

## 1. MapperRegistry — Global Type Conversion System

**New Files:**

- `apps/api/app/core/mapper_registry.py` — `@mapper.register(from_types, to_types)` decorator with cartesian product registration; `mapper.get_mapper(src, dst)` lookup
- `apps/api/app/modules/datasets/domain/mapper.py` — Classification/Detection/VQA: all `Sample ↔ Domain ↔ View` conversion functions (~276 lines)
- `apps/api/app/modules/sc/domain/mapper.py` — SC: `Sample ↔ PatchSample ↔ View(v1/v2)`, die coordinate support (~296 lines)

**Modified:**

- `CORE_DESIGNS.md` — documents MapperRegistry as the standard
- `apps/api/app/registrations.py` — imports both mapper files + `patch_image_v2`
- `apps/api/AGENTS.md` — updated structure docs

**Removed from model classes:** `from_sample()`, `to_sample()`, `get_adapter()`, `as_*()` methods on `ClassificationSample`, `DetectionSample`, `VQASample`, `PatchSample`

**Modified adapter layer:**

- `apps/api/app/modules/datasets/app/session.py` — `_resolve_projector` / `_resolve_from_sample` use mapper registry; dead `getattr` fallbacks removed; `patch_image_v2` branch with die coordinate resolution
- `apps/api/app/modules/sc/models.py` — `@view` decorators moved to schema files; `VIEW_TYPES` includes `patch_image_v2`

---

## 2. SC Module — patch_image_v2 + Die Coordinates + Sprite + Redis Cache

**New:**

- `apps/api/app/modules/sc/views/patch_image/v2/` — `ScPatchImageV2Row` schema (`die_x: int`, `die_y: int`)
- `apps/api/app/modules/sc/app/services/sprite_service.py` — pyvips-based sprite generation (patch/review/patch-batch/review-batch)
- `apps/api/app/modules/sc/adapter/_wafer_mock/redis_cache.py` — `RedisPatchImageCache`: TTL, distributed lock dedup, LRU eviction

**Modified:**

- `apps/api/app/modules/sc/domain/models.py` — `PatchSample` gains `die_x`/`die_y` fields
- `apps/api/app/modules/sc/port/http/router.py` — +4 sprite endpoints (`/sprites/patch/...`, `/sprites/review/...`, `/sprites/patch-batch/...`, `/sprites/review-batch/...`)
- `apps/api/app/modules/sc/container.py` — `ScContext` gains `sprite_service`; config-driven Redis switch (`redis.enabled`)
- `apps/api/app/modules/sc/port/http/deps.py` — `ScSpriteServiceDep`
- `apps/api/app/modules/sc/adapter/flows/sc_import.py` — uses `mapper.get_mapper()` instead of `.to_sample()`; `view_types` includes `"patch_image_v2"`
- `apps/api/app/modules/sc/views/patch_image/v1/schemas.py` — `@view` decorator on schema
- `apps/api/app/modules/sc/views/review_image/v1/schemas.py` — `@view` decorator on schema

**New dependency:** `pyvips-binary` (pyproject.toml)

---

## 3. Prediction Module — BatchPredictionService + Flow Optimizations

**New:**

- `apps/api/app/modules/prediction/app/services/batch_lookup.py` — `BatchPredictionService`: SQL subquery for latest prediction per sample

**Modified:**

- `apps/api/app/modules/prediction/port/http/router.py` — `GET /datasets/{dataset_id}/latest-predictions`
- `apps/api/app/modules/prediction/port/http/deps.py` — `BatchPredictionServiceDep`
- `apps/api/app/modules/prediction/container.py` — `PredictionContext.batch_prediction`
- `apps/api/app/modules/prediction/flows/_predictors/sc.py` — refactored `_get_defective_bytes` (direct bytes + metadata paths), added `_get_reference_bytes`
- `apps/api/app/modules/prediction/flows/predict_job.py` — predictor `_view_id` resolution, `MaterializeClient` auth (`PLATFORM_INTERNAL_TOKEN`), all byte columns passed through to predictor

---

## 4. Cross-Module Dependency — DieResolverProtocol Port (REMOVED)

Die coordinate resolution was originally externalized via a `DieResolverProtocol` cross-module port and `ScDieCoordinateResolver` implementation. This was later inlined: `PatchSample` now carries `die_x`/`die_y` fields directly, eliminating the cross-module port.

**Removed:**

- `apps/api/app/modules/datasets/domain/die_resolver.py` — `DieResolverProtocol`
- `apps/api/app/modules/sc/app/services/die_resolver.py` — `ScDieCoordinateResolver`
- `apps/api/app/modules/datasets/container.py` — `die_resolver` field removed from `DatasetsContext`
- `apps/api/app/modules/sc/container.py` — `die_resolver` parameter removed from `init_sc()`
- `apps/api/app/composition.py` — `die_resolver` creation and cross-module wiring removed
- `apps/api/app/modules/datasets/views/deps.py` — `die_resolver` removed from `DatasetSessionFactory`

---

## 5. Frontend — Blink Table Split + ReclassifyPage Upgrade

**New Components:**

- `apps/web/src/shared/components/blink-virtual-table/BlinkVirtualTable.vue` — generic virtualized sprite table (~392 lines)
- `apps/web/src/features/sc/presentation/components/ScPreviewBlinkTable.vue` — preview mode (~605 lines)
- `apps/web/src/features/sc/presentation/components/ScReclassifyBlinkTable.vue` — reclassify mode with prediction/draft badges (~669 lines)
- `apps/web/src/features/sc/presentation/components/ScBlinkClassifyTable.vue` — classify mode (~56 lines)
- `apps/web/src/features/sc/presentation/components/ScBlinkPreviewTable.vue` — preview mode wrapper (~52 lines)

**New Composables:**

- `apps/web/src/features/sc/presentation/composables/useBlinkVirtualScroll.ts` — virtual scroll (extracted from ScBlinkTable)
- `apps/web/src/features/sc/presentation/composables/useBlinkRubberBand.ts` — rubber band selection (extracted from ScBlinkTable)

**Modified:**

- `ScBlinkTable.vue` — 826→23 lines, compatibility shim wrapping `ScPreviewBlinkTable`
- `ReclassifyPage.vue` — uses `ScReclassifyBlinkTable`, prediction/draft badge props, label creation UI (NInput+NButton)
- `InspectionQuad.vue` — uses `ScPreviewBlinkTable`
- `useReclassifyPage.ts` — switched to `patch_image_v2` view, `predictionLabels`/`predictionConfidences` from `useListLatestPredictions`, `addLabel` with label space mutation, die coordinates, fixed `labelSpace` access path

---

## 6. OpenAPI + Generated Artifacts

**Modified:**

- `openapi/openapi.yaml` — added `/datasets/{dataset_id}/latest-predictions`, removed `ScDatasetDetailResponse`
- `apps/api/app/shared/generated/openapi_models.py` — regenerated
- `apps/web/src/generated/orval/endpoints/api.ts` — new `useListLatestPredictions`, `useScBulkCreateAnnotations` (renamed)
- `apps/web/src/generated/orval/models/` — deleted `scDatasetDetailResponse.ts`, `scDatasetDetailResponseTaskSpec.ts`; removed `inspection_time`/`wafer_key` params

---

## 7. Redis Infrastructure

**New:**

- `infra/k8s/redis.yaml` — Deployment + Service (redis:7-alpine)
- `apps/api/config/base.yaml` — `redis:` config section (`enabled: false`, host, port, password, db)

**Modified:**

- `infra/compose/docker-compose.yaml`, `infra/compose/docker-compose.dev.yaml`, and `infra/compose/production/` — Redis service, runtime connection settings, and persistent storage
- `infra/k8s/kustomization.yaml` — registered `redis.yaml`
- `infra/k8s/configmap.yaml` — `REDIS_HOST`, `REDIS_PORT`
- `infra/k8s/secret.example.yaml` — `REDIS_PASSWORD`
- `apps/api/pyproject.toml` — added `redis>=5.0` dependency

**New Protocol:**

- `apps/api/app/modules/sc/adapter/_wafer_mock/cache.py` — `PatchCacheProtocol` structural interface shared by `PatchImageCache` and `RedisPatchImageCache`
- `apps/api/app/modules/sc/adapter/_wafer_mock/image_service.py` — `cache` typed as `PatchCacheProtocol | None`

---

## 8. Datasets Module Changes

**Modified:**

- `apps/api/app/modules/datasets/app/session.py` — mapper registry integration; `DatasetSession` takes `dataset_type`; `patch_image_v2` uses `PatchSample.die_x`/`die_y`
- `apps/api/app/modules/datasets/app/view_loader.py` — doc updates
- `apps/api/app/modules/datasets/views/deps.py` — `DatasetSessionFactory` injected via datasets context
- `apps/api/app/modules/datasets/app/services/runtime_materializer.py` — annotation label lookup: `defect_id` first, then `sample_id`
- `apps/api/app/modules/datasets/app/services/sparse_import_operator.py` — defect_id identity doc

---

## 9. Tests (New Files)

| File                                                      | Lines | Tests                                                                |
| --------------------------------------------------------- | ----- | -------------------------------------------------------------------- |
| `apps/api/tests/test_mapper_registry.py`                  | 296   | registration, cartesian product, duplicates, real mapper integration |
| `apps/api/tests/test_latest_predictions.py`               | 133   | latest per sample, empty dataset, dedup                              |
| `apps/api/tests/test_patch_image_v2.py`                   | 117   | defaults, explicit coords, serialization                             |
| `apps/api/tests/temp_bdd_wafer_e2e.py`                    | 1167  | full BDD: annotate→train→predict→verify                              |
| `apps/api/app/modules/sc/tests/test_redis_patch_cache.py` | 197   | cache hit/miss, lock, eviction                                       |
| `apps/api/app/modules/sc/tests/test_sprite_service.py`    | 116   | sprite generation                                                    |
| `apps/web/.../useReclassifyPage.spec.ts`                  | 186   | predictionLabels, dieDisplay, addLabel duplicate                     |
| `apps/web/.../ScReclassifyBlinkTable.spec.ts`             | 218   | badges (prediction/draft/empty), selection, empty state              |
| `apps/web/.../BlinkVirtualTable.spec.ts`                  | 143   | rendering, row/col count, toggle timer                               |
| `apps/web/.../ScBlinkClassifyTable.spec.ts`               | —     | classify mode                                                        |
| `apps/web/.../ScBlinkPreviewTable.spec.ts`                | —     | preview mode                                                         |

---

## 10. Config + Infra Changes

**Modified:**

- `scripts/smoke_wafer_e2e.py` — enhanced prediction count assertions
- `apps/api/pyproject.toml` — `pyvips-binary`, `redis>=5.0`
- `uv.lock` — updated

---

## Known Limitation: Die Coordinates in Predict/Train Flows

`_BulkViewLoader` in `predict_job.py` and `train_job.py` calls `map_f(row)`. When the view is `patch_image_v2`, `die_x`/`die_y` come from the `PatchSample` model fields (default: `0`). Accurate die coordinates are only needed for the reclassify UI (handled by `DatasetSession`).
