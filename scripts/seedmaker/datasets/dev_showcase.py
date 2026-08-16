from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from seedmaker import SeedConfig, SeedRunner, registry
from seedmaker.images import png_data_uri
from seedmaker.utils import _find_by_name, _items_from_collection_response

CLASS_LABELS = ["normal", "scratch", "particle", "residue", "crack", "void"]
SC_LABELS = ("normal", "scratch", "particle")

BALANCED_DATASET_NAME = "Dev Classification - Balanced"
REVIEW_DATASET_NAME = "Dev Classification - Review Queue"
EMPTY_DATASET_NAME = "Dev Classification - Empty"
SC_DATASET_NAME = "Dev SC Inspection - Sparse"
CLASSIFICATION_COLLECTION_NAME = "Dev Classification Bundle"
SC_COLLECTION_NAME = "Dev SC Inspection Bundle"
DYNAMIC_SC_COLLECTION_NAME = "Dev SC Dynamic Collection"
SC_SOURCE_CONNECTOR_NAME = "Dev SC Upstream"
SC_MEMBERSHIP_RULE_NAME = "New SC inspections with defects"

COMMON_METADATA_SCHEMA = {
    "source": {"type": "string", "description": "Development fixture source."},
    "split": {"type": "string", "description": "train, validation, or review."},
    "scatter_x": {"type": "float", "description": "Scatter plot X coordinate."},
    "scatter_y": {"type": "float", "description": "Scatter plot Y coordinate."},
    "point_label": {"type": "string", "description": "Scatter point group."},
    "sample_title": {"type": "string", "description": "Display title."},
    "image_count": {"type": "integer", "description": "Images in the sample."},
    "primary_image_index": {
        "type": "integer",
        "description": "Default image index.",
    },
    "review_priority": {
        "type": "integer",
        "description": "Synthetic review priority from 1 to 5.",
    },
}

config = SeedConfig(
    name="dev-showcase",
    description="Moderate, repeatable development data for all management pages",
    defer_dataset=True,
    org_name="Dev No Auth",
    org_slug="dev-no-auth",
)


def run(args: Any, runner: SeedRunner) -> int:
    from seedmaker.dev_activity import DevActivityContext

    classification_samples = _positive_count(
        args.classification_samples,
        "--classification-samples",
    )
    review_samples = _positive_count(args.review_samples, "--review-samples")
    sc_samples = _positive_count(args.sc_samples, "--sc-samples")
    sc_annotations = _positive_count(args.sc_annotations, "--sc-annotations")
    if sc_annotations > sc_samples:
        raise ValueError("--sc-annotations cannot exceed --sc-samples")

    print("[6/13] Seeding classification datasets ...")
    balanced = _ensure_dataset(
        runner,
        name=BALANCED_DATASET_NAME,
        dataset_type="image_classification",
        task_type="classification",
        label_space=CLASS_LABELS,
        storage_mode="db_full",
        metadata_schema=COMMON_METADATA_SCHEMA,
    )
    _converge_samples(
        runner,
        balanced,
        classification_samples,
        lambda index: _classification_item(index, fully_labeled=True),
    )

    review = _ensure_dataset(
        runner,
        name=REVIEW_DATASET_NAME,
        dataset_type="image_classification",
        task_type="classification",
        label_space=CLASS_LABELS,
        storage_mode="db_full",
        metadata_schema=COMMON_METADATA_SCHEMA,
    )
    _converge_samples(
        runner,
        review,
        review_samples,
        lambda index: _classification_item(
            index,
            fully_labeled=index < max(2, review_samples // 3),
            multi_image=True,
        ),
    )

    empty = _ensure_dataset(
        runner,
        name=EMPTY_DATASET_NAME,
        dataset_type="image_classification",
        task_type="classification",
        label_space=CLASS_LABELS,
        storage_mode="db_full",
        metadata_schema=COMMON_METADATA_SCHEMA,
    )

    print("[7/13] Importing the current SC inspection ...")
    inspection = _latest_inspection(runner, args.sc_inspection_time)
    sc_dataset = _ensure_sc_dataset(
        runner,
        inspection=inspection,
        max_rows=sc_samples,
    )
    actual_sc_samples = _sample_count(runner, str(sc_dataset["id"]))
    actual_sc_annotations = min(sc_annotations, actual_sc_samples)
    _converge_sc_annotations(
        runner,
        str(sc_dataset["id"]),
        actual_sc_annotations,
    )

    print("[8/13] Seeding dataset collections and revisions ...")
    classification_collection, classification_revision = _ensure_collection(
        runner,
        name=CLASSIFICATION_COLLECTION_NAME,
        description="Balanced and review-queue classification datasets.",
        target_view_id="labeled_image_v1",
        dataset_ids=(str(balanced["id"]), str(review["id"])),
    )
    sc_collection, sc_revision = _ensure_collection(
        runner,
        name=SC_COLLECTION_NAME,
        description="Saved membership snapshot for the development inspection.",
        target_view_id="patch_image_v1",
        dataset_ids=(str(sc_dataset["id"]),),
    )

    print("[9/13] Seeding a safe Source membership rule ...")
    dynamic_collection = _ensure_draft_collection(
        runner,
        name=DYNAMIC_SC_COLLECTION_NAME,
        description=(
            "Empty Collection for manual Discovery and Backfill testing. "
            "seed-dev never runs the rule."
        ),
        target_view_id="patch_image_v1",
    )
    _ensure_source_membership_rule(runner, dynamic_collection)

    print("[10/13] Seeding safe, paused schedules ...")
    _ensure_schedules(
        runner,
        classification_dataset_id=str(balanced["id"]),
        sc_dataset_id=str(sc_dataset["id"]),
    )

    print("[11/13] Seeding disabled sensor subscriptions ...")
    _ensure_sensor_subscriptions(
        runner,
        classification_dataset_id=str(balanced["id"]),
        sc_dataset_id=str(sc_dataset["id"]),
    )

    print("[12/13] Seeding non-executing job and model activity ...")
    activity = asyncio.run(
        _seed_activity(
            DevActivityContext(
                org_id=str(sc_dataset["org_id"]),
                created_by=str(sc_dataset["created_by"]),
                sc_dataset_id=str(sc_dataset["id"]),
                sc_collection_id=str(sc_collection["id"]),
                sc_collection_revision_id=str(sc_revision["id"]),
                label_space=SC_LABELS,
                sc_sample_count=actual_sc_samples,
                sc_annotation_count=actual_sc_annotations,
            )
        )
    )

    print("[13/13] Development seed summary")
    print(
        "  Datasets: 4 "
        f"({classification_samples + review_samples + actual_sc_samples} samples; "
        "1 intentionally empty)"
    )
    print(
        f"  Collections: 3 (current revisions: {classification_revision['id']}, "
        f"{sc_revision['id']}; dynamic draft: {dynamic_collection['id']})"
    )
    print(
        f"  Activity: {activity.training_jobs} training jobs, "
        f"{activity.prediction_jobs} prediction jobs, {activity.models} models"
    )
    print(
        "  Automation: 1 manual-only membership rule, 2 paused schedules, "
        "4 disabled sensor subscriptions"
    )
    print(f"  Empty-state dataset: {empty['id']}")
    return 0


def _positive_count(value: int, flag: str) -> int:
    if value < 1:
        raise ValueError(f"{flag} must be >= 1")
    return value


def _ensure_dataset(
    runner: SeedRunner,
    *,
    name: str,
    dataset_type: str,
    task_type: str,
    label_space: list[str],
    storage_mode: str,
    metadata_schema: dict[str, dict[str, str]],
) -> dict[str, Any]:
    response = runner.client.get("/api/v1/datasets", params={"limit": 200})
    response.raise_for_status()
    existing = _find_by_name(response.json(), name)
    if existing is not None:
        if existing.get("dataset_type") != dataset_type:
            raise RuntimeError(
                f"dataset {name!r} exists with dataset_type="
                f"{existing.get('dataset_type')!r}, expected {dataset_type!r}"
            )
        if existing.get("storage_mode") != storage_mode:
            raise RuntimeError(
                f"dataset {name!r} exists with storage_mode="
                f"{existing.get('storage_mode')!r}, expected {storage_mode!r}"
            )
        print(f"  Reusing dataset: {name} ({existing['id']})")
        return existing

    response = runner.client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "dataset_type": dataset_type,
            "storage_mode": storage_mode,
            "task_spec": {
                "task_type": task_type,
                "label_space": label_space,
                "metadata_schema": metadata_schema,
            },
        },
    )
    response.raise_for_status()
    dataset = response.json()
    print(f"  Created dataset: {name} ({dataset['id']})")
    return dataset


def _converge_samples(
    runner: SeedRunner,
    dataset: dict[str, Any],
    target: int,
    builder: Any,
) -> None:
    dataset_id = str(dataset["id"])
    existing = _sample_count(runner, dataset_id)
    if existing >= target:
        print(f"  {dataset['name']}: {existing} samples (target {target}; unchanged)")
        return
    created = 0
    batch_size = 30
    for start in range(existing, target, batch_size):
        items = [
            builder(index) for index in range(start, min(start + batch_size, target))
        ]
        response = runner.client.post(
            f"/api/v1/datasets/{dataset_id}/samples/import",
            json={"items": items},
        )
        response.raise_for_status()
        created += int(response.json().get("imported", 0))
    print(
        f"  {dataset['name']}: added {created}, total {_sample_count(runner, dataset_id)}"
    )


def _classification_item(
    index: int,
    *,
    fully_labeled: bool,
    multi_image: bool = False,
) -> dict[str, Any]:
    label_index = index % len(CLASS_LABELS)
    label = CLASS_LABELS[label_index]
    image_count = 3 if multi_image else 1
    images = [
        png_data_uri(
            64 if multi_image else 96,
            (37 * index + 31 * image_index) % 255,
            (73 * label_index + 23 * image_index) % 255,
            (149 + 17 * index + 11 * image_index) % 255,
        )
        for image_index in range(image_count)
    ]
    cluster_x = (label_index % 3) * 8.0 - 8.0
    cluster_y = (label_index // 3) * 9.0 - 4.5
    item: dict[str, Any] = {
        "image_uris": images,
        "metadata": {
            "source": "dev-showcase",
            "split": "review"
            if multi_image
            else ("validation" if index % 5 == 0 else "train"),
            "scatter_x": round(cluster_x + (index % 7) * 0.61, 3),
            "scatter_y": round(cluster_y + (index % 11) * 0.43, 3),
            "point_label": label,
            "sample_title": f"{label.title()} sample {index + 1}",
            "image_count": image_count,
            "primary_image_index": 0,
            "review_priority": index % 5 + 1,
        },
    }
    if fully_labeled:
        item["label"] = label
    return item


def _sample_count(runner: SeedRunner, dataset_id: str) -> int:
    response = runner.client.get(
        f"/api/v1/datasets/{dataset_id}/samples",
        params={"offset": 0, "limit": 1},
    )
    response.raise_for_status()
    return int(response.json().get("total", 0))


def _latest_inspection(
    runner: SeedRunner,
    inspection_time: str | None,
) -> dict[str, Any]:
    center = (
        datetime.fromisoformat(inspection_time)
        if inspection_time is not None
        else datetime.now(UTC)
    )
    window = timedelta(days=2 if inspection_time is not None else 365)
    response = runner.client.get(
        "/api/v1/sc/inspections",
        params={
            "start_time": (center - window).isoformat(),
            "end_time": (center + timedelta(days=1)).isoformat(),
        },
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        raise RuntimeError(
            "SC upstream returned no inspection; run make seed-wafer-mock first"
        )
    return items[0]


def _ensure_sc_dataset(
    runner: SeedRunner,
    *,
    inspection: dict[str, Any],
    max_rows: int,
) -> dict[str, Any]:
    response = runner.client.get("/api/v1/datasets", params={"limit": 200})
    response.raise_for_status()
    existing = _find_by_name(response.json(), SC_DATASET_NAME)
    if existing is not None:
        if existing.get("dataset_type") != "image_sc":
            raise RuntimeError(
                f"dataset {SC_DATASET_NAME!r} exists with incompatible type"
            )
        if existing.get("storage_mode") != "file_shard_sparse":
            raise RuntimeError(
                f"dataset {SC_DATASET_NAME!r} exists with incompatible storage mode"
            )
        source_time = (existing.get("dataset_meta") or {}).get("source_inspection_time")
        if source_time and str(source_time) != str(inspection["inspection_time"]):
            raise RuntimeError(
                f"dataset {SC_DATASET_NAME!r} points to inspection {source_time}, "
                f"but the current upstream fixture is {inspection['inspection_time']}; "
                "remove only the dev-showcase SC fixtures before changing the fixed "
                "inspection time"
            )
        existing_count = _sample_count(runner, str(existing["id"]))
        if existing_count != max_rows:
            raise RuntimeError(
                f"dataset {SC_DATASET_NAME!r} has {existing_count} samples, but "
                f"--sc-samples requested {max_rows}; remove only the dev-showcase "
                "SC fixtures before resizing the sparse import"
            )
        print(f"  Reusing SC dataset: {existing['id']}")
        return existing

    response = runner.client.post(
        "/api/v1/sc/import",
        json={
            "source_inspection_time": inspection["inspection_time"],
            "source_wafer_key": inspection["wafer_key"],
            "dataset_name": SC_DATASET_NAME,
            "storage_mode": "file_shard_sparse",
            "label_space": list(SC_LABELS),
            "max_rows": max_rows,
        },
    )
    response.raise_for_status()
    body = response.json()
    if body.get("status") == "failed" or not body.get("dataset_id"):
        raise RuntimeError(f"SC import failed: {body}")
    dataset_response = runner.client.get(f"/api/v1/datasets/{body['dataset_id']}")
    dataset_response.raise_for_status()
    dataset = dataset_response.json()
    print(
        f"  Imported SC dataset: {dataset['id']} "
        f"({body.get('imported_count', 0)} samples)"
    )
    return dataset


def _converge_sc_annotations(
    runner: SeedRunner,
    dataset_id: str,
    target: int,
) -> None:
    response = runner.client.get(
        f"/api/v1/datasets/{dataset_id}/views/patch_image_v1/samples",
        params={"offset": 0, "limit": target},
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    missing = [item for item in items[:target] if not item.get("label")]
    if not missing:
        print(
            f"  SC annotations: first {min(target, len(items))} samples already labeled"
        )
        return
    annotations = [
        {
            "defect_id": str(item["defect_id"]),
            "label": SC_LABELS[index % len(SC_LABELS)],
        }
        for index, item in enumerate(missing)
    ]
    response = runner.client.post(
        f"/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
        json={"annotations": annotations},
    )
    response.raise_for_status()
    print(f"  SC annotations: created {response.json().get('created', 0)}")


def _ensure_collection(
    runner: SeedRunner,
    *,
    name: str,
    description: str,
    target_view_id: str,
    dataset_ids: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    response = runner.client.get(
        "/api/v1/dataset-collections",
        params={"limit": 200},
    )
    response.raise_for_status()
    collection = _find_by_name(response.json(), name)
    if collection is None:
        response = runner.client.post(
            "/api/v1/dataset-collections",
            json={
                "name": name,
                "description": description,
                "target_view_id": target_view_id,
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        response.raise_for_status()
        collection = response.json()
        print(f"  Created collection: {name}")
    elif collection.get("target_view_id") != target_view_id:
        raise RuntimeError(
            f"collection {name!r} uses {collection.get('target_view_id')!r}, "
            f"expected {target_view_id!r}"
        )

    members_response = runner.client.get(
        f"/api/v1/dataset-collections/{collection['id']}/members"
    )
    members_response.raise_for_status()
    members = members_response.json()
    existing_ids = {str(item["source_dataset_id"]) for item in members}
    unexpected = existing_ids - set(dataset_ids)
    if unexpected:
        raise RuntimeError(
            f"collection {name!r} has unexpected members {sorted(unexpected)}"
        )
    missing_ids = [
        dataset_id for dataset_id in dataset_ids if dataset_id not in existing_ids
    ]
    if missing_ids:
        response = runner.client.post(
            f"/api/v1/dataset-collections/{collection['id']}/members",
            json={
                "expected_definition_version": collection["definition_version"],
                "members": [
                    {
                        "source_dataset_id": dataset_id,
                        "position": dataset_ids.index(dataset_id),
                        "filter_spec": {},
                        "label_mapping": {},
                        "sampling_spec": {},
                    }
                    for dataset_id in missing_ids
                ],
            },
        )
        response.raise_for_status()
        collection = response.json()["collection"]

    revisions_response = runner.client.get(
        f"/api/v1/dataset-collections/{collection['id']}/revisions"
    )
    revisions_response.raise_for_status()
    revisions = revisions_response.json()
    revision = next(
        (
            item
            for item in revisions
            if item.get("definition_version") == collection["definition_version"]
            and item.get("status") == "ready"
        ),
        None,
    )
    if revision is None:
        response = runner.client.post(
            f"/api/v1/dataset-collections/{collection['id']}/revisions",
            json={"expected_definition_version": collection["definition_version"]},
        )
        response.raise_for_status()
        revision = response.json()
        print(f"  Created collection revision: {name} r{revision['revision_number']}")
    else:
        print(f"  Reusing collection revision: {name} r{revision['revision_number']}")
    return collection, revision


def _ensure_draft_collection(
    runner: SeedRunner,
    *,
    name: str,
    description: str,
    target_view_id: str,
) -> dict[str, Any]:
    response = runner.client.get(
        "/api/v1/dataset-collections",
        params={"limit": 200},
    )
    response.raise_for_status()
    collection = _find_by_name(response.json(), name)
    if collection is None:
        response = runner.client.post(
            "/api/v1/dataset-collections",
            json={
                "name": name,
                "description": description,
                "target_view_id": target_view_id,
                "duplicate_policy": "keep_all",
                "missing_data_policy": "fail",
            },
        )
        response.raise_for_status()
        collection = response.json()
        print(f"  Created dynamic Collection: {name}")
    elif collection.get("target_view_id") != target_view_id:
        raise RuntimeError(
            f"collection {name!r} uses {collection.get('target_view_id')!r}, "
            f"expected {target_view_id!r}"
        )
    return collection


def _ensure_source_membership_rule(
    runner: SeedRunner,
    collection: dict[str, Any],
) -> None:
    response = runner.client.get("/api/v1/source-connectors")
    response.raise_for_status()
    connector = _find_by_name(response.json(), SC_SOURCE_CONNECTOR_NAME)
    if connector is None:
        response = runner.client.post(
            "/api/v1/source-connectors",
            json={
                "provider_id": "sc",
                "name": SC_SOURCE_CONNECTOR_NAME,
                "config": {},
            },
        )
        response.raise_for_status()
        connector = response.json()
        print(f"  Created Source connector: {SC_SOURCE_CONNECTOR_NAME}")
    elif connector.get("provider_id") != "sc":
        raise RuntimeError(
            f"source connector {SC_SOURCE_CONNECTOR_NAME!r} uses provider "
            f"{connector.get('provider_id')!r}, expected 'sc'"
        )

    rules_response = runner.client.get(
        f"/api/v1/dataset-collections/{collection['id']}/membership-rules"
    )
    rules_response.raise_for_status()
    rule = _find_by_name(rules_response.json(), SC_MEMBERSHIP_RULE_NAME)
    if rule is not None:
        version = rule.get("active_version", {})
        if version.get("connector_id") != connector["id"]:
            raise RuntimeError(
                f"membership rule {SC_MEMBERSHIP_RULE_NAME!r} uses a different "
                "Source connector"
            )
        print(f"  Reusing membership rule: {SC_MEMBERSHIP_RULE_NAME}")
        return

    profile_response = runner.client.post(
        f"/api/v1/source-connectors/{connector['id']}/import-profiles",
        json={
            "name": "Dev SC inspection import",
            "settings": {"label_space": list(SC_LABELS)},
            "max_records_per_run": 10,
            "max_rows_per_dataset": 2500,
        },
    )
    profile_response.raise_for_status()
    profile = profile_response.json()
    rule_response = runner.client.post(
        f"/api/v1/dataset-collections/{collection['id']}/membership-rules",
        json={
            "name": SC_MEMBERSHIP_RULE_NAME,
            "connector_id": connector["id"],
            "import_profile_version_id": profile["id"],
            "condition": {
                "kind": "group",
                "combinator": "all",
                "children": [
                    {
                        "kind": "predicate",
                        "field": "defects",
                        "operator": "gte",
                        "value": 1,
                    }
                ],
            },
        },
    )
    rule_response.raise_for_status()
    print(f"  Created membership rule: {SC_MEMBERSHIP_RULE_NAME}")


def _ensure_schedules(
    runner: SeedRunner,
    *,
    classification_dataset_id: str,
    sc_dataset_id: str,
) -> None:
    definitions = (
        {
            "name": "Dev Monthly Classification Export (paused)",
            "cron": "0 2 1 * *",
            "timezone": "UTC",
            "parameters": {
                "dataset_id": classification_dataset_id,
                "target_format": "jsonl",
                "destination": "local",
            },
        },
        {
            "name": "Dev Quarterly SC Export (paused)",
            "cron": "30 3 1 1,4,7,10 *",
            "timezone": "Asia/Shanghai",
            "parameters": {
                "dataset_id": sc_dataset_id,
                "target_format": "parquet",
                "destination": "local",
            },
        },
    )
    response = runner.client.get("/api/v1/schedules", params={"limit": 200})
    response.raise_for_status()
    schedules = list(_items_from_collection_response(response.json()))
    for definition in definitions:
        existing = _find_by_name(schedules, str(definition["name"]))
        if existing is None:
            response = runner.client.post(
                "/api/v1/schedules",
                json={
                    **definition,
                    "flow_name": "drain-dataset",
                    "description": (
                        "Development display fixture. Created paused and never "
                        "triggered by seed-dev."
                    ),
                },
            )
            response.raise_for_status()
            existing = response.json()
        response = runner.client.patch(
            f"/api/v1/schedules/{existing['id']}",
            json={
                "cron": definition["cron"],
                "timezone": definition["timezone"],
                "parameters": definition["parameters"],
                "is_schedule_active": False,
                "description": (
                    "Development display fixture. Created paused and never "
                    "triggered by seed-dev."
                ),
            },
        )
        response.raise_for_status()


def _ensure_sensor_subscriptions(
    runner: SeedRunner,
    *,
    classification_dataset_id: str,
    sc_dataset_id: str,
) -> None:
    definitions = (
        (
            "dataset_size_sensor",
            "train",
            {"dataset_id": classification_dataset_id, "min_sample_count": 100},
        ),
        (
            "dataset_size_sensor",
            "predict",
            {"dataset_id": sc_dataset_id, "min_sample_count": 1000},
        ),
        ("timer_sensor", "train", {"year": 2099, "month": 1, "day": 1}),
        ("timer_sensor", "predict", {"year": 2099, "month": 7, "day": 1}),
    )
    by_sensor: dict[str, list[dict[str, Any]]] = {}
    for sensor_id, workflow_type, filter_config in definitions:
        if sensor_id not in by_sensor:
            response = runner.client.get(f"/api/v1/sensors/{sensor_id}/subscriptions")
            response.raise_for_status()
            by_sensor[sensor_id] = response.json()
        existing = next(
            (
                item
                for item in by_sensor[sensor_id]
                if item.get("workflow_type") == workflow_type
                and item.get("filter_config") == filter_config
            ),
            None,
        )
        if existing is None:
            response = runner.client.post(
                f"/api/v1/sensors/{sensor_id}/subscriptions",
                json={
                    "workflow_type": workflow_type,
                    "filter_config": filter_config,
                    "enabled": False,
                },
            )
            response.raise_for_status()
            by_sensor[sensor_id].append(response.json())
        elif existing.get("enabled"):
            response = runner.client.patch(
                f"/api/v1/sensors/{sensor_id}/subscriptions/{existing['id']}",
                json={"enabled": False},
            )
            response.raise_for_status()


async def _seed_activity(context: Any):
    from app.core.config import load_config
    from app.shared.db.session import create_engine, create_session_factory
    from app.shared.infrastructure.storage.factory import build_artifact_storage
    from seedmaker.dev_activity import seed_dev_activity

    profile = os.environ.get("APP_CONFIG_PROFILE", "dev")
    if profile != "dev":
        raise RuntimeError(
            "dev-showcase activity records require APP_CONFIG_PROFILE=dev"
        )
    cfg = load_config()
    engine = create_engine(str(cfg.db.url), echo=False)
    try:
        return await seed_dev_activity(
            create_session_factory(engine),
            build_artifact_storage(),
            context,
        )
    finally:
        await engine.dispose()


registry.register(config, run)
