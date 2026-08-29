import { expect, test } from "../../fixtures";

test("switches and persists the browser locale @mock", async ({ page }) => {
  await page.goto("/login");

  await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
  await expect(page.getByTestId("login-submit")).toHaveText("Sign In");

  await page.getByRole("button", { name: "简体中文" }).click();

  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByTestId("login-submit")).toHaveText("登录");
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("platform.locale")))
    .toBe("zh-CN");

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await expect(page.getByTestId("login-submit")).toHaveText("登录");
});
