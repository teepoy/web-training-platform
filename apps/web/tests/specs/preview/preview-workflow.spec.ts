/**
 * Preview workflow E2E specs — mock mode.
 *
 * Covers preview session creation, workspace rendering, expired session
 * error handling, and wafer map rendering with session-loaded metadata.
 *
 * @legacy — uses authedPage (auto mock) + apiMocks preview handlers.
 */
import { test, expect } from "../../fixtures";
import { PreviewWorkflowPage } from "../../pages/preview/PreviewWorkflowPage";

const sessionId = "sess-123";
const sessionIdWafer = "sess-wafer";
const collectionRef = "test-collection";
const datasetId = "dataset-preview-1";

test("shows error for expired session @legacy", async ({ authedPage, apiMocks }) => {
  await apiMocks.preview.mockExpiredPreviewSession("expired-session");

  const previewPage = new PreviewWorkflowPage(authedPage);
  await previewPage.goto("/preview/expired-session");

  await expect(previewPage.expiredError).toBeVisible();
});

test("runs preview launch and workspace flow @legacy", async ({ authedPage, apiMocks }) => {
  await apiMocks.preview.mockCreatePreviewSession(sessionId, collectionRef);
  await apiMocks.preview.mockGetPreviewSession(sessionId);
  await apiMocks.preview.mockGetPreviewItems(sessionId);
  await apiMocks.preview.mockPersistPreview(sessionId, datasetId);
  await apiMocks.preview.mockGetPersistStatus(sessionId, datasetId);

  const previewPage = new PreviewWorkflowPage(authedPage);
  await previewPage.goToPreviewLaunch();

  await previewPage.fillCollectionRef(collectionRef);
  await previewPage.clickPreview();
  await authedPage.waitForURL(`**/preview/${sessionId}`);

  await expect(previewPage.persistButton).toBeVisible();
  await expect.poll(async () => previewPage.sampleItems.count()).toBeGreaterThan(0);

  await expect(previewPage.gridRadio).toBeVisible();
  await expect(previewPage.listRadio).toBeVisible();
  await expect(previewPage.classificationToggle).toBeVisible();

  await expect(authedPage.getByRole("button", { name: /Submit/ })).toHaveCount(0);

  await previewPage.waitForSamplesLoaded();
  const itemCount = await previewPage.sampleItems.count();
  expect(itemCount).toBeGreaterThan(0);

  await expect(previewPage.waferMapPanel).toBeVisible();
  await expect(previewPage.waferMapPanel).toContainText("No wafer points");

  await previewPage.switchToListView();
  await expect(previewPage.listImage).toBeVisible();
  await expect
    .poll(async () => previewPage.listImage.evaluate((el) => el.getBoundingClientRect().width))
    .toBeGreaterThanOrEqual(100);

  await previewPage.clickPersist();
  await expect(authedPage.getByLabel("Entire collection (recommended)")).toBeChecked();

  await previewPage.confirmPersist();
  await authedPage.waitForURL(
    `**/datasets/${datasetId}/classify?previewPersistSession=${sessionId}`,
  );
});

test("renders wafer map with session-loaded metadata points @legacy", async ({
  authedPage,
  apiMocks,
}) => {
  const waferItems = [
    {
      upstream_item_id: "item-w1",
      image_uris: ["memory://item-w1.png"],
      metadata: { wafer_x: 0.1, wafer_y: 0.2 },
    },
    {
      upstream_item_id: "item-w2",
      image_uris: ["memory://item-w2.png"],
      metadata: { wafer_x: -0.3, wafer_y: 0.5 },
    },
  ];
  await apiMocks.preview.mockGetPreviewSession(sessionIdWafer, "wafer-collection");
  await apiMocks.preview.mockGetPreviewItems(sessionIdWafer, waferItems);

  const previewPage = new PreviewWorkflowPage(authedPage);
  await authedPage.goto(`/preview/${sessionIdWafer}`);
  await previewPage.waitForSamplesLoaded();

  await expect(previewPage.waferMapPanel).toBeVisible();
  await expect(previewPage.waferMapPanel).not.toContainText("No wafer points");
  await expect(previewPage.waferMapCanvas).toBeVisible();
});
