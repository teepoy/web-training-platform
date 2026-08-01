import { test, expect } from "../../fixtures";
import { DatasetDetailPage } from "../../pages/datasets/DatasetDetailPage";
import { createDataset, cleanupTestArtifacts } from "../../seed";

test("LS project link accessible from dataset detail @live", async ({
  page,
  liveAuth,
  seedClient: _sc,
  testPrefix,
}) => {
  await page.addInitScript((token) => {
    localStorage.setItem("auth_token", token);
  }, liveAuth.token);

  const datasetName = `${testPrefix}-ls`;

  const dataset = await createDataset({
    name: datasetName,
    dataset_type: "image_classification",
    task_spec: { task_type: "classification", label_space: ["cat", "dog"] },
  });

  try {
    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(dataset.id!);
    await detailPage.waitForLoaded();
    await detailPage.gotoAnnotateTab();
    await detailPage.expectLabelStudioLink();

    const lsLink = detailPage.getLabelStudioLink();
    const href = await lsLink.getAttribute("href");
    expect(href).toBeTruthy();
    expect(href!).toContain("localhost:8080");
  } finally {
    await cleanupTestArtifacts(testPrefix);
  }
});
