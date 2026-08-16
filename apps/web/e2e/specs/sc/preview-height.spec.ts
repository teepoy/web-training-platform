/**
 * SC preview page height spec — mock mode.
 *
 * Verifies that the SC preview page body/document does not overflow
 * the viewport (allowing small tolerance for borders).
 *
 * @mock — uses authedPage (auto mock) + apiMocks SC handlers.
 */
import { test, expect } from "../../fixtures";

test("sc preview page height does not overflow viewport @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.sc.mockScInspections();
  await apiMocks.sc.mockScInspectionSamples();

  await authedPage.goto("/sc/preview");
  await authedPage.waitForLoadState("networkidle");

  const viewport = authedPage.viewportSize();
  expect(viewport).not.toBeNull();

  const bodyHeight = await authedPage.evaluate(() => document.body.scrollHeight);
  const docHeight = await authedPage.evaluate(() => document.documentElement.scrollHeight);

  console.log(
    `viewport: ${viewport!.width}x${viewport!.height}, body scroll: ${bodyHeight}, doc scroll: ${docHeight}`,
  );

  expect(bodyHeight).toBeLessThanOrEqual(viewport!.height + 2);
  expect(docHeight).toBeLessThanOrEqual(viewport!.height + 2);
});

test("sc preview attaches help to inputs and only shows collection action after selection @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.sc.mockScInspections();
  await apiMocks.sc.mockScInspectionSamples();

  await authedPage.goto("/sc/preview");
  await authedPage.waitForLoadState("networkidle");

  await expect(authedPage.getByText("Filter help", { exact: true })).toHaveCount(0);
  await expect(authedPage.getByRole("button", { name: "Inspection filter syntax" })).toHaveCount(0);
  await authedPage.getByPlaceholder("Device").hover();
  await expect(authedPage.getByText(/Blank includes every device/)).toBeVisible();

  const searchBar = authedPage.locator(".sc-preview-search-bar");
  const buildCollection = searchBar.getByRole("button", { name: /Build collection/i });
  await expect(buildCollection).toHaveCount(0);
  await authedPage.getByRole("checkbox").nth(1).check();
  await expect(buildCollection).toBeVisible();
  await expect(buildCollection).toHaveText("Build collection (1)");

  const search = searchBar.getByRole("button", { name: "Search", exact: true });
  expect((await buildCollection.boundingBox())!.x).toBeGreaterThan((await search.boundingBox())!.x);
});

test("sc preview opens one or many linked datasets in new tabs @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.sc.mockScInspections({
    datasets: [
      { id: "dataset-one", name: "First dataset" },
      { id: "dataset-two", name: "Second dataset" },
    ],
  });
  await apiMocks.sc.mockScInspectionSamples();
  await authedPage.goto("/sc/preview");
  await authedPage.waitForLoadState("networkidle");

  await authedPage.getByRole("button", { name: "Datasets (2)" }).click();
  await expect(authedPage.getByText("First dataset", { exact: true })).toBeVisible();
  const popupPromise = authedPage.waitForEvent("popup");
  await authedPage.getByTestId("open-dataset-dataset-one").click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(/\/datasets\/dataset-one$/);
});

test("sc preview exposes explicit row actions without triggering the row click @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.sc.mockScInspections();
  await apiMocks.sc.mockScInspectionSamples();
  await authedPage.goto("/sc/preview");
  await authedPage.waitForLoadState("networkidle");

  const row = authedPage.getByTestId(/inspection-row-/).first();
  await expect(row.getByRole("button", { name: "Preview", exact: true })).toBeVisible();
  await expect(row.getByRole("button", { name: "New dataset", exact: true })).toBeVisible();
  await expect(row.getByText("None", { exact: true })).toBeVisible();

  const popupPromise = authedPage.waitForEvent("popup");
  await row.getByRole("button", { name: "Preview", exact: true }).click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(/\/sc\/inspections\/.*\/1$/);
});

test("sc preview creates another dataset from the row action @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.sc.mockScInspections({
    datasets: [{ id: "dataset-one", name: "First dataset" }],
  });
  await apiMocks.sc.mockScInspectionSamples();
  let importPayload: Record<string, unknown> | undefined;
  await authedPage.route("**/api/v1/sc/import/stream", async (route) => {
    importPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'event: data\ndata: {"event_type":"data","payload":{"status":"completed","dataset_id":"dataset-two","imported_count":50}}\n\n',
    });
  });
  let popupCount = 0;
  authedPage.on("popup", () => {
    popupCount += 1;
  });

  await authedPage.goto("/sc/preview");
  await authedPage.waitForLoadState("networkidle");
  const row = authedPage.getByTestId(/inspection-row-/).first();
  await row.getByRole("button", { name: "New dataset", exact: true }).click();

  await expect(row.getByRole("button", { name: "Datasets (2)", exact: true })).toBeVisible();
  expect(importPayload?.dataset_name).toBe("Patch_LOT-001_WAF-001_2026-05-26T08-00-00_2");
  expect(popupCount).toBe(0);
});
