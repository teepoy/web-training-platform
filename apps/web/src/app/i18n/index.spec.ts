import { beforeEach, describe, expect, it } from "vitest";

import {
  LOCALE_STORAGE_KEY,
  i18n,
  initializeAppLocale,
  normalizeLocale,
  resolveInitialLocale,
  setAppLocale,
} from "./index";

describe("application locale", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setAppLocale("en-US", false);
  });

  it("normalizes supported browser locale variants", () => {
    expect(normalizeLocale("zh-Hans-CN")).toBe("zh-CN");
    expect(normalizeLocale("en-GB")).toBe("en-US");
    expect(normalizeLocale("fr-FR")).toBeNull();
  });

  it("prefers the stored browser setting over browser languages", () => {
    expect(resolveInitialLocale("en-US", ["zh-CN"])).toBe("en-US");
    expect(resolveInitialLocale(null, ["zh-CN", "en-US"])).toBe("zh-CN");
  });

  it("persists locale and synchronizes document metadata", () => {
    setAppLocale("zh-CN");

    expect(i18n.global.locale.value).toBe("zh-CN");
    expect(window.localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("zh-CN");
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(document.title).toBe("机器学习训练平台");
  });

  it("initializes the component-library and document locale", () => {
    initializeAppLocale();
    expect(document.documentElement.lang).toBe("en-US");
  });
});
