import { describe, expect, it } from "vitest";

import { messages } from "./messages";

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
});
