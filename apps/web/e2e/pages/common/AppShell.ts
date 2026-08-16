import type { Page } from "@playwright/test";
import { BasePage } from "../BasePage";

/**
 * Page Object Model for the authenticated application shell.
 *
 * Covers the sidebar navigation menu, header bar, avatar dropdown,
 * and top-level route navigation.
 *
 * The shell is rendered by `App.vue` for all authenticated (non-auth-page)
 * routes and wraps every feature page behind `<RouterView>`.
 */
export class AppShell extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  /**
   * Wait for the sidebar navigation menu to render, signalling the shell
   * is ready for interaction.
   */
  async waitForLoaded(): Promise<void> {
    // The Naive UI n-menu renders menuitem roles with recognizable labels.
    await this.page.getByRole("menuitem", { name: "Library" }).waitFor();
  }

  // ── Sidebar navigation ──────────────────────────────────────────

  /**
   * Navigate to the data-resource **Library** by clicking the sidebar menu item.
   */
  async gotoDatasets(): Promise<void> {
    await this.page.getByRole("menuitem", { name: "Library" }).click();
    await this.page.waitForURL("**/library");
  }

  /**
   * Navigate to **Training Jobs** (`/jobs`).
   *
   * There is no top-level "Training" sidebar entry; this method navigates
   * directly to the `/jobs` route via `page.goto`.
   */
  async gotoTraining(): Promise<void> {
    await this.goto("/jobs");
  }

  /**
   * Navigate to **Schedules** (`/schedules`).
   *
   * There is no top-level "Schedules" sidebar entry; this method navigates
   * directly to the `/schedules` route via `page.goto`.
   */
  async gotoSchedules(): Promise<void> {
    await this.goto("/schedules");
  }

  // ── User menu / logout ──────────────────────────────────────────

  /**
   * Log out via the avatar dropdown in the header bar.
   *
   * 1. Click the user avatar (`data-testid="nav-avatar"`) to open the dropdown.
   * 2. Select the **Logout** option from the teleported dropdown overlay.
   * 3. Wait for redirect to `/login`.
   */
  async logout(): Promise<void> {
    await this.page.getByTestId("nav-avatar").click();
    await this.page.locator(".n-dropdown-option").filter({ hasText: "Logout" }).click();
    await this.page.waitForURL("**/login");
  }
}
