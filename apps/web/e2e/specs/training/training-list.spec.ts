import { test, expect } from "../../fixtures";
import { TrainingListPage } from "../../pages/training/TrainingListPage";
import { createDataset, addSamples, deleteDataset } from "../../seed";

test.describe("Training Jobs", () => {
  let datasetId: string | undefined;
  let datasetName: string | undefined;

  test.beforeEach(async ({ page, liveAuth, seedClient, testPrefix }) => {
    await page.addInitScript((token) => {
      localStorage.setItem("auth_token", token);
    }, liveAuth.token);

    datasetName = `${testPrefix}-training-ds`;

    const dataset = await createDataset({
      name: datasetName,
      dataset_type: "image_sc",
      task_spec: { task_type: "sc", label_space: ["Scratch", "Clean"] },
    });
    datasetId = dataset.id!;

    await addSamples(datasetId, {
      items: [
        {
          image_uris: ["memory://sample-a.jpg"],
          metadata: { split: "train", defect_id: "e2e-a" },
          label: "Scratch",
        },
        {
          image_uris: ["memory://sample-b.jpg"],
          metadata: { split: "train", defect_id: "e2e-b" },
          label: "Clean",
        },
      ],
    });
  });

  test.afterEach(async () => {
    if (datasetId) {
      await deleteDataset(datasetId).catch(() => {});
    }
  });

  test("create training job and monitor SSE @live", async ({ page }) => {
    const trainingPage = new TrainingListPage(page);
    await trainingPage.goto();

    await trainingPage.clickStartNewJob();

    await trainingPage.selectDataset(datasetName!);
    await trainingPage.selectFirstTrainer();
    await trainingPage.clickStart();

    await trainingPage.waitForJobStarted();

    const jobRow = page.locator(".n-data-table tr", {
      has: page.getByText(`${datasetId!.slice(0, 8)}…`, { exact: true }),
    });
    await expect(jobRow).toBeVisible({ timeout: 10000 });
    await jobRow.getByRole("button", { name: "View" }).click();

    await expect(page).toHaveURL(/\/jobs\//);
    await trainingPage.waitForSseOpen();
  });

  test("training progress card shows metrics @live", async ({ page }) => {
    const trainingPage = new TrainingListPage(page);
    await trainingPage.goto();

    const completedCount = await trainingPage.completedJobRow.count();
    if (completedCount === 0) {
      test.skip(true, "No completed jobs found — run the training test first");
      return;
    }

    await trainingPage.completedJobRow.first().getByRole("button", { name: "View" }).click();
    await expect(page).toHaveURL(/\/jobs\//);

    const progressCard = trainingPage.trainingProgressCard;
    await expect(progressCard).toBeVisible({ timeout: 10000 });

    const hasChart = (await progressCard.locator("canvas").count()) > 0;
    const hasEmpty = (await progressCard.locator(".n-empty").count()) > 0;
    const hasTable = (await progressCard.locator(".n-data-table").count()) > 0;
    const hasContent = hasChart || hasEmpty || hasTable;

    expect(hasContent, "Training Progress card should render chart, empty-state or table").toBe(
      true,
    );
  });
});
