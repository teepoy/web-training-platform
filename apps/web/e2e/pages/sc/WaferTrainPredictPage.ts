import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";
import { E2E_TIMEOUTS } from "../../timeouts";

interface TrainPredictResponseBody {
  train_job?: {
    id?: string;
  };
}

/** Page object for the current unified SC Train & Predict workflow. */
export class WaferTrainPredictPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.workspace.waitFor({ timeout: E2E_TIMEOUTS.operation.scDataLoad });
  }

  get workspace(): Locator {
    return this.page.locator(".sc-classify-page");
  }

  get trainerSelect(): Locator {
    return this.page.getByTestId("sc-trainer-select");
  }

  get trainPredictButton(): Locator {
    return this.page.getByTestId("sc-train-predict");
  }

  get status(): Locator {
    return this.page.getByTestId("sc-train-predict-status");
  }

  async goToWorkspace(datasetId: string): Promise<this> {
    await this.goto(`/datasets/${datasetId}/sc/classify`);
    await this.waitForLoaded();
    return this;
  }

  async selectFirstTrainer(): Promise<this> {
    await this.trainerSelect.click();
    const firstOption = this.page.locator(".n-base-select-option").first();
    await firstOption.waitFor({ timeout: E2E_TIMEOUTS.expect });
    await firstOption.click();
    return this;
  }

  async applyTestIdFilter(testIds: number[]): Promise<this> {
    if (testIds.length === 0) throw new Error("At least one Test ID is required");
    await this.page.getByRole("button", { name: "Test ID", exact: true }).click();
    const menu = this.page.locator(".sst-filter-popover--set:visible");
    await menu.waitFor({ timeout: E2E_TIMEOUTS.expect });

    for (const testId of testIds) {
      const option = menu.getByRole("checkbox", { name: String(testId), exact: true });
      await option.waitFor({ timeout: E2E_TIMEOUTS.operation.scDataLoad });
      await option.check();
    }

    await menu.getByRole("button", { name: "Apply", exact: true }).click();
    return this;
  }

  async startTrainAndPredict(): Promise<string> {
    const responsePromise = this.page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/training-jobs/train-and-predict",
      { timeout: E2E_TIMEOUTS.operation.training },
    );

    await this.trainPredictButton.click();
    const response = await responsePromise;
    if (!response.ok()) {
      throw new Error(
        `Train & Predict submission failed (${response.status()}): ${await response.text()}`,
      );
    }
    const body = (await response.json()) as TrainPredictResponseBody;
    const jobId = body.train_job?.id;
    if (!jobId) throw new Error("Train & Predict response did not include a training job ID");
    return jobId;
  }

  async startFilteredTrainAndPredict(): Promise<string> {
    const responsePromise = this.page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/training-jobs/train-and-predict",
      { timeout: E2E_TIMEOUTS.operation.training },
    );

    await this.trainPredictButton.click();
    const continueButton = this.page.getByRole("button", {
      name: /Continue with [\d,]+ defects/,
    });
    await continueButton.waitFor({ timeout: E2E_TIMEOUTS.operation.scDataLoad });
    await continueButton.click();

    const response = await responsePromise;
    if (!response.ok()) {
      throw new Error(
        `Filtered Train & Predict submission failed (${response.status()}): ${await response.text()}`,
      );
    }
    const body = (await response.json()) as TrainPredictResponseBody;
    const jobId = body.train_job?.id;
    if (!jobId) throw new Error("Train & Predict response did not include a training job ID");
    return jobId;
  }
}
