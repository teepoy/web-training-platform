/**
 * Sample browser virtualization spec — mock mode.
 *
 * Verifies that the shared sample browser renders only a bounded subset
 * of DOM nodes when loaded with a large item set (200 items → < 50 nodes).
 *
 * @legacy — requires migration to the current sample-browser contract.
 */
import { test, expect } from "../../fixtures";
import { DatasetSamplesPage } from "../../pages/datasets/DatasetSamplesPage";
import { makeSamples } from "../../mocks/factories";

const datasetId = "dataset-virt-1";

test.describe("shared browser virtualization @legacy", () => {
  test("renders only a bounded subset of nodes for large item sets", async ({
    authedPage,
    apiMocks,
  }) => {
    const largeSamples = makeSamples(datasetId, 200);
    await apiMocks.datasets.mockGetDataset(datasetId);
    await apiMocks.datasets.mockListSamples(datasetId, largeSamples);
    await apiMocks.datasets.mockAnnotationStats(datasetId, { total_samples: 200 });
    await apiMocks.prediction.mockListModels();
    await apiMocks.prediction.mockListPredictionJobs();
    await apiMocks.training.mockListTrainingJobs();
    await apiMocks.training.mockListTrainers();
    await apiMocks.core.mockExportFormats();

    const classifyPage = new DatasetSamplesPage(authedPage);
    await classifyPage.goToClassify(datasetId);

    const renderedCount = await classifyPage.getSampleBrowserItems().count();
    expect(renderedCount).toBeLessThan(50);
    expect(renderedCount).toBeGreaterThan(0);
  });
});
