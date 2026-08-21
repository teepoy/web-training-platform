import { test, expect } from "../../fixtures";
import { LoginPage } from "../../pages/auth/LoginPage";
import { AppShell } from "../../pages/common/AppShell";
import { DatasetListPage } from "../../pages/datasets/DatasetListPage";

const liveAuthEnabled = process.env.PLAYWRIGHT_AUTH_ENABLED === "1";

// ═══════════════════════════════════════════════════════════════════
// @mock tests — auth flows with mocked backend
// ═══════════════════════════════════════════════════════════════════

test("redirects unauthenticated users to login @mock", async ({ page }) => {
  // Uses plain page (no authedPage) — no localStorage token set.
  // The auth guard redirects to /login purely client-side.
  await page.goto("/datasets");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByTestId("login-email")).toBeVisible();
});

test("logs in and shows the Library @mock", async ({ page, apiMocks }) => {
  // Uses plain page (no authedPage) — no pre-seeded token.
  // apiMocks.mockCoreApi wires up routes (login, me, orgs, datasets).
  await apiMocks.core.mockCoreApi();

  const loginPage = new LoginPage(page);
  await loginPage.goto("/login");
  await loginPage.waitForLoaded();

  await loginPage.fillEmail("e2e@example.com");
  await loginPage.fillPassword("password123");
  await loginPage.submit();

  await expect(page).toHaveURL(/\/library$/);
  await expect(page.getByRole("heading", { name: "Library" })).toBeVisible();
  await expect(page.getByText("flowers-dataset")).toBeVisible();
});

// ═══════════════════════════════════════════════════════════════════
// @live tests — auth flows against real backend
// ═══════════════════════════════════════════════════════════════════

test.describe("Auth Flow — without existing session", () => {
  test.skip(!liveAuthEnabled, "requires a live stack with frontend and API auth enabled");
  test.use({ storageState: { cookies: [], origins: [] } });

  test("registration creates new user @live", async ({ page }) => {
    const uniqueEmail = `e2e-reg-${Date.now()}@test.com`;

    await page.goto("/register");
    await page.getByTestId("register-form").waitFor();

    await page.getByPlaceholder("Your name").fill("E2E Test");
    await page.getByPlaceholder("you@example.com").fill(uniqueEmail);
    await page.getByPlaceholder("Password").fill("test1234");

    await page.getByRole("button", { name: "Create Account" }).click();

    await expect(page).toHaveURL(/\/library/);
    await expect(page.getByTestId("nav-avatar")).toBeVisible();
  });

  test("login with seed credentials @live", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("login-form").waitFor();

    await page.getByPlaceholder("you@example.com").fill("seed@example.com");
    await page.getByPlaceholder("Password").fill("seed1234");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page).toHaveURL(/\/library/);
    await expect(page.getByTestId("nav-avatar")).toBeVisible();
  });

  test("login with invalid password shows error @live", async ({ page }) => {
    await page.goto("/login");
    await page.getByTestId("login-form").waitFor();

    await page.getByPlaceholder("you@example.com").fill("seed@example.com");
    await page.getByPlaceholder("Password").fill("wrongpassword");
    await page.getByRole("button", { name: "Sign In" }).click();

    await expect(page).not.toHaveURL(/\/datasets/);

    const errorLocator = page.locator(".n-message, .n-form-item-feedback--error");
    await expect(errorLocator.first()).toBeVisible({ timeout: 10_000 });
  });

  test("protected route redirects when unauthenticated @live", async ({ page }) => {
    await page.goto("/datasets");
    await page.waitForURL("**/login");
    await expect(page).toHaveURL(/\/login/);
  });
});

test("logout redirects to login @live", async ({ page }) => {
  test.skip(!liveAuthEnabled, "requires a live stack with frontend and API auth enabled");

  // Uses storageState from project config — already authenticated
  await page.goto("/datasets");

  const listPage = new DatasetListPage(page);
  await listPage.waitForLoaded();

  await expect(page.getByTestId("nav-avatar")).toBeVisible();

  const shell = new AppShell(page);
  await shell.logout();

  await expect(page).toHaveURL(/\/login/);
});
