import { describe, expect, it } from "vitest";

import { cssBackgroundImageUrl } from "./scSpriteStyle";

describe("cssBackgroundImageUrl", () => {
  it("quotes inspection sprite URLs whose timestamps contain spaces", () => {
    const url =
      "/api/v1/sc/sprites/patch/2026-08-01 04:00:00.000000/1/1?image_types=patchDefective";

    expect(cssBackgroundImageUrl(url)).toBe(`url(${JSON.stringify(url)})`);
  });

  it("escapes characters that would otherwise terminate the CSS URL", () => {
    const url = '/api/v1/sc/sprites/patch/value with "quotes" and (parentheses)';

    expect(cssBackgroundImageUrl(url)).toBe(`url(${JSON.stringify(url)})`);
  });
});
