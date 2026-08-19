import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";

export class ReclassifyPagePom extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page
      .getByText(/\d+ samples/)
      .first()
      .waitFor({ timeout: 15_000 });
  }

  async gotoReclassify(datasetId: string): Promise<this> {
    await this.goto(`/datasets/${datasetId}/sc/classify`);
    await this.waitForLoaded();
    return this;
  }

  get waferMap(): Locator {
    return this.page.locator("canvas, svg").first();
  }

  get blinkTable(): Locator {
    return this.page.getByTestId("reclassify-table-loadmore-sentinel").locator("..");
  }

  get blinkScrollContainer(): Locator {
    return this.page.getByTestId("blink-table-scrollbar").locator(".sbt-scroll");
  }

  get loadMoreSentinel(): Locator {
    return this.page.getByTestId("reclassify-table-loadmore-sentinel");
  }

  get loadMoreSpinner(): Locator {
    return this.page.getByTestId("reclassify-table-loadmore-spinner");
  }

  get annotationSamplingButton(): Locator {
    return this.page.getByTestId("sc-random-filter-trigger");
  }

  get clearRandomFilterButton(): Locator {
    return this.page.getByTestId("sc-random-filter-clear");
  }

  get reviewSamplingDialog(): Locator {
    return this.page.getByTestId("review-sampling-modal");
  }

  async openReviewSampling(): Promise<void> {
    await this.annotationSamplingButton.click();
    await this.reviewSamplingDialog.waitFor();
  }

  headerSampleCount(total: number): Locator {
    return this.page.getByText(`${total} samples`);
  }
}
