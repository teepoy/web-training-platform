import { test, expect } from "../../fixtures";
import { DashboardPage } from "../../pages/dashboard/DashboardPage";

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page, liveAuth }) => {
    await page.addInitScript((token) => {
      localStorage.setItem("auth_token", token);
    }, liveAuth.token);
  });

  test("dashboard loads statistics @live", async ({ page }) => {
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.goto();

    await expect(dashboardPage.workPoolCard).toBeVisible({ timeout: 10000 });
    await expect(dashboardPage.jobQueueCard).toBeVisible({ timeout: 10000 });

    await expect(
      dashboardPage.workPoolCard.locator(".n-statistic").filter({ hasText: "Pool Name" }),
    ).toBeVisible();
    await expect(
      dashboardPage.workPoolCard.locator(".n-statistic").filter({ hasText: "Type" }),
    ).toBeVisible();

    await expect(
      dashboardPage.jobQueueCard.locator(".n-statistic").filter({ hasText: "Queued" }),
    ).toBeVisible();
    await expect(
      dashboardPage.jobQueueCard.locator(".n-statistic").filter({ hasText: "Running" }),
    ).toBeVisible();
    await expect(
      dashboardPage.jobQueueCard.locator(".n-statistic").filter({ hasText: "Completed" }),
    ).toBeVisible();
    await expect(
      dashboardPage.jobQueueCard.locator(".n-statistic").filter({ hasText: "Failed" }),
    ).toBeVisible();
  });

  test("dashboard shows service health table @live", async ({ page }) => {
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.goto();

    const serviceHealthCard = dashboardPage.serviceHealthCard;
    await expect(serviceHealthCard).toBeVisible({ timeout: 10000 });

    const table = serviceHealthCard.locator(".n-data-table");
    await expect(table).toBeVisible();
    await expect(table.locator("th").filter({ hasText: "Service" })).toBeVisible();
    await expect(table.locator("th").filter({ hasText: "Status" })).toBeVisible();
  });

  test("dashboard shows recent items @live", async ({ page }) => {
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.goto();

    const recentJobsCard = dashboardPage.recentJobsCard;
    await expect(recentJobsCard).toBeVisible({ timeout: 10000 });

    const table = recentJobsCard.locator(".n-data-table");
    await expect(table).toBeVisible();
    await expect(table.locator("th").filter({ hasText: "ID" })).toBeVisible();
    await expect(table.locator("th").filter({ hasText: "Status" })).toBeVisible();
  });
});
