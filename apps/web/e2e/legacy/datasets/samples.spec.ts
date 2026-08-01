import { test, expect } from "../../fixtures";
import { makeSample } from "../../mocks/factories";
import { DatasetSamplesPage } from "../../pages/datasets/DatasetSamplesPage";

const datasetId = "dataset-ds-1";
const sampleId = "sample-ds-1";

test("dataset Samples tab shows shared browser controls and opens Sample Detail @legacy", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetSamplesPage(authedPage);

  await apiMocks.datasets.mockGetDataset(datasetId, {
    ls_project_id: "101",
    ls_project_url: "http://localhost:8080/projects/101",
  });
  await apiMocks.datasets.mockListSamples(datasetId, [
    makeSample(datasetId, 0, { id: sampleId, metadata: { split: "train" } }),
    makeSample(datasetId, 1, { id: "sample-ds-2", metadata: { split: "val" } }),
  ]);
  await apiMocks.datasets.mockAnnotationStats(datasetId, {
    total_samples: 2,
    annotated_samples: 0,
    unlabeled_samples: 2,
  });
  await apiMocks.datasets.mockGetSample(datasetId, sampleId, {
    metadata: { split: "train" },
  });
  await apiMocks.datasets.mockSampleAnnotations(datasetId, sampleId);
  await apiMocks.datasets.mockSamplePredictions(datasetId, sampleId);
  await apiMocks.datasets.mockSampleSimilar(datasetId, sampleId);
  await apiMocks.datasets.mockDatasetQuery(datasetId);
  await apiMocks.training.mockListTrainingJobs([]);
  await apiMocks.training.mockListTrainers([]);

  await page.goto(`/datasets/${datasetId}`);
  await page.waitForLoaded();

  await expect(page.getGridRadio()).toBeVisible();
  await expect(page.getListRadio()).toBeVisible();
  await expect(page.getSidebarToggle()).toBeVisible();
  expect(await page.getSampleBrowserItems().count()).toBeGreaterThan(0);

  await page.clickFirstSample();
  await expect(page.getSampleDetail()).toBeVisible();
  await expect(page.getWaferMapPanel()).toBeVisible();
  await expect(page.getWaferMapCanvas()).toBeVisible();
  await expect(page.getWaferMapPanel()).not.toContainText("No wafer points");
});
