/**
 * Navigation / UI helpers for E2E test specs.
 *
 * Shared navigation helpers for Playwright page objects and specs.
 */
import type { Page } from "@playwright/test";

const DEFAULT_WAIT_TIMEOUT = 10000;

/**
 * Wait for a Naive UI message toast to appear.
 *
 * Naive UI messages are rendered by `<n-message-provider>` with class
 * `.n-message`. When `text` is provided, the function waits for a toast
 * containing that substring.
 *
 * @param page - Playwright Page
 * @param text - Optional text to match within the toast content
 */
export async function waitForToast(page: Page, text?: string): Promise<void> {
  const locator = text
    ? page.locator(".n-message", { hasText: text })
    : page.locator(".n-message").first();

  await locator.waitFor({ timeout: DEFAULT_WAIT_TIMEOUT });
}
