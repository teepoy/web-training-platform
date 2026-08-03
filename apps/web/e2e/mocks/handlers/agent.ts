import type { Page } from "@playwright/test";

export async function mockAgentUnavailable(
  page: Page,
  detail = "Mock Agent backend unavailable",
): Promise<void> {
  await page.route("**/api/v1/agent/chat", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail }),
    });
  });
}
