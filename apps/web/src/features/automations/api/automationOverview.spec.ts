import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/testing/msw/server";
import {
  listAutomationRuns,
  retryAutomationRun,
  type AutomationRunOverview,
} from "./automationOverview";

const predictionRun: AutomationRunOverview = {
  id: "batch-1",
  run_source: "prediction_batch",
  target_type: "collection",
  target_id: "collection-1",
  target_label: "Wafer review",
  recipe_kind: "prediction",
  status: "partial",
  started_at: "2026-08-15T00:00:00Z",
  completed_at: "2026-08-15T00:02:00Z",
  needs_attention: true,
  retry_supported: true,
  detail: "One prediction failed",
};

describe("automation overview API", () => {
  it("sends scalable server-side filters", async () => {
    server.use(
      http.get("/api/v1/automations", ({ request }) => {
        const params = new URL(request.url).searchParams;
        expect(Object.fromEntries(params)).toEqual({
          offset: "20",
          limit: "20",
          status: "needs_attention",
          kind: "prediction",
          q: "wafer",
        });
        return HttpResponse.json({ items: [predictionRun], total: 1 });
      }),
    );

    await expect(
      listAutomationRuns({
        offset: 20,
        limit: 20,
        status: "needs_attention",
        kind: "prediction",
        q: "wafer",
      }),
    ).resolves.toEqual({ items: [predictionRun], total: 1 });
  });

  it("uses the target-bound prediction retry endpoint", async () => {
    server.use(
      http.post("/api/v1/dataset-collections/collection-1/prediction-batches/batch-1/retry", () =>
        HttpResponse.json({ ok: true }),
      ),
    );

    await expect(retryAutomationRun(predictionRun)).resolves.toEqual({ ok: true });
  });

  it("does not retry an ambiguous discovery attention state", async () => {
    await expect(
      retryAutomationRun({
        ...predictionRun,
        run_source: "discovery",
        recipe_kind: "backfill",
        retry_supported: false,
      }),
    ).rejects.toThrow("no retryable work");
  });
});
