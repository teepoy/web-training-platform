import { expect, type Page } from "@playwright/test";

/**
 * Abstract base class for all Page Object Models.
 *
 * Provides shared navigation helpers and a contract for page-load detection.
 * Subclasses must implement {@link waitForLoaded} to signal when the page
 * is ready for interaction.
 */
export abstract class BasePage {
  protected readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  /**
   * Navigate to a path relative to the application base URL.
   * Delegates to `page.goto()` which respects the configured `baseURL`.
   */
  async goto(path: string): Promise<void> {
    await this.page.goto(path);
  }

  /**
   * Assert that the current page URL matches a pattern.
   * Uses Playwright's `toHaveURL` under the hood.
   *
   * EXEMPT: Navigation-gate method (same as `waitForLoaded`), not a test
   * assertion. This is a page-load verification utility; it does not assert
   * business logic. The "POMs should not call expect()" rule targets assertion
   * logic leaking into page objects.
   *
   * @param pattern - A string or RegExp to match against the current URL.
   */
  async expectUrl(pattern: string | RegExp): Promise<void> {
    await expect(this.page).toHaveURL(pattern);
  }

  /**
   * Wait until the page has fully loaded and is ready for interaction.
   * Each subclass defines its own readiness signal (e.g. a visible
   * `data-testid` element or a stable selector).
   */
  abstract waitForLoaded(): Promise<void>;
}
