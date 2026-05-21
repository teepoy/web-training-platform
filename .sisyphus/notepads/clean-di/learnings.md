# Learnings — clean-di

## [2026-05-21] Session ses_1b7320dcaffeyNmX8rvGERT4h6 — Plan Start
- Plan: 23 tasks, strictly sequential, 14 backend modules
- Worktree: refactor/clean-di branch
- Working dir: /Users/jin/Desktop/_/web-training-platform

## [T1 complete] Protocol surfaces derived
- LabelStudioClient methods: create_project, update_project, delete_project, create_task, import_tasks, create_annotation, create_prediction, generate_image_classification_config, generate_vqa_config
- LlmClient methods: answer_vqa
- PrefectClient methods: ensure_work_pool, get_work_pool, list_work_queues, resolve_deployment_id, get_deployment, get_work_queue_by_name, create_flow_run_from_deployment, get_flow_run, get_flow_run_logs, list_task_runs, set_flow_run_state, filter_flow_runs
- EmbeddingClient methods: embed_image, health
- InferenceWorker methods: predict_batch, embed_batch
- GpuWorker methods: submit_train, get_train_status, predict_batch, embed_batch
- KubeflowClient methods: submit_pytorch_job, get_job_phase, delete_job, get_job_logs
- interfaces.py deleted: yes (already absent in branch)
- Import sites updated: 23 files

## [T2 complete] composition.py created
- AppContainer fields: config, session_factory, artifact_storage, label_studio_client, llm_client, prefect_client, embedding_client, inference_worker, gpu_worker, kubeflow_client, notification_sink, training_engine
- close() closes: prefect_client, embedding_client
- Config branching preserved: yes, storage.kind selects memory/minio and execution.engine selects local/kubeflow/prefect; Kubeflow client is created only for kubeflow engine in the new eager container.
- load_config() location: apps/api/app/core/config.py

## [T3 complete] _assert_clean_overrides fixture added
- Location: apps/api/conftest.py
- Existing tests clean: yes
- Leak detection works: yes

## [T4 complete] Sensors pilot pattern established
- SensorRepository Protocol location: app/modules/sensors/domain/repository.py
- deps.py pattern: get_sensor_repository reads request.app.state.container.sensor_repository
- AppContainer.sensor_repository field added: yes
- Coexistence with AppServices: yes (AppServices still present, app.state.container added to lifespan)
- Any gotchas: Existing tests still override the legacy AppServices prefect_client; lifespan mirrors that override into the pilot AppContainer so sensor dispatch tests remain compatible during the coexistence period. The required deps.py snippet needed an additional PrefectClient dependency because SensorDispatchService still requires Prefect to create flow runs.

## [T5 complete] Legacy bridge deleted
- _register_legacy_provider_overrides: deleted (was already a no-op `return None`)
- Sensor-related conftest fixtures migrated: no (none existed — conftest had no sensor container overrides)
- Any hidden call sites found: no (only definition at line 378 and call at line 436 in main.py)

## [T6 complete] Auth module migrated
- Auth deps: AuthService has no constructor deps (it's a stateless class wrapping module-level functions). The real deps are session_factory (for DB access in get_current_user, get_current_org, etc.)
- _mock_auth_deps: still works (yes) — conftest imports get_current_user/get_current_org from app.shared.deps which re-exports from interfaces/controllers/deps.py; no change to import path
- Any gotchas: _get_session_factory is called without a request in test helper functions (test_auth.py, test_auth_routes.py) to directly access the DB. Kept the optional-request fallback to get_container().session_factory() for this test-only path. FastAPI route handlers always pass request. The new api/deps.py provides the canonical get_session_factory(request) for future use.
