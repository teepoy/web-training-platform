import type { DatasetCollectionResponse } from "../../../src/generated/orval/models";
import { expect, test } from "../../fixtures";

test("selects and deletes multiple owned dataset collections @mock", async ({ authedPage }) => {
  const collections: DatasetCollectionResponse[] = [
    {
      id: "collection-bulk-1",
      org_id: "org-e2e-1",
      name: "Bulk Collection One",
      description: "First collection",
      target_view_id: "labeled_image_v1",
      target_view_contract: "labeled_image_v1",
      target_schema_version: "1",
      duplicate_policy: "keep_all",
      missing_data_policy: "error",
      definition_version: 1,
      created_by: "user-e2e-1",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
    {
      id: "collection-bulk-2",
      org_id: "org-e2e-1",
      name: "Bulk Collection Two",
      description: "Second collection",
      target_view_id: "labeled_image_v1",
      target_view_contract: "labeled_image_v1",
      target_schema_version: "1",
      duplicate_policy: "keep_all",
      missing_data_policy: "error",
      definition_version: 1,
      created_by: "user-e2e-1",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  ];
  await authedPage.route("**/api/v1/dataset-collections**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "DELETE") {
      const collectionId = url.pathname.split("/").pop();
      const index = collections.findIndex((collection) => collection.id === collectionId);
      if (index >= 0) collections.splice(index, 1);
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: collections, total: collections.length }),
    });
  });

  await authedPage.goto("/library?tab=collections");
  await authedPage.getByRole("heading", { name: "Library" }).waitFor();

  const rowCheckboxes = authedPage.getByRole("checkbox");
  await rowCheckboxes.nth(1).check();
  await rowCheckboxes.nth(2).check();
  await expect(authedPage).toHaveURL(/\/library\?tab=collections$/);
  await expect(authedPage.getByText("2 collections selected")).toBeVisible();

  authedPage.once("dialog", (dialog) => dialog.accept());
  await authedPage.getByRole("button", { name: "Delete selected" }).click();

  await expect(authedPage.getByText("Bulk Collection One")).toHaveCount(0);
  await expect(authedPage.getByText("Bulk Collection Two")).toHaveCount(0);
});
