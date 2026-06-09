import type { Locator, Page } from '@playwright/test'
import { BasePage } from '../BasePage'

export class PreviewWorkflowPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  async waitForLoaded(): Promise<void> {
    await this.page.getByText('Preview Dataset').waitFor()
  }

  get collectionRefInput(): Locator {
    return this.page.getByPlaceholder('e.g. imagenet-1k-sample')
  }

  get previewButton(): Locator {
    return this.page.getByRole('button', { name: 'Preview' })
  }

  get persistButton(): Locator {
    return this.page.getByRole('button', { name: 'Persist Dataset' })
  }

  get persistDialog(): Locator {
    return this.page.getByRole('dialog')
  }

  get persistConfirmButton(): Locator {
    return this.page.getByRole('button', { name: 'Persist', exact: true })
  }

  get gridRadio(): Locator {
    return this.page.getByRole('radio', { name: 'Grid' })
  }

  get listRadio(): Locator {
    return this.page.getByRole('radio', { name: 'List' })
  }

  get waferMapPanel(): Locator {
    return this.page.locator('[data-testid="wafer-map-panel"]')
  }

  get waferMapCanvas(): Locator {
    return this.page.locator('[data-testid="wafer-map-panel"] canvas')
  }

  get classificationToggle(): Locator {
    return this.page.locator('.cs-header__toggle')
  }

  get sampleItems(): Locator {
    return this.page.locator('[data-sb-item]')
  }

  get listImage(): Locator {
    return this.page.locator('[data-sb-item] img, .sb-list-img').first()
  }

  get expiredError(): Locator {
    return this.page.getByText('Preview session not found or expired.')
  }

  async fillCollectionRef(ref: string): Promise<this> {
    await this.collectionRefInput.fill(ref)
    return this
  }

  async clickPreview(): Promise<this> {
    await this.previewButton.click()
    return this
  }

  async switchToListView(): Promise<this> {
    await this.listRadio.click()
    return this
  }

  async clickPersist(): Promise<this> {
    await this.persistButton.click()
    await this.persistDialog.waitFor()
    return this
  }

  async confirmPersist(): Promise<this> {
    await this.persistConfirmButton.click()
    return this
  }

  async waitForSamplesLoaded(): Promise<this> {
    await this.page.waitForSelector('[data-sb-item]')
    return this
  }

  async goToPreviewLaunch(): Promise<this> {
    await this.goto('/preview')
    await this.waitForLoaded()
    return this
  }
}
