from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.types import JobStatus
from app.services.scheduler import SchedulerService
from app.api.schemas import (
    TaskTrackerCheckResult,
    TaskTrackerDeepLinks,
    TaskTrackerDerived,
    TaskTrackerDetailResponse,
    TaskTrackerNode,
    TaskTrackerRawPayload,
    TaskTrackerScorecard,
    TaskTrackerStage,
    TaskTrackerSummaryMetrics,
    TaskTrackerSummaryResponse,
)


_QUEUE_STATES = {"SCHEDULED", "PENDING"}
_RUNNING_STATES = {"RUNNING", "CANCELLING", "PAUSED"}
_TERMINAL_STATES = {"COMPLETED", "FAILED", "CRASHED", "CANCELLED"}


@dataclass
class _TaskRecord:
    task_kind: str
    platform_job: Any
    raw_platform_job: dict[str, Any]
    dataset_id: str
    model_id: str | None
    preset_id: str | None
    external_job_id: str | None
    schedule_id: str | None = None


class TaskTrackerService:
    def __init__(self, repository, prefect_client, config) -> None:
        self._repository = repository
        self._prefect = prefect_client
        self._config = config

    async def list_tasks(self, org_id: str, kind: str | None = None) -> list[TaskTrackerSummaryResponse]:
        tasks: list[_TaskRecord] = []
        if kind in (None, "training"):
            jobs = await self._repository.list_jobs(org_id=org_id)
            tasks.extend(self._to_training_record(job) for job in jobs)
        if kind in (None, "prediction"):
            jobs = await self._repository.list_prediction_jobs(org_id=org_id)
            tasks.extend(self._to_prediction_record(job) for job in jobs)
        if kind in (None, "schedule_run"):
            tasks.extend(await self._list_schedule_run_records(org_id))

        summaries = []
        for task in tasks:
            detail = await self._build_detail(task)
            summaries.append(
                TaskTrackerSummaryResponse(
                    id=detail.id,
                    task_kind=detail.task_kind,
                    execution_kind=detail.derived.execution_kind,
                    display_name=self._display_name(task),
                    display_status=detail.derived.display_status,
                    stage=detail.derived.stage,
                    dataset_id=task.dataset_id,
                    model_id=task.model_id,
                    preset_id=task.preset_id,
                    created_by=task.platform_job.created_by,
                    created_at=task.platform_job.created_at,
                    updated_at=task.platform_job.updated_at,
                    prefect_state=detail.derived.prefect_state,
                    work_pool_name=self._string_or_none(detail.raw.flow_run, "work_pool_name"),
                    work_queue_name=self._string_or_none(detail.raw.flow_run, "work_queue_name"),
                    queue_priority=detail.derived.queue_priority,
                    queue_priority_label=detail.derived.queue_priority_label,
                    queue_depth_ahead=detail.derived.queue_depth_ahead,
                    capacity_status=detail.derived.capacity_status,
                    pool_concurrency_limit=detail.derived.pool_concurrency_limit,
                    pool_slots_used=detail.derived.pool_slots_used,
                )
            )
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries

    async def get_task(self, task_id: str, org_id: str) -> TaskTrackerDetailResponse | None:
        task = await self._resolve_task(task_id, org_id)
        if task is None:
            return None
        return await self._build_detail(task)

    async def cancel_task(self, task_id: str, org_id: str) -> bool:
        task = await self._resolve_task(task_id, org_id)
        if task is None:
            return False
        if task.task_kind == "training":
            ext = await self._repository.get_job_external_id(task_id)
            if not ext:
                return False
            try:
                await self._prefect.set_flow_run_state(ext, "CANCELLING")
            except Exception:
                return False
            await self._repository.update_job_status(task_id, JobStatus.CANCELLED)
            return True
        if task.task_kind == "schedule_run":
            return False
        if task.external_job_id is None:
            return False
        try:
            await self._prefect.set_flow_run_state(task.external_job_id, "CANCELLING")
        except Exception:
            return False
        await self._repository.update_prediction_job_status(task_id, JobStatus.CANCELLED)
        return True

    async def _resolve_task(self, task_id: str, org_id: str) -> _TaskRecord | None:
        training = await self._repository.get_job(task_id, org_id=org_id)
        if training is not None:
            return self._to_training_record(training)
        prediction = await self._repository.get_prediction_job(task_id, org_id=org_id)
        if prediction is not None:
            return self._to_prediction_record(prediction)
        for task in await self._list_schedule_run_records(org_id):
            if task.platform_job.id == task_id:
                return task
        return None

    async def _list_schedule_run_records(self, org_id: str) -> list[_TaskRecord]:
        schedules = await self._repository.list_schedules(org_id)
        scheduler = SchedulerService(
            prefect_api_url=str(self._config.prefect.api_url),
            repository=self._repository,
        )
        try:
            tasks: list[_TaskRecord] = []
            for schedule in schedules:
                try:
                    runs = await scheduler.list_runs(schedule.id, limit=5)
                except Exception:
                    continue
                for run in runs:
                    tasks.append(
                        _TaskRecord(
                            task_kind="schedule_run",
                            platform_job=type("ScheduleRunRecord", (), {
                                "id": str(run.get("id", "")),
                                "created_by": getattr(schedule, "created_by", "system"),
                                "created_at": getattr(schedule, "created_at", None),
                                "updated_at": getattr(schedule, "updated_at", None) or getattr(schedule, "created_at", None),
                                "flow_name": run.get("flow_name") or schedule.flow_name,
                                "state_type": run.get("state_type"),
                                "state_name": run.get("state_name"),
                                "schedule_name": schedule.name,
                                "schedule_id": schedule.id,
                                "parameters": run.get("parameters", {}),
                            })(),
                            raw_platform_job={
                                "id": run.get("id"),
                                "flow_name": run.get("flow_name") or schedule.flow_name,
                                "state_type": run.get("state_type"),
                                "state_name": run.get("state_name"),
                                "schedule_name": schedule.name,
                                "schedule_id": schedule.id,
                                "parameters": run.get("parameters", {}),
                                "created_at": getattr(schedule, "created_at", None).isoformat() if getattr(schedule, "created_at", None) else None,
                                "updated_at": getattr(schedule, "updated_at", None).isoformat() if getattr(schedule, "updated_at", None) else None,
                            },
                            dataset_id="",
                            model_id=None,
                            preset_id=None,
                            external_job_id=str(run.get("id", "")),
                            schedule_id=schedule.id,
                        )
                    )
            return tasks
        finally:
            await scheduler.close()

    def _to_training_record(self, job) -> _TaskRecord:
        return _TaskRecord(
            task_kind="training",
            platform_job=job,
            raw_platform_job=job.model_dump(mode="json"),
            dataset_id=job.dataset_id,
            model_id=None,
            preset_id=job.preset_id,
            external_job_id=getattr(job, "external_job_id", None),
        )

    def _to_prediction_record(self, job) -> _TaskRecord:
        return _TaskRecord(
            task_kind="prediction",
            platform_job=job,
            raw_platform_job=job.model_dump(mode="json"),
            dataset_id=job.dataset_id,
            model_id=job.model_id,
            preset_id=None,
            external_job_id=job.external_job_id,
        )

    async def _build_detail(self, task: _TaskRecord) -> TaskTrackerDetailResponse:
        flow_run = None
        deployment = None
        task_runs: list[dict[str, Any]] = []
        work_queue = None
        work_pool = None
        logs: list[dict[str, Any]] = []
        if task.external_job_id:
            try:
                flow_run = await self._prefect.get_flow_run(task.external_job_id)
            except Exception:
                flow_run = None
            if flow_run is not None:
                deployment_id = self._string_or_none(flow_run, "deployment_id")
                if deployment_id:
                    try:
                        deployment = await self._prefect.get_deployment(deployment_id)
                    except Exception:
                        deployment = None
                work_pool_name = self._string_or_none(flow_run, "work_pool_name")
                work_queue_name = self._string_or_none(flow_run, "work_queue_name")
                if work_queue_name:
                    try:
                        work_queue = await self._prefect.get_work_queue_by_name(
                            work_queue_name,
                            work_pool_name=work_pool_name,
                        )
                    except Exception:
                        work_queue = None
                if work_pool_name:
                    try:
                        work_pool = await self._prefect.get_work_pool(work_pool_name)
                    except Exception:
                        work_pool = None
                try:
                    logs = await self._prefect.get_flow_run_logs(task.external_job_id, limit=80)
                except Exception:
                    logs = []
                try:
                    task_runs = await self._prefect.list_task_runs(task.external_job_id, limit=200)
                except Exception:
                    task_runs = []

        derived = await self._derive(task, flow_run, deployment, task_runs, work_queue, work_pool, logs)
        return TaskTrackerDetailResponse(
            id=task.platform_job.id,
            task_kind=task.task_kind,
            meta={
                "dataset_id": task.dataset_id,
                "model_id": task.model_id,
                "preset_id": task.preset_id,
                "external_job_id": task.external_job_id,
                "schedule_id": task.schedule_id,
                "source": "prefect+platform",
            },
            raw=TaskTrackerRawPayload(
                platform_job=task.raw_platform_job,
                flow_run=flow_run,
                deployment=deployment,
                work_queue=work_queue,
                work_pool=work_pool,
                logs=logs,
            ),
            derived=derived,
        )

    async def _derive(
        self,
        task: _TaskRecord,
        flow_run: dict[str, Any] | None,
        deployment: dict[str, Any] | None,
        task_runs: list[dict[str, Any]],
        work_queue: dict[str, Any] | None,
        work_pool: dict[str, Any] | None,
        logs: list[dict[str, Any]],
    ) -> TaskTrackerDerived:
        prefect_state = self._nested_string(flow_run, "state", "type")
        display_status = self._display_status(task.platform_job, prefect_state)
        stage = self._stage_for(prefect_state)
        execution_kind = self._execution_kind(task, flow_run)
        active_node = self._active_node(task, prefect_state)
        queue_priority = self._int_or_none(work_queue, "priority")
        pool_limit = self._int_or_none(work_pool, "concurrency_limit")
        pool_slots = self._int_or_none(work_pool, "status", "slot_count")
        if pool_slots is None:
            pool_slots = self._int_or_none(work_pool, "status", "slots_used")
        queue_depth = await self._queue_depth(flow_run)
        artifacts = self._artifacts(task)
        scorecard = self._scorecard(task, display_status, artifacts)
        summary_metrics = self._summary_metrics(task)
        return TaskTrackerDerived(
            task_kind=task.task_kind,
            execution_kind=execution_kind,
            display_status=display_status,
            prefect_state=prefect_state,
            stage=stage,
            active_node=active_node,
            capacity_status=self._capacity_status(pool_slots, pool_limit),
            queue_priority=queue_priority,
            queue_priority_label="none" if queue_priority is None else str(queue_priority),
            queue_depth_ahead=queue_depth,
            pool_concurrency_limit=pool_limit,
            pool_slots_used=pool_slots,
            stages=self._stages(task, active_stage=stage, prefect_state=prefect_state, task_runs=task_runs),
            scorecard=scorecard,
            summary_metrics=summary_metrics,
            artifacts=artifacts,
            dynamic_console_lines=self._console_lines(task, logs),
            deep_links=self._deep_links(task, flow_run, deployment),
        )

    async def _queue_depth(self, flow_run: dict[str, Any] | None) -> int | None:
        if flow_run is None:
            return None
        work_queue_name = self._string_or_none(flow_run, "work_queue_name")
        if work_queue_name is None:
            return None
        work_pool_name = self._string_or_none(flow_run, "work_pool_name")
        runs = await self._prefect.filter_flow_runs(
            work_pool_name=work_pool_name,
            work_queue_name=work_queue_name,
            state_types=sorted(_QUEUE_STATES),
            limit=200,
        )
        current_id = self._string_or_none(flow_run, "id")
        ahead = [run for run in runs if run.get("id") != current_id]
        return max(0, len(ahead))

    def _artifacts(self, task: _TaskRecord) -> list[dict[str, Any]]:
        if task.task_kind == "training":
            return [artifact.model_dump(mode="json") for artifact in task.platform_job.artifact_refs]
        return []

    def _scorecard(self, task: _TaskRecord, display_status: str, artifacts: list[dict[str, Any]]) -> TaskTrackerScorecard:
        checks: list[TaskTrackerCheckResult] = []
        if task.task_kind == "training" and artifacts:
            checks.append(
                TaskTrackerCheckResult(
                    key="artifacts_present",
                    label="Artifacts",
                    status="passed",
                    message=f"{len(artifacts)} artifact(s) persisted",
                )
            )
        summary = getattr(task.platform_job, "summary", {}) or {}
        if task.task_kind == "prediction":
            processed = summary.get("processed")
            if processed is not None:
                checks.append(
                    TaskTrackerCheckResult(
                        key="processed_items",
                        label="Processed Items",
                        status="passed" if display_status == "completed" else "not_available",
                        message=f"Processed {processed} item(s)",
                        value=str(processed),
                    )
                )
        return TaskTrackerScorecard(
            errors=1 if display_status == "failed" else 0,
            warnings=0,
            checks=checks,
        )

    def _summary_metrics(self, task: _TaskRecord) -> TaskTrackerSummaryMetrics:
        summary = getattr(task.platform_job, "summary", {}) or {}
        if task.task_kind == "schedule_run":
            summary = getattr(task.platform_job, "parameters", {}) or {}
        return TaskTrackerSummaryMetrics(
            total=self._coerce_int(summary.get("total_samples")),
            processed=self._coerce_int(summary.get("processed")),
            successful=self._coerce_int(summary.get("successful")),
            failed=self._coerce_int(summary.get("failed")),
            skipped=self._coerce_int(summary.get("skipped")),
            rate_hint=self._rate_hint(summary),
        )

    def _rate_hint(self, summary: dict[str, Any]) -> str | None:
        total = self._coerce_int(summary.get("total_samples"))
        processed = self._coerce_int(summary.get("processed"))
        if total is None or processed is None or total <= 0:
            return None
        return f"{processed}/{total} processed"

    def _console_lines(self, task: _TaskRecord, logs: list[dict[str, Any]]) -> list[str]:
        if logs:
            return [str(log.get("message", "")) for log in logs[-5:] if str(log.get("message", "")).strip()]
        summary = getattr(task.platform_job, "summary", {}) or {}
        if summary:
            return [json_line for json_line in self._summary_lines(summary)[:5]]
        return []

    def _summary_lines(self, summary: dict[str, Any]) -> list[str]:
        lines = []
        for key in ("status", "processed", "successful", "failed", "skipped", "embedding_model"):
            value = summary.get(key)
            if value is not None:
                lines.append(f"{key}: {value}")
        return lines

    def _deep_links(
        self,
        task: _TaskRecord,
        flow_run: dict[str, Any] | None,
        deployment: dict[str, Any] | None,
    ) -> TaskTrackerDeepLinks:
        ui_base = self._prefect_ui_base_url()
        flow_run_id = self._string_or_none(flow_run, "id")
        deployment_id = self._string_or_none(deployment, "id")
        return TaskTrackerDeepLinks(
            prefect_run_url=None if ui_base is None or flow_run_id is None else f"{ui_base}/runs/flow-run/{flow_run_id}",
            prefect_deployment_url=None if ui_base is None or deployment_id is None else f"{ui_base}/deployments/deployment/{deployment_id}",
            platform_job_url=f"/jobs/{task.platform_job.id}" if task.task_kind == "training" else None,
        )

    def _prefect_ui_base_url(self) -> str | None:
        explicit_ui_url = str(getattr(self._config.prefect, "ui_url", "") or "").rstrip("/")
        if explicit_ui_url:
            return explicit_ui_url
        api_url = str(getattr(self._config.prefect, "api_url", "") or "").rstrip("/")
        if not api_url:
            return None
        for suffix in ("/api/v1", "/api"):
            if api_url.endswith(suffix):
                return api_url[: -len(suffix)] or None
        return api_url

    def _display_name(self, task: _TaskRecord) -> str:
        if task.task_kind == "training":
            return f"Training {task.platform_job.preset_id}"
        if task.task_kind == "schedule_run":
            return f"Schedule {getattr(task.platform_job, 'schedule_name', 'run')}"
        target = getattr(task.platform_job, "target", "prediction")
        return "Embedding Batch" if target == "embedding" else f"Prediction {target}"

    def _display_status(self, platform_job: Any, prefect_state: str | None) -> str:
        if hasattr(platform_job, "state_type") and getattr(platform_job, "state_type", None):
            return self._display_status_from_prefect(str(platform_job.state_type))
        if prefect_state is None:
            status = getattr(platform_job, "status", "queued")
            return status.value if hasattr(status, "value") else str(status)
        return self._display_status_from_prefect(prefect_state)

    def _display_status_from_prefect(self, prefect_state: str) -> str:
        mapping = {
            "SCHEDULED": "queued",
            "PENDING": "queued",
            "RUNNING": "running",
            "CANCELLING": "running",
            "PAUSED": "running",
            "COMPLETED": "completed",
            "FAILED": "failed",
            "CRASHED": "failed",
            "CANCELLED": "cancelled",
        }
        return mapping.get(prefect_state, "queued")

    def _stage_for(self, prefect_state: str | None) -> str:
        if prefect_state in _TERMINAL_STATES:
            return "validation_output"
        if prefect_state in _RUNNING_STATES:
            return "execution_flow"
        return "queue_allocation"

    def _execution_kind(self, task: _TaskRecord, flow_run: dict[str, Any] | None) -> str:
        if task.task_kind == "training":
            return self._string_or_none(flow_run, "work_queue_name") or "training-default"
        if task.task_kind == "schedule_run":
            return self._string_or_none(flow_run, "flow_name") or getattr(task.platform_job, "flow_name", "schedule-run")
        target = getattr(task.platform_job, "target", "prediction")
        if target == "embedding":
            return "embedding-batch"
        return self._string_or_none(flow_run, "work_queue_name") or "predict-batch"

    def _active_node(self, task: _TaskRecord, prefect_state: str | None) -> str | None:
        if prefect_state in _QUEUE_STATES or prefect_state is None:
            return "queue"
        if prefect_state in _RUNNING_STATES:
            return "execute"
        return "output"

    def _stages(
        self,
        task: _TaskRecord,
        active_stage: str,
        prefect_state: str | None,
        task_runs: list[dict[str, Any]],
    ) -> list[TaskTrackerStage]:
        queue_stage = TaskTrackerStage(
            key="queue_allocation",
            label="Queue & Allocation",
            status=self._stage_status("queue_allocation", active_stage),
            summary=self._stage_summary("queue_allocation", task, prefect_state),
            nodes=self._queue_nodes(active_stage, prefect_state),
        )
        execution_stage = TaskTrackerStage(
            key="execution_flow",
            label="Execution Flow",
            status=self._stage_status("execution_flow", active_stage),
            summary=self._execution_summary(task_runs, prefect_state),
            nodes=self._execution_nodes(task, task_runs, active_stage, prefect_state),
        )
        validation_stage = TaskTrackerStage(
            key="validation_output",
            label="Validation & Output",
            status=self._stage_status("validation_output", active_stage),
            summary=self._stage_summary("validation_output", task, prefect_state),
            nodes=self._validation_nodes(task, active_stage, prefect_state),
        )
        return [queue_stage, execution_stage, validation_stage]

    def _queue_nodes(self, active_stage: str, prefect_state: str | None) -> list[TaskTrackerNode]:
        stage_status = self._stage_status("queue_allocation", active_stage)
        return [
            TaskTrackerNode(
                key="queue",
                label="Queue",
                status=self._node_status("queue_allocation", active_stage, stage_status, "queue"),
                detail="waiting for worker" if prefect_state in _QUEUE_STATES or prefect_state is None else "queue cleared",
                expected_start_at=None,
                started_at=None,
                ended_at=None,
            ),
            TaskTrackerNode(
                key="dispatch",
                label="Dispatch",
                status=self._node_status("queue_allocation", active_stage, stage_status, "dispatch"),
                detail="worker selection and handoff",
                expected_start_at=None,
                started_at=None,
                ended_at=None,
            ),
        ]

    def _execution_nodes(
        self,
        task: _TaskRecord,
        task_runs: list[dict[str, Any]],
        active_stage: str,
        prefect_state: str | None,
    ) -> list[TaskTrackerNode]:
        stage_status = self._stage_status("execution_flow", active_stage)
        if task_runs:
            nodes = [
                TaskTrackerNode(
                    key=self._string_or_none(run, "id") or f"task-run-{index}",
                    label=self._task_run_label(run, index=index),
                    status=self._task_run_status(run, stage_status),
                    detail=self._task_run_detail(run),
                    expected_start_at=self._task_run_timestamp(run, "expected_start_time"),
                    started_at=self._task_run_timestamp(run, "start_time"),
                    ended_at=self._task_run_timestamp(run, "end_time"),
                )
                for index, run in enumerate(task_runs, start=1)
            ]
            return nodes

        fallback_detail = self._fallback_execution_detail(task)
        return [
            TaskTrackerNode(
                key="execute",
                label=self._fallback_execution_label(task),
                status=self._node_status("execution_flow", active_stage, stage_status, "execute") if prefect_state else stage_status,
                detail=fallback_detail,
                expected_start_at=None,
                started_at=None,
                ended_at=None,
            )
        ]

    def _validation_nodes(self, task: _TaskRecord, active_stage: str, prefect_state: str | None) -> list[TaskTrackerNode]:
        stage_status = self._stage_status("validation_output", active_stage)
        if task.task_kind == "training":
            validate_detail = "check artifacts"
            output_detail = "artifacts available"
        elif task.task_kind == "prediction":
            validate_detail = "summarize output"
            output_detail = "results ready"
        else:
            validate_detail = "terminal state"
            output_detail = "run summary"
        if prefect_state not in _TERMINAL_STATES:
            output_detail = "awaiting completion"
        return [
            TaskTrackerNode(
                key="validate",
                label="Validate",
                status=self._node_status("validation_output", active_stage, stage_status, "validate"),
                detail=validate_detail,
                expected_start_at=None,
                started_at=None,
                ended_at=None,
            ),
            TaskTrackerNode(
                key="output",
                label="Output",
                status=self._node_status("validation_output", active_stage, stage_status, "output"),
                detail=output_detail,
                expected_start_at=None,
                started_at=None,
                ended_at=None,
            ),
        ]

    def _execution_summary(self, task_runs: list[dict[str, Any]], prefect_state: str | None) -> str:
        if task_runs:
            completed = sum(1 for run in task_runs if self._task_run_state_type(run) == "COMPLETED")
            total = len(task_runs)
            active = next((self._task_run_name(run) for run in task_runs if self._task_run_state_type(run) in _RUNNING_STATES), None)
            if active:
                return f"{completed}/{total} task runs completed, active: {active}"
            if prefect_state in _TERMINAL_STATES:
                return f"{completed}/{total} task runs completed"
            return f"{completed}/{total} task runs ready"
        return "Task is actively progressing" if prefect_state in _RUNNING_STATES else "Execution not active"

    def _task_run_label(self, task_run: dict[str, Any], index: int) -> str:
        name = self._task_run_name(task_run)
        if name:
            return name
        task_key = self._string_or_none(task_run, "task_key")
        if task_key:
            return task_key
        return f"Task {index}"

    def _task_run_name(self, task_run: dict[str, Any]) -> str | None:
        for key in ("name", "task_key"):
            value = self._string_or_none(task_run, key)
            if value:
                return value
        return None

    def _task_run_state_type(self, task_run: dict[str, Any]) -> str | None:
        return self._nested_string(task_run, "state", "type") or self._string_or_none(task_run, "state_type")

    def _task_run_status(self, task_run: dict[str, Any], default_status: str) -> str:
        state_type = self._task_run_state_type(task_run)
        if state_type in _TERMINAL_STATES:
            return "completed" if state_type == "COMPLETED" else "failed"
        if state_type in _RUNNING_STATES:
            return "active"
        if state_type in _QUEUE_STATES:
            return "pending"
        return default_status

    def _task_run_detail(self, task_run: dict[str, Any]) -> str:
        state_name = self._nested_string(task_run, "state", "name") or self._string_or_none(task_run, "state_name")
        start = self._string_or_none(task_run, "start_time") or self._string_or_none(task_run, "expected_start_time")
        end = self._string_or_none(task_run, "end_time")
        parts = []
        if state_name:
            parts.append(state_name)
        if start:
            parts.append(f"start {start}")
        if end:
            parts.append(f"end {end}")
        return " | ".join(parts) if parts else "Prefect task run"

    def _task_run_timestamp(self, task_run: dict[str, Any], key: str) -> datetime | None:
        value = self._string_or_none(task_run, key)
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _fallback_execution_label(self, task: _TaskRecord) -> str:
        if task.task_kind == "training":
            return "Train / Optimize"
        if task.task_kind == "schedule_run":
            return "Execute Flow"
        if getattr(task.platform_job, "target", "prediction") == "embedding":
            return "Embed Batch"
        return "Predict Batch"

    def _fallback_execution_detail(self, task: _TaskRecord) -> str:
        if task.task_kind == "training":
            return "runtime execution"
        if task.task_kind == "schedule_run":
            return "scheduled run execution"
        if getattr(task.platform_job, "target", "prediction") == "embedding":
            return "embedding worker execution"
        return "prediction worker execution"

    def _stage_status(self, stage_key: str, active_stage: str) -> str:
        order = ["queue_allocation", "execution_flow", "validation_output"]
        stage_index = order.index(stage_key)
        active_index = order.index(active_stage)
        if stage_index < active_index:
            return "completed"
        if stage_index == active_index:
            return "active"
        return "pending"

    def _node_status(self, stage_key: str, active_stage: str, stage_status: str, node_key: str) -> str:
        if stage_key != active_stage:
            return stage_status
        if node_key in {"dispatch", "output"} and stage_status == "active":
            return "active"
        return stage_status

    def _stage_summary(self, stage_key: str, task: _TaskRecord, prefect_state: str | None) -> str:
        if stage_key == "queue_allocation":
            return "Waiting for orchestration resources" if prefect_state in _QUEUE_STATES or prefect_state is None else "Scheduling completed"
        if stage_key == "execution_flow":
            return "Task is actively progressing" if prefect_state in _RUNNING_STATES else "Execution not active"
        if task.task_kind == "training":
            return "Artifacts and final status" if prefect_state in _TERMINAL_STATES else "Awaiting completion"
        if task.task_kind == "prediction":
            return "Prediction outputs and checks" if prefect_state in _TERMINAL_STATES else "Awaiting completion"
        return "Run logs and final state" if prefect_state in _TERMINAL_STATES else "Awaiting completion"

    def _capacity_status(self, slots_used: int | None, limit: int | None) -> str:
        if limit is None or limit <= 0 or slots_used is None:
            return "unknown"
        ratio = slots_used / limit
        if slots_used >= limit:
            return "at_capacity"
        if ratio >= 0.7:
            return "busy"
        return "normal"

    def _coerce_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _int_or_none(self, payload: dict[str, Any] | None, *keys: str) -> int | None:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return self._coerce_int(current)

    def _string_or_none(self, payload: dict[str, Any] | None, key: str) -> str | None:
        if not isinstance(payload, dict):
            return None
        value = payload.get(key)
        return None if value is None else str(value)

    def _nested_string(self, payload: dict[str, Any] | None, *keys: str) -> str | None:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return None if current is None else str(current)
