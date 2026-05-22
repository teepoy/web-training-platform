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

## [T7 complete] Settings module migrated
- Settings deps: SettingsRepository (no session_factory needed — InMemorySettingsRepository has no DB deps)
- Any gotchas: Settings router had no prefix on the empty stub router. Adding routes without a prefix caused /{key} to intercept /api/v1/training-jobs before the training router, breaking test_unauthenticated_jobs_returns_401 (got 404 instead of 401). Fix: add prefix="/settings" to APIRouter. Always add a prefix when a module router has wildcard path params.

## [T8 complete] task_tracker module migrated
- task_tracker deps: TaskTrackerRepository (Protocol over SqlRepository), PrefectClient, config (Any)
- task_tracker_repository added to AppContainer as SqlRepository instance
- Router prefix changed from "/api/v1" to "/task-tracker" (routes become /api/v1/task-tracker/tasks via include_router prefix="/api/v1")
- Test migration: container.prefect_client.override() → app.dependency_overrides[get_prefect_client] set before TestClient context
- Any gotchas: The old router had prefix="/api/v1" which was stripped by _strip_api_prefix; new router has prefix="/task-tracker" which is correct for the include_router(prefix="/api/v1") pattern. The config dep uses Any type since AppConfig is a TypeAlias for Any.

## [T9 complete] Schedules module migrated
- SchedulerService deps: prefect_client: PrefectClient (Protocol), repository: SqlRepository | None
- PrefectClient Protocol coverage: SchedulerService uses its own httpx.AsyncClient for deployment-specific Prefect calls (not in Protocol). It extracts the URL via getattr(prefect_client, '_base', ...) from the concrete PrefectClient.
- No domain/repository.py needed: SchedulerService uses SqlRepository directly (no domain-specific repo Protocol)
- runs_router added: /runs/{run_id} routes live on a separate APIRouter(prefix="/runs") registered alongside schedules_router in MODULE_ROUTERS
- shared/deps.py get_scheduler_service also updated (used by agent router)
- task_tracker.py _list_schedule_run_records updated to use self._prefect instead of prefect_api_url
- Any gotchas: SchedulerService is a second Prefect HTTP client (deployment CRUD). It doesn't use PrefectClient Protocol methods — it uses raw httpx. The DI pattern is satisfied by accepting PrefectClient in __init__ and extracting _base for the URL.

## [T10 complete] Dashboard module migrated
- DashboardService location: app/modules/dashboard/application/dashboard_service.py
- deps.py: app/modules/dashboard/api/deps.py — get_dashboard_service reads container.task_tracker_repository, container.service_health_service, container.prefect_client, container.config
- domain/protocols.py: local JobRepository Protocol (list_jobs method only)
- AppContainer new field: service_health_service: ServiceHealthService (constructed in _build_base_container with config, prefect_client, embedding_client)
- Handler reduced from ~80 lines to 4 lines (thin delegator)
- Response shape: unchanged (DashboardResponse contract preserved)
- Gotcha: Annotated dep (DashboardServiceDep) must come BEFORE params with defaults in handler signature, otherwise Python raises "parameter without a default follows parameter with a default" SyntaxError
- task_tracker_repository (SqlRepository) reused as JobRepository — no new AppContainer field needed for the repo

## [T11 complete] Models module migrated
- ModelRepository Protocol location: app/modules/models/domain/repository.py
- Methods: list_models, get_model, delete_artifact, add_artifacts
- deps.py: app/modules/models/api/deps.py — get_model_service reads container.model_repository + container.artifact_storage
- AppContainer.model_repository field added: yes (ModelArtifactRepository)
- Router: Annotated type aliases (ModelServiceDep, CurrentUserDep, CurrentOrgDep) used throughout
- Critical gotcha: AppContainer creates a fresh InMemoryArtifactStorage separate from legacy AppServices. When the new deps.py used container.artifact_storage, uploads stored to a different instance than what PredictionService (still on legacy container) reads from. Fix: always sync artifact_storage from legacy to new container in _build_state_container (unconditional, not just on override). This is the first module using artifact_storage — future modules with storage deps must be aware of this coexistence issue.
- Router prefix: kept prefix="/api/v1" (existing pattern for this router)

## [T12 complete] Presets module migrated
- PresetRegistry is a pure in-memory singleton (no DB) — no domain/repository.py needed
- deps.py: app/modules/presets/api/deps.py — get_preset_registry reads request.app.state.container.preset_registry
- AppContainer.preset_registry field added: yes (PresetRegistry constructed in _build_base_container from cfg.presets.dir + cfg.presets.strict)
- Routers updated: training router (list_presets, get_preset, create_training_job) + agent router (global_agent_chat)
- PresetRegistryDep Annotated alias used; placed before params-with-defaults in handler signatures
- shared/deps.py get_preset_registry kept for backward compat (no callers remain in routers, but not removed per "don't touch other modules" rule)
- Tests: 479 passed, pyright: 0 errors, ruff: clean

## [T13 complete] Preview module migrated
- PreviewService deps: PreviewStore (in-memory TTL), UpstreamAdapter (ABC, concrete: PreviewUpstreamRouter wrapping MockUpstreamAdapter)
- deps.py: app/modules/preview/api/deps.py — get_preview_service constructs PreviewService from store + upstream read from container
- AppContainer new fields: preview_store: PreviewStore, preview_upstream: UpstreamAdapter (both constructed in _build_base_container)
- Router: Annotated type aliases (PreviewServiceDep, RepositoryDep, LabelStudioClientDep) used throughout; Annotated deps before params-with-defaults
- get_repository in preview deps.py: constructs SqlRepository(session_factory=container.session_factory) — no separate repo field needed in AppContainer
- Critical gotcha: _mock_ls_client conftest fixture overrides legacy container.label_studio_client but NOT app.state.container.label_studio_client. Fix: also add app.dependency_overrides[preview_get_ls_client] = lambda: _mock_ls in the fixture. This is the same coexistence issue as T11 artifact_storage — any new module dep that reads from app.state.container must have its conftest mock updated.
- Tests: 479 passed, pyright: 0 errors, ruff: clean

## 2026-05-22 T15 training Protocol DI
- Added training-specific FastAPI deps against app.state.container and kept legacy AppServices override compatibility for tests that patch container.orchestrator()/gpu_worker().
- Training Prefect flow now resolves via _app_container_ref or build_flow_container(), but falls back to AppServices only when gpu_worker is explicitly overridden.
- TrainingExecutionEngine.stream_events Protocol must be a synchronous async-iterator method, not async def, to match engine implementations and async-for usage.

## 2026-05-22 T16 datasets Protocol DI
- DatasetService now receives typed constructor deps (DatasetRepository Protocol, SampleAccessFactory, LabelStudioClient Protocol, ArtifactStorage Protocol, DatasetPayloadStore, capability guard callable, config) and owns dataset response enrichment via to_response().
- Avoid eagerly constructing LsReadRepository in app.state.container during lifespan: test profile has an empty LS database URL, so export routes still resolve the direct LS read repository only when export handlers need it.
- Dataset Label Studio FastAPI dep reads app.state.container by default but preserves legacy AppServices patch compatibility for older tests that patch container.label_studio_client directly.
- _mock_ls_client now uses app.dependency_overrides for the datasets and preview get_label_studio_client deps; it only seeds the legacy SingletonProvider instance for assertions/backward compatibility, not as the route injection path.

## 2026-05-22 T17 agent Protocol DI
- Agent router now imports module-local deps from app.modules.agent.api.deps; no app.shared.deps imports remain under app/modules/agent.
- AppContainer gained prediction_orchestrator, scheduler_service, model_service, surface_store, and session_store for agent constructor injection.
- _build_state_container syncs legacy surface/session/model/prediction services for coexistence; scheduler sync must avoid constructing SchedulerService when prefect_client is an AsyncMock without a string _base.
- _mock_ls_client must override agent_get_label_studio_client alongside datasets/preview to keep Label Studio tests isolated during app.state.container migration.

## 2026-05-22 T18 classify Protocol DI
- Classify deps now live in app/modules/classify/api/deps.py and read from request.app.state.container for config, session_factory-backed SqlRepository, sample_access_factory, and surface_store.
- Classify router keeps Annotated dep aliases before params with defaults to avoid Python's parameter-order SyntaxError.
- Classify has no direct embedding dependency in its router, so _mock_embedding_service remains on the legacy container override path for now; that fixture migration is out of scope for T18.

## 2026-05-22 T19 AppServices removal
- Removed AppServices/SingletonProvider and module-level container/services from app.main; lifespan now builds and exposes AppContainer only via app.state.container.
- Tests that patched legacy providers now use app.dependency_overrides for route deps or app.state.container for lifespan-scoped instances.
- Flow modules keep _app_container_ref; direct-flow tests seed that ref or patch app.state.container workers instead of importing app.main services.
- AppContainer now owns db_engine and sensor_registry so lifespan/test helpers no longer need AppServices providers; close() disposes DB engine and tolerates mocked clients.
- Full verification: make test passed with 479 passed / 1 xpassed; pyright clean; ruff clean.

## T20 shared deps deletion - 2026-05-22
- Deleted app/shared/deps.py after moving route dependency providers into module api/deps.py files.
- Dataset utility helpers now live in app/shared/api/utils.py with legacy underscored aliases for existing call sites.
- Dependency overrides in tests must import the exact provider used by the route; images/resolve belongs to models.api.deps, not datasets.api.deps.
