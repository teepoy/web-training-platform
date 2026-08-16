import type { Page } from "@playwright/test";
import { BasePage } from "../BasePage";

export class AdminInfrastructurePage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page.getByTestId("admin-infrastructure-page").waitFor();
  }
}
