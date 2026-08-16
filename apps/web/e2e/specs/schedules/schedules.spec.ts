import { expect, test } from "../../fixtures";

test("legacy Schedule and Sensor URLs no longer expose mechanism pages @mock", async ({
  authedPage,
}) => {
  await authedPage.goto("/schedules");
  await expect(authedPage).toHaveURL(/\/sc\/preview$/);
  await expect(authedPage.getByRole("heading", { name: "Schedules" })).toHaveCount(0);

  await authedPage.goto("/schedules/legacy-schedule");
  await expect(authedPage).toHaveURL(/\/sc\/preview$/);

  await authedPage.goto("/sensors");
  await expect(authedPage).toHaveURL(/\/sc\/preview$/);
  await expect(authedPage.getByRole("heading", { name: "Sensors" })).toHaveCount(0);
});
