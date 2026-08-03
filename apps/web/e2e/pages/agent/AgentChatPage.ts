import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";
import { E2E_TIMEOUTS } from "../../timeouts";

/**
 * Page Object Model for the Agent Chat drawer on the classify view.
 *
 * Covers the FAB (floating action button), drawer panel,
 * message list, input field, send button, and streaming indicators.
 */
export class AgentChatPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.getFab().waitFor({
      state: "visible",
      timeout: E2E_TIMEOUTS.expect,
    });
  }

  // ── FAB ──────────────────────────────────────────────────────────

  getFab(): Locator {
    return this.page.getByTestId("agent-chat-open");
  }

  async waitForFabVisible(): Promise<void> {
    await this.getFab().waitFor({ state: "visible", timeout: E2E_TIMEOUTS.expect });
  }

  async waitForFabHidden(): Promise<void> {
    await this.getFab().waitFor({ state: "hidden", timeout: E2E_TIMEOUTS.expect });
  }

  async clickFab(): Promise<void> {
    await this.getFab().click();
  }

  // ── Drawer ───────────────────────────────────────────────────────

  getDrawer(): Locator {
    return this.page.getByTestId("agent-chat-drawer");
  }

  async waitForDrawerOpen(): Promise<void> {
    await this.getDrawer().waitFor({ state: "visible", timeout: E2E_TIMEOUTS.expect });
  }

  async openDrawer(): Promise<void> {
    await this.waitForFabVisible();
    await this.clickFab();
    await this.waitForFabHidden();
    await this.waitForDrawerOpen();
  }

  // ── Header ───────────────────────────────────────────────────────

  getHeaderTitle(): Locator {
    return this.getDrawer().getByText("Agent Chat", { exact: true });
  }

  // ── Messages ─────────────────────────────────────────────────────

  getEmptyState(): Locator {
    return this.page.getByTestId("agent-chat-empty");
  }

  getUserMessages(): Locator {
    return this.page.getByTestId("agent-chat-message-user");
  }

  getAssistantMessages(): Locator {
    return this.page.getByTestId("agent-chat-message-assistant");
  }

  getActionMessages(): Locator {
    return this.page.getByTestId("agent-chat-message-action");
  }

  getLoadingIndicator(): Locator {
    return this.page.getByTestId("agent-chat-loading");
  }

  getAnyResponse(): Locator {
    return this.getAssistantMessages().or(this.getActionMessages());
  }

  // ── Input ────────────────────────────────────────────────────────

  getInputField(): Locator {
    return this.page.getByPlaceholder("Ask the agent...");
  }

  getSendButton(): Locator {
    return this.page.getByRole("button", { name: "Send Agent message" });
  }

  async fillMessage(text: string): Promise<void> {
    await this.getInputField().fill(text);
  }

  async clickSend(): Promise<void> {
    await this.getSendButton().click();
  }

  async sendMessage(text: string): Promise<void> {
    await this.fillMessage(text);
    await this.clickSend();
  }
}
