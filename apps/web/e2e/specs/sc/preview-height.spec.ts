/**
 * SC preview page height spec — mock mode.
 *
 * Verifies that the SC preview page body/document does not overflow
 * the viewport (allowing small tolerance for borders).
 *
 * @mock — uses authedPage (auto mock) + apiMocks SC handlers.
 */
import { test, expect } from "../../fixtures";

test("sc preview page height does not overflow viewport @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.sc.mockScInspections();
  await apiMocks.sc.mockScInspectionSamples();

  await authedPage.goto("/sc/preview");
  await authedPage.waitForLoadState("networkidle");

  const viewport = authedPage.viewportSize();
  expect(viewport).not.toBeNull();

  const bodyHeight = await authedPage.evaluate(() => document.body.scrollHeight);
  const docHeight = await authedPage.evaluate(() => document.documentElement.scrollHeight);

  console.log(
    `viewport: ${viewport!.width}x${viewport!.height}, body scroll: ${bodyHeight}, doc scroll: ${docHeight}`,
  );

  expect(bodyHeight).toBeLessThanOrEqual(viewport!.height + 2);
  expect(docHeight).toBeLessThanOrEqual(viewport!.height + 2);
});
