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
  await authedPage.locator(".models-creator").click();
  await authedPage.getByText("Bob", { exact: true }).last().click();
  await expect(authedPage.getByText("Beta Model")).toBeVisible();
  await expect(authedPage.getByText("Alpha Model")).toHaveCount(0);
});

test("model training sources link to their real dataset or collection @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.prediction.mockListModels([
    makeModel({
      id: "model-dataset-source",
      name: "Dataset Model",
      dataset_id: "dataset-source-1",
      dataset_name: "Source Dataset",
      collection_id: null,
      collection_name: null,
    }),
    makeModel({
      id: "model-collection-source",
      name: "Collection Model",
      dataset_id: null,
      dataset_name: null,
      collection_id: "collection-source-1",
      collection_name: "Source Collection",
    }),
  ]);

  await authedPage.goto("/models");
  await authedPage.getByRole("button", { name: "Collection · Source Collection" }).click();
  await expect(authedPage).toHaveURL(/\/dataset-collections\/collection-source-1$/);

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
