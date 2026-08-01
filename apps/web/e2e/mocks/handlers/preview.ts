import type { Page } from "@playwright/test";
import type {
  PreviewSession,
  PreviewItemsPage,
  PreviewItem,
  PreviewPersistStatus,
} from "@/shared/api/preview";

export async function mockCreatePreviewSession(
  page: Page,
  sessionId: string,
  collectionRef: string,
): Promise<void> {
  await page.route("**/api/v1/preview-sessions", async (route) => {
    if (route.request().method() === "POST") {
      const body: PreviewSession = {
        session_id: sessionId,
        collection_ref: collectionRef,
        classification_enabled: true,
        estimated_total: 50,
        loaded_count: 20,
        next_cursor: "cursor-20",
        has_more: true,
      };
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    } else {
      await route.continue();
    }
  });
}

export async function mockGetPreviewSession(
  page: Page,
  sessionId: string,
  collectionRef = "test-collection",
): Promise<void> {
  await page.route(`**/api/v1/preview-sessions/${sessionId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: sessionId,
        collection_ref: collectionRef,
        classification_enabled: true,
        estimated_total: 50,
        loaded_count: 20,
        next_cursor: "cursor-20",
        has_more: true,
      } satisfies PreviewSession),
    });
  });
}

export async function mockGetPreviewItems(
  page: Page,
  sessionId: string,
  items?: PreviewItem[],
): Promise<void> {
  const defaultItems: PreviewItem[] = items ?? [
    {
      upstream_item_id: "item-1",
      image_uris: ["memory://item-1.png"],
      metadata: {},
    },
    {
      upstream_item_id: "item-2",
      image_uris: ["memory://item-2.png"],
      metadata: {},
    },
  ];
  const body: PreviewItemsPage = {
    items: defaultItems,
    next_cursor: null,
    has_more: false,
    estimated_total: defaultItems.length,
  };
  await page.route(`**/api/v1/preview-sessions/${sessionId}/items**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockPersistPreview(
  page: Page,
  sessionId: string,
  datasetId: string,
): Promise<void> {
  await page.route(`**/api/v1/preview-sessions/${sessionId}/persist`, async (route) => {
    const body: PreviewPersistStatus = {
      dataset_id: datasetId,
      persist_session_id: "persist-123",
      status: "running",
      imported_count: 0,
      remaining_count: 3,
      error: "",
    };
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockGetPersistStatus(
  page: Page,
  sessionId: string,
  datasetId: string,
): Promise<void> {
  await page.route(`**/api/v1/preview-sessions/${sessionId}/persist-status`, async (route) => {
    const body: PreviewPersistStatus = {
      dataset_id: datasetId,
      persist_session_id: "persist-123",
      status: "completed",
      imported_count: 3,
      remaining_count: 0,
      error: "",
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockExpiredPreviewSession(page: Page, sessionId: string): Promise<void> {
  await page.route(`**/api/v1/preview-sessions/${sessionId}`, async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "preview session expired or not found" }),
    });
  });
}
