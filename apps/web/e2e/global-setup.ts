import { chromium, type FullConfig } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import { E2E_PATHS } from "./paths";

async function globalSetup(config: FullConfig): Promise<void> {
  if (process.env.PLAYWRIGHT_MODE !== "live") return;

  const apiUrl = process.env.API_URL || "http://localhost:8000";
  const email = process.env.PW_USER_EMAIL;
  const password = process.env.PW_USER_PASSWORD;
  if (!email || !password) {
    throw new Error("PW_USER_EMAIL and PW_USER_PASSWORD are required in live E2E mode");
  }

  let token: string;
  let user: unknown;
  try {
    const { seedLogin } = await import("./seed/auth");
    const result = await seedLogin({ email, password });
    token = result.token;
    user = result.user;
  } catch {
    try {
      const { request } = await import("http");
      const loginBody = JSON.stringify({ email, password });
      const loginResp = await new Promise<{
        status: number;
        body: { access_token: string; user: unknown };
      }>((resolve, reject) => {
        const url = new URL(apiUrl);
        const req = request(
          {
            hostname: url.hostname,
            port: url.port || "8000",
            path: "/api/v1/auth/login",
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Content-Length": Buffer.byteLength(loginBody).toString(),
            },
          },
          (res) => {
            let raw = "";
            res.on("data", (chunk: string) => (raw += chunk));
            res.on("end", () => {
              try {
                resolve({
                  status: res.statusCode ?? 0,
                  body: JSON.parse(raw) as { access_token: string; user: unknown },
                });
              } catch {
                reject(new Error(`Failed to parse login response: ${raw.slice(0, 200)}`));
              }
            });
          },
        );
        req.on("error", reject);
        req.write(loginBody);
        req.end();
      });
      if (loginResp.status !== 200) {
        throw new Error(`Auth login failed: status=${loginResp.status}`);
      }
      token = loginResp.body.access_token;
      user = loginResp.body.user;
    } catch {
      console.warn(
        "[global-setup] Backend unreachable — skipping storage state (mock-only or backend down).",
      );
      return;
    }
  }

  const accessToken = token;

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  const baseURL =
    (config.projects?.[0]?.use?.baseURL as string | undefined) || "http://localhost:5174";
  await page.goto(baseURL, { waitUntil: "domcontentloaded" });

  await page.evaluate(
    ({ t, u }) => {
      localStorage.setItem("auth_token", t);
      localStorage.setItem("auth_user", JSON.stringify(u));
    },
    { t: accessToken, u: user },
  );

  await mkdir(path.dirname(E2E_PATHS.authState), { recursive: true });
  await context.storageState({ path: E2E_PATHS.authState });
  await browser.close();
}

export default globalSetup;
