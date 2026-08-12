import { test, expect } from "../../fixtures";
import { SchedulesPage } from "../../pages/schedules/SchedulesPage";
import { createSchedule, deleteSchedule } from "../../seed";
import type { CreateScheduleRequest } from "../../../src/generated/orval/models";

test("create schedule uses registered capability and explicit timezone @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.schedules.mockScheduleCapabilities();
  await apiMocks.schedules.mockListSchedules();
  await apiMocks.schedules.mockCreateSchedule();

  const schedulesPage = new SchedulesPage(authedPage);
  await schedulesPage.goto();
  await schedulesPage.clickCreateSchedule();
  await schedulesPage.fillScheduleName("mock-schedule");
  await schedulesPage.selectFlow("drain-dataset");
  await schedulesPage.fillCron("0 6 * * 1");

  const requestPromise = authedPage.waitForRequest(
    (request) =>
      request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/schedules",
  );
  await schedulesPage.clickCreate();
  const request = await requestPromise;

  expect(request.postDataJSON()).toMatchObject({
    name: "mock-schedule",
    flow_name: "drain-dataset",
    cron: "0 6 * * 1",
    timezone: "UTC",
  });
  await schedulesPage.waitForToast("Schedule created");
});

test.describe("Schedules", () => {
  let scheduleName: string | undefined;
  let scheduleId: string | undefined;

  test.beforeEach(async ({ page, liveAuth, seedClient, testPrefix }) => {
    await page.addInitScript((token) => {
      localStorage.setItem("auth_token", token);
    }, liveAuth.token);

    scheduleName = `${testPrefix}-sched`;
  });

  test.afterEach(async () => {
    if (scheduleId) {
      await deleteSchedule(scheduleId).catch(() => {});
    }
  });

  test("list schedules page loads @live", async ({ page }) => {
    const schedulesPage = new SchedulesPage(page);
    await schedulesPage.goto();

    await schedulesPage.expectHeaderVisible();
    await expect(page.locator(".n-data-table")).toBeVisible();
    await schedulesPage.expectCreateButtonVisible();
  });

  test("create schedule @live", async ({ page }) => {
    const schedulesPage = new SchedulesPage(page);
    await schedulesPage.goto();

    await schedulesPage.clickCreateSchedule();
    await schedulesPage.fillScheduleName(scheduleName!);
    await schedulesPage.selectFlow("drain-dataset");
    await schedulesPage.fillCron("0 6 * * 1");
    await schedulesPage.clickCreate();

    await schedulesPage.waitForToast("Schedule created");

    const row = schedulesPage.getRowByName(scheduleName!);
    await expect(row).toBeVisible();

    // Capture the schedule ID from the row for cleanup
    scheduleId = (await row.getAttribute("data-row-key")) ?? undefined;

    await expect(row.locator(".n-tag").filter({ hasText: "active" })).toBeVisible();
  });

  test("pause and resume schedule @live", async ({ page, testPrefix }) => {
    // Seed a schedule before the test
    const req: CreateScheduleRequest = {
      name: `${testPrefix}-sched-pr`,
      flow_name: "drain-dataset",
      cron: "0 6 * * 1",
    };
    const schedule = await createSchedule(req);
    scheduleId = schedule.id;
    const seededName = schedule.name;

    const schedulesPage = new SchedulesPage(page);
    await schedulesPage.goto();

    const row = schedulesPage.getRowByName(seededName);
    await expect(row).toBeVisible();

    // Pause
    await schedulesPage.clickPause(row);
    await schedulesPage.waitForToast("Schedule paused");

    await expect(row.locator(".n-tag").filter({ hasText: "paused" })).toBeVisible({
      timeout: 5000,
    });

    // Resume
    await schedulesPage.clickResume(row);
    await schedulesPage.waitForToast("Schedule resumed");

    await expect(row.locator(".n-tag").filter({ hasText: "active" })).toBeVisible({
      timeout: 5000,
    });
  });
});
