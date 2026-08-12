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
      created_by: "user-alice",
      creator_name: "Alice",
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
