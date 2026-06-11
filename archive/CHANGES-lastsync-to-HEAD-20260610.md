# Changes Archive: `lastsync` → `HEAD`

**Generated**: 2026-06-10 08:08:39 CST
**Range**: `lastsync` (dbe9bc9d) → `HEAD` (271dff40) — **inclusive**
**Branch**: `dev/messy`
**Summary**: **1545 files changed**, 113,386 insertions(+), 39,627 deletions(-)

---

## Commits (7 total)

### 1. `271dff40` — feat(sc): add wafer map filtering, class list, refactor plot points API and proto
**Author**: Emia <47446852+YuShigurey@users.noreply.github.com>
**Date**: 2026-06-10 08:07:34 +0800

### 2. `1140c793` — feat(auth): persist darkMode to localStorage + fix auth page themes
**Author**: Emia <47446852+YuShigurey@users.noreply.github.com>
**Date**: 2026-06-09 23:08:02 +0800

- Add hydrateDarkMode() to useUiStore with try/catch for graceful degradation
- Persist darkMode preference to localStorage (key: ui_dark_mode)
- Hydrate darkMode in App.vue onMounted for session persistence
- Replace hardcoded dark CSS in RegisterView, OAuthRegisterView, OAuthCallbackView
- Use useThemeVars() from Naive UI for theme-responsive background + box-shadow

### 3. `02238b0f` — fix(sc): expand ScSampleTableRow schema to include full wafer/sample fields
**Author**: Emia <47446852+YuShigurey@users.noreply.github.com>
**Date**: 2026-06-09 23:05:53 +0800

Schema now exposes all 10 fields (was 4): defect_id, rough_bin, class_number, test_id, wafer_x, wafer_y, index_x, index_y, adder, cluster_id.

### 4. `207eaad2` — fix(sc): eliminate 1px gap between die edges and grid lines in wafer map
**Author**: Emia <47446852+YuShigurey@users.noreply.github.com>
**Date**: 2026-06-09 22:41:18 +0800

Replace independent Math.round(dw/dh) with edge-based rounding (left/right/top/bottom).
Co-authored-by: Sisyphus <clio-agent@sisyphuslabs.ai>

### 5. `6654c137` — fix: persist predictions through dataset storage aggregate
**Author**: Emia <47446852+YuShigurey@users.noreply.github.com>
**Date**: 2026-06-09 21:56:01 +0800

### 6. `3d0c4baf` — fix YOLO artifacts and add production compose deployment
**Author**: Emia <47446852+YuShigurey@users.noreply.github.com>
**Date**: 2026-06-09 21:16:08 +0800

### 7. `dbe9bc9d` — feat: overhaul platform architecture and SC workflows _(lastsync)_
**Author**: Emia <47446852+YuShigurey@users.noreply.github.com>
**Date**: 2026-06-09 12:55:39 +0800

---

## File Change Summary

```
 .github/workflows/ci.yml                           |    41 +
 .gitignore                                         |    14 +
 .opencode/opencode.json                            |     7 -
 .opencode/opencode.jsonc                           |     9 +
 .opencode/package-lock.json                        |    45 +-
 .opencode/plans/worker-flow-tests.md               |    63 -
 .opencode/semgrep/forbid-wafer-mock.yml            |    28 +
 .opencode/skills/issue-analyzer/SKILL.md           |    91 +
 .opencode/skills/page-design-contract/SKILL.md     |   142 +
 .opencode/skills/plan-handoff/SKILL.md             |   130 -
 .pre-commit-config.yaml                            |    12 +
 .../evidence/task-3-preset-registry-unchanged.txt  |     1 +
 .sisyphus/evidence/task-3-registry-smoke.txt       |     1 +
 .sisyphus/notepads/clean-di/learnings.md           |    34 +
 .../notepads/dataset-type-modules/learnings.md     |     5 +
 .../learnings.md                                   |    86 +
 .sisyphus/plans/sc-hybrid-import.md                |   863 ++
 AGENTS.md                                          |   466 +-
 CORE_DESIGNS.md                                    |   212 +
 Makefile                                           |   306 +-
 README.md                                          |    11 +-
 apps/api/.prefectignore                            |    41 +
 apps/api/AGENTS.md                                 |   198 +-
 apps/api/Dockerfile                                |    27 +-
 apps/api/Dockerfile.prefect-worker-cpu             |    48 +
 apps/api/Dockerfile.prefect-worker-gpu             |    54 +
 apps/api/README.md                                 |     2 +-
 apps/api/alembic/versions/0001_initial_schema.py   |   101 -
 apps/api/alembic/versions/0002_image_uris.py       |    47 -
 .../alembic/versions/0003_pgvector_embeddings.py   |    44 -
 .../alembic/versions/0004_dataset_embed_config.py  |    24 -
 .../versions/0005_add_label_studio_fields.py       |    23 -
 .../alembic/versions/0006_add_sample_created_at.py |    32 -
 .../versions/0007_add_users_orgs_memberships.py    |    45 -
 .../versions/0008_add_personal_access_tokens.py    |    25 -
 .../alembic/versions/0009_add_schedules_table.py   |    34 -
 .../versions/0010_add_org_id_to_resources.py       |    56 -
 .../0011_seed_default_org_and_superadmin.py        |    62 -
 .../alembic/versions/0012_add_is_public_flag.py    |    22 -
 .../versions/0013_add_user_id_fk_columns.py        |    24 -
 .../versions/0014_ls_project_id_not_null.py        |    33 -
 apps/api/alembic/versions/0015_add_model_fields.py |    38 -
 .../versions/0016_add_prediction_review_tables.py  |    92 -
 .../alembic/versions/0017_add_prediction_jobs.py   |    67 -
 .../0018_platform_predictions_and_collections.py   |   248 -
 ...28010cffc0bc_prune_legacy_worker_deployments.py |    59 +
 .../versions/6c6df75eb294_initial_schema.py        |   355 +
 .../7d7d807e0161_add_annotation_value_column.py    |    24 -
 ...e25_remove_platform_predictions_sample_id_fk.py |    37 +
 .../9967d60b337d_add_oauth_fields_to_users.py      |    33 -
 ...ee02352bd_add_oauth_provider_fields_to_users.py |    37 +
 .../a2b4ae7f5b18_merge_oauth_and_storage_mode.py   |    25 -
 .../b1f5b33fab04_add_storage_mode_to_datasets.py   |    32 -
 ...6571_add_sensor_subscription_and_checkpoint_.py |    40 -
 apps/api/app/_torch_boundary_test.py               |     3 +
 apps/api/app/{cli.py => cli/__init__.py}           |    17 +-
 .../controllers/__init__.py => cli/__main__.py}    |     4 +
 apps/api/app/cli/deployments.py                    |    58 +
 apps/api/app/composition.py                        |   203 +-
 apps/api/app/core/config.py                        |    36 +-
 apps/api/app/core/mapper_registry.py               |    78 +
 apps/api/app/core/prefect_runner.py                |   114 +
 apps/api/app/core/registry.py                      |   424 +
 apps/api/app/main.py                               |   202 +-
 .../app/modules/agent/{api => adapter}/__init__.py |     0
 .../services => adapter/clients}/__init__.py       |     0
 .../clients => adapter/repositories}/__init__.py   |     0
 .../{application => adapter/tools}/__init__.py     |     0
 .../{infrastructure => adapter}/tools/assembler.py |     2 +-
 .../tools/global_assembler.py                      |     4 +-
 .../tools/global_prompt_template.md                |    13 +-
 .../tools/global_tools.py                          |   204 +-
 .../tools/metadata_inference.py                    |    14 +-
 .../tools/prompt_template.md                       |     0
 .../{infrastructure => adapter}/tools/tools.py     |     2 +-
 apps/api/app/modules/agent/api/deps.py             |    67 -
 .../agent/{infrastructure => app}/__init__.py      |     0
 .../repositories => app/services}/__init__.py      |     0
 .../services/global_runtime.py                     |    55 +-
 .../agent/{application => app}/services/runtime.py |     0
 .../{application => app}/services/session_store.py |     2 +-
 .../{application => app}/services/surface_store.py |     0
 apps/api/app/modules/agent/container.py            |    15 +
 .../infrastructure/repositories/repository.py      |   134 -
 .../controllers => port/http}/__init__.py          |     0
 apps/api/app/modules/agent/port/http/deps.py       |    83 +
 .../controllers => port/http}/router.py            |    84 +-
 .../{interfaces/dtos => port/http}/schemas.py      |     0
 apps/api/app/modules/agent/tests/test_agent.py     |    83 +-
 .../modules/agent/tests/test_classify_endpoint.py  |    24 +-
 .../app/modules/agent/tests/test_global_agent.py   |   102 +-
 .../tools => auth/adapter}/__init__.py             |     0
 .../dtos => auth/adapter/clients}/__init__.py      |     0
 .../services => adapter/repositories}/__init__.py  |     0
 .../auth/{api => adapter/tools}/__init__.py        |     0
 apps/api/app/modules/auth/api/deps.py              |    23 -
 .../modules/auth/{application => app}/__init__.py  |     0
 .../clients => app/services}/__init__.py           |     0
 .../{application => app}/services/auth_service.py  |     0
 .../auth/{application => app}/services/oauth.py    |     4 +-
 apps/api/app/modules/auth/container.py             |    14 +
 .../repositories => port/http}/__init__.py         |     0
 .../{interfaces/controllers => port/http}/deps.py  |   193 +-
 .../controllers => port/http}/router.py            |   175 +-
 .../auth/{interfaces/dtos => port/http}/schemas.py |    11 +
 apps/api/app/modules/auth/tests/test_auth.py       |     2 +-
 .../api/app/modules/auth/tests/test_auth_routes.py |     4 +-
 .../adapter}/__init__.py                           |     0
 .../adapter/clients}/__init__.py                   |     0
 .../adapter/repositories}/__init__.py              |     0
 .../classify/{api => adapter/tools}/__init__.py    |     0
 .../{infrastructure => adapter}/tools/assembler.py |     4 +-
 .../tools/metadata_inference.py                    |    10 +-
 .../tools/prompt_template.md                       |     0
 .../{infrastructure => adapter}/tools/tools.py     |    94 +-
 apps/api/app/modules/classify/api/deps.py          |    34 -
 .../classify/{application => app}/__init__.py      |     0
 .../{application => app}/services/__init__.py      |     0
 .../{application => app}/services/runtime.py       |    18 +-
 apps/api/app/modules/classify/container.py         |    28 +
 .../clients => port/http}/__init__.py              |     0
 apps/api/app/modules/classify/port/http/deps.py    |    42 +
 .../controllers => port/http}/router.py            |    86 +-
 .../{interfaces/dtos => port/http}/schemas.py      |     0
 .../adapter}/__init__.py                           |     0
 .../adapter/clients}/__init__.py                   |     0
 .../adapter/repositories}/__init__.py              |     0
 apps/api/app/modules/dashboard/api/deps.py         |    42 -
 .../tools => dashboard/app}/__init__.py            |     0
 .../{application => app}/dashboard_service.py      |     4 +-
 .../dtos => dashboard/app/services}/__init__.py    |     0
 .../services/service_health.py                     |    94 +-
 apps/api/app/modules/dashboard/container.py        |    36 +
 .../dashboard/{api => port/http}/__init__.py       |     0
 apps/api/app/modules/dashboard/port/http/deps.py   |    36 +
 .../controllers => port/http}/router.py            |    16 +-
 .../app/modules/dashboard/tests/test_dashboard.py  |    20 +-
 .../app/modules/dataset_classification/__init__.py |     3 -
 .../dataset_classification/domain/schema.py        |    64 -
 .../mocks/imagenet_100_rchannel.py                 |   238 -
 .../dataset_classification/mocks/imagenet_mock.py  |   198 -
 .../dataset_classification/mocks/imagenet_real.py  |   249 -
 .../dataset_classification/mocks/oxford_flowers.py |   114 -
 .../presets/clip_zero_shot_v1.py                   |    62 -
 .../presets/resnet50_cls_v1.py                     |    82 -
 .../dataset_classification/runtime/torch.py        |   319 -
 apps/api/app/modules/dataset_detection/__init__.py |     3 -
 .../app/modules/dataset_detection/domain/schema.py |   102 -
 apps/api/app/modules/dataset_vqa/__init__.py       |     3 -
 apps/api/app/modules/dataset_vqa/domain/schema.py  |    67 -
 apps/api/app/modules/dataset_vqa/presets/dspy.py   |    84 -
 apps/api/app/modules/dataset_vqa/runtime/dspy.py   |   194 -
 .../application => datasets/adapter}/__init__.py   |     0
 .../modules/datasets/adapter/db_full_storage.py    |  1179 ++
 .../adapter/flows}/__init__.py                     |     0
 .../flows/drain_dataset.py                         |     0
 .../adapter/repositories}/__init__.py              |     0
 .../app/modules/datasets/adapter/sparse_storage.py |  1506 +++
 .../modules/datasets/adapter/storage_factory.py    |    79 +
 apps/api/app/modules/datasets/api/deps.py          |    92 -
 .../infrastructure => datasets/app}/__init__.py    |     0
 .../{application => app/sample_access}/__init__.py |     0
 .../{application => app}/sample_access/sparse.py   |     2 +-
 .../app/services}/__init__.py                      |     0
 .../services/dataset_capability_guard.py           |     0
 .../datasets/app/services/dataset_payload_store.py |     7 +
 .../services/dataset_service.py                    |    67 +-
 .../{application => app}/services/feature_ops.py   |   101 +-
 .../modules/datasets/app/services/sparse_export.py |   616 +
 .../app/services/sparse_import_operator.py         |   182 +
 .../datasets/app/services/sparse_manifest.py       |     7 +
 apps/api/app/modules/datasets/app/session.py       |   193 +
 apps/api/app/modules/datasets/app/view_loader.py   |   109 +
 .../datasets/application/sample_access/base.py     |   139 -
 .../datasets/application/sample_access/db_full.py  |   123 -
 .../datasets/application/sample_access/factory.py  |    91 -
 .../application/services/sparse_manifest.py        |    71 -
 .../modules/datasets/classification/__init__.py    |    19 +
 .../app/modules/datasets/classification/models.py  |    54 +
 .../modules/datasets/classification/upstream.py    |    22 +
 apps/api/app/modules/datasets/container.py         |    51 +
 .../api/app/modules/datasets/detection/__init__.py |    19 +
 apps/api/app/modules/datasets/detection/models.py  |    66 +
 .../api/app/modules/datasets/detection/upstream.py |    21 +
 apps/api/app/modules/datasets/domain/__init__.py   |    23 +
 .../app/modules/datasets/domain/compatibility.py   |   101 +
 .../modules/datasets/domain/entities/__init__.py   |     2 +
 .../datasets/domain/entities/classification.py     |    53 -
 .../datasets/domain/entities/dataset_payload.py    |   128 +-
 .../datasets/domain/entities/dataset_schema.py     |    58 -
 .../datasets/domain/entities/schema_registry.py    |    40 -
 .../app/modules/datasets/domain/entities/vqa.py    |    41 -
 apps/api/app/modules/datasets/domain/mapper.py     |   584 +
 .../datasets/domain/repositories/__init__.py       |     5 -
 apps/api/app/modules/datasets/domain/repository.py |    16 +-
 apps/api/app/modules/datasets/domain/sample_row.py |    85 +
 apps/api/app/modules/datasets/domain/schemas.py    |     4 -
 .../api/app/modules/datasets/domain/storage_agg.py |   137 +
 .../infrastructure/repositories/repository.py      |   761 --
 .../app/modules/datasets/port/dataset_reader.py    |    22 +
 .../controllers => datasets/port/http}/__init__.py |     0
 apps/api/app/modules/datasets/port/http/deps.py    |   104 +
 .../port/http/extensions}/__init__.py              |     0
 .../http}/extensions/export_parquet_router.py      |    33 +-
 .../http}/extensions/import_parquet_router.py      |    82 +-
 .../port/http/extensions/prediction_router.py      |   142 +
 .../controllers => port/http}/router.py            |  1117 +-
 .../{interfaces/dtos => port/http}/schemas.py      |    44 +-
 .../app/modules/datasets/port/local/__init__.py    |    58 +
 .../app/modules/datasets/port/local/_protocols.py  |    92 +
 apps/api/app/modules/datasets/seed_runner.py       |    70 +
 apps/api/app/modules/datasets/storage/__init__.py  |     7 +
 apps/api/app/modules/datasets/storage/protocol.py  |    70 +
 apps/api/app/modules/datasets/tests/conftest.py    |   310 +
 .../modules/datasets/tests/test_annotation_crud.py |   216 +-
 .../modules/datasets/tests/test_dataset_routes.py  |   308 +-
 .../modules/datasets/tests/test_db_full_storage.py |   599 +
 .../app/modules/datasets/tests/test_detection.py   |    29 +-
 .../modules/datasets/tests/test_image_upload.py    |    25 +-
 .../datasets/tests/test_ls_annotation_sync.py      |   113 +-
 .../datasets/tests/test_ls_dataset_hooks.py        |     2 +-
 .../app/modules/datasets/tests/test_ls_export.py   |    42 +-
 .../datasets/tests/test_ls_image_resolve.py        |     2 +-
 .../modules/datasets/tests/test_ls_sample_hooks.py |     2 +-
 .../modules/datasets/tests/test_parquet_plugins.py |     6 +-
 .../datasets/tests/test_runtime_preservation.py    |    67 +
 apps/api/app/modules/datasets/tests/test_sc.py     |   114 +
 .../datasets/tests/test_session_sample_filter.py   |    44 +
 .../modules/datasets/tests/test_sparse_datasets.py |   714 +-
 .../modules/datasets/tests/test_sparse_storage.py  |   559 +
 .../datasets/tests/test_view_contract_specs.py     |     7 +
 .../datasets/tests/test_views_compatibility.py     |     7 +
 .../data => datasets/views}/__init__.py            |     0
 .../views/box_detection/v1}/__init__.py            |     0
 .../datasets/views/box_detection/v1/schemas.py     |    19 +
 apps/api/app/modules/datasets/views/deps.py        |    24 +
 .../views/image_input/v1}/__init__.py              |     0
 .../views/labeled_image/v1}/__init__.py            |     0
 .../datasets/views/labeled_image/v1/schemas.py     |     9 +
 .../views/qa_input/v1}/__init__.py                 |     0
 .../modules/datasets/views/qa_input/v1/schemas.py  |     9 +
 apps/api/app/modules/datasets/vqa/__init__.py      |    17 +
 apps/api/app/modules/datasets/vqa/models.py        |    55 +
 apps/api/app/modules/datasets/vqa/upstream.py      |    22 +
 .../infrastructure => embedding}/__init__.py       |     0
 .../{models/api => embedding/flows}/__init__.py    |     0
 apps/api/app/modules/embedding/flows/embed.py      |   124 +
 .../models/{application => adapter}/__init__.py    |     0
 .../domain => models/adapter/clients}/__init__.py  |     0
 .../adapter/repositories}/__init__.py              |     0
 .../repositories/repository.py                     |    24 +-
 apps/api/app/modules/models/api/deps.py            |    28 -
 .../models/{infrastructure => app}/__init__.py     |     0
 .../data => models/app/services}/__init__.py       |     0
 .../{application => app}/services/model_service.py |     9 +-
 apps/api/app/modules/models/container.py           |    19 +
 .../application => models/port/http}/__init__.py   |     0
 apps/api/app/modules/models/port/http/deps.py      |    24 +
 .../controllers => port/http}/router.py            |    24 +-
 .../{interfaces/dtos => port/http}/schemas.py      |     2 +-
 .../app/modules/models/tests/test_model_upload.py  |     6 +-
 .../{infrastructure => adapter}/__init__.py        |     0
 .../adapter/clients}/__init__.py                   |     0
 .../api => prediction/adapter/engines}/__init__.py |     0
 .../adapter/repositories}/__init__.py              |     0
 .../repositories/repository.py                     |    10 +-
 .../adapter/runtime}/__init__.py                   |     0
 .../{presets/domain => prediction/app}/__init__.py |     0
 .../app/services}/__init__.py                      |     0
 .../prediction/app/services/batch_lookup.py        |   128 +
 .../services/prediction_orchestrator.py            |     8 +-
 .../prediction/app/services/prediction_service.py  |   776 ++
 .../prediction/app/services/sparse_prediction.py   |   663 ++
 .../application/services/prediction_service.py     |  1138 --
 .../application/services/sparse_prediction.py      |   149 -
 apps/api/app/modules/prediction/container.py       |    41 +
 .../app/modules/prediction/domain/repository.py    |     2 +
 .../runtime => prediction/flows}/__init__.py       |     0
 .../prediction/flows/_predictors/__init__.py       |    47 +
 .../app/modules/prediction/flows/_predictors/sc.py |   171 +
 .../prediction/flows/_predictors/yolo_sc.py        |   171 +
 .../app/modules/prediction/flows/predict_job.py    |   802 ++
 .../prediction/infrastructure/flows/predict_job.py |   440 -
 .../services => prediction/port/http}/__init__.py  |     0
 .../modules/prediction/{api => port/http}/deps.py  |    85 +-
 .../controllers => port/http}/router.py            |   191 +-
 .../{interfaces/dtos => port/http}/schemas.py      |     5 +-
 .../prediction/tests/test_gpu_reliability.py       |   315 -
 .../prediction/tests/test_gpu_worker_client.py     |   610 -
 .../prediction/tests/test_prediction_flow.py       |   564 +-
 .../prediction/tests/test_prediction_review.py     |   151 +
 .../prediction/tests/test_prediction_routes.py     |     5 +
 .../tests/test_sparse_readback_compat.py           |   415 +
 .../modules/prediction/tests/test_vqa_runtime.py   |    52 +-
 apps/api/app/modules/presets/__init__.py           |    24 -
 apps/api/app/modules/presets/_registry.py          |   179 -
 apps/api/app/modules/presets/api/deps.py           |    14 -
 apps/api/app/modules/presets/clip_zero_shot_v1.py  |    62 -
 apps/api/app/modules/presets/dspy_vqa_v1.py        |    84 -
 .../presets/interfaces/controllers/router.py       |     5 -
 apps/api/app/modules/presets/registry.py           |   290 -
 apps/api/app/modules/presets/resnet50_cls_v1.py    |    82 -
 apps/api/app/modules/presets/runtime.py            |     3 -
 apps/api/app/modules/presets/schema.py             |   203 -
 .../infrastructure => preview/adapter}/__init__.py |     0
 .../adapter}/clients/__init__.py                   |     0
 .../clients/preview_upstream_s3.py                 |     4 +-
 .../adapter/repositories}/__init__.py              |     0
 .../preview/{api => adapter/tools}/__init__.py     |     0
 .../preview/{application => app}/__init__.py       |     0
 .../app/services}/__init__.py                      |     0
 .../services/preview_service.py                    |    44 +-
 .../{application => app}/services/preview_store.py |     0
 .../services/preview_upstream.py                   |     0
 apps/api/app/modules/preview/container.py          |    26 +
 .../controllers => preview/port/http}/__init__.py  |     0
 .../app/modules/preview/{api => port/http}/deps.py |    24 +-
 .../controllers => port/http}/router.py            |    10 +-
 .../{interfaces/dtos => port/http}/schemas.py      |     0
 .../modules/preview/tests/test_preview_routes.py   |     2 +-
 .../modules/preview/tests/test_preview_sessions.py |    53 +-
 apps/api/app/modules/registry.py                   |    40 +-
 .../{preview/infrastructure => sc}/__init__.py     |     0
 apps/api/app/modules/sc/adapter/__init__.py        |   199 +
 .../app/modules/sc/adapter/_wafer_mock/__init__.py |    33 +
 .../app/modules/sc/adapter/_wafer_mock/cache.py    |   183 +
 .../sc/adapter/_wafer_mock/image_service.py        |    72 +
 .../app/modules/sc/adapter/_wafer_mock/images.py   |   198 +
 .../app/modules/sc/adapter/_wafer_mock/models.py   |    98 +
 .../modules/sc/adapter/_wafer_mock/redis_cache.py  |   177 +
 .../api/app/modules/sc/adapter/_wafer_mock/seed.py |   743 ++
 .../sc/adapter/_wafer_mock/sqlite_upstream.py      |   322 +
 .../modules/sc/adapter/_wafer_mock/url_cache.py    |    26 +
 apps/api/app/modules/sc/adapter/batch_reader.py    |   105 +
 .../api => sc/adapter/flows}/__init__.py           |     0
 apps/api/app/modules/sc/adapter/flows/sc_import.py |   381 +
 .../app/modules/sc/adapter/sparse_aware_reader.py  |   100 +
 .../controllers/extensions => sc/app}/__init__.py  |     0
 .../dtos => sc/app/services}/__init__.py           |     0
 .../api/app/modules/sc/app/services/import_rows.py |    94 +
 .../modules/sc/app/services/sc_import_service.py   |   638 +
 .../sc/app/services/sc_plot_points_service.py      |   397 +
 .../sc/app/services/sparse_training_records.py     |   395 +
 .../app/modules/sc/app/services/sprite_service.py  |   174 +
 apps/api/app/modules/sc/container.py               |   122 +
 .../application/services => sc/domain}/__init__.py |     0
 .../application => sc/domain/entities}/__init__.py |     0
 .../app/modules/sc/domain/entities/sc_import.py    |    18 +
 apps/api/app/modules/sc/domain/geometry.py         |    40 +
 apps/api/app/modules/sc/domain/image_fetcher.py    |    32 +
 apps/api/app/modules/sc/domain/mapper.py           |   236 +
 apps/api/app/modules/sc/domain/models.py           |   148 +
 apps/api/app/modules/sc/domain/upstream_reader.py  |    70 +
 apps/api/app/modules/sc/models.py                  |    41 +
 .../infrastructure/clients => sc/port}/__init__.py |     0
 apps/api/app/modules/sc/port/http/__init__.py      |     5 +
 apps/api/app/modules/sc/port/http/deps.py          |    54 +
 apps/api/app/modules/sc/port/http/router.py        |  1019 ++
 apps/api/app/modules/sc/proto_adapter.py           |   268 +
 apps/api/app/modules/sc/sc_dataset_agg.py          |   364 +
 apps/api/app/modules/sc/schema.py                  |   244 +
 apps/api/app/modules/sc/schemas.py                 |   143 +
 .../infrastructure => sc/tests}/__init__.py        |     0
 apps/api/app/modules/sc/tests/conftest.py          |    75 +
 apps/api/app/modules/sc/tests/db_fixture.py        |    56 +
 apps/api/app/modules/sc/tests/fixtures.py          |    29 +
 apps/api/app/modules/sc/tests/test_geometry.py     |    92 +
 .../api/app/modules/sc/tests/test_proto_adapter.py |   492 +
 .../app/modules/sc/tests/test_redis_patch_cache.py |   197 +
 .../app/modules/sc/tests/test_sc_annotations.py    |   307 +
 .../app/modules/sc/tests/test_sc_dataset_detail.py |   159 +
 .../modules/sc/tests/test_sc_import_endpoint.py    |   145 +
 .../app/modules/sc/tests/test_sc_import_flow.py    |   748 ++
 .../app/modules/sc/tests/test_sc_import_schemas.py |    81 +
 .../app/modules/sc/tests/test_sc_import_service.py |   504 +
 .../sc/tests/test_sc_import_sparse_bytes.py        |   869 ++
 .../api/app/modules/sc/tests/test_sc_import_sse.py |   131 +
 .../app/modules/sc/tests/test_sc_import_status.py  |    55 +
 .../app/modules/sc/tests/test_sc_inspections.py    |   314 +
 .../app/modules/sc/tests/test_sc_plot_points.py    |   532 +
 apps/api/app/modules/sc/tests/test_sc_views.py     |   277 +
 apps/api/app/modules/sc/tests/test_seed_images.py  |    66 +
 .../sc/tests/test_sparse_training_records.py       |   519 +
 .../app/modules/sc/tests/test_sprite_service.py    |   118 +
 .../app/modules/sc/tests/test_sqlite_upstream.py   |   357 +
 .../app/modules/sc/tests/test_training_preview.py  |   330 +
 apps/api/app/modules/sc/tests/test_upstream.py     |   521 +
 apps/api/app/modules/sc/training/__init__.py       |     5 +
 apps/api/app/modules/sc/training/dataset.py        |   292 +
 .../repositories => sc/types}/__init__.py          |     0
 .../controllers => sc/views}/__init__.py           |     0
 .../dtos => sc/views/patch_image}/__init__.py      |     0
 .../modules/sc/views/patch_image/v1/__init__.py    |     3 +
 .../app/modules/sc/views/patch_image/v1/schemas.py |    44 +
 .../api => sc/views/review_image}/__init__.py      |     0
 .../modules/sc/views/review_image/v1/__init__.py   |     3 +
 .../modules/sc/views/review_image/v1/schemas.py    |    26 +
 apps/api/app/modules/sc/wafer_data_gen.py          |   158 +
 .../application => schedules/adapter}/__init__.py  |     0
 .../adapter/clients}/__init__.py                   |     0
 .../adapter/repositories}/__init__.py              |     0
 apps/api/app/modules/schedules/api/deps.py         |    18 -
 .../infrastructure => schedules/app}/__init__.py   |     0
 .../app/services}/__init__.py                      |     0
 .../{application => app}/services/scheduler.py     |     6 +-
 apps/api/app/modules/schedules/container.py        |    24 +
 .../application => schedules/port}/__init__.py     |     0
 .../port/http}/__init__.py                         |     0
 apps/api/app/modules/schedules/port/http/deps.py   |    14 +
 .../controllers => port/http}/router.py            |    18 +-
 .../{interfaces/dtos => port/http}/schemas.py      |     0
 .../schedules/tests/test_schedule_endpoints.py     |     2 +-
 .../api => sensors/adapter}/__init__.py            |     0
 .../adapter/clients}/__init__.py                   |     0
 .../dtos => sensors/adapter/flows}/__init__.py     |     0
 .../flows/dataset_size_sensor.py                   |     2 +-
 .../flows/sensor_base.py                           |     0
 .../flows/timer_sensor.py                          |     2 +-
 .../adapter/repositories}/__init__.py              |     0
 .../repositories/repository.py                     |     0
 .../application => sensors/app}/__init__.py        |     0
 .../entities => sensors/app/services}/__init__.py  |     0
 .../services/sensor_dispatch.py                    |     0
 apps/api/app/modules/sensors/container.py          |    29 +
 .../sensors/infrastructure/clients/__init__.py     |     1 -
 .../sensors/infrastructure/flows/__init__.py       |     1 -
 .../infrastructure/repositories/__init__.py        |     1 -
 .../sensors/infrastructure/yaml/dataset_size_sensor.yaml |    17 -
 .../sensors/infrastructure/yaml/timer_sensor.yaml  |    29 -
 .../modules/sensors/interfaces/dtos/__init__.py    |     1 -
 .../repositories => sensors/port}/__init__.py      |     0
 .../clients => sensors/port/http}/__init__.py      |     0
 .../app/modules/sensors/{api => port/http}/deps.py |     8 +-
 .../controllers => port/http}/router.py            |     6 +-
 .../sensors/tests/test_dataset_size_sensor_flow.py |     4 +-
 .../modules/sensors/tests/test_sensor_dispatch.py  |     4 +-
 .../sensors/tests/test_sensor_subscriptions.py     |     2 +-
 .../adapter}/__init__.py                           |     0
 .../adapter/clients}/__init__.py                   |     0
 .../adapter/repositories}/__init__.py              |     0
 .../repositories/repository.py                     |     0
 apps/api/app/modules/settings/api/__init__.py      |     9 -
 .../application => settings/app}/__init__.py       |     0
 .../dtos => settings/app/services}/__init__.py     |     0
 .../settings/application/services/__init__.py      |     1 -
 apps/api/app/modules/settings/container.py         |    30 +
 .../settings/infrastructure/clients/__init__.py    |     1 -
 .../infrastructure/repositories/__init__.py        |     1 -
 .../settings/interfaces/controllers/__init__.py    |     1 -
 .../modules/settings/interfaces/dtos/__init__.py   |     1 -
 .../port/http}/__init__.py                         |     0
 .../modules/settings/{api => port/http}/deps.py    |     2 +-
 .../controllers => port/http}/router.py            |     2 +-
 .../app/modules/task_tracker/adapter/__init__.py   |     0
 .../adapter/clients}/__init__.py                   |     0
 .../adapter/repositories}/__init__.py              |     0
 apps/api/app/modules/task_tracker/app/__init__.py  |     0
 .../app/services}/__init__.py                      |     0
 .../{application => app}/services/task_tracker.py  |    20 +-
 .../task_tracker/application/services/__init__.py  |     1 -
 apps/api/app/modules/task_tracker/container.py     |    29 +
 .../infrastructure/clients/__init__.py             |     1 -
 .../infrastructure/repositories/__init__.py        |     1 -
 .../interfaces/controllers/__init__.py             |     1 -
 .../task_tracker/interfaces/dtos/__init__.py       |     1 -
 .../port/http}/__init__.py                         |     0
 .../task_tracker/{api => port/http}/deps.py        |     8 +-
 .../controllers => port/http}/router.py            |    19 +-
 .../{interfaces/dtos => port/http}/schemas.py      |     2 +-
 .../modules/task_tracker/port/task_tracker_port.py |     9 +
 .../task_tracker/tests/test_task_tracker.py        |    42 +-
 apps/api/app/modules/training/adapter/__init__.py  |     0
 .../dtos => training/adapter/clients}/__init__.py  |     0
 .../clients/kubeflow_client.py                     |     0
 .../modules/training/adapter/engines/__init__.py   |     0
 .../engines/local_kubeflow.py                      |   252 +-
 .../engines/prefect_engine.py                      |    52 +-
 .../adapter/repositories}/__init__.py              |     0
 .../repositories/repository.py                     |    18 +-
 .../modules/training/adapter/runtime/__init__.py   |     0
 .../{infrastructure => adapter}/runtime/torch.py   |   125 +-
 apps/api/app/modules/training/api/deps.py          |    35 -
 apps/api/app/modules/training/app/__init__.py      |     0
 .../clients => training/app/services}/__init__.py  |     0
 .../{application => app}/services/orchestrator.py  |     0
 .../training/application/services/__init__.py      |     1 -
 apps/api/app/modules/training/container.py         |   108 +
 apps/api/app/modules/training/flows/__init__.py    |     0
 .../modules/training/flows/_trainers/__init__.py   |     0
 .../api/app/modules/training/flows/_trainers/sc.py |   378 +
 .../modules/training/flows/_trainers/yolo_sc.py    |   194 +
 apps/api/app/modules/training/flows/train_job.py   |   309 +
 .../training/infrastructure/clients/__init__.py    |     1 -
 .../training/infrastructure/flows/train_job.py     |   169 -
 .../infrastructure/repositories/__init__.py        |     1 -
 .../training/infrastructure/runtime/dspy.py        |   193 -
 .../infrastructure/runtime/training_runner.py      |   250 -
 .../training/interfaces/controllers/__init__.py    |     1 -
 .../modules/training/interfaces/dtos/__init__.py   |     1 -
 .../port/http}/__init__.py                         |     0
 apps/api/app/modules/training/port/http/deps.py    |    23 +
 .../controllers => port/http}/router.py            |   118 +-
 .../{interfaces/dtos => port/http}/schemas.py      |     2 +-
 .../app/modules/training/tests/test_embedding.py   |    38 +-
 .../training/tests/test_flow_worker_bootstrap.py   |   119 -
 .../app/modules/training/tests/test_train_flow.py  |   477 +-
 .../training/tests/test_training_metrics_events.py |   202 +
 .../modules/training/tests/test_training_routes.py |    10 +-
 .../modules/training/tests/test_training_runner.py |   207 +-
 .../interfaces/controllers => types}/__init__.py   |     0
 apps/api/app/modules/types/catalog.py              |    99 +
 .../dtos => types/predictors}/__init__.py          |     0
 apps/api/app/modules/types/predictors/clip.py      |   158 +
 apps/api/app/modules/types/predictors/detection.py |    15 +
 apps/api/app/modules/types/predictors/dspy_vqa.py  |    15 +
 apps/api/app/modules/types/predictors/resnet.py    |    17 +
 .../{sensors/api => types/trainers}/__init__.py    |     0
 apps/api/app/registrations.py                      |    27 +
 apps/api/app/shared/api/internal_schemas.py        |    16 +-
 apps/api/app/shared/api/schemas.py                 |    74 +-
 apps/api/app/shared/api/utils.py                   |    10 +-
 apps/api/app/shared/application/compatibility.py   |   118 +-
 apps/api/app/shared/context.py                     |   122 +
 apps/api/app/shared/db/models/auth.py              |     4 +-
 apps/api/app/shared/db/models/datasets.py          |     3 +-
 apps/api/app/shared/db/models/prediction.py        |     4 +-
 apps/api/app/shared/db/models/training.py          |    15 +-
 apps/api/app/shared/db/sql_repository.py           |   242 +-
 .../api/app/shared/db/tests/test_sql_repository.py |    62 +
 apps/api/app/shared/domain/protocols.py            |    71 +-
 apps/api/app/shared/domain/runtime.py              |   185 +-
 apps/api/app/shared/generated/openapi_models.py    |   892 +-
 .../shared/infrastructure/label_studio/client.py   |    40 +-
 apps/api/app/shared/infrastructure/llm/client.py   |    12 +-
 apps/api/app/shared/infrastructure/llm/factory.py  |    15 +
 .../app/shared/infrastructure/prefect/client.py    |    61 +
 .../shared/infrastructure/prefect/flow_serve.py    |   232 -
 .../app/shared/infrastructure/storage/factory.py   |    25 +
 .../app/shared/infrastructure/storage/memory.py    |     4 +-
 .../api/app/shared/infrastructure/storage/minio.py |    62 +-
 .../api/app/shared/infrastructure/workers/embedding.py |   182 -
 .../shared/infrastructure/workers/gpu_worker.py    |   259 -
 .../infrastructure/workers/inference_worker.py     |    77 -
 apps/api/app/shared/seed_images.py                 |    56 +
 .../services => shared/sse}/__init__.py            |     0
 apps/api/app/shared/sse/emit.py                    |     7 +
 apps/api/app/shared/sse/events.py                  |    97 +
 apps/api/config/base.yaml                          |    30 +-
 apps/api/config/dev.yaml                           |    10 +
 apps/api/config/test.yaml                          |     4 +
 apps/api/conftest.py                               |   121 +-
 apps/api/presets/clip-zero-shot-v1/preset.yaml     |    75 -
 apps/api/presets/dspy-vqa-v1/preset.yaml           |    54 -
 apps/api/presets/resnet50-cls-v1/preset.yaml       |   104 -
 apps/api/pyproject.toml                            |   109 +-
 apps/api/tests/__init__.py                         |     0
 apps/api/tests/bench_ls_import.py                  |     9 +-
 apps/api/tests/bench_sample_upload.py              |     4 +-
 apps/api/tests/conftest.py                         |   319 +-
 apps/api/tests/helpers/factories.py                |     8 +-
 apps/api/tests/helpers/fixtures.py                 |    29 +-
 apps/api/tests/temp_bdd_wafer_e2e.py               |  1609 +++
 apps/api/tests/test_api_flows.py                   |    95 +-
 apps/api/tests/test_architecture_boundaries.py     |   110 +
 apps/api/tests/test_artifact_download.py           |     6 +-
 apps/api/tests/test_catalog_endpoints.py           |    42 +
 apps/api/tests/test_classification_embed.py        |   298 +
 apps/api/tests/test_clip_predictor.py              |   172 +
 apps/api/tests/test_compatibility.py               |   635 +
 apps/api/tests/test_data_integrity.py              |   977 ++
 apps/api/tests/test_e2e_training.py                |   234 +
 apps/api/tests/test_health.py                      |    33 +-
 apps/api/tests/test_latest_predictions.py          |   133 +
 apps/api/tests/test_mapper_registry.py             |   296 +
 apps/api/tests/test_ml_package.py                  |   209 +
 apps/api/tests/test_openapi_sync.py                |    47 +
 apps/api/tests/test_plot_points_filter.py          |   176 +
 apps/api/tests/test_predictor_registry.py          |   137 +
 apps/api/tests/test_prefect_deployments_seed.py    |   116 +
 apps/api/tests/test_proto_sync.py                  |    40 +
 apps/api/tests/test_registry.py                    |   210 +
 apps/api/tests/test_registry_audit.py              |   620 +
 apps/api/tests/test_runtime_bucket_config.py       |   108 +
 apps/api/tests/test_sc_image_endpoint.py           |   220 +
 apps/api/tests/test_sc_proto_adapter.py            |   157 +
 apps/api/tests/test_sparse_import_operator.py      |   240 +
 apps/api/tests/test_sse_emit.py                    |    74 +
 apps/api/tests/test_sse_schema.py                  |   240 +
 apps/api/tests/test_view_endpoints.py              |   449 +
 apps/api/tests/test_view_loader_contract.py        |   106 +
 apps/api/tests/test_yolo_registry.py               |   239 +
 apps/embedding/Dockerfile                          |    28 -
 apps/embedding/__init__.py                         |     1 -
 apps/embedding/app/__init__.py                     |     1 -
 apps/embedding/app/__main__.py                     |    11 -
 apps/embedding/app/server.py                       |   183 -
 apps/embedding/pyproject.toml                      |    16 -
 apps/inference/Dockerfile                          |    26 -
 apps/inference/app/__init__.py                     |     1 -
 apps/inference/app/job_registry.py                 |   191 -
 apps/inference/app/main.py                         |   510 -
 apps/inference/app/metrics.py                      |    44 -
 apps/inference/app/train_handler.py                |   296 -
 apps/inference/pyproject.toml                      |    20 -
 apps/inference/tests/conftest.py                   |     8 -
 apps/inference/tests/test_main.py                  |   919 --
 apps/web/.prettierignore                           |     3 +
 apps/web/.storybook/main.ts                        |     3 +-
 apps/web/.storybook/preview.ts                     |     7 +
 apps/web/AGENTS.md                                 |    85 +-
 apps/web/Dockerfile                                |    30 +-
 apps/web/apps/web/components.d.ts                  |    17 +
 apps/web/components.d.ts                           |     2 -
 apps/web/e2e-live/global-setup.ts                  |   103 -
 apps/web/e2e-live/helpers/auth.ts                  |    81 -
 apps/web/e2e-live/helpers/index.ts                 |    11 -
 apps/web/e2e-live/helpers/navigation.ts            |   123 -
 apps/web/e2e-live/playwright.config.ts             |    22 -
 apps/web/e2e-live/tests/agent-chat.spec.ts         |   155 -
 apps/web/e2e-live/tests/auth.spec.ts               |    48 -
 apps/web/e2e-live/tests/dashboard.spec.ts          |    58 -
 apps/web/e2e-live/tests/datasets.spec.ts           |   143 -
 apps/web/e2e-live/tests/imagenet-workflow.spec.ts  |    73 -
 apps/web/e2e-live/tests/labelstudio.spec.ts        |    66 -
 apps/web/e2e-live/tests/placeholder.spec.ts        |     3 -
 apps/web/e2e-live/tests/samples.spec.ts            |   169 -
 apps/web/e2e-live/tests/schedules.spec.ts          |    84 -
 apps/web/e2e-live/tests/training.spec.ts           |   152 -
 apps/web/e2e-live/tests/vqa.spec.ts                |   118 -
 apps/web/e2e/auth-and-datasets.spec.ts             |   193 -
 apps/web/e2e/classify-workflow.spec.ts             |   407 -
 apps/web/e2e/dataset-samples.spec.ts               |   231 -
 apps/web/e2e/preview-workflow.spec.ts              |   301 -
 apps/web/e2e/sample-browser-virtualization.spec.ts |   168 -
 apps/web/e2e/wafer-map.spec.ts                     |   277 -
 apps/web/orval.config.ts                           |    24 +
 apps/web/package.json                              |    28 +-
 apps/web/playwright.config.ts                      |    23 -
 apps/web/src/app/App.vue                           |    40 +-
 apps/web/src/app/layouts/AdminLayout.vue           |     1 -
 apps/web/src/app/main.ts                           |    29 +-
 apps/web/src/app/registrations.ts                  |     7 +-
 apps/web/src/app/router.ts                         |     2 +
 .../features/agent/application/useAgentAdapter.ts  |    12 +-
 apps/web/src/features/agent/infrastructure/api.ts  |   118 -
 apps/web/src/features/auth/application/org.ts      |    53 +-
 apps/web/src/features/auth/application/store.ts    |   103 +-
 apps/web/src/features/auth/application/ui.ts       |    20 +-
 apps/web/src/features/auth/domain/models.ts        |    29 -
 apps/web/src/features/auth/infrastructure/api.ts   |   105 -
 .../features/auth/presentation/pages/LoginView.vue |    48 +-
 .../auth/presentation/pages/OAuthCallbackView.vue  |    21 +-
 .../auth/presentation/pages/OAuthRegisterView.vue  |    46 +-
 .../auth/presentation/pages/RegisterView.vue       |    23 +-
 .../src/features/classify/application/actions.ts   |    11 +-
 .../classify/application/buildBlinkTableData.ts    |    71 -
 .../classify/application/useClassifyPage.ts        |   258 +-
 .../classify/application/useImageAdapters.ts       |    57 -
 apps/web/src/features/classify/config.ts           |    44 +-
 .../src/features/classify/infrastructure/api.ts    |   145 -
 .../components/ClassifyAddLabelModal.stories.ts    |    95 +
 .../components/ClassifyBrowserArea.stories.ts      |    90 +
 .../components/ClassifyBrowserArea.vue             |    59 +-
 .../components/ClassifyPredictionJobs.stories.ts   |   140 +
 .../components/ClassifySidebar.stories.ts          |    37 +
 .../presentation/components/ClassifySidebar.vue    |     2 +-
 .../components/ClassifyWorkflowCards.stories.ts    |    94 +
 .../components/ClassifyWorkflowCards.vue           |    12 +-
 .../presentation/pages/ClassifyView.stories.ts     |   176 +
 .../classify/presentation/pages/ClassifyView.vue   |    27 +-
 .../classify/presentation/widgets/descriptors.ts   |    45 -
 .../classify/presentation/widgets/widgetMap.ts     |     2 -
 apps/web/src/features/dashboard/domain/models.ts   |    10 +-
 .../src/features/dashboard/infrastructure/api.ts   |     6 -
 .../dashboard/presentation/pages/DashboardView.vue |    43 +-
 .../src/features/datasets/application/surface.ts   |    17 +
 .../web/src/features/datasets/application/types.ts |   100 -
 .../datasets/application/useDatasetBrowser.ts      |    34 +-
 .../features/datasets/application/useFeatureOps.ts |     7 +-
 apps/web/src/features/datasets/domain/models.ts    |    69 -
 .../src/features/datasets/infrastructure/api.ts    |   294 -
 .../presentation/__tests__/view-routing.spec.ts    |   185 +
 .../components/DatasetPredictTab.stories.ts        |    19 +
 .../presentation/components/DatasetPredictTab.vue  |     7 +-
 .../components/DatasetSparseSummary.stories.ts     |    58 +
 .../components/DatasetSparseSummary.vue            |    26 +-
 .../components/DatasetTrainTab.stories.ts          |    19 +
 .../presentation/components/DatasetTrainTab.vue    |    38 +-
 .../components/ManualDatasetImporter.vue           |    15 +-
 .../presentation/components/ManualImporter.vue     |     2 +-
 .../components/ParquetExportPlugin.vue             |    17 +-
 .../presentation/components/ParquetImporter.vue    |    24 +-
 .../components/PersistExportPlugin.vue             |    13 +-
 .../dataset-types/classification}/index.ts         |     0
 .../dataset-types/classification}/registrations.ts |     0
 .../views/LabeledImageView.stories.ts              |    40 +
 .../classification/views/LabeledImageView.vue      |    86 +
 .../classification}/views/ListShim.stories.ts      |     2 +-
 .../classification}/views/ListShim.vue             |    10 +-
 .../dataset-types/classification}/views/schema.ts  |     2 +
 .../presentation/dataset-types/detection}/index.ts |     0
 .../dataset-types/detection}/registrations.ts      |     0
 .../detection/views/BoxDetectionView.stories.ts    |    52 +
 .../detection/views/BoxDetectionView.vue           |   113 +
 .../detection}/views/ListShim.stories.ts           |    18 +-
 .../dataset-types/detection}/views/ListShim.vue    |    18 +-
 .../dataset-types/detection}/views/schema.ts       |     2 +
 .../presentation/dataset-types/sc}/index.ts        |     0
 .../dataset-types/sc}/registrations.ts             |     0
 .../dataset-types/sc/views/ListShim.vue            |   119 +
 .../dataset-types/sc/views/ScPatchImageView.vue    |   415 +
 .../presentation/dataset-types/sc/views/schema.ts  |    23 +
 .../presentation/dataset-types/vqa/index.ts}       |     0
 .../dataset-types/vqa/registrations.ts             |     1 +
 .../dataset-types/vqa}/views/ListShim.stories.ts   |     2 +-
 .../dataset-types/vqa}/views/ListShim.vue          |    10 +-
 .../dataset-types/vqa/views/QAInputView.stories.ts |    46 +
 .../dataset-types/vqa/views/QAInputView.vue        |    86 +
 .../dataset-types/vqa}/views/schema.ts             |     2 +
 .../presentation/pages/DatasetDetailView.vue       |   173 +-
 .../presentation/pages/DatasetListView.vue         |    22 +-
 .../presentation/pages/DatasetViewPage.vue         |    99 +
 .../datasets/presentation/pages/registry.spec.ts   |    26 +-
 .../datasets/presentation/pages/registry.ts        |     4 +-
 .../datasets/presentation/pages/schema-registry.ts |   102 +-
 .../datasets/presentation/pages/selection.ts       |    11 +-
 apps/web/src/features/datasets/router.ts           |     5 +-
 apps/web/src/features/models/infrastructure/api.ts |     6 -
 .../src/features/prediction/infrastructure/api.ts  |   176 -
 .../presentation/pages/PredictionJobsView.vue      |   144 +-
 apps/web/src/features/presets/router.ts            |     2 -
 .../preview/application/usePreviewLoader.ts        |    71 -
 .../features/preview/application/usePreviewPage.ts |    17 +-
 .../web/src/features/preview/infrastructure/api.ts |    50 -
 .../preview-item-drawer/PreviewItemDrawer.vue      |     2 +-
 .../RChannelDenoiseSandboxView.vue                 |     2 +-
 apps/web/src/features/sc/__tests__/api.spec.ts     |   159 +
 apps/web/src/features/sc/api/boxFilter.ts          |    66 +
 apps/web/src/features/sc/api/classList.ts          |    52 +
 apps/web/src/features/sc/api/plotPoints.ts         |   105 +
 .../__tests__/useDieCoordinates.spec.ts            |    82 +
 .../__tests__/useReclassifyPage.spec.ts            |   514 +
 .../src/features/sc/application/reclassifyStore.ts |    15 +
 .../features/sc/application/reticleMapOptions.ts   |    34 +
 .../features/sc/application/useDieCoordinates.ts   |    35 +
 .../src/features/sc/application/usePreviewPage.ts  |   892 ++
 .../features/sc/application/useReclassifyPage.ts   |  1226 ++
 .../web/src/features/sc/application/useScPoints.ts |    39 +
 .../features/sc/domain/__tests__/models.spec.ts    |   146 +
 apps/web/src/features/sc/domain/models.ts          |   130 +
 .../features/sc/generated/proto/sc/v1/sample_pb.ts |   476 +
 .../components/InspectionQuad.stories.ts           |   185 +
 .../sc/presentation/components/InspectionQuad.vue  |   485 +
 .../components/ScDieStackMap.stories.ts            |    31 +
 .../sc/presentation/components/ScDieStackMap.vue   |   137 +
 .../sc/presentation/components/ScFilterPanel.vue   |   108 +
 .../sc/presentation/components/ScLegend.vue        |   171 +
 .../presentation/components/ScMapPanel.stories.ts  |   156 +
 .../sc/presentation/components/ScMapPanel.vue      |   687 ++
 .../components/ScPreviewBlinkVirtualTable.vue      |    49 +
 .../components/ScReclassifyBlinkVirtualTable.vue   |   156 +
 .../components/ScReticleMap.stories.ts             |    41 +
 .../sc/presentation/components/ScReticleMap.vue    |   183 +
 .../components/ScReticleMapOptionsButton.vue       |   126 +
 .../components/ScSampleTable.stories.ts            |    45 +
 .../sc/presentation/components/ScSampleTable.vue   |   434 +
 .../presentation/components/ScWaferMap.stories.ts  |    29 +
 .../sc/presentation/components/ScWaferMap.vue      |   298 +
 .../components/SimpleDieStackMap.stories.ts        |    79 +
 .../presentation/components/SimpleDieStackMap.vue  |   281 +
 .../sc/presentation/components/SimpleMapPoint.ts   |     9 +
 .../components/SimpleReticleMap.stories.ts         |    83 +
 .../presentation/components/SimpleReticleMap.vue   |   314 +
 .../components/SimpleWaferMap.stories.ts           |   117 +
 .../sc/presentation/components/SimpleWaferMap.vue  |   499 +
 .../components/__tests__/InspectionQuad.spec.ts    |   122 +
 .../components/__tests__/ScDieStackMap.spec.ts     |   116 +
 .../components/__tests__/ScLegend.spec.ts          |   126 +
 .../components/__tests__/ScMapPanel.spec.ts        |   435 +
 .../ScReclassifyBlinkVirtualTable.spec.ts          |   121 +
 .../components/__tests__/ScReticleMap.spec.ts      |   115 +
 .../components/__tests__/ScWaferMap.spec.ts        |   418 +
 .../components/__tests__/scMapFixtures.spec.ts     |   133 +
 .../components/__tests__/scMapFixtures.ts          |    82 +
 .../components/__tests__/scMapUtils.spec.ts        |   287 +
 .../sc/presentation/components/scMapUtils.ts       |   197 +
 .../features/sc/presentation/components/types.ts   |     8 +
 .../presentation/composables/useBlinkRubberBand.ts |   170 +
 .../composables/useBlinkVirtualScroll.ts           |   138 +
 .../sc/presentation/pages/PreviewPage.stories.ts   |   211 +
 .../features/sc/presentation/pages/PreviewPage.vue |   461 +
 .../presentation/pages/ReclassifyPage.stories.ts   |   147 +
 .../sc/presentation/pages/ReclassifyPage.vue       |   784 ++
 apps/web/src/features/sc/proto/sc/v1/sample.proto  |   130 +
 apps/web/src/features/sc/router.ts                 |    23 +
 apps/web/src/features/schedules/domain/models.ts   |    17 -
 .../src/features/schedules/infrastructure/api.ts   |    68 -
 .../presentation/pages/ScheduleDetailView.vue      |   142 +-
 .../schedules/presentation/pages/SchedulesView.vue |    97 +-
 apps/web/src/features/sensors/domain/models.ts     |    13 -
 .../web/src/features/sensors/infrastructure/api.ts |    35 -
 .../presentation/pages/SensorSubscriptionModal.vue |    63 +-
 .../sensors/presentation/pages/SensorsView.vue     |    61 +-
 .../src/features/settings/infrastructure/api.ts    |     7 -
 .../settings/presentation/pages/SettingsView.vue   |    60 +-
 .../features/task_tracker/infrastructure/api.ts    |    14 -
 .../presentation/pages/TaskExplorerView.vue        |     4 +-
 .../features/training/application/useJobEvents.ts  |     2 +-
 .../src/features/training/infrastructure/api.ts    |    64 -
 .../training/presentation/pages/JobDetailView.vue  |    76 +-
 .../presentation/pages/TrainingJobsView.vue        |   166 +-
 apps/web/src/generated/openapi-types.ts            |  6878 -----------
 apps/web/src/generated/orval/endpoints/api.ts      | 11857 +++++++++++++++++++
 .../src/generated/orval/models/addMemberRequest.ts |    11 +
 .../web/src/generated/orval/models/agentContext.ts |    29 +
 .../orval/models/agentContextDatasetId.ts          |    11 +
 .../generated/orval/models/agentContextExtra.ts    |    11 +
 .../generated/orval/models/agentContextJobId.ts    |    11 +
 .../orval/models/agentContextScheduleId.ts         |    11 +
 .../generated/orval/models/agentPanelDescriptor.ts |    40 +
 .../orval/models/agentPanelDescriptorConfig.ts     |    11 +
 .../orval/models/agentPanelDescriptorData.ts       |    12 +
 .../orval/models/agentPanelDescriptorDataAnyOf.ts  |     8 +
 .../orval/models/agentPanelDescriptorDataSource.ts |    13 +
 .../orval/models/agentPanelDescriptorTtl.ts        |    11 +
 apps/web/src/generated/orval/models/annotation.ts  |    16 +
 .../orval/models/annotationAnnotationValue.ts      |     9 +
 .../orval/models/annotationAnnotationValueAnyOf.ts |     8 +
 .../orval/models/annotationVersionResponse.ts      |    22 +
 .../models/annotationVersionResponseConfidence.ts  |     8 +
 .../annotationVersionResponsePredictionId.ts       |     8 +
 apps/web/src/generated/orval/models/artifactRef.ts |    24 +
 .../generated/orval/models/artifactRefCreatedAt.ts |     8 +
 .../generated/orval/models/artifactRefFileHash.ts  |     8 +
 .../generated/orval/models/artifactRefFileSize.ts  |     8 +
 .../generated/orval/models/artifactRefFormat.ts    |     8 +
 .../generated/orval/models/artifactRefMetadata.ts  |     8 +
 .../src/generated/orval/models/artifactRefName.ts  |     8 +
 ...rtParquetApiV1PluginsImportParquetImportPost.ts |    10 +
 ...esApiV1DatasetsDatasetIdSamplesImportVqaPost.ts |    10 +
 .../models/bodyUploadModelApiV1ModelsUploadPost.ts |    11 +
 ...V1DatasetsDatasetIdSamplesSampleIdUploadPost.ts |    10 +
 .../generated/orval/models/bulkAnnotationItem.ts   |    12 +
 .../orval/models/bulkAnnotationRequest.ts          |    11 +
 .../orval/models/bulkAnnotationResponse.ts         |    10 +
 .../generated/orval/models/bulkCreateSampleItem.ts |    14 +
 .../orval/models/bulkCreateSampleItemLabel.ts      |     8 +
 .../orval/models/bulkCreateSampleItemMetadata.ts   |     8 +
 .../orval/models/bulkCreateSampleRequest.ts        |    11 +
 .../orval/models/bulkCreateSampleResponse.ts       |    15 +
 .../generated/orval/models/cancelJobResponse.ts    |    10 +
 apps/web/src/generated/orval/models/chatRequest.ts |    17 +
 .../orval/models/createAnnotationRequest.ts        |    15 +
 .../createAnnotationRequestAnnotationValue.ts      |     9 +
 .../createAnnotationRequestAnnotationValueAnyOf.ts |     8 +
 .../generated/orval/models/createDatasetRequest.ts |    16 +
 .../models/createDatasetRequestDatasetType.ts      |     8 +
 .../src/generated/orval/models/createOrgRequest.ts |    11 +
 .../orval/models/createPreviewSessionRequest.ts    |    10 +
 .../orval/models/createReviewActionRequest.ts      |    25 +
 .../createReviewActionRequestCollectionId.ts       |    11 +
 .../createReviewActionRequestModelVersion.ts       |    11 +
 .../models/createReviewActionRequestSyncTag.ts     |    11 +
 .../generated/orval/models/createSampleRequest.ts  |    12 +
 .../orval/models/createSampleRequestMetadata.ts    |     8 +
 .../orval/models/createScheduleRequest.ts          |    15 +
 .../models/createScheduleRequestParameters.ts      |     8 +
 .../orval/models/createSubscriptionRequest.ts      |    13 +
 .../createSubscriptionRequestFilterConfig.ts       |     8 +
 .../generated/orval/models/createTokenRequest.ts   |    10 +
 .../orval/models/createTrainingJobRequest.ts       |    12 +
 .../generated/orval/models/dashboardResponse.ts    |    18 +
 .../orval/models/dashboardResponseWorkPool.ts      |     9 +
 .../src/generated/orval/models/dataSourceApi.ts    |    22 +
 .../generated/orval/models/dataSourceApiParams.ts  |     8 +
 .../generated/orval/models/dataSourceContext.ts    |    17 +
 .../orval/models/dataSourceContextPath.ts          |     8 +
 apps/web/src/generated/orval/models/dataset.ts     |    32 +
 .../orval/models/datasetAnnotationStats.ts         |    14 +
 .../models/datasetAnnotationStatsLabelCounts.ts    |     8 +
 .../generated/orval/models/datasetCapabilities.ts  |     9 +
 .../orval/models/datasetCapabilitiesAnyOf.ts       |     8 +
 .../generated/orval/models/datasetDatasetMeta.ts   |     8 +
 .../generated/orval/models/datasetEmbedConfig.ts   |     8 +
 .../generated/orval/models/datasetLsProjectId.ts   |     8 +
 .../generated/orval/models/datasetLsProjectUrl.ts  |     8 +
 .../web/src/generated/orval/models/datasetOrgId.ts |     8 +
 .../orval/models/datasetStatusResponse.ts          |    12 +
 .../generated/orval/models/datasetStorageMode.ts   |    15 +
 ...tionApiV1AnnotationsAnnotationIdDeleteParams.ts |    13 +
 ...V1SensorsSensorIdSubscriptionsSubIdDelete200.ts |     8 +
 .../deleteSettingApiV1SettingsKeyDelete200.ts      |     8 +
 .../downloadExportApiV1ExportsDownloadGetParams.ts |    10 +
 .../generated/orval/models/embedConfigResponse.ts  |    11 +
 .../exportDatasetApiV1ExportsDatasetIdGet200.ts    |     8 +
 .../generated/orval/models/exportFormatResponse.ts |    13 +
 ...arquetApiV1PluginsExportParquetExportPost200.ts |     8 +
 ...uetApiV1PluginsExportParquetExportPostParams.ts |    10 +
 ...onApiV1PredictionReviewsActionIdExportGet200.ts |     8 +
 ...piV1PredictionReviewsActionIdExportGetParams.ts |    10 +
 ...V1DatasetsDatasetIdFeaturesExtractPostParams.ts |    10 +
 ...ionsInspectionTimeWaferKeyClassListGetParams.ts |    17 +
 ...ionsInspectionTimeWaferKeyMapPointsGetParams.ts |    28 +
 .../getInspectionsApiV1ScInspectionsGetParams.ts   |    11 +
 ...ApiV1TrainingJobsJobIdEventsHistoryGetParams.ts |    11 +
 ...tesPatchBatchInspectionTimeWaferKeyGetParams.ts |    11 +
 ...PatchInspectionTimeWaferKeyDefectIdGetParams.ts |    10 +
 ...esReviewBatchInspectionTimeWaferKeyGetParams.ts |    12 +
 ...eviewInspectionTimeWaferKeyDefectIdGetParams.ts |    11 +
 .../getRunLogsApiV1RunsRunIdLogsGetParams.ts       |    10 +
 ...stApiV1ScDatasetsDatasetIdClassListGetParams.ts |    17 +
 ...sApiV1ScDatasetsDatasetIdPlotPointsGetParams.ts |    23 +
 .../getTrainerRouteApiV1TrainersTrainerIdGet200.ts |     8 +
 .../generated/orval/models/globalChatRequest.ts    |    22 +
 .../orval/models/globalChatRequestSessionId.ts     |    11 +
 .../generated/orval/models/hTTPValidationError.ts  |    11 +
 .../generated/orval/models/healthHealthGet200.ts   |     8 +
 ...uetApiV1PluginsImportParquetImportPostParams.ts |    10 +
 .../orval/models/importVqaJsonlResponse.ts         |    13 +
 apps/web/src/generated/orval/models/index.ts       |   384 +
 .../src/generated/orval/models/jobQueueStats.ts    |    14 +
 apps/web/src/generated/orval/models/jobStatus.ts   |    18 +
 .../src/generated/orval/models/latestAnnotation.ts |    13 +
 .../models/listJobsApiV1TrainingJobsGetParams.ts   |    13 +
 .../orval/models/listModelsApiV1ModelsGetParams.ts |    11 +
 ...llectionsApiV1PredictionCollectionsGetParams.ts |    10 +
 ...ApiV1PredictionJobsJobIdPredictionsGetParams.ts |    17 +
 ...sApiV1PreviewSessionsSessionIdItemsGetParams.ts |    11 +
 ...ReviewActionsApiV1PredictionReviewsGetParams.ts |    10 +
 ...istRunsApiV1SchedulesScheduleIdRunsGetParams.ts |    10 +
 ...ionsApiV1SamplesSampleIdPredictionsGetParams.ts |    14 +
 ...amplesApiV1DatasetsDatasetIdSamplesGetParams.ts |    11 +
 ...1DatasetsDatasetIdSamplesWithLabelsGetParams.ts |    14 +
 .../models/listSettingsApiV1SettingsGet200.ts      |     8 +
 ...skTrackerTasksApiV1TaskTrackerTasksGetParams.ts |    10 +
 .../listTrainersRouteApiV1TrainersGet200Item.ts    |     8 +
 ...tasetsDatasetIdViewsViewTypeSamplesGetParams.ts |    14 +
 .../web/src/generated/orval/models/loginRequest.ts |    11 +
 .../src/generated/orval/models/loginResponse.ts    |    12 +
 .../src/generated/orval/models/markLeftResponse.ts |    10 +
 .../src/generated/orval/models/memberResponse.ts   |    15 +
 .../generated/orval/models/membershipResponse.ts   |    13 +
 .../src/generated/orval/models/modelResponse.ts    |    28 +
 .../orval/models/modelResponseCreatedAt.ts         |     8 +
 .../orval/models/modelResponseFileHash.ts          |     8 +
 .../orval/models/modelResponseFileSize.ts          |     8 +
 .../generated/orval/models/modelResponseFormat.ts  |     8 +
 .../orval/models/modelResponseMetadata.ts          |     8 +
 .../generated/orval/models/modelResponseName.ts    |     8 +
 .../orval/models/modelUploadTemplateResponse.ts    |    17 +
 .../generated/orval/models/oAuthProviderInfo.ts    |    12 +
 .../generated/orval/models/oAuthRegisterRequest.ts |    11 +
 ...lbackApiV1AuthOauthProviderCallbackGetParams.ts |    11 +
 apps/web/src/generated/orval/models/orgResponse.ts |    13 +
 .../orval/models/paginatedResponseSample.ts        |    12 +
 .../models/paginatedResponseSampleWithLabels.ts    |    12 +
 .../orval/models/paginatedResponseTrainingEvent.ts |    12 +
 .../orval/models/persistExportResponse.ts          |    10 +
 .../orval/models/persistStatusResponse.ts          |    16 +
 .../orval/models/persistStatusResponseError.ts     |     8 +
 .../generated/orval/models/predictSingleRequest.ts |    26 +
 .../models/predictSingleRequestModelVersion.ts     |    11 +
 .../orval/models/predictSingleRequestPrompt.ts     |    11 +
 .../orval/models/predictionCollectionRequest.ts    |    18 +
 .../predictionCollectionRequestModelVersion.ts     |     8 +
 .../predictionCollectionRequestSourceJobId.ts      |     8 +
 .../orval/models/predictionCollectionResponse.ts   |    23 +
 .../predictionCollectionResponseModelVersion.ts    |     8 +
 .../predictionCollectionResponseSourceJobId.ts     |     8 +
 .../models/predictionCollectionResponseSyncTag.ts  |     8 +
 .../orval/models/predictionEventResponse.ts        |    15 +
 .../orval/models/predictionEventResponsePayload.ts |     8 +
 .../orval/models/predictionJobResponse.ts          |    25 +
 .../models/predictionJobResponseExternalJobId.ts   |     8 +
 .../models/predictionJobResponseModelVersion.ts    |     8 +
 .../orval/models/predictionJobResponseSampleIds.ts |     8 +
 .../orval/models/predictionJobResponseSummary.ts   |     8 +
 .../orval/models/predictionResultResponse.ts       |    30 +
 .../models/predictionResultResponseConfidence.ts   |     8 +
 .../models/predictionResultResponseCreatedAt.ts    |     8 +
 .../orval/models/predictionResultResponseError.ts  |     8 +
 .../orval/models/predictionResultResponseId.ts     |     8 +
 .../orval/models/predictionResultResponseJobId.ts  |     8 +
 .../models/predictionResultResponseModelId.ts      |     8 +
 .../models/predictionResultResponseModelVersion.ts |     8 +
 .../orval/models/predictionResultResponseTarget.ts |     8 +
 .../generated/orval/models/previewItemResponse.ts  |    13 +
 .../orval/models/previewItemResponseMetadata.ts    |     8 +
 .../generated/orval/models/previewItemsResponse.ts |    16 +
 .../models/previewItemsResponseEstimatedTotal.ts   |     8 +
 .../orval/models/previewItemsResponseNextCursor.ts |     8 +
 .../orval/models/previewSessionResponse.ts         |    18 +
 .../models/previewSessionResponseEstimatedTotal.ts |     8 +
 .../models/previewSessionResponseNextCursor.ts     |     8 +
 .../src/generated/orval/models/queryDataRequest.ts |    16 +
 .../orval/models/queryDataRequestParams.ts         |     8 +
 ...atasetDataApiV1DatasetsDatasetIdQueryPost200.ts |     8 +
 .../generated/orval/models/readinessReadyGet200.ts |     8 +
 .../src/generated/orval/models/recentJobSummary.ts |    16 +
 .../src/generated/orval/models/registerRequest.ts  |    12 +
 .../resolveImageApiV1ImagesResolveGetParams.ts     |    10 +
 .../generated/orval/models/reviewActionResponse.ts |    23 +
 .../models/reviewActionResponseCollectionId.ts     |     8 +
 .../models/reviewActionResponseModelVersion.ts     |     8 +
 .../orval/models/reviewActionResponseSyncTag.ts    |     8 +
 .../src/generated/orval/models/runLogResponse.ts   |    16 +
 .../orval/models/runLogResponseFlowRunId.ts        |     8 +
 .../src/generated/orval/models/runLogResponseId.ts |     8 +
 .../generated/orval/models/runPredictionRequest.ts |    27 +
 .../models/runPredictionRequestModelVersion.ts     |    11 +
 .../orval/models/runPredictionRequestPrompt.ts     |    11 +
 .../orval/models/runPredictionRequestSampleIds.ts  |    11 +
 apps/web/src/generated/orval/models/runResponse.ts |    27 +
 .../orval/models/runResponseDeploymentId.ts        |     8 +
 .../generated/orval/models/runResponseEndTime.ts   |     8 +
 .../generated/orval/models/runResponseFlowName.ts  |     8 +
 .../orval/models/runResponseParameters.ts          |     8 +
 .../generated/orval/models/runResponseStartTime.ts |     8 +
 .../generated/orval/models/runResponseStateName.ts |     8 +
 .../generated/orval/models/runResponseStateType.ts |     8 +
 .../orval/models/runResponseTotalRunTime.ts        |     8 +
 apps/web/src/generated/orval/models/sample.ts      |    17 +
 .../src/generated/orval/models/sampleLsTaskId.ts   |     8 +
 .../src/generated/orval/models/sampleMetadata.ts   |     8 +
 .../src/generated/orval/models/sampleWithLabels.ts |    20 +
 .../models/sampleWithLabelsLatestAnnotation.ts     |     9 +
 .../models/sampleWithLabelsLatestPrediction.ts     |     9 +
 .../sampleWithLabelsLatestPredictionAnyOf.ts       |     8 +
 .../orval/models/sampleWithLabelsLsTaskId.ts       |     8 +
 .../orval/models/sampleWithLabelsMetadata.ts       |     8 +
 .../orval/models/saveReviewAnnotationItem.ts       |    19 +
 .../models/saveReviewAnnotationItemConfidence.ts   |     8 +
 .../models/saveReviewAnnotationItemPredictionId.ts |     8 +
 .../orval/models/saveReviewAnnotationsRequest.ts   |    14 +
 .../orval/models/saveReviewAnnotationsResponse.ts  |    16 +
 .../src/generated/orval/models/scAnnotationItem.ts |    12 +
 .../generated/orval/models/scBoxFilterRequest.ts   |    23 +
 .../orval/models/scBoxFilterRequestMode.ts         |    16 +
 .../generated/orval/models/scBoxFilterResponse.ts  |    11 +
 .../orval/models/scBulkAnnotationRequest.ts        |    11 +
 .../orval/models/scBulkAnnotationResponse.ts       |    10 +
 .../src/generated/orval/models/scImportRequest.ts  |    20 +
 .../orval/models/scImportRequestFilters.ts         |     9 +
 .../orval/models/scImportRequestFiltersAnyOf.ts    |     8 +
 .../orval/models/scImportRequestMaxRows.ts         |     8 +
 .../src/generated/orval/models/scImportResponse.ts |    16 +
 .../orval/models/scImportResponseError.ts          |     8 +
 .../orval/models/scImportResponseFlowRunId.ts      |     8 +
 .../orval/models/scInspectionListResponse.ts       |    12 +
 .../models/scInspectionReviewImagesResponse.ts     |    12 +
 .../orval/models/scInspectionSummaryItem.ts        |    25 +
 .../generated/orval/models/scReviewImageItem.ts    |    12 +
 .../orval/models/scReviewImagesByDefectItem.ts     |    12 +
 .../src/generated/orval/models/scSampleTableRow.ts |    19 +
 .../orval/models/scSampleTableRowsRequest.ts       |    17 +
 .../orval/models/scSampleTableRowsResponse.ts      |    12 +
 .../src/generated/orval/models/scheduleResponse.ts |    23 +
 .../orval/models/scheduleResponseCreated.ts        |     8 +
 .../generated/orval/models/scheduleResponseCron.ts |     8 +
 .../orval/models/scheduleResponseParameters.ts     |     8 +
 .../orval/models/scheduleResponseUpdated.ts        |     8 +
 ...ApiV1DatasetsDatasetIdSelectionMetricsGet200.ts |     8 +
 .../orval/models/sensorDefinitionResponse.ts       |    16 +
 .../models/sensorDefinitionResponseFilterSchema.ts |     8 +
 .../src/generated/orval/models/sensorEventBatch.ts |    14 +
 .../orval/models/sensorEventBatchEventsItem.ts     |     8 +
 .../orval/models/sensorEventBatchWatermark.ts      |     9 +
 .../orval/models/sensorEventBatchWatermarkAnyOf.ts |     8 +
 .../orval/models/sensorEventIngestResponse.ts      |    12 +
 .../orval/models/sensorSubscriptionResponse.ts     |    17 +
 .../sensorSubscriptionResponseFilterConfig.ts      |     8 +
 ...ectionTimeWaferKeyDefectIdImageTypeGetParams.ts |    11 +
 .../src/generated/orval/models/serviceStatus.ts    |    17 +
 .../orval/models/serviceStatusEndpoint.ts          |     8 +
 .../orval/models/serviceStatusLatencyMs.ts         |     8 +
 .../src/generated/orval/models/setPanelRequest.ts  |    14 +
 .../src/generated/orval/models/setPublicRequest.ts |    10 +
 .../generated/orval/models/setPublicResponse.ts    |    10 +
 .../models/setSettingApiV1SettingsKeyPut200.ts     |     8 +
 .../models/setSettingApiV1SettingsKeyPutBody.ts    |     8 +
 .../generated/orval/models/similarityNeighbor.ts   |    11 +
 .../generated/orval/models/similarityResponse.ts   |    12 +
 ...DatasetsDatasetIdSimilaritySampleIdGetParams.ts |    10 +
 .../orval/models/sparseManifestSummary.ts          |    14 +
 .../sparseManifestSummarySchemaColumnsItem.ts      |     8 +
 .../generated/orval/models/sparseShardSummary.ts   |    13 +
 .../orval/models/sparseSummaryResponse.ts          |    19 +
 .../models/sparseSummaryResponseSampleRowsItem.ts  |    11 +
 ...sparseSummaryResponseSampleRowsItemAnyOfItem.ts |     8 +
 ...eSummaryResponseSampleRowsItemAnyOfThreeItem.ts |     8 +
 .../sparseSummaryResponseSampleRowsItemAnyOfTwo.ts |     8 +
 .../generated/orval/models/startPersistRequest.ts  |    10 +
 ...rogressApiV1ScImportFlowRunIdStreamGetParams.ts |    10 +
 .../src/generated/orval/models/surfaceLayout.ts    |    19 +
 .../orval/models/surfaceStateDocumentInput.ts      |    23 +
 .../models/surfaceStateDocumentInputExportedAt.ts  |     8 +
 .../models/surfaceStateDocumentInputMetadata.ts    |    11 +
 .../orval/models/surfaceStateDocumentOutput.ts     |    23 +
 .../models/surfaceStateDocumentOutputExportedAt.ts |     8 +
 .../models/surfaceStateDocumentOutputMetadata.ts   |    11 +
 .../orval/models/syncAnnotationsResponse.ts        |    11 +
 .../models/syncPredictionCollectionRequest.ts      |    11 +
 .../syncPredictionCollectionRequestSyncTag.ts      |     8 +
 .../models/syncPredictionCollectionResponse.ts     |    14 +
 apps/web/src/generated/orval/models/taskSpec.ts    |    13 +
 .../orval/models/taskSpecMetadataSchema.ts         |     8 +
 .../orval/models/taskTrackerCheckResult.ts         |    15 +
 .../orval/models/taskTrackerCheckResultValue.ts    |     8 +
 .../generated/orval/models/taskTrackerDeepLinks.ts |    15 +
 .../models/taskTrackerDeepLinksPlatformJobUrl.ts   |     8 +
 .../taskTrackerDeepLinksPrefectDeploymentUrl.ts    |     8 +
 .../models/taskTrackerDeepLinksPrefectRunUrl.ts    |     8 +
 .../generated/orval/models/taskTrackerDerived.ts   |    38 +
 .../orval/models/taskTrackerDerivedActiveNode.ts   |     8 +
 .../models/taskTrackerDerivedArtifactsItem.ts      |     8 +
 .../taskTrackerDerivedPoolConcurrencyLimit.ts      |     8 +
 .../models/taskTrackerDerivedPoolSlotsUsed.ts      |     8 +
 .../orval/models/taskTrackerDerivedPrefectState.ts |     8 +
 .../models/taskTrackerDerivedQueueDepthAhead.ts    |     8 +
 .../models/taskTrackerDerivedQueuePriority.ts      |     8 +
 .../orval/models/taskTrackerDetailResponse.ts      |    17 +
 .../orval/models/taskTrackerDetailResponseMeta.ts  |     8 +
 .../src/generated/orval/models/taskTrackerNode.ts  |    19 +
 .../orval/models/taskTrackerNodeEndedAt.ts         |     8 +
 .../orval/models/taskTrackerNodeExpectedStartAt.ts |     8 +
 .../orval/models/taskTrackerNodeStartedAt.ts       |     8 +
 .../orval/models/taskTrackerRawPayload.ts          |    23 +
 .../models/taskTrackerRawPayloadDeployment.ts      |     9 +
 .../models/taskTrackerRawPayloadDeploymentAnyOf.ts |     8 +
 .../orval/models/taskTrackerRawPayloadFlowRun.ts   |     9 +
 .../models/taskTrackerRawPayloadFlowRunAnyOf.ts    |     8 +
 .../orval/models/taskTrackerRawPayloadGpuJobId.ts  |     8 +
 .../orval/models/taskTrackerRawPayloadLogsItem.ts  |     8 +
 .../models/taskTrackerRawPayloadPlatformJob.ts     |     8 +
 .../orval/models/taskTrackerRawPayloadWorkPool.ts  |     9 +
 .../models/taskTrackerRawPayloadWorkPoolAnyOf.ts   |     8 +
 .../orval/models/taskTrackerRawPayloadWorkQueue.ts |     9 +
 .../models/taskTrackerRawPayloadWorkQueueAnyOf.ts  |     8 +
 .../generated/orval/models/taskTrackerScorecard.ts |    13 +
 .../src/generated/orval/models/taskTrackerStage.ts |    15 +
 .../orval/models/taskTrackerSummaryMetrics.ts      |    21 +
 .../models/taskTrackerSummaryMetricsFailed.ts      |     8 +
 .../models/taskTrackerSummaryMetricsProcessed.ts   |     8 +
 .../models/taskTrackerSummaryMetricsRateHint.ts    |     8 +
 .../models/taskTrackerSummaryMetricsSkipped.ts     |     8 +
 .../models/taskTrackerSummaryMetricsSuccessful.ts  |     8 +
 .../orval/models/taskTrackerSummaryMetricsTotal.ts |     8 +
 .../orval/models/taskTrackerSummaryResponse.ts     |    39 +
 .../models/taskTrackerSummaryResponseModelId.ts    |     8 +
 ...skTrackerSummaryResponsePoolConcurrencyLimit.ts |     8 +
 .../taskTrackerSummaryResponsePoolSlotsUsed.ts     |     8 +
 .../taskTrackerSummaryResponsePrefectState.ts      |     8 +
 .../taskTrackerSummaryResponseQueueDepthAhead.ts   |     8 +
 .../taskTrackerSummaryResponseQueuePriority.ts     |     8 +
 .../models/taskTrackerSummaryResponseTrainerId.ts  |     8 +
 .../taskTrackerSummaryResponseWorkPoolName.ts      |     8 +
 .../taskTrackerSummaryResponseWorkQueueName.ts     |     8 +
 .../generated/orval/models/tokenCreatedResponse.ts |    13 +
 .../src/generated/orval/models/tokenResponse.ts    |    13 +
 .../src/generated/orval/models/trainingEvent.ts    |    15 +
 .../generated/orval/models/trainingEventPayload.ts |     8 +
 apps/web/src/generated/orval/models/trainingJob.ts |    25 +
 .../orval/models/trainingJobExternalJobId.ts       |     8 +
 .../src/generated/orval/models/trainingJobOrgId.ts |     8 +
 ...tsApiV1DatasetsDatasetIdHintsUncoveredGet200.ts |     8 +
 .../orval/models/updateAnnotationRequest.ts        |    11 +
 .../orval/models/updateEmbedConfigRequest.ts       |    11 +
 .../orval/models/updateLabelSpaceRequest.ts        |    10 +
 .../orval/models/updateSampleImageResponse.ts      |    12 +
 .../orval/models/updateScheduleRequest.ts          |    19 +
 .../orval/models/updateScheduleRequestCron.ts      |     8 +
 .../models/updateScheduleRequestDescription.ts     |     8 +
 .../updateScheduleRequestIsScheduleActive.ts       |     8 +
 .../orval/models/updateScheduleRequestName.ts      |     8 +
 .../models/updateScheduleRequestParameters.ts      |     9 +
 .../models/updateScheduleRequestParametersAnyOf.ts |     8 +
 .../orval/models/updateSubscriptionRequest.ts      |    13 +
 .../models/updateSubscriptionRequestEnabled.ts     |     8 +
 .../updateSubscriptionRequestFilterConfig.ts       |     9 +
 .../updateSubscriptionRequestFilterConfigAnyOf.ts  |     8 +
 .../orval/models/uploadTemplateProfileResponse.ts  |    14 +
 .../uploadTemplateProfileResponseModelSpec.ts      |     8 +
 .../web/src/generated/orval/models/userResponse.ts |    14 +
 .../generated/orval/models/userWithOrgsResponse.ts |    16 +
 .../src/generated/orval/models/validationError.ts  |    16 +
 .../generated/orval/models/validationErrorCtx.ts   |     8 +
 .../orval/models/validationErrorLocItem.ts         |     8 +
 .../orval/models/versionExportPersistResponse.ts   |    11 +
 .../generated/orval/models/versionExportRequest.ts |    14 +
 .../src/generated/orval/models/workPoolStatus.ts   |    16 +
 .../orval/models/workPoolStatusConcurrencyLimit.ts |     8 +
 apps/web/src/generated/sse-types.ts                |   288 +
 apps/web/src/shared.ts                             |     1 -
 apps/web/src/shared/api/agent.ts                   |    11 +-
 apps/web/src/shared/api/annotations.ts             |    44 +-
 apps/web/src/shared/api/auth.ts                    |    81 -
 apps/web/src/shared/api/client.ts                  |    39 +-
 apps/web/src/shared/api/datasets.ts                |   280 +-
 apps/web/src/shared/api/hooks/datasets.ts          |    48 -
 apps/web/src/shared/api/hooks/index.ts             |     3 -
 apps/web/src/shared/api/hooks/preview.ts           |    79 -
 apps/web/src/shared/api/hooks/samples.ts           |   113 -
 apps/web/src/shared/api/index.ts                   |    20 +-
 apps/web/src/shared/api/jobs.ts                    |    55 -
 apps/web/src/shared/api/models.ts                  |    43 -
 apps/web/src/shared/api/orgs.ts                    |     6 -
 apps/web/src/shared/api/orval-fetcher.ts           |    92 +
 apps/web/src/shared/api/predictions.ts             |   215 +-
 apps/web/src/shared/api/samples.ts                 |   117 +-
 apps/web/src/shared/api/schedules.ts               |    80 +-
 apps/web/src/shared/api/sensors.ts                 |    35 -
 apps/web/src/shared/api/sse.ts                     |     2 +-
 apps/web/src/shared/api/task-tracker.ts            |    31 +-
 apps/web/src/shared/api/types.ts                   |   780 +-
 apps/web/src/shared/api/ui-helpers.ts              |    43 +
 .../agent-chat-drawer/AgentChatDrawer.spec.ts      |    19 +-
 .../agent-chat-drawer/AgentChatDrawer.stories.ts   |     2 +-
 .../annotation-grid/AnnotationGrid.spec.ts         |    24 +-
 .../annotation-grid/AnnotationGrid.stories.ts      |     2 +-
 .../AnnotationProgressWidget.stories.ts            |     2 +-
 .../components/blink-table/BlinkImageCell.vue      |    68 -
 .../components/blink-table/BlinkTable.spec.ts      |   226 -
 .../components/blink-table/BlinkTable.stories.ts   |    36 -
 .../shared/components/blink-table/BlinkTable.vue   |   327 -
 .../components/blink-table/BlinkTableWidget.vue    |    62 -
 .../src/shared/components/blink-table/fixtures.ts  |    83 -
 .../web/src/shared/components/blink-table/index.ts |    23 -
 .../components/blink-table/multiImageFixture.ts    |   109 -
 ...bleWithSelectionAndPreviewResultDisplay.spec.ts |    95 +
 ...alTableWithSelectionAndPreviewResultDisplay.vue |   697 ++
 .../shared/components/blink-virtual-table/index.ts |     1 +
 .../browser-sidebar/BrowserSidebar.spec.ts         |    40 +-
 .../browser-sidebar/BrowserSidebar.stories.ts      |     2 +-
 .../BrowserSummaryWidget.stories.ts                |     2 +-
 .../data-table/DataTableWidget.stories.ts          |     2 +-
 .../dataset-page-shell/DatasetPageShell.stories.ts |     2 +-
 .../DatasetRowActions.stories.ts                   |     2 +-
 .../datasets/dataset-table/DatasetTable.stories.ts |     2 +-
 .../dataset-toolbar/DatasetToolbar.stories.ts      |     2 +-
 .../GenericEChartsWidget.stories.ts                |     2 +-
 .../components/flow-modal/FlowModal.stories.ts     |     2 +-
 .../flow-type-selector/FlowTypeSelector.stories.ts |     2 +-
 .../full-screen-layout/FullScreenLayout.vue        |    11 +
 .../shared/components/full-screen-layout/index.ts  |     1 +
 .../InteractiveScatterWidget.stories.ts            |     2 +-
 .../LabelDistributionWidget.stories.ts             |     2 +-
 .../markdown-log/MarkdownLogWidget.stories.ts      |     2 +-
 .../metric-cards/MetricCardsWidget.stories.ts      |     2 +-
 .../page-provider/PageProvider.stories.ts          |    23 +
 .../components/panel-host/PanelHost.stories.ts     |    37 +
 .../PredictionSummaryWidget.stories.ts             |     2 +-
 .../preview-item-drawer/PreviewItemDrawer.spec.ts  |    10 +-
 .../PreviewItemDrawer.stories.ts                   |     2 +-
 .../run-log-viewer/RunLogViewer.stories.ts         |    15 +
 .../components/run-log-viewer/RunLogViewer.vue     |     2 +-
 .../sample-browser/SampleBrowser.stories.ts        |    67 +
 .../components/sample-browser/SampleBrowser.vue    |     2 +-
 .../SampleDetailDrawer.stories.ts                  |    18 +
 .../sample-detail-drawer/SampleDetailDrawer.vue    |    50 +-
 .../sample-viewer/SampleViewerWidget.stories.ts    |     2 +-
 .../task-insight-modal/TaskInsightModal.stories.ts |    42 +
 .../task-insight-modal/TaskInsightModal.vue        |    34 +-
 .../training-chart/TrainingChart.spec.ts           |    32 +-
 .../training-chart/TrainingChart.stories.ts        |     2 +-
 .../UpstreamPreviewLauncher.stories.ts             |    17 +
 .../UpstreamPreviewLauncher.vue                    |     6 +-
 .../components/wafer-map/WaferMapWidget.spec.ts    |   231 -
 .../components/wafer-map/WaferMapWidget.stories.ts |    84 -
 .../shared/components/wafer-map/WaferMapWidget.vue |  1135 +-
 apps/web/src/shared/components/wafer-map/index.ts  |    25 +-
 .../WidgetErrorBoundary.spec.ts                    |    14 +-
 .../WidgetErrorBoundary.stories.ts                 |     2 +-
 .../src/shared/composables/useClassifyDashboard.ts |     2 +-
 apps/web/src/shared/composables/useDataPipeline.ts |    29 +-
 .../shared/composables/usePreviewLoader.spec.ts    |   264 +-
 .../web/src/shared/composables/usePreviewLoader.ts |   107 +-
 .../src/shared/composables/useSampleLoader.spec.ts |   268 +-
 apps/web/src/shared/composables/useSampleLoader.ts |   182 +-
 apps/web/src/shared/composables/useTaskHandoff.ts  |     2 +-
 apps/web/src/shared/index.ts                       |     8 +-
 apps/web/src/shared/keys.ts                        |     2 +-
 apps/web/src/shared/storybook/mocks.ts             |    53 +-
 apps/web/src/shared/types/sidebar-widgets.ts       |     4 +-
 .../shared/utils/__tests__/image-adapters.spec.ts  |    86 +
 apps/web/src/shared/utils/image-adapters.ts        |    13 +-
 apps/web/src/shared/utils/webglScatterRenderer.ts  |   445 +
 apps/web/src/shared/views/types.ts                 |    60 +
 apps/web/src/shared/widgets/widgetComponentMap.ts  |     3 -
 apps/web/src/testing/README.md                     |    87 +
 apps/web/src/testing/index.ts                      |     4 +
 apps/web/src/testing/mocks/.gitkeep                |     0
 apps/web/src/testing/mocks/echarts.ts              |    45 +
 apps/web/src/testing/mocks/tanstack-virtual.ts     |    48 +
 apps/web/src/testing/mount.ts                      |    98 +
 apps/web/src/testing/msw/factories/.gitkeep        |     0
 .../src/testing/msw/factories/dataset.factory.ts   |    31 +
 apps/web/src/testing/msw/factories/user.factory.ts |    37 +
 apps/web/src/testing/msw/handlers/.gitkeep         |     0
 apps/web/src/testing/msw/handlers/auth.ts          |    28 +
 apps/web/src/testing/msw/handlers/datasets.ts      |    59 +
 apps/web/src/testing/msw/handlers/index.ts         |     4 +
 apps/web/src/testing/msw/handlers/sc.ts            |    67 +
 apps/web/src/testing/msw/server.ts                 |     7 +
 apps/web/src/testing/query-client.ts               |    10 +
 apps/web/src/testing/setup.ts                      |    14 +
 apps/web/src/testing/withQuerySetup.ts             |    40 +
 apps/web/src/types.ts                              |   105 -
 apps/web/src/ui-types.ts                           |    92 -
 apps/web/tests/README.md                           |   100 +
 apps/web/tests/fixtures/.gitkeep                   |     0
 apps/web/tests/fixtures/index.ts                   |   466 +
 apps/web/tests/global-setup.ts                     |    83 +
 apps/web/tests/helpers/.gitkeep                    |     0
 apps/web/tests/helpers/navigation.ts               |    26 +
 apps/web/tests/migration-map.md                    |   103 +
 apps/web/tests/mocks/constants.ts                  |     4 +
 apps/web/tests/mocks/factories/.gitkeep            |     0
 apps/web/tests/mocks/factories/dataset.factory.ts  |    59 +
 apps/web/tests/mocks/factories/index.ts            |     6 +
 .../tests/mocks/factories/prediction.factory.ts    |    61 +
 apps/web/tests/mocks/factories/sample.factory.ts   |    32 +
 apps/web/tests/mocks/factories/training.factory.ts |    22 +
 apps/web/tests/mocks/factories/user.factory.ts     |    41 +
 apps/web/tests/mocks/handlers/.gitkeep             |     0
 apps/web/tests/mocks/handlers/auth.ts              |    25 +
 apps/web/tests/mocks/handlers/core.ts              |   108 +
 apps/web/tests/mocks/handlers/datasets.ts          |   223 +
 apps/web/tests/mocks/handlers/index.ts             |    62 +
 apps/web/tests/mocks/handlers/prediction.ts        |   122 +
 apps/web/tests/mocks/handlers/preview.ts           |   157 +
 apps/web/tests/mocks/handlers/sc.ts                |   250 +
 apps/web/tests/mocks/handlers/schedules.ts         |    96 +
 apps/web/tests/mocks/handlers/training.ts          |    72 +
 apps/web/tests/pages/.gitkeep                      |     0
 apps/web/tests/pages/BasePage.ts                   |    46 +
 apps/web/tests/pages/agent/AgentChatPage.ts        |   108 +
 apps/web/tests/pages/auth/LoginPage.ts             |    60 +
 apps/web/tests/pages/auth/RegisterPage.ts          |    66 +
 .../tests/pages/classify/ClassifyWorkflowPage.ts   |   145 +
 apps/web/tests/pages/classify/WaferMapPage.ts      |    19 +
 apps/web/tests/pages/common/AppShell.ts            |    74 +
 apps/web/tests/pages/dashboard/DashboardPage.ts    |    40 +
 apps/web/tests/pages/datasets/DatasetDetailPage.ts |   126 +
 apps/web/tests/pages/datasets/DatasetListPage.ts   |   124 +
 .../web/tests/pages/datasets/DatasetSamplesPage.ts |    66 +
 .../web/tests/pages/preview/PreviewWorkflowPage.ts |   101 +
 apps/web/tests/pages/sc/ReclassifyPagePom.ts       |    42 +
 apps/web/tests/pages/sc/WaferAnnotatePage.ts       |    61 +
 apps/web/tests/pages/sc/WaferImportPage.ts         |   156 +
 apps/web/tests/pages/sc/WaferPredictExportPage.ts  |   161 +
 apps/web/tests/pages/sc/WaferTrainingPage.ts       |   100 +
 apps/web/tests/pages/schedules/SchedulesPage.ts    |    95 +
 apps/web/tests/pages/training/TrainingListPage.ts  |    94 +
 apps/web/tests/playwright.config.ts                |    37 +
 apps/web/tests/scripts/.gitkeep                    |     0
 apps/web/tests/scripts/README.md                   |    32 +
 apps/web/tests/scripts/check-parity.ts             |   315 +
 apps/web/tests/seed/_smoke.ts                      |    69 +
 apps/web/tests/seed/auth.ts                        |    34 +
 apps/web/tests/seed/cleanup.ts                     |    43 +
 apps/web/tests/seed/client.ts                      |    46 +
 apps/web/tests/seed/datasets.ts                    |    43 +
 apps/web/tests/seed/index.ts                       |    27 +
 apps/web/tests/seed/prediction.ts                  |    37 +
 apps/web/tests/seed/sc.ts                          |   148 +
 apps/web/tests/seed/schedules.ts                   |    49 +
 apps/web/tests/seed/training.ts                    |    86 +
 apps/web/tests/specs/.gitkeep                      |     0
 apps/web/tests/specs/agent/agent-chat.spec.ts      |    99 +
 apps/web/tests/specs/auth/login.spec.ts            |   106 +
 apps/web/tests/specs/classify/wafer-map.spec.ts    |   115 +
 apps/web/tests/specs/classify/workflow.spec.ts     |   113 +
 apps/web/tests/specs/dashboard/dashboard.spec.ts   |    64 +
 apps/web/tests/specs/datasets/dataset-tabs.spec.ts |   132 +
 .../tests/specs/datasets/export-download.spec.ts   |    46 +
 .../tests/specs/datasets/imagenet-workflow.spec.ts |    66 +
 apps/web/tests/specs/datasets/labelstudio.spec.ts  |    33 +
 apps/web/tests/specs/datasets/list.spec.ts         |   205 +
 apps/web/tests/specs/datasets/samples.spec.ts      |   165 +
 .../tests/specs/datasets/virtualization.spec.ts    |    37 +
 apps/web/tests/specs/datasets/vqa.spec.ts          |    96 +
 apps/web/tests/specs/infra/api-prefix.spec.ts      |    32 +
 .../tests/specs/preview/preview-workflow.spec.ts   |   111 +
 apps/web/tests/specs/sc/preview-height.spec.ts     |    37 +
 .../tests/specs/sc/reclassify-lazy-load.spec.ts    |    75 +
 apps/web/tests/specs/sc/sc-classify-page.spec.ts   |    58 +
 apps/web/tests/specs/sc/wafer-annotate.spec.ts     |    71 +
 apps/web/tests/specs/sc/wafer-import.spec.ts       |    69 +
 .../tests/specs/sc/wafer-predict-export.spec.ts    |   145 +
 apps/web/tests/specs/sc/wafer-smoke-e2e.spec.ts    |   227 +
 apps/web/tests/specs/sc/wafer-training.spec.ts     |    62 +
 apps/web/tests/specs/schedules/schedules.spec.ts   |    89 +
 .../web/tests/specs/training/training-list.spec.ts |    78 +
 apps/web/tests/tsconfig.json                       |     8 +
 apps/web/vite.config.ts                            |    25 +-
 apps/worker/Dockerfile                             |    27 -
 apps/worker/README.md                              |    29 -
 apps/worker/pyproject.toml                         |     8 -
 docs/architecture/api-sync-worker-callsites.md     |   116 +
 docs/architecture/backend-ddd-convention.md        |    96 +
 docs/architecture/dataset-schema-system.md         |    10 +-
 docs/architecture/dataset-storage-modes.md         |   180 +-
 docs/architecture/datasets-shim-architecture.md    |    18 +-
 docs/architecture/overview.md                      |    83 +-
 docs/architecture/runtime-contract.md              |     6 +-
 docs/architecture/sample-browser.md                |     6 +
 docs/architecture/system-design-diagram.md         |     8 +-
 docs/architecture/view-contract-backlog.md         |    87 +
 docs/architecture/view-contract-foundation.md      |    76 +
 docs/guides/extension-guide.md                     |     8 +-
 docs/guides/preview-dataset-mode.md                |    12 +-
 docs/guides/production-compose-deployment.md       |   369 +
 docs/index.md                                      |     2 +
 docs/observability/runbook.md                      |     7 +
 docs/reference/api-endpoints.md                    |    18 +
 examples/load_hf_dataset.py                        |    69 +-
 infra/AGENTS.md                                    |    28 +
 infra/compose/README.md                            |   118 +-
 infra/compose/docker-compose.dev.yaml              |   381 +
 infra/compose/docker-compose.prod.yaml             |   294 +
 infra/compose/docker-compose.yaml                  |   334 +-
 infra/compose/prefect.yaml                         |    38 +
 infra/compose/production/compose.data.yaml         |    55 +
 .../compose/production/compose.observability.yaml  |   156 +
 infra/compose/production/compose.platform.yaml     |   227 +
 infra/k8s/README.md                                |    10 +-
 infra/k8s/api-deployment.yaml                      |     2 +-
 infra/k8s/configmap.yaml                           |     3 +
 infra/k8s/embedding.yaml                           |    52 -
 infra/k8s/gpu-worker.yaml                          |    66 -
 infra/k8s/kustomization.yaml                       |     6 +-
 infra/k8s/prefect-worker-cpu.yaml                  |    42 +
 infra/k8s/prefect-worker-gpu.yaml                  |    58 +
 infra/k8s/prefect-worker.yaml                      |    37 -
 infra/k8s/redis.yaml                               |    43 +
 infra/k8s/secret.example.yaml                      |     3 +
 libs/ml/libs/__init__.py                           |     1 +
 libs/ml/libs/ml/__init__.py                        |    22 +
 libs/ml/libs/ml/classification/__init__.py         |     2 +
 libs/ml/libs/ml/classification/_utils.py           |    58 +
 libs/ml/libs/ml/classification/predictor.py        |   149 +
 libs/ml/libs/ml/classification/trainer.py          |   136 +
 libs/ml/libs/ml/detection/__init__.py              |     1 +
 libs/ml/libs/ml/detection/predictor.py             |   165 +
 libs/ml/libs/ml/detection/trainer.py               |   138 +
 libs/ml/libs/ml/domain.py                          |    31 +
 libs/ml/libs/ml/protocols.py                       |    13 +
 libs/ml/libs/ml/vqa/__init__.py                    |     4 +
 libs/ml/libs/ml/vqa/predictor.py                   |   104 +
 libs/ml/libs/ml/vqa/trainer.py                     |   106 +
 libs/ml/pyproject.toml                             |    26 +
 libs/platform-runtime/pyproject.toml               |    27 +
 .../src/platform_runtime/__init__.py               |     5 +
 .../src/platform_runtime/contracts.py              |   232 +
 .../src/platform_runtime/datasets/__init__.py      |     3 +
 .../src/platform_runtime/datasets/torch_adapter.py |    92 +
 .../src/platform_runtime/sdk/__init__.py           |     6 +
 .../src/platform_runtime/sdk/agent_tools.py        |    22 +
 .../src/platform_runtime/sdk/cli.py                |    70 +
 .../src/platform_runtime/sdk/client.py             |    54 +
 .../src/platform_runtime/sparse/__init__.py        |    40 +
 .../src/platform_runtime/sparse/annotations.py     |   142 +
 .../src/platform_runtime/sparse/models.py          |   181 +
 .../src/platform_runtime/sparse/parquet_helpers.py |   155 +
 .../src/platform_runtime/sparse/reader.py          |   122 +
 .../src/platform_runtime/sparse/store.py           |    67 +-
 libs/platform-runtime/tests/__init__.py            |     0
 .../tests/test_materialization_schema.py           |   166 +
 .../platform-runtime/tests/test_predict_context.py |   344 +
 .../tests/test_runtime_parquet_helpers.py          |   128 +
 libs/platform-runtime/tests/test_sparse_reader.py  |   392 +
 libs/platform-runtime/tests/test_sparse_store.py   |   393 +
 libs/protos/embedding_pb/__init__.py               |    35 -
 libs/protos/embedding_pb/embedding_pb2.py          |    58 -
 libs/protos/embedding_pb/embedding_pb2_grpc.py     |   269 -
 libs/protos/pyproject.toml                         |    20 +-
 libs/protos/src/proto_stubs/__init__.py            |     0
 libs/protos/src/proto_stubs/embedding/__init__.py  |     0
 .../src/proto_stubs/embedding/embedding_pb2.py     |    55 +
 .../proto_stubs/embedding/embedding_pb2_grpc.py    |   295 +
 libs/protos/src/proto_stubs/sc/__init__.py         |     0
 libs/protos/src/proto_stubs/sc/v1/__init__.py      |     0
 libs/protos/src/proto_stubs/sc/v1/sample_pb2.py    |    71 +
 libs/protos/src/proto_stubs/sc/v1/sample_pb2.pyi   |   573 +
 libs/python-sdk/ftsdk/__init__.py                  |     7 +-
 libs/python-sdk/ftsdk/agent_tools.py               |    21 +-
 libs/python-sdk/ftsdk/cli.py                       |    62 +-
 libs/python-sdk/ftsdk/client.py                    |    47 +-
 libs/python-sdk/pyproject.toml                     |     6 +-
 libs/seedmaker/pyproject.toml                      |    24 +-
 libs/seedmaker/src/seedmaker/cli.py                |    21 +-
 .../seedmaker/datasets/imagenet_100_rchannel.py    |     5 +-
 .../src/seedmaker/datasets/imagenet_mock.py        |   100 +-
 .../src/seedmaker/datasets/imagenet_real.py        |    95 +-
 .../src/seedmaker/datasets/mock_multi_image.py     |    16 +-
 .../src/seedmaker/datasets/oxford_flowers.py       |     2 +-
 .../seedmaker/src/seedmaker/datasets/wafer_demo.py |   129 +-
 libs/seedmaker/src/seedmaker/loaders/s3_zip.py     |     2 +-
 libs/seedmaker/src/seedmaker/presets.py            |   194 -
 libs/seedmaker/src/seedmaker/runner.py             |     6 +-
 libs/seedmaker/src/seedmaker/utils.py              |    15 +-
 main-fix-diff.md                                   |   165 +
 mkdocs.yml                                         |     2 -
 openapi/openapi.yaml                               |  5432 ++++++---
 openapi/sse-events.schema.json                     |   910 ++
 package.json                                       |     4 +
 pnpm-lock.yaml                                     |  9118 +++++++++++---
 protos/buf.gen.yaml                                |    11 +
 protos/buf.yaml                                    |     5 +
 {libs/protos => protos/embedding}/embedding.proto  |     0
 protos/sc/v1/sample.proto                          |   130 +
 protos/sc/v1/sample.proto.bak                      |    31 +
 pyproject.toml                                     |    43 +-
 .../__snapshots__/disable-reexport-snapshot.yml    |    42 +
 .../forbid-handwritten-api-dto-snapshot.yml        |    42 +
 .../forbid-index-external-import-snapshot.yml      |    62 +
 rule-tests/disable-reexport-test.yml               |    14 +
 rule-tests/forbid-handwritten-api-dto-test.yml     |    11 +
 rule-tests/forbid-index-external-import-test.yml   |    13 +
 rule-tests/forbid-unsafe-type-casts-test.yml       |    24 +
 rules/disable-reexport.yml                         |    31 +
 rules/forbid-export-from-generated-orval.yml       |    12 +
 rules/forbid-handwritten-api-dto.yml               |    31 +
 rules/forbid-index-external-import.yml             |    23 +
 rules/forbid-others-import-sc-frontend.yml         |    18 +
 rules/forbid-preset-python.yml                     |    16 +
 rules/forbid-preset-typescript.yml                 |    19 +
 rules/forbid-raw-api-url.yml                       |    20 +
 rules/forbid-unsafe-type-casts.yml                 |    20 +
 scripts/batch-clean-duplicate-types.py             |   403 +
 scripts/check-duplicate-types.js                   |   152 +
 scripts/check-duplicate-types.py                   |   134 +
 scripts/check-duplicate-types.ts                   |   161 +
 scripts/dev-init.sh                                |    55 +-
 scripts/export_openapi_spec.py                     |    60 +
 scripts/export_sse_schema.py                       |    25 +
 scripts/run_with_timeout.py                        |     2 -
 scripts/save-compose-images.sh                     |   120 +
 scripts/seed.py                                    |     1 -
 scripts/smoke_dev_prediction.py                    |    34 +-
 scripts/smoke_dev_training.py                      |    34 +-
 scripts/smoke_prediction_export.py                 |   215 +
 scripts/smoke_wafer_e2e.py                         |  1089 ++
 sgconfig.yaml                                      |     4 +
 uv.lock                                            |  1725 ++-
 1545 files changed, 113386 insertions(+), 39627 deletions(-)
```
