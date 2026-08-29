import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const webRoot = `${process.cwd()}/`;

describe("development package boundaries", () => {
  it("keeps sandbox pages out of the production feature tree", () => {
    expect(existsSync(`${webRoot}src/features/sandbox`)).toBe(false);
    expect(existsSync(`${webRoot}devtools/sandbox/router.ts`)).toBe(true);
  });

  it("keeps Storybook providers out of shared runtime source", () => {
    expect(existsSync(`${webRoot}src/shared/storybook`)).toBe(false);
    expect(existsSync(`${webRoot}.storybook/support/mocks.ts`)).toBe(true);
  });

  it("loads development routes only behind Vite's development guard", () => {
    const mainSource = readFileSync(`${webRoot}src/app/main.ts`, "utf8");
    const routerSource = readFileSync(`${webRoot}src/app/router.ts`, "utf8");

    expect(mainSource).toContain("if (import.meta.env.DEV)");
    expect(mainSource).toContain('import("../../devtools/register")');
    expect(routerSource).not.toContain("sandbox");
  });
});
