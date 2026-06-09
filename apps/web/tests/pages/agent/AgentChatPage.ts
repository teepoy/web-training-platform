import type { Locator, Page } from '@playwright/test'
import { BasePage } from '../BasePage'

/**
 * Page Object Model for the Agent Chat drawer on the classify view.
 *
 * Covers the FAB (floating action button), drawer panel,
 * message list, input field, send button, and streaming indicators.
 */
export class AgentChatPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  async waitForLoaded(): Promise<void> {
    await this.page.locator('.acd-fab').waitFor({ state: 'visible' })
  }

  // ── FAB ──────────────────────────────────────────────────────────

  getFab(): Locator {
    return this.page.locator('.acd-fab')
  }

  async waitForFabVisible(): Promise<void> {
    await this.getFab().waitFor({ state: 'visible', timeout: 10_000 })
  }

  async waitForFabHidden(): Promise<void> {
    await this.getFab().waitFor({ state: 'hidden', timeout: 3_000 })
  }

  async clickFab(): Promise<void> {
    await this.getFab().click()
  }

  // ── Drawer ───────────────────────────────────────────────────────

  getDrawer(): Locator {
    return this.page.locator('.acd')
  }

  async waitForDrawerOpen(): Promise<void> {
    await this.getDrawer().waitFor({ state: 'visible', timeout: 5_000 })
  }

  async openDrawer(): Promise<void> {
    await this.waitForFabVisible()
    await this.clickFab()
    await this.waitForFabHidden()
    await this.waitForDrawerOpen()
  }

  // ── Header ───────────────────────────────────────────────────────

  getHeaderTitle(): Locator {
    return this.page.locator('.acd-header__title')
  }

  // ── Messages ─────────────────────────────────────────────────────

  getEmptyState(): Locator {
    return this.page.locator('.acd-messages__empty')
  }

  getUserMessages(): Locator {
    return this.page.locator('.acd-msg--user')
  }

  getAssistantMessages(): Locator {
    return this.page.locator('.acd-msg--assistant')
  }

  getActionMessages(): Locator {
    return this.page.locator('.acd-msg--action')
  }

  getLoadingIndicator(): Locator {
    return this.page.locator('.acd-msg--loading')
  }

  getAnyResponse(): Locator {
    return this.page.locator('.acd-msg--assistant, .acd-msg--action')
  }

  // ── Input ────────────────────────────────────────────────────────

  getInputField(): Locator {
    return this.page.locator('.acd-input__field')
  }

  getSendButton(): Locator {
    return this.page.locator('.acd-input__btn')
  }

  async fillMessage(text: string): Promise<void> {
    await this.getInputField().fill(text)
  }

  async clickSend(): Promise<void> {
    await this.getSendButton().click()
  }

  async sendMessage(text: string): Promise<void> {
    await this.fillMessage(text)
    await this.clickSend()
  }
}
