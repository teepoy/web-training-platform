import type { Locator, Page } from '@playwright/test'
import { BasePage } from '../BasePage'

/**
 * Page Object Model for the `/login` route.
 *
 * Covers the Naive UI login form with email, password, submit button,
 * and error toasts produced by `message.error()`.
 */
export class LoginPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  /** Wait for the login form card to render. */
  async waitForLoaded(): Promise<void> {
    await this.page.waitForSelector('[data-testid="login-form"]')
  }

  /**
   * Fill the email input.
   *
   * Naive UI `n-input` renders a wrapper div that carries the `data-testid`;
   * the actual `<input>` is a descendant of that wrapper.
   */
  async fillEmail(email: string): Promise<this> {
    await this.page
      .locator('[data-testid="login-email"] input')
      .fill(email)
    return this
  }

  /**
   * Fill the password input.
   */
  async fillPassword(password: string): Promise<this> {
    await this.page
      .locator('[data-testid="login-password"] input')
      .fill(password)
    return this
  }

  /**
   * Click the Sign In button.
   */
  async submit(): Promise<this> {
    await this.page.getByTestId('login-submit').click()
    return this
  }

  /**
   * Return a locator for a visible error toast containing the given text.
   *
   * Login errors are displayed via Naive UI `message.error()` toasts,
   * which appear as `.n-message` elements in the DOM.
   */
  expectErrorMessage(text: string): Locator {
    return this.page.locator('.n-message', { hasText: text })
  }
}
