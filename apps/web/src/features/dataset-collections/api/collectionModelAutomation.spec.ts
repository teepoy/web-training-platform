import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/testing/msw/server";
import {
  createCollectionPredictionBatch,
  listCollectionPredictionCoverage,
  updateCollectionDefaultModel,
} from "./collectionModelAutomation";

describe("collection model automation API", () => {
  it("pins an exact default model without requesting a rerun", async () => {
    let body: unknown;
    server.use(
      http.patch("/api/v1/dataset-collections/collection-1/default-model", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ default_model_id: "model-7", model_binding_version: 3 });
      }),
    );

    await expect(
      updateCollectionDefaultModel("collection-1", {
        expected_binding_version: 2,
        model_id: "model-7",
      }),
    ).resolves.toEqual({ default_model_id: "model-7", model_binding_version: 3 });
    expect(body).toEqual({ expected_binding_version: 2, model_id: "model-7" });
  });

  it("keeps latest successful coverage and an active rerun separately visible", async () => {
    server.use(
      http.get("/api/v1/dataset-collections/collection-1/prediction-coverage", ({ request }) => {
        expect(new URL(request.url).searchParams.get("snapshot_id")).toBe("snapshot-4");
        return HttpResponse.json([
          {
            member_id: "member-1",
            dataset_id: "dataset-1",
            expected_dataset_revision_id: "revision-2",
            status: "model_mismatch",
            default_model_id: "model-7",
            latest_prediction_job_id: "job-old",
            latest_prediction_model_id: "model-3",
            latest_prediction_dataset_revision_id: "revision-2",
            latest_prediction_status: "completed",
            active_prediction_job_id: "job-new",
            active_prediction_status: "running",
          },
        ]);
      }),
    );

    const result = await listCollectionPredictionCoverage("collection-1", "snapshot-4");

    expect(result[0]?.status).toBe("model_mismatch");
    expect(result[0]?.latest_prediction_job_id).toBe("job-old");
    expect(result[0]?.active_prediction_job_id).toBe("job-new");
  });

  it("submits only the explicitly selected datasets", async () => {
    let body: unknown;
    server.use(
      http.post(
        "/api/v1/dataset-collections/collection-1/prediction-batches",
        async ({ request }) => {
          body = await request.json();
          return HttpResponse.json({
            id: "batch-1",
            collection_id: "collection-1",
            collection_revision_id: "snapshot-4",
            model_id: "model-7",
            kind: "reconciliation",
            request_id: "request-1",
            status: "submitted",
            created_by: "user-1",
            created_at: "2026-08-15T00:00:00Z",
            updated_at: "2026-08-15T00:00:00Z",
            items: [],
          });
        },
      ),
    );

    await createCollectionPredictionBatch("collection-1", {
      snapshot_id: "snapshot-4",
      expected_default_model_id: "model-7",
      request_id: "request-1",
      dataset_ids: ["dataset-2", "dataset-5"],
    });

    expect(body).toEqual({
      snapshot_id: "snapshot-4",
      expected_default_model_id: "model-7",
      request_id: "request-1",
      dataset_ids: ["dataset-2", "dataset-5"],
    });
  });
});
