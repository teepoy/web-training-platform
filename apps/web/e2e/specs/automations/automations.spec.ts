import { expect, test } from "../../fixtures";

test("Automations is a target-bound monitoring and recovery surface @mock", async ({
  authedPage,
}) => {
  await authedPage.route("**/api/v1/automations**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        total: 2,
        items: [
          {
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
            detail: "One Dataset prediction needs attention",
          },
          {
            id: "backfill-1",
            run_source: "discovery",
            target_type: "collection",
            target_id: "collection-2",
            target_label: "Layer history",
            recipe_kind: "backfill",
            status: "needs_attention",
            started_at: "2026-08-14T00:00:00Z",
            completed_at: "2026-08-14T00:05:00Z",
            needs_attention: true,
            retry_supported: false,
            detail: "Source record changed; review the Collection",
          },
        ],
      }),
    });
  });
  await authedPage.route(
    "**/api/v1/dataset-collections/collection-1/prediction-batches/batch-1/retry",
    async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    },
  );

  await authedPage.goto("/automations");

  await expect(authedPage).toHaveURL(/\/automations$/);
  await expect(authedPage.getByRole("menuitem", { name: "Automations" })).toBeVisible();
  await expect(authedPage.getByRole("heading", { name: "Automations" })).toBeVisible();
  await expect(authedPage.getByText("Wafer review")).toBeVisible();
  await expect(authedPage.getByText("Layer history")).toBeVisible();
  await expect(authedPage.getByText("Source record changed; review the Collection")).toBeVisible();
  await expect(authedPage.getByRole("button", { name: /create automation/i })).toHaveCount(0);
  await expect(authedPage.getByRole("button", { name: "Retry" })).toHaveCount(1);
  await expect(authedPage.getByRole("button", { name: "Open Collection" })).toHaveCount(1);

  const retryRequest = authedPage.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname ===
        "/api/v1/dataset-collections/collection-1/prediction-batches/batch-1/retry",
  );
  await authedPage.getByRole("button", { name: "Retry" }).click();
  await retryRequest;
});
