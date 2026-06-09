import type { Page } from '@playwright/test'
import { MOCK_AUTH_TOKEN } from '../constants'
import { makeUser } from '../factories'
import type { MockUser } from '../factories'

export async function mockAuthLogin(page: Page, token = MOCK_AUTH_TOKEN): Promise<void> {
  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: token, token_type: 'bearer' }),
    })
  })
}

export async function mockAuthMe(page: Page, user?: Partial<MockUser>): Promise<void> {
  const response = makeUser(user)
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response),
    })
  })
}
