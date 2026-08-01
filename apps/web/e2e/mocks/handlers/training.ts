import type { Page } from "@playwright/test";
import type { TrainingJob } from "@/generated/orval/models";
import { makeTrainingJob, makeTrainingJobList } from "../factories";

export async function mockListTrainingJobs(page: Page, jobs?: TrainingJob[]): Promise<void> {
  const body = jobs ?? [];
  await page.route("**/api/v1/training-jobs", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockGetJob(
  page: Page,
  jobId: string,
  job?: Partial<TrainingJob>,
): Promise<void> {
  const body = makeTrainingJob({ id: jobId, ...job });
  await page.route(`**/api/v1/training-jobs/${jobId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockCreateTrainingJob(page: Page): Promise<void> {
  await page.route("**/api/v1/training-jobs", async (route) => {
    if (route.request().method() === "POST") {
      const body = makeTrainingJob({ status: "queued" });
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

export async function mockListTrainers(
  page: Page,
  trainers?: Record<string, unknown>[],
): Promise<void> {
  const body = trainers ?? [
    {
      id: "trainer-e2e-1",
      name: "resnet50-cls-v1",
      trainable: true,
      view_type: "labeled_image_v1",
    },
  ];
  await page.route("**/api/v1/trainers", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}
