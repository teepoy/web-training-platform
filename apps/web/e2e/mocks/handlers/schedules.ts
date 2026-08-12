import type { Page } from "@playwright/test";
import type { ScheduleCapabilityResponse, ScheduleResponse } from "@/generated/orval/models";

export async function mockScheduleCapabilities(
  page: Page,
  capabilities: ScheduleCapabilityResponse[] = [
    { flow_name: "drain-dataset", deployment_name: "drain-dataset" },
  ],
): Promise<void> {
  await page.route("**/api/v1/schedules/capabilities", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(capabilities),
    });
  });
}

export async function mockListSchedules(page: Page, schedules?: ScheduleResponse[]): Promise<void> {
  const body = schedules ?? [];
  await page.route("**/api/v1/schedules?*", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: body, total: body.length }),
    });
  });
}

export async function mockGetSchedule(
  page: Page,
  scheduleId: string,
  schedule?: Partial<ScheduleResponse>,
): Promise<void> {
  const body: ScheduleResponse = {
    id: scheduleId,
    name: "e2e-schedule",
    flow_name: "training_v1",
    timezone: "UTC",
    is_schedule_active: true,
    prefect_deployment_id: "deploy-e2e-1",
    prefect_deployment_url: "http://prefect.example/deployments/deployment/deploy-e2e-1",
    created: "2026-01-01T00:00:00Z",
    updated: "2026-01-01T00:00:00Z",
    ...schedule,
  };
  await page.route(`**/api/v1/schedules/${scheduleId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockCreateSchedule(page: Page): Promise<void> {
  await page.route("**/api/v1/schedules", async (route) => {
    if (route.request().method() === "POST") {
      const body: ScheduleResponse = {
        id: "schedule-new-1",
        name: "new-schedule",
        flow_name: "drain-dataset",
        timezone: "UTC",
        is_schedule_active: true,
        prefect_deployment_id: "deploy-new-1",
        prefect_deployment_url: "http://prefect.example/deployments/deployment/deploy-new-1",
        created: "2026-01-01T00:00:00Z",
        updated: "2026-01-01T00:00:00Z",
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    } else {
      await route.continue();
    }
  });
}

export async function mockDeleteSchedule(page: Page, scheduleId: string): Promise<void> {
  await page.route(`**/api/v1/schedules/${scheduleId}`, async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204 });
    } else {
      await route.continue();
    }
  });
}

export async function mockScheduleRuns(page: Page, scheduleId: string): Promise<void> {
  await page.route(`**/api/v1/schedules/${scheduleId}/runs**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}
