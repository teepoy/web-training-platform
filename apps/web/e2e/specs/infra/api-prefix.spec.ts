import { test, expect } from "../../fixtures";

test("API requests do NOT use duplicated /api/v1/ prefix @mock @smoke", async ({
  authedPage,
  apiMocks,
}) => {
  const capturedUrls: string[] = [];

  authedPage.on("request", (request) => {
    const url = request.url();
    if (url.includes("/api/")) {
      capturedUrls.push(url);
    }
  });

  await apiMocks.core.mockDashboard();
  await apiMocks.core.mockHealth();
  await apiMocks.core.mockExportFormats();
  await apiMocks.core.mockSettings();
  await apiMocks.core.mockPlugins();

  await authedPage.goto("/datasets", { waitUntil: "networkidle" });

  const apiUrls = capturedUrls.filter((u) => u.includes("/api/"));
  expect(apiUrls.length).toBeGreaterThan(0);

  for (const url of apiUrls) {
    expect(url, `API request URL must not contain double /api/v1/ prefix: ${url}`).not.toMatch(
      /\/api\/v1\/api\/v1\//,
    );
  }
});
