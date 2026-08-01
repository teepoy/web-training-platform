import { test, expect } from "../../fixtures";
import { DatasetDetailPage } from "../../pages/datasets/DatasetDetailPage";
import { createDataset, addSamples, cleanupTestArtifacts } from "../../seed";

// ═══════════════════════════════════════════════════════════════════
// @live tests — sample interactions against real backend
// ═══════════════════════════════════════════════════════════════════

test("create sample with image upload @live", async ({
  page,
  liveAuth,
  seedClient: _sc,
  testPrefix,
}) => {
  await page.addInitScript((token) => {
    localStorage.setItem("auth_token", token);
  }, liveAuth.token);

  const datasetName = `${testPrefix}-samples-upload`;

  const dataset = await createDataset({
    name: datasetName,
    dataset_type: "image_classification",
    task_spec: { task_type: "classification", label_space: ["cat", "dog"] },
  });

  try {
    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(dataset.id!);
    await detailPage.waitForLoaded();

    await expect(page.getByRole("button", { name: "Add Sample" })).toBeVisible();
    await page.getByRole("button", { name: "Add Sample" }).click();

    await expect(page.getByText("Manual Sample Entry")).toBeVisible();
    await page.getByText("Manual Sample Entry").click();

    const fileInput = page.locator('input[type="file"]').first();
    await expect(fileInput).toBeAttached();

    const pngBytes = Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg==",
      "base64",
    );
    await fileInput.setInputFiles({
      name: "test-sample.png",
      mimeType: "image/png",
      buffer: pngBytes,
    });

    await expect(page.locator(".n-image img").first()).toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: "Create" }).click();

    await expect(page.locator(".n-message", { hasText: "Sample created" })).toBeVisible({
      timeout: 10_000,
    });

    await expect(page.locator('[data-testid^="dataset-sample-row-"]').first()).toBeVisible();
  } finally {
    await cleanupTestArtifacts(testPrefix);
  }
});

test("annotate sample with label @live", async ({
  page,
  liveAuth,
  seedClient: _sc,
  testPrefix,
}) => {
  await page.addInitScript((token) => {
    localStorage.setItem("auth_token", token);
  }, liveAuth.token);

  const datasetName = `${testPrefix}-samples-annot`;

  const dataset = await createDataset({
    name: datasetName,
    dataset_type: "image_classification",
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
  });

  await addSamples(dataset.id!, {
    items: [{ image_uris: ["memory://annot-test.png"], metadata: { source: "e2e" } }],
  });

  try {
    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(dataset.id!);
    await detailPage.waitForLoaded();
    await detailPage.gotoSamplesTab();

    const sampleRow = page.locator('[data-testid^="dataset-sample-row-"]').first();
    await expect(sampleRow).toBeVisible();

    await sampleRow.click();
    await expect(page.getByText("Sample Detail")).toBeVisible();

    const labelSelect = page.locator(".n-drawer .n-select").first();
    await labelSelect.click();

    const selectOption = page.locator(".n-base-select-option").filter({ hasText: "rose" });
    await expect(selectOption).toBeVisible({ timeout: 5_000 });
    await selectOption.click();

    await page.locator(".n-drawer").getByRole("button", { name: "Add" }).first().click();

    await expect(page.locator(".n-drawer .n-tag").filter({ hasText: "rose" }).first()).toBeVisible({
      timeout: 10_000,
    });

    await expect(page.locator(".n-drawer").getByRole("button", { name: "Edit" })).toBeVisible({
      timeout: 5_000,
    });
  } finally {
    await cleanupTestArtifacts(testPrefix);
  }
});
