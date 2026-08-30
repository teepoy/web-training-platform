export const supportedLocales = ["en-US", "zh-CN"] as const;
export type AppLocale = (typeof supportedLocales)[number];

export interface MessageTree {
  [key: string]: string | MessageTree;
}

export interface FeatureMessageCatalog {
  name: string;
  messages: Record<AppLocale, MessageTree>;
}

export function defineMessageCatalog(
  name: string,
  messages: Record<AppLocale, MessageTree>,
): FeatureMessageCatalog {
  return { name, messages };
}

export function mergeMessageCatalogs(
  catalogs: readonly FeatureMessageCatalog[],
): Record<AppLocale, MessageTree> {
  const merged = Object.fromEntries(supportedLocales.map((locale) => [locale, {}])) as Record<
    AppLocale,
    MessageTree
  >;

  for (const catalog of catalogs) {
    for (const locale of supportedLocales) {
      for (const [namespace, messages] of Object.entries(catalog.messages[locale])) {
        if (namespace in merged[locale]) {
          throw new Error(
            `Duplicate i18n namespace "${namespace}" for ${locale} in catalog "${catalog.name}"`,
          );
        }
        merged[locale][namespace] = messages;
      }
    }
  }

  return merged;
}
