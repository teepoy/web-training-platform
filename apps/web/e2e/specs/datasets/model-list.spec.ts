import { expect, test } from "../../fixtures";
import { makeModel } from "../../mocks/factories";

test("model search and creator filters apply before pagination @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.prediction.mockListModels([
    makeModel({
      id: "model-alpha",
      name: "Alpha Model",
      created_by: "user-e2e-1",
      creator_name: "E2E User",
    }),
    makeModel({
      id: "model-beta",
      name: "Beta Model",
      created_by: "user-bob",
      creator_name: "Bob",
    }),
  ]);
  await authedPage.goto("/models");
  await authedPage.locator(".n-data-table").waitFor();

  await authedPage.getByPlaceholder("Search models").fill("alpha");
  await expect(authedPage.getByText("Alpha Model")).toBeVisible();
  await expect(authedPage.getByText("Beta Model")).toHaveCount(0);

  await authedPage.getByPlaceholder("Search models").clear();
  await authedPage.getByTestId("creator-scope-select").click();
  await authedPage.getByText("Bob", { exact: true }).last().click();
  await expect(authedPage.getByText("Beta Model")).toBeVisible();
  await expect(authedPage.getByText("Alpha Model")).toHaveCount(0);
});

test("model Collection sources link to Collection detail @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.prediction.mockListModels([
    makeModel({
      id: "model-collection-source",
      name: "Collection Model",
      dataset_id: null,
      dataset_name: null,
      collection_id: "collection-source-1",
      collection_name: "Source Collection",
    }),
  ]);
  await authedPage.route("**/api/v1/dataset-collections/collection-source-1**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname.endsWith("/snapshot-update-status")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          snapshot_id: null,
          snapshot_revision_number: null,
          update_available: false,
          outdated_member_count: 0,
          members: [],
        }),
      });
      return;
    }
    if (
      ["/members", "/revisions", "/membership-rules", "/prediction-batches"].some((suffix) =>
        pathname.endsWith(suffix),
      )
    ) {
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "collection-source-1",
        org_id: "org-e2e-1",
        name: "Source Collection",
        description: "",
        target_view_id: "image_input_v1",
        target_view_contract: "dataset.image-input",
        target_schema_version: "1",
        duplicate_policy: "keep_all",
        missing_data_policy: "fail",
        definition_version: 1,
        default_model_id: null,
        model_binding_version: 1,
        created_by: "user-e2e-1",
        created_at: "2026-08-15T00:00:00Z",
        updated_at: "2026-08-15T00:00:00Z",
      }),
    });
  });
  await authedPage.route("**/api/v1/source-connectors**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });

  await authedPage.goto("/models");
  await authedPage.getByRole("button", { name: "Collection · Source Collection" }).click();
  await expect(authedPage).toHaveURL(/\/dataset-collections\/collection-source-1$/);
});

test("model Dataset sources link to Dataset detail @mock", async ({ authedPage, apiMocks }) => {
  await apiMocks.prediction.mockListModels([
    makeModel({
      id: "model-dataset-source",
      name: "Dataset Model",
      dataset_id: "dataset-source-1",
      dataset_name: "Source Dataset",
      collection_id: null,
      collection_name: null,
    }),
  ]);

  await authedPage.goto("/models");
  await authedPage.getByRole("button", { name: "Dataset · Source Dataset" }).click();
  await expect(authedPage).toHaveURL(/\/datasets\/dataset-source-1$/);
});

test("selects and deletes multiple owned models @mock", async ({ authedPage, apiMocks }) => {
  await apiMocks.prediction.mockListModels([
    makeModel({ id: "model-bulk-1", name: "Bulk Model One" }),
    makeModel({ id: "model-bulk-2", name: "Bulk Model Two" }),
  ]);
  await authedPage.goto("/models");
  await authedPage.locator(".n-data-table").waitFor();

  const rowCheckboxes = authedPage.getByRole("checkbox");
  await rowCheckboxes.nth(1).check();
  await rowCheckboxes.nth(2).check();
  await expect(authedPage.getByText("2 models selected")).toBeVisible();

  authedPage.once("dialog", (dialog) => dialog.accept());
  await authedPage.getByRole("button", { name: "Delete selected" }).click();

  await expect(authedPage.getByText("Bulk Model One")).toHaveCount(0);
  await expect(authedPage.getByText("Bulk Model Two")).toHaveCount(0);
});
