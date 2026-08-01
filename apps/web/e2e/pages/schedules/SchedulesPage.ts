import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";

/**
 * Page Object Model for the Schedules list view at `/schedules`.
 */
export class SchedulesPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page.waitForSelector(".n-data-table");
  }

  async goto(): Promise<void> {
    await this.page.goto("/schedules");
    await this.waitForLoaded();
  }

  /** Assert the page header is visible. */
  async expectHeaderVisible(): Promise<void> {
    await this.page
      .locator(".n-page-header")
      .filter({ hasText: "Schedules" })
      .waitFor({ state: "visible" });
  }

  /** Assert the "Create Schedule" button is visible. */
  async expectCreateButtonVisible(): Promise<void> {
    await this.page.getByRole("button", { name: "Create Schedule" }).waitFor({ state: "visible" });
  }

  /** Click "Create Schedule" to open the creation dialog. */
  async clickCreateSchedule(): Promise<void> {
    await this.page.getByRole("button", { name: "Create Schedule" }).click();
    await this.creationDialog.waitFor({ state: "visible" });
  }

  /** Locator for the schedule creation dialog. */
  get creationDialog(): Locator {
    return this.page.locator(".n-dialog");
  }

  /** Fill the schedule name input in the creation dialog. */
  async fillScheduleName(name: string): Promise<void> {
    await this.creationDialog.getByPlaceholder("my-schedule").fill(name);
  }

  /** Select a flow in the creation dialog. */
  async selectFlow(flowName: string): Promise<void> {
    await this.creationDialog.locator(".n-select").click();
    await this.page.locator(".n-base-select-option").filter({ hasText: flowName }).click();
  }

  /** Fill the cron expression in the creation dialog. */
  async fillCron(cron: string): Promise<void> {
    await this.creationDialog.getByPlaceholder("*/5 * * * *").fill(cron);
  }

  /** Click the "Create" button in the dialog. */
  async clickCreate(): Promise<void> {
    await this.creationDialog.getByRole("button", { name: "Create" }).click();
  }

  /** Wait for a toast message containing the given text. */
  async waitForToast(text: string): Promise<void> {
    await this.page
      .locator(".n-message")
      .filter({ hasText: text })
      .waitFor({ state: "visible", timeout: 15000 });
  }

  /** Get the table row locator matching a schedule name. */
  getRowByName(name: string): Locator {
    return this.page.locator(".n-data-table tr", {
      has: this.page.getByText(name),
    });
  }

  /** Click the "Pause" button on the given schedule row. */
  async clickPause(row: Locator): Promise<void> {
    await row.getByRole("button", { name: "Pause" }).click();
  }

  /** Click the "Resume" button on the given schedule row. */
  async clickResume(row: Locator): Promise<void> {
    await row.getByRole("button", { name: "Resume" }).click();
  }
}
