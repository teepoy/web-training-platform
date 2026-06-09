import type { Locator, Page } from '@playwright/test'
import { BasePage } from '../BasePage'

/**
 * Page Object Model for the `/register` route.
 *
 * Covers the Naive UI registration form with name, email, password inputs,
 * and submit button.
 */
export class RegisterPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  /** Wait for the register form card to render. */
  async waitForLoaded(): Promise<void> {
    await this.page.waitForSelector('[data-testid="register-form"]')
  }

  /**
   * Fill the name input.
   */
  async fillName(name: string): Promise<this> {
    await this.page
      .locator('[data-testid="register-name"] input')
      .fill(name)
    return this
  }

  /**
   * Fill the email input.
   */
  async fillEmail(email: string): Promise<this> {
    await this.page
      .locator('[data-testid="register-email"] input')
      .fill(email)
    return this
  }

  /**
   * Fill the password input.
   */
  async fillPassword(password: string): Promise<this> {
    await this.page
      .locator('[data-testid="register-password"] input')
      .fill(password)
    return this
  }

  /**
   * Click the Create Account button.
   */
  async submit(): Promise<this> {
    await this.page.getByTestId('register-submit').click()
    return this
  }

  /**
   * Return a locator for a visible error toast containing the given text.
   *
   * Registration errors are displayed via Naive UI `message.error()` toasts.
   */
  expectErrorMessage(text: string): Locator {
    return this.page.locator('.n-message', { hasText: text })
  }
}
