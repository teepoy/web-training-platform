import { chromium, type FullConfig } from '@playwright/test'
import * as http from 'http'

interface LoginResponse {
  access_token: string
  user: {
    id: string
    email: string
    name: string
    is_superadmin: boolean
    is_active: boolean
    created_at: string
  }
}

async function httpJson<T>(
  apiUrl: string,
  method: string,
  path: string,
  body?: unknown,
  token?: string,
): Promise<{ status: number; body: T }> {
  return new Promise((resolve, reject) => {
    const url = new URL(apiUrl)
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const data = body ? JSON.stringify(body) : undefined

    const req = http.request(
      {
        hostname: url.hostname,
        port: url.port || (url.protocol === 'https:' ? 443 : 80),
        path,
        method,
        headers,
      },
      (res) => {
        let raw = ''
        res.on('data', (chunk) => (raw += chunk))
        res.on('end', () => {
          try {
            resolve({ status: res.statusCode ?? 0, body: JSON.parse(raw) as T })
          } catch {
            reject(new Error(`Failed to parse response: ${raw.slice(0, 200)}`))
          }
        })
      },
    )
    req.on('error', reject)
    if (data) req.write(data)
    req.end()
  })
}

async function globalSetup(config: FullConfig): Promise<void> {
  const apiUrl = process.env.API_URL || 'http://localhost:8000'

  const loginResp = await httpJson<LoginResponse>(apiUrl, 'POST', '/api/v1/auth/login', {
    email: 'seed@example.com',
    password: 'seed1234',
  })

  if (loginResp.status !== 200) {
    throw new Error(`Auth login failed: ${loginResp.status}`)
  }

  const token = loginResp.body.access_token

  const meResp = await httpJson<unknown>(apiUrl, 'GET', '/api/v1/auth/me', undefined, token)

  if (meResp.status !== 200) {
    throw new Error(`Auth me failed: ${meResp.status}`)
  }

  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  const baseURL = config.projects?.[0]?.use?.baseURL
  const origin = typeof baseURL === 'string' ? baseURL : 'http://localhost:5173'

  await page.goto(origin, { waitUntil: 'domcontentloaded' })

  await page.evaluate(
    ({ t, u }) => {
      localStorage.setItem('auth_token', t)
      localStorage.setItem('auth_user', JSON.stringify(u))
    },
    { t: token, u: meResp.body },
  )

  const storageStatePath =
    typeof config.projects?.[0]?.use?.storageState === 'string'
      ? config.projects[0].use.storageState
      : 'e2e-live/storageState.json'

  await context.storageState({ path: storageStatePath })
  await browser.close()
}

export default globalSetup
