import { expect, test } from "../../fixtures";
import { AdminInfrastructurePage } from "../../pages/admin/AdminInfrastructurePage";

test("admin infrastructure hides unconfigured operator-console links @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.auth.mockAuthMe({ is_superadmin: true });
  await authedPage.addInitScript(() => {
    localStorage.setItem(
      "auth_user",
      JSON.stringify({
        id: "user-e2e-admin",
        name: "E2E Admin",
        email: "admin@example.com",
        is_superadmin: true,
      }),
    );
  });

  const infrastructure = new AdminInfrastructurePage(authedPage);
  await infrastructure.goto("/admin/infrastructure");
  await infrastructure.waitForLoaded();

  await expect(authedPage.getByText("Infrastructure", { exact: true }).last()).toBeVisible();
  await expect(authedPage.getByTestId("prefect-launch")).toHaveCount(0);
  await expect(authedPage.getByTestId("minio-launch")).toHaveCount(0);
  await expect(authedPage.getByText("Not configured")).toHaveCount(2);
  await expect(authedPage.getByText(/TLS and an authenticated reverse proxy/)).toBeVisible();
});
