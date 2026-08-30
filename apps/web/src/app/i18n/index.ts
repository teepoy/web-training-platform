import { createI18n } from "vue-i18n";
import VxeUI from "vxe-pc-ui";
import vxeEnUS from "vxe-pc-ui/lib/language/en-US.js";
import vxeZhCN from "vxe-pc-ui/lib/language/zh-CN.js";

import { messages } from "./messages";
import { supportedLocales, type AppLocale } from "./catalog";

export { supportedLocales, type AppLocale } from "./catalog";

export const LOCALE_STORAGE_KEY = "platform.locale";

export function normalizeLocale(value: string | null | undefined): AppLocale | null {
  if (!value) return null;
  if (value === "zh-CN" || value.toLowerCase().startsWith("zh")) return "zh-CN";
  if (value === "en-US" || value.toLowerCase().startsWith("en")) return "en-US";
  return null;
}

export function resolveInitialLocale(
  storedLocale?: string | null,
  browserLocales?: readonly string[],
): AppLocale {
  const stored = normalizeLocale(storedLocale);
  if (stored) return stored;

  for (const browserLocale of browserLocales ?? []) {
    const resolved = normalizeLocale(browserLocale);
    if (resolved) return resolved;
  }
  return "en-US";
}

function readBrowserLocale(): AppLocale {
  if (typeof window === "undefined") return "en-US";
  return resolveInitialLocale(
    window.localStorage.getItem(LOCALE_STORAGE_KEY),
    window.navigator.languages,
  );
}

const initialLocale = readBrowserLocale();

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale,
  fallbackLocale: "en-US",
  messages,
  datetimeFormats: {
    "en-US": { short: { dateStyle: "medium" } },
    "zh-CN": { short: { dateStyle: "medium" } },
  },
});

function syncExternalLocale(locale: AppLocale): void {
  VxeUI.setI18n("en-US", vxeEnUS);
  VxeUI.setI18n("zh-CN", vxeZhCN);
  VxeUI.setLanguage(locale);

  if (typeof document !== "undefined") {
    document.documentElement.lang = locale;
    document.title = i18n.global.t("app.title");
  }
}

export function setAppLocale(locale: AppLocale, persist = true): void {
  i18n.global.locale.value = locale;
  if (persist && typeof window !== "undefined") {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  }
  syncExternalLocale(locale);
}

export function initializeAppLocale(): void {
  setAppLocale(initialLocale, false);
}
