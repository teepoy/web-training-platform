import { test, expect } from "../../fixtures";
import { DatasetDetailPage } from "../../pages/datasets/DatasetDetailPage";
import { createDataset, cleanupTestArtifacts } from "../../seed";

test("add labels through the removed generic classify route @legacy", async ({
  page,
  seedClient: _sc,
  testPrefix,
}) => {
  const dataset = await createDataset({
    name: `${testPrefix}-labels`,
    dataset_type: "image_classification",
    task_spec: { task_type: "classification", label_space: ["cat", "dog"] },
  });

  try {
    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(dataset.id!);
    await detailPage.waitForLoaded();
    await detailPage.clickOpenWorkflow();
    await detailPage.waitForClassifyPage();

    const addLabelButton = page.locator(".classify-label-add");
    await expect(addLabelButton).toBeVisible();
    await addLabelButton.click();
    await page.getByPlaceholder("Enter label name").fill("bird");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.locator(".classify-label-item").filter({ hasText: "bird" })).toBeVisible();
  } finally {
    await cleanupTestArtifacts(testPrefix);
  }
});
