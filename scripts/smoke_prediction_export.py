#!/usr/bin/env python3
"""Focused prediction + export smoke test — reuses an existing dataset and model."""

from __future__ import annotations

import json
import time

import httpx

from smoke_common import login_smoke_user, resolve_smoke_org

API_URL = "http://localhost:8000"
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})

DATASET_ID = "84f7c068-4c9c-440a-b034-b24f529a4dbc"
MODEL_ID = "286f1f33-ab91-4383-aa2e-ecaf1bdf683b"


def _headers(token: str, org_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}


def _list_sample_ids(
    client: httpx.Client, h: dict, ds_id: str, max_count: int = 200
) -> list[str]:
    ids: list[str] = []
    offset = 0
    limit = 200
    while True:
        r = client.get(
            f"{API_URL}/api/v1/datasets/{ds_id}/views/patch_image_v1/samples",
            headers=h,
            params={"offset": offset, "limit": limit},
        )
        r.raise_for_status()
        body = r.json()
        items = body.get("items", [])
        if not items:
            break
        ids.extend(s.get("sample_id", "") for s in items if s.get("sample_id"))
        if len(ids) >= max_count:
            break
        offset += limit
        if offset >= body.get("total", 0):
            break
    return ids


def _start_prediction(
    client: httpx.Client, h: dict, ds_id: str, model_id: str, sample_ids: list[str]
) -> dict:
    r = client.post(
        f"{API_URL}/api/v1/predictions/run",
        headers=h,
        json={
            "dataset_id": ds_id,
            "model_id": model_id,
            "target": "image_classification",
            "sample_ids": sample_ids,
        },
    )
    if r.status_code >= 400:
        raise RuntimeError(f"POST /predictions/run failed: {r.status_code} {r.text}")
    return r.json()


def _poll_prediction(client: httpx.Client, h: dict, job_id: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"{API_URL}/api/v1/prediction-jobs/{job_id}", headers=h)
        r.raise_for_status()
        body = r.json()
        if str(body.get("status", "")).lower() in TERMINAL_STATES:
            return body
        time.sleep(2)
    raise RuntimeError(f"Prediction job {job_id} timed out")


def _get_prediction_results(client: httpx.Client, h: dict, job_id: str) -> list[dict]:
    r = client.get(f"{API_URL}/api/v1/prediction-jobs/{job_id}/predictions", headers=h)
    r.raise_for_status()
    body = r.json()
    return body if isinstance(body, list) else body.get("items", [])


def _export_dataset(client: httpx.Client, h: dict, ds_id: str) -> dict:
    r = client.get(f"{API_URL}/api/v1/exports/{ds_id}", headers=h)
    r.raise_for_status()
    return r.json()


def _persist_export(client: httpx.Client, h: dict, ds_id: str) -> dict:
    r = client.post(f"{API_URL}/api/v1/exports/{ds_id}/persist", headers=h)
    r.raise_for_status()
    return r.json()


def _check_export_predictions(export_data: dict) -> dict:
    export_str = json.dumps(export_data, default=str).lower()
    has_pred_label = "predicted_label" in export_str
    has_prediction = "prediction" in export_str
    # deeper: check if samples array contains predictions
    samples = export_data.get("samples", []) or []
    predicted_count = sum(
        1
        for s in samples
        if isinstance(s, dict) and (s.get("predicted_label") or s.get("prediction"))
    )
    return {
        "has_predicted_label": has_pred_label,
        "has_prediction_key": has_prediction,
        "total_samples_in_export": len(samples),
        "samples_with_predictions": predicted_count,
    }


def main() -> int:
    print("[1] Login ...")
    token = login_smoke_user(API_URL)
    org_id = resolve_smoke_org(API_URL, token)
    h = _headers(token, org_id)

    with httpx.Client(timeout=60.0) as client:
        print(f"[2] Listing samples for dataset {DATASET_ID} ...")
        sample_ids = _list_sample_ids(client, h, DATASET_ID, max_count=100)
        print(f"    Using {len(sample_ids)} samples (100 limit)")

        print(f"[3] Starting prediction (model={MODEL_ID}) ...")
        t0 = time.time()
        pred_job = _start_prediction(client, h, DATASET_ID, MODEL_ID, sample_ids)
        pred_job_id = str(pred_job["id"])
        print(f"    job_id={pred_job_id}")

        print("[4] Polling prediction ...")
        pred_result = _poll_prediction(client, h, pred_job_id, timeout=300)
        elapsed = time.time() - t0
        status = pred_result.get("status", "?")
        summary = pred_result.get("summary", {})
        processed = int(summary.get("processed", 0))
        successful = int(summary.get("successful", 0))
        print(
            f"    status={status}, processed={processed}, successful={successful}, elapsed={elapsed:.1f}s"
        )

        if status != "completed":
            print("    FAILED")
            return 1

        # count assertions (against the subset we chose, not full dataset)
        total = len(sample_ids)
        assert processed == total, f"processed={processed} != total={total}"
        assert successful == total, f"successful={successful} != total={total}"
        print(f"    [PASS] count assertions: {processed}/{total}")

        print("[5] Verifying prediction results ...")
        pred_results = _get_prediction_results(client, h, pred_job_id)
        covered = len(pred_results)
        assert covered == total, f"coverage={covered} != total={total}"
        print(f"    [PASS] coverage: {covered}/{total}")

        # Verify every prediction has label + confidence
        labeled = sum(1 for p in pred_results if p.get("predicted_label"))
        confident = sum(1 for p in pred_results if p.get("confidence") is not None)
        print(f"    labeled={labeled}, with_confidence={confident}")

        print("[6] Export dataset ...")
        export_data = _export_dataset(client, h, DATASET_ID)
        export_check = _check_export_predictions(export_data)
        print(f"    export: {json.dumps(export_check)}")

        persist_result = _persist_export(client, h, DATASET_ID)
        uri = str(persist_result.get("uri", ""))
        print(f"    persist URI: {uri}")

        assert export_check["samples_with_predictions"] > 0, (
            "Export contains no prediction data"
        )
        print("    [PASS] export contains predictions")

        # Save result
        result = {
            "dataset_id": DATASET_ID,
            "model_id": MODEL_ID,
            "predict_job_id": pred_job_id,
            "total_samples": total,
            "prediction_status": status,
            "prediction_processed": processed,
            "prediction_successful": successful,
            "prediction_covered": covered,
            "prediction_labeled": labeled,
            "prediction_with_confidence": confident,
            "export_check": export_check,
            "export_uri": uri,
            "elapsed_sec": round(elapsed, 1),
        }
        print(f"\nALL PASSED: {json.dumps(result, indent=2, default=str)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
