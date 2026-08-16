import { expect, test } from "../../fixtures";

async function mockCollections(page: import("@playwright/test").Page): Promise<void> {
  await page.route("**/api/v1/dataset-collections**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0 }),
    });
  });
}

test("Library keeps shared query state while switching resource tabs @mock", async ({
  authedPage,
}) => {
  await mockCollections(authedPage);
  await authedPage.goto("/library?q=flowers&creator=me");

  await expect(authedPage.getByRole("menuitem", { name: "Library" })).toBeVisible();
  await expect(authedPage.getByRole("menuitem", { name: "Datasets" })).toHaveCount(0);
  await expect(authedPage.getByRole("menuitem", { name: "Collections" })).toHaveCount(0);
  await expect(authedPage.getByRole("heading", { name: "Library" })).toBeVisible();
  await expect(authedPage.getByTestId("library-tab-datasets")).toHaveClass(/active/);
  await expect(authedPage.getByText("flowers-dataset")).toBeVisible();
  const tabsBox = await authedPage.locator(".library-tabs").boundingBox();
  const filtersBox = await authedPage.locator(".library-query").boundingBox();
  expect(tabsBox!.y).toBeLessThan(filtersBox!.y);

  const collectionRequestPromise = authedPage.waitForRequest((request) =>
    request.url().includes("/api/v1/dataset-collections"),
  );
  await authedPage.getByTestId("library-tab-collections").click();
  const collectionRequest = await collectionRequestPromise;
  expect(new URL(collectionRequest.url()).searchParams.get("q")).toBe("flowers");

  await expect(authedPage).toHaveURL(/\/library\?/);
  const collectionUrl = new URL(authedPage.url());
  expect(collectionUrl.searchParams.get("tab")).toBe("collections");
  expect(collectionUrl.searchParams.get("q")).toBe("flowers");
  expect(collectionUrl.searchParams.get("creator")).toBe("me");
  await expect(authedPage.getByTestId("library-tab-collections")).toHaveClass(/active/);
  await expect(authedPage.getByText("No dataset collections match this search")).toBeVisible();
});

test("Library sorts the full Dataset result set and opens rows @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.datasets.mockListDatasets();
  await authedPage.goto("/library?creator=all");
  await expect(authedPage.getByText("flowers-dataset")).toBeVisible();

  const sortedRequestPromise = authedPage.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname === "/api/v1/datasets" && url.searchParams.get("sort_by") === "name";
  });
  await authedPage.getByRole("columnheader", { name: /Name/ }).click();
  const sortedRequest = await sortedRequestPromise;
  expect(new URL(sortedRequest.url()).searchParams.get("sort_order")).toBe("desc");

  await authedPage.getByText("flowers-dataset", { exact: true }).click();
  await expect(authedPage).toHaveURL(/\/datasets\/dataset-e2e-1$/);
});

test("legacy list URLs redirect to their Library tabs without changing detail URLs @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await mockCollections(authedPage);

  await authedPage.goto("/datasets?q=flowers&creator=all");
  await expect(authedPage).toHaveURL(/\/library\?/);
  const datasetListUrl = new URL(authedPage.url());
  expect(datasetListUrl.searchParams.get("tab")).toBe("datasets");
  expect(datasetListUrl.searchParams.get("q")).toBe("flowers");
  expect(datasetListUrl.searchParams.get("creator")).toBe("all");

  await authedPage.goto("/dataset-collections?q=review&creator=me");
  await expect(authedPage).toHaveURL(/\/library\?/);
  const collectionListUrl = new URL(authedPage.url());
  expect(collectionListUrl.searchParams.get("tab")).toBe("collections");
  expect(collectionListUrl.searchParams.get("q")).toBe("review");
  expect(collectionListUrl.searchParams.get("creator")).toBe("me");

  await apiMocks.datasets.mockGetDataset("dataset-route-stable");
  await authedPage.goto("/datasets/dataset-route-stable");
  await expect(authedPage).toHaveURL(/\/datasets\/dataset-route-stable$/);
});
