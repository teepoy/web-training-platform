#!/usr/bin/env python3
"""End-to-end wafer inspection smoke test.

Uses the seedmaker / wafer_data_gen shared data generation (``wafer_demo``
coordinate distribution, digit images, 100 classes) for all upstream data.
No raw wafer SQLite DB or MinIO seeding is required.

Steps:
   1. Verify the API is healthy.
   2. Auth as seed user.
   3. Resolve organisation context.
   4. Query /sc/inspections for a mock inspection_time + wafer_key.
   5. POST /sc/import (file_shard_sparse) and use the completed direct response.
   6. List samples; random-annotate ~1k into 5 classes via /sc/.../annotations/bulk.
   7. POST /training-jobs to train on the annotated subset (5 epochs).
   8. Wait for training completion; log accuracy, F1 etc from training events.
   9. POST /predictions/run to predict every sample.
   10. Wait for prediction completion; verify every sample has a result.
   11. GET /exports/{dataset_id} + POST /exports/{dataset_id}/persist and
       verify predictions appear in the export payload.
   12. Save all timings and results to a JSON file.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.modules.sc.wafer_data_gen import LABELS as CLASS_LABELS

API_URL = "http://localhost:8000"
SEED_EMAIL = "seed@example.com"
SEED_PASSWORD = "seed1234"
DEFAULT_ANNOTATE_COUNT = 100
DEFAULT_TRAINER_ID = "resnet50-sc-v1"
DEFAULT_IMPORT_TIMEOUT = 180
DEFAULT_TRAIN_TIMEOUT = 900
DEFAULT_PREDICT_TIMEOUT = 1_800  # 30 min
DEFAULT_CLASSES = 5
DEFAULT_IMPORT_MAX_ROWS = 1000

SIMPLIFIED_LABELS = list(CLASS_LABELS.values())[:DEFAULT_CLASSES]

TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


def _fail(message: str) -> int:
    print(f"ERROR: {message}")
    return 1


def _wait_for_api(api_url: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{api_url}/health")
            if r.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise RuntimeError("API health check timed out")


def _login(api_url: str) -> str:
    r = httpx.post(
        f"{api_url}/api/v1/auth/login",
        json={"email": SEED_EMAIL, "password": SEED_PASSWORD},
    )
    r.raise_for_status()
    return str(r.json()["access_token"])


def _resolve_org(api_url: str, token: str) -> str:
    r = httpx.get(
        f"{api_url}/api/v1/organizations",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    orgs = r.json()
    if not isinstance(orgs, list) or not orgs:
        raise RuntimeError("No organisations available for seed user")
    DEFAULT_ORG = "00000000-0000-0000-0000-000000000001"
    for org in orgs:
        if org.get("id") == DEFAULT_ORG:
            return DEFAULT_ORG
    return str(orgs[0]["id"])


def _default_headers(token: str, org_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}


def _find_inspection(
    client: httpx.Client, headers: dict[str, str], api_url: str
) -> tuple[str, int]:
    """Find the first mock inspection within the last 13 days to tomorrow."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=13)).strftime("%Y-%m-%dT00:00:00")
    end = (now + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59")

    r = client.get(
        f"{api_url}/api/v1/sc/inspections",
        headers=headers,
        params={"start_time": start, "end_time": end},
    )
    r.raise_for_status()
    body = r.json()
    items = body.get("items") if isinstance(body, dict) else body
    if not isinstance(items, list) or not items:
        raise RuntimeError(
            "No inspections found. Ensure the wafer-mock store is loaded "
            "(imports wafer_mock.db_reader.WaferDBReader at startup)."
        )
    item = items[0]
    return str(item["inspection_time"]), int(item["wafer_key"])


def _start_sc_import(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    inspection_time: str,
    wafer_key: int,
    dataset_name: str,
    label_space: list[str] | None = None,
    max_rows: int | None = None,
) -> tuple[str, int]:
    payload: dict = {
        "source_inspection_time": inspection_time,
        "source_wafer_key": wafer_key,
        "dataset_name": dataset_name,
        "storage_mode": "file_shard_sparse",
    }
    if label_space:
        payload["label_space"] = label_space
    if max_rows is not None:
        payload["max_rows"] = max_rows

    r = client.post(
        f"{api_url}/api/v1/sc/import",
        headers=headers,
        json=payload,
    )
    r.raise_for_status()
    body = r.json()

    status = str(body.get("status", ""))
    if status == "failed":
        raise RuntimeError(f"sc_import failed: {body.get('error', 'unknown')}")

    dataset_id = body.get("dataset_id", "")
    imported_count = int(body.get("imported_count") or 0)
    if not dataset_id:
        raise RuntimeError(f"sc_import returned no dataset_id: {body}")

    return str(dataset_id), imported_count


def _resolve_dataset_after_import(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_name: str,
    timeout: int = 30,
) -> tuple[str, int]:
    """After import completes, resolve ``dataset_id`` and ``imported_count``.

    Polls ``GET /api/v1/datasets`` until the named dataset is found,
    then returns ``(dataset_id, imported_count)``.  ``imported_count``
    is obtained from the sparse-summary manifest when available, or 0
    as a safe fallback.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(
            f"{api_url}/api/v1/datasets",
            headers=headers,
        )
        r.raise_for_status()
        datasets = r.json()
        if isinstance(datasets, list):
            for ds in datasets:
                if ds.get("name") == dataset_name:
                    dataset_id = str(ds.get("id", "") or "")
                    if not dataset_id:
                        continue
                    try:
                        sr = client.get(
                            f"{api_url}/api/v1/datasets/{dataset_id}/sparse-summary",
                            headers=headers,
                        )
                        if sr.status_code == 200:
                            body = sr.json()
                            count = int(body.get("manifest", {}).get("total_rows", 0))
                            return dataset_id, count
                    except httpx.HTTPError:
                        pass
                    return dataset_id, 0
        time.sleep(2)
    raise RuntimeError(f"Dataset '{dataset_name}' not found after import completion")


def _list_sc_samples(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_id: str,
) -> list[dict]:
    """List all samples from the SC dataset (page through patch_image_v1 view)."""
    all_items: list[dict] = []
    offset = 0
    limit = 200
    while True:
        r = client.get(
            f"{api_url}/api/v1/datasets/{dataset_id}/views/patch_image_v1/samples",
            headers=headers,
            params={"offset": offset, "limit": limit},
        )
        print(offset)
        r.raise_for_status()
        body = r.json()
        items = body.get("items", [])
        if not items:
            break
        all_items.extend(items)
        offset += limit
        if offset >= body.get("total", 0):
            break
        # break
    return all_items


def _annotate_sc_samples(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_id: str,
    defect_ids: list[str],
    label_space: list[str],
) -> int:
    """Bulk-annotate SC samples with randomly distributed labels."""
    annotations = []
    for defect_id in defect_ids:
        label = random.choice(label_space)
        annotations.append({"defect_id": defect_id, "label": label})

    r = client.post(
        f"{api_url}/api/v1/datasets/{dataset_id}/annotations/bulk-sc",
        headers=headers,
        json={"annotations": annotations},
    )
    r.raise_for_status()
    return int(r.json().get("created", 0))


def _start_training(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_id: str,
    trainer_id: str,
) -> dict:
    r = client.post(
        f"{api_url}/api/v1/training-jobs",
        headers=headers,
        json={
            "dataset_id": dataset_id,
            "trainer_id": trainer_id,
            "created_by": "seed-user",
        },
    )
    r.raise_for_status()
    return r.json()


def _poll_training(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    job_id: str,
    timeout: int,
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(
            f"{api_url}/api/v1/training-jobs/{job_id}",
            headers=headers,
        )
        r.raise_for_status()
        body = r.json()
        if str(body.get("status", "")).lower() in TERMINAL_STATES:
            return body
        time.sleep(2)
    raise RuntimeError(f"Training job {job_id} timed out after {timeout}s")


def _collect_training_metrics(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    job_id: str,
) -> dict:
    """Collect training metrics from the event history endpoint."""
    r = client.get(
        f"{api_url}/api/v1/training-jobs/{job_id}/events/history",
        headers=headers,
        params={"offset": 0, "limit": 500},
    )
    r.raise_for_status()
    body = r.json()
    items = body.get("items") if isinstance(body, dict) else body
    if not isinstance(items, list):
        return {}

    metrics: dict = {"epoch_events": [], "metric_events": [], "final_metrics": {}}
    for ev in items:
        p = ev.get("payload", {}) or {}
        msg = str(ev.get("message", ""))
        if ev.get("level") == "metric" or "metric" in msg.lower():
            metrics["metric_events"].append(p)
            if p.get("val/acc") is not None:
                metrics["final_metrics"]["accuracy"] = p["val/acc"]
            if p.get("val/f1") is not None:
                metrics["final_metrics"]["f1"] = p["val/f1"]
            if p.get("val/loss") is not None:
                metrics["final_metrics"]["loss"] = p["val/loss"]
        if ev.get("level") == "epoch" or "epoch" in msg.lower():
            metrics["epoch_events"].append(p)

    return metrics


def _find_model(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_id: str,
    job_id: str,
) -> dict:
    r = client.get(
        f"{api_url}/api/v1/models",
        headers=headers,
        params={"dataset_id": dataset_id},
    )
    r.raise_for_status()
    models = r.json()
    if not isinstance(models, list):
        raise RuntimeError("Model list response was not a list")
    for model in models:
        if str(model.get("job_id", "")) == job_id:
            return model
    raise RuntimeError(f"No model found for training job {job_id}")


def _start_prediction(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_id: str,
    model_id: str,
    sample_ids: list[str] | None,
) -> dict:
    payload: dict = {
        "dataset_id": dataset_id,
        "model_id": model_id,
        "target": "image_classification",
    }
    if sample_ids:
        payload["sample_ids"] = sample_ids

    r = client.post(
        f"{api_url}/api/v1/predictions/run",
        headers=headers,
        json=payload,
    )
    if r.status_code >= 400:
        raise RuntimeError(
            f"POST /predictions/run failed: {r.status_code} {r.reason_phrase}\n"
            f"  request payload: {payload}\n"
            f"  response body: {r.text}"
        )
    return r.json()


def _poll_prediction(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    job_id: str,
    timeout: int,
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(
            f"{api_url}/api/v1/prediction-jobs/{job_id}",
            headers=headers,
        )
        r.raise_for_status()
        body = r.json()
        if str(body.get("status", "")).lower() in TERMINAL_STATES:
            return body
        time.sleep(2)
    raise RuntimeError(f"Prediction job {job_id} timed out after {timeout}s")


def _get_prediction_events(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    job_id: str,
    limit: int = 200,
) -> list[dict]:
    r = client.get(
        f"{api_url}/api/v1/prediction-jobs/{job_id}/events",
        headers=headers,
        params={"offset": 0, "limit": limit},
    )
    if r.status_code >= 400:
        return []
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", [])
    return items if isinstance(items, list) else []


def _get_prediction_results(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    job_id: str,
    limit: int = 200,
) -> list[dict]:
    all_items: list[dict] = []
    offset = 0
    page_limit = 1000
    while True:
        r = client.get(
            f"{api_url}/api/v1/prediction-jobs/{job_id}/predictions",
            headers=headers,
            params={"offset": offset, "limit": page_limit},
        )
        if r.status_code >= 400:
            return all_items
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", [])
        if not items:
            break
        all_items.extend(items)
        offset += page_limit
        if offset >= 20000:  # safety cap
            break
    return all_items


def _export_dataset(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_id: str,
) -> dict:
    r = client.get(
        f"{api_url}/api/v1/exports/{dataset_id}",
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


def _persist_export(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_id: str,
) -> dict:
    r = client.post(
        f"{api_url}/api/v1/exports/{dataset_id}/persist",
        headers=headers,
    )
    r.raise_for_status()
    return r.json()


def _verify_patch_image_refs(samples: list[dict], max_check: int = 5) -> dict:
    """Verify patch_image_v1 samples contain image refs with URLs.

    Checks the first *max_check* samples.  Returns a summary dict.
    """
    checked = samples[:max_check]
    with_images = 0
    with_urls = 0
    image_counts: list[int] = []
    for s in checked:
        imgs = s.get("images", []) or []
        if imgs:
            with_images += 1
        if any(img.get("url") for img in imgs):
            with_urls += 1
        image_counts.append(len(imgs))
    return {
        "checked": len(checked),
        "samples_with_images": with_images,
        "samples_with_image_urls": with_urls,
        "image_counts_per_sample": image_counts,
    }


def _verify_image_proxy_get(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    sample: dict,
    dataset_id: str,
) -> dict:
    """GET the first image proxy URL from *sample* and verify 200 + image type + non-empty body."""
    images = sample.get("images", []) or []
    if not images:
        return {"verified": False, "reason": "no images in sample"}

    img = images[0]
    url_path = img.get("url", "")
    if not url_path:
        return {"verified": False, "reason": "no url in first image"}

    # url_path is relative like /api/v1/samples/...?dataset_id=...
    full_url = f"{api_url}{url_path}"
    try:
        r = client.get(full_url, headers=headers)
        content_type = (r.headers.get("content-type") or "").lower()
        body_len = len(r.content)
        return {
            "verified": r.status_code == 200
            and content_type.startswith("image/")
            and body_len > 0,
            "status_code": r.status_code,
            "content_type": content_type,
            "body_bytes": body_len,
            "sample_id": sample.get("sample_id", ""),
            "image_id": img.get("image_id", ""),
        }
    except httpx.HTTPError as exc:
        return {"verified": False, "reason": f"HTTP error: {exc}"}


def _list_review_samples(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    dataset_id: str,
    limit: int = 5,
) -> list[dict]:
    """List samples from review_image_v1 view (first page)."""
    r = client.get(
        f"{api_url}/api/v1/datasets/{dataset_id}/views/review_image_v1/samples",
        headers=headers,
        params={"offset": 0, "limit": limit},
    )
    r.raise_for_status()
    body = r.json()
    items = body.get("items", [])
    return items if isinstance(items, list) else []


def _verify_review_images(items: list[dict]) -> dict:
    """Verify review_image_v1 items contain non-empty review_images."""
    total = len(items)
    with_reviews = sum(1 for s in items if s.get("review_images"))
    review_counts = [len(s.get("review_images", []) or []) for s in items[:5]]
    return {
        "total_items": total,
        "items_with_review_images": with_reviews,
        "review_counts_first_5": review_counts,
    }


def _verify_sc_upstream_images(
    client: httpx.Client,
    headers: dict[str, str],
    api_url: str,
    inspection_time: str,
    wafer_key: int,
    sample_defect_ids: list[str],
) -> dict:
    """Optionally verify SC upstream ``/api/v1/sc/images/...`` endpoint.

    Tries a few image types for the first defect_id.  Best-effort only;
    failures are recorded but do not fail the smoke test.
    """
    from urllib.parse import quote

    if not sample_defect_ids:
        return {"skipped": True, "reason": "no defect_ids available"}

    defect_id = sample_defect_ids[0]
    results: dict = {}
    for img_type in ("defective", "template", "review", "difference"):
        encoded_time = quote(inspection_time, safe="")
        encoded_defect = quote(defect_id, safe="")
        url = (
            f"{api_url}/api/v1/sc/images/"
            f"{encoded_time}/{wafer_key}/{encoded_defect}/{img_type}"
        )
        params: dict[str, int] = {}
        if img_type == "review":
            params["review_image_id"] = 1
        try:
            r = client.get(url, headers=headers, params=params)
            ct = (r.headers.get("content-type") or "").lower()
            bl = len(r.content)
            results[f"{img_type}_status"] = r.status_code
            results[f"{img_type}_content_type"] = ct
            results[f"{img_type}_body_bytes"] = bl
            results[f"{img_type}_ok"] = (
                r.status_code == 200 and ct.startswith("image/") and bl > 0
            )
        except httpx.HTTPError as exc:
            results[f"{img_type}_error"] = str(exc)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wafer inspection end-to-end smoke test"
    )
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--annotate", type=int, default=DEFAULT_ANNOTATE_COUNT)
    parser.add_argument("--classes", type=int, default=DEFAULT_CLASSES)
    parser.add_argument("--labels", nargs="*", default=SIMPLIFIED_LABELS)
    parser.add_argument("--trainer-id", default=DEFAULT_TRAINER_ID)
    parser.add_argument("--import-timeout", type=int, default=DEFAULT_IMPORT_TIMEOUT)
    parser.add_argument("--train-timeout", type=int, default=DEFAULT_TRAIN_TIMEOUT)
    parser.add_argument("--predict-timeout", type=int, default=DEFAULT_PREDICT_TIMEOUT)
    parser.add_argument("--import-max-rows", type=int, default=DEFAULT_IMPORT_MAX_ROWS)
    parser.add_argument(
        "--output",
        default="smoke_wafer_e2e_result.json",
        help="Path for the result JSON file",
    )
    args = parser.parse_args()

    if args.classes > len(args.labels):
        print(
            f"WARNING: {args.classes} classes requested but only "
            f"{len(args.labels)} label names provided. "
            f"Using first {args.classes} labels."
        )

    label_space = args.labels[: args.classes]

    results: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "annotate_count": args.annotate,
        "num_classes": args.classes,
        "import_max_rows": args.import_max_rows,
        "label_space": label_space,
        "trainer_id": args.trainer_id,
        "steps": [],
    }

    def _step(name: str, **kw: object) -> None:
        entry: dict = {"step": name, "ts": datetime.now(timezone.utc).isoformat()}
        entry.update(kw)
        results["steps"].append(entry)

    try:
        # ── 1. Wait for API health ───────────────────────────────
        print("[1/12] Waiting for API health ...")
        _wait_for_api(args.api_url)

        # ── 2. Login ─────────────────────────────────────────────
        print("[2/12] Logging in as seed user ...")
        token = _login(args.api_url)

        # ── 3. Resolve org ───────────────────────────────────────
        print("[3/12] Resolving organisation context ...")
        org_id = _resolve_org(args.api_url, token)
        headers = _default_headers(token, org_id)

        with httpx.Client(timeout=60.0) as client:
            # ── 4. Find inspection ──────────────────────────────
            print("[4/12] Fetching inspection metadata ...")
            inspection_time, wafer_key = _find_inspection(client, headers, args.api_url)
            _step(
                "find_inspection",
                inspection_time=inspection_time,
                wafer_key=wafer_key,
            )
            print(f"  inspection_time={inspection_time}, wafer_key={wafer_key}")

            # ── 5. Start SC import (file_shard_sparse) ─────────
            dataset_name = f"Wafer E2E Smoke {uuid.uuid4().hex[:8]}"
            print(f"[5/12] Starting SC import → {dataset_name} ...")
            t0 = time.time()
            dataset_id, imported_count = _start_sc_import(
                client,
                headers,
                args.api_url,
                inspection_time,
                wafer_key,
                dataset_name,
                label_space=label_space,
                max_rows=args.import_max_rows,
            )
            _step(
                "sc_import_completed",
                dataset_id=dataset_id,
                imported_count=imported_count,
            )
            results["dataset_id"] = dataset_id
            results["dataset_name"] = dataset_name

            print(f"  dataset_id={dataset_id}  imported_count={imported_count}")

            # Resolve real dataset_id and imported_count from completed import
            resolved_dataset_id, resolved_imported_count = (
                _resolve_dataset_after_import(
                    client,
                    headers,
                    args.api_url,
                    dataset_name,
                )
            )
            if not resolved_dataset_id:
                raise RuntimeError(
                    "SC import completed but dataset_id is empty "
                    f"(dataset_name={dataset_name})"
                )
            dataset_id = resolved_dataset_id
            imported_count = resolved_imported_count

            import_elapsed = time.time() - t0
            _step(
                "sc_import_completed",
                dataset_id=dataset_id,
                imported_count=imported_count,
                elapsed_sec=round(import_elapsed, 1),
            )
            results["dataset_id"] = dataset_id
            results["imported_count"] = imported_count
            results["import_elapsed_sec"] = round(import_elapsed, 1)
            print(
                f"  Import completed in {import_elapsed:.1f}s "
                f"— {imported_count} samples"
            )

            # ── 6. Get samples & image validation ──────────────
            print("[6/12] Listing samples ...")
            samples = _list_sc_samples(client, headers, args.api_url, dataset_id)
            results["total_samples"] = len(samples)
            print(f"  Dataset has {len(samples)} samples")

            # ── 7. Image availability validation ─────────────
            print("[7/12] Validating image availability ...")
            t0_img = time.time()

            img_verify = _verify_patch_image_refs(samples, max_check=5)
            print(
                f"  patch_image_v1: {img_verify['samples_with_image_urls']}/"
                f"{img_verify['checked']} have image URLs"
            )

            proxy_result: dict = {"verified": False, "reason": "no sample attempted"}
            if samples:
                proxy_result = _verify_image_proxy_get(
                    client, headers, args.api_url, samples[0], dataset_id
                )
            proxy_ok = proxy_result.get("verified", False)
            print(
                f"  image proxy GET: {'PASS' if proxy_ok else 'FAIL'} "
                f"(status={proxy_result.get('status_code')}, "
                f"type={proxy_result.get('content_type')}, "
                f"bytes={proxy_result.get('body_bytes')})"
            )

            review_items = _list_review_samples(
                client, headers, args.api_url, dataset_id, limit=5
            )
            review_verify = _verify_review_images(review_items)
            print(
                f"  review_image_v1: {review_verify['items_with_review_images']}/"
                f"{review_verify['total_items']} with review_images"
            )

            # Optional SC upstream image check (best-effort)
            upstream_result = _verify_sc_upstream_images(
                client,
                headers,
                args.api_url,
                str(inspection_time),
                wafer_key,
                [s["defect_id"] for s in samples[:1] if s.get("defect_id")],
            )

            img_elapsed = time.time() - t0_img
            _step(
                "image_verification",
                patch_image_refs=img_verify,
                image_proxy_get=proxy_result,
                review_image_v1=review_verify,
                sc_upstream_images=upstream_result,
                elapsed_sec=round(img_elapsed, 1),
            )
            print(f"  Image validation completed in {img_elapsed:.1f}s")

            annotate_count = min(args.annotate, len(samples))
            selected_defect_ids = random.sample(
                [s["defect_id"] for s in samples if s.get("defect_id")],
                annotate_count,
            )

            print(
                f"[8/12] Annotating {annotate_count} samples "
                f"into {args.classes} classes ..."
            )
            t0 = time.time()
            created = _annotate_sc_samples(
                client,
                headers,
                args.api_url,
                dataset_id,
                selected_defect_ids,
                label_space,
            )
            annot_elapsed = time.time() - t0
            _step(
                "annotate",
                annotated=created,
                elapsed_sec=round(annot_elapsed, 1),
                sample_defect_ids=selected_defect_ids[:10] + ["..."],
            )
            results["annotated_count"] = created
            print(f"  Created {created} annotations in {annot_elapsed:.1f}s")

            # ── 9. Train ──────────────────────────────────────
            print(f"[9/12] Starting training (trainer={args.trainer_id}) ...")
            t0 = time.time()
            train_job = _start_training(
                client, headers, args.api_url, dataset_id, args.trainer_id
            )
            train_job_id = str(train_job["id"])
            _step("training_started", job_id=train_job_id)
            results["train_job_id"] = train_job_id

            train_result = _poll_training(
                client, headers, args.api_url, train_job_id, args.train_timeout
            )
            train_elapsed = time.time() - t0
            _step(
                "training_completed",
                status=train_result.get("status"),
                elapsed_sec=round(train_elapsed, 1),
            )
            results["train_elapsed_sec"] = round(train_elapsed, 1)
            results["train_status"] = train_result.get("status")

            if str(train_result.get("status", "")).lower() != "completed":
                raise RuntimeError(
                    f"Training ended with status={train_result.get('status')}"
                )

            # Collect training metrics (accuracy, F1, etc.)
            metrics = _collect_training_metrics(
                client, headers, args.api_url, train_job_id
            )
            results["train_metrics"] = metrics

            print(f"  Training completed in {train_elapsed:.1f}s")
            if metrics.get("final_metrics"):
                print(
                    f"  Final metrics: {json.dumps(metrics['final_metrics'], indent=2)}"
                )
            print(
                f"  Epoch events: {len(metrics.get('epoch_events', []))}, "
                f"Metric events: {len(metrics.get('metric_events', []))}"
            )

            # ── 10. Find trained model ────────────────────────
            print("[10/12] Locating trained model ...")
            model = _find_model(client, headers, args.api_url, dataset_id, train_job_id)
            model_id = str(model["id"])
            _step("model_found", model_id=model_id)
            results["model_id"] = model_id
            print(f"  model_id={model_id}")

            # ── 11. Predict on all samples ────────────────────
            print(f"[11/12] Starting prediction on all {len(samples)} samples ...")
            all_sample_ids = [s["sample_id"] for s in samples if s.get("sample_id")]
            t0 = time.time()
            pred_job = _start_prediction(
                client,
                headers,
                args.api_url,
                dataset_id,
                model_id,
                None,
            )
            pred_job_id = str(pred_job["id"])
            _step("prediction_started", job_id=pred_job_id)
            results["predict_job_id"] = pred_job_id

            pred_result = _poll_prediction(
                client, headers, args.api_url, pred_job_id, args.predict_timeout
            )
            predict_elapsed = time.time() - t0
            _step(
                "prediction_completed",
                status=pred_result.get("status"),
                elapsed_sec=round(predict_elapsed, 1),
            )
            results["predict_elapsed_sec"] = round(predict_elapsed, 1)
            results["predict_status"] = pred_result.get("status")

            if str(pred_result.get("status", "")).lower() != "completed":
                pred_summary = pred_result.get("summary", {}) or {}
                pred_events = _get_prediction_events(
                    client, headers, args.api_url, pred_job_id
                )
                event_tail = pred_events[-10:] if pred_events else []
                event_lines = "\n".join(
                    f"    [{e.get('level')}] {e.get('message')} "
                    f"payload={e.get('payload')}"
                    for e in event_tail
                )
                raise RuntimeError(
                    f"Prediction ended with status={pred_result.get('status')}\n"
                    f"  summary: {json.dumps(pred_summary, default=str)}\n"
                    f"  last {len(event_tail)} events:\n{event_lines}"
                )

            summary = pred_result.get("summary", {})
            results["prediction_summary"] = dict(summary)
            processed = int(summary.get("processed", 0))
            successful = int(summary.get("successful", 0))
            print(
                f"  Prediction completed in {predict_elapsed:.1f}s "
                f"(processed={processed}, successful={successful})"
            )

            # ── Verify prediction counts ──
            total = len(all_sample_ids)
            if processed != total:
                raise RuntimeError(
                    f"Prediction processed count mismatch: "
                    f"expected {total}, got {processed}"
                )
            if successful != total:
                raise RuntimeError(
                    f"Prediction successful count mismatch: "
                    f"expected {total}, got {successful}"
                )

            # Verify every sample was predicted
            pred_results_list = _get_prediction_results(
                client, headers, args.api_url, pred_job_id
            )
            results["sample_prediction_count"] = len(pred_results_list)

            covered = len(pred_results_list)
            print(
                f"  Prediction coverage: {covered}/{total} samples "
                f"({100 * covered / total:.1f}%)"
                if total
                else ""
            )

            if covered != total:
                raise RuntimeError(
                    f"Prediction coverage mismatch: expected {total}, got {covered}"
                )

            # ── 12. Export ────────────────────────────────────
            print("[12/12] Exporting dataset ...")
            export_data = _export_dataset(client, headers, args.api_url, dataset_id)
            export_str = json.dumps(export_data, default=str).lower()
            has_predictions = (
                "predicted_label" in export_str or "prediction" in export_str
            )
            results["export_has_predictions"] = has_predictions

            persist_result = _persist_export(client, headers, args.api_url, dataset_id)
            results["export_persist_uri"] = str(persist_result.get("uri", ""))
            print(f"  Export URI: {results['export_persist_uri']}")
            print(f"  Predictions present in export: {has_predictions}")

        # ── Save results ─────────────────────────────────────
        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        results["passed"] = True

        output_path = Path(args.output)
        output_path.write_text(
            json.dumps(results, indent=2, default=str, ensure_ascii=False)
        )
        print(f"\nSmoke test PASSED. Results saved to {output_path}")
        return 0

    except Exception as exc:
        results["error"] = str(exc)
        results["passed"] = False
        results["completed_at"] = datetime.now(timezone.utc).isoformat()

        output_path = Path(args.output)
        output_path.write_text(
            json.dumps(results, indent=2, default=str, ensure_ascii=False)
        )
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
