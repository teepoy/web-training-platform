import { describe, expect, it } from "vitest";

import { mergeMessageCatalogs } from "./catalog";
import { messageCatalogs, messages } from "./messages";

function flattenMessages(value: Record<string, unknown>, prefix = ""): Record<string, string> {
  const flattened: Record<string, string> = {};
  for (const [key, item] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof item === "string") {
      flattened[path] = item;
    } else if (item && typeof item === "object" && !Array.isArray(item)) {
      Object.assign(flattened, flattenMessages(item as Record<string, unknown>, path));
    }
  }
  return flattened;
}

function placeholders(message: string): string[] {
  return Array.from(
    new Set(Array.from(message.matchAll(/\{([\w-]+)\}/g), (match) => match[1])),
  ).sort();
}

describe("application message catalogs", () => {
  const english = flattenMessages(messages["en-US"]);
  const chinese = flattenMessages(messages["zh-CN"]);

  it("keeps the English and Simplified Chinese key sets in sync", () => {
    expect(Object.keys(chinese).sort()).toEqual(Object.keys(english).sort());
  });

  it("keeps interpolation parameters compatible across locales", () => {
    for (const [key, source] of Object.entries(english)) {
      expect(placeholders(chinese[key]), key).toEqual(placeholders(source));
    }
  });

  it("keeps every feature catalog independently complete", () => {
    for (const catalog of messageCatalogs) {
      const featureEnglish = flattenMessages(catalog.messages["en-US"]);
      const featureChinese = flattenMessages(catalog.messages["zh-CN"]);

      expect(Object.keys(featureChinese).sort(), catalog.name).toEqual(
        Object.keys(featureEnglish).sort(),
      );
      for (const [key, source] of Object.entries(featureEnglish)) {
        expect(placeholders(featureChinese[key]), `${catalog.name}:${key}`).toEqual(
          placeholders(source),
        );
      }
    }
  });

  it("rejects duplicate top-level namespaces during composition", () => {
    expect(() =>
      mergeMessageCatalogs([
        {
          name: "first",
          messages: { "en-US": { common: {} }, "zh-CN": { common: {} } },
        },
        {
          name: "second",
          messages: { "en-US": { common: {} }, "zh-CN": { common: {} } },
        },
      ]),
    ).toThrow('Duplicate i18n namespace "common"');
  });
});
