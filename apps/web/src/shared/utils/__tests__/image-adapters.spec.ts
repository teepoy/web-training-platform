import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  resolveImageUri,
  resolveImageUris,
  FALLBACK_PLACEHOLDER,
} from "../image-adapters";

const TOKEN = "test-jwt";

beforeEach(() => {
  localStorage.setItem("auth_token", TOKEN);
});

afterEach(() => {
  localStorage.removeItem("auth_token");
});

describe("resolveImageUri", () => {
  it("passes through data: URIs", () => {
    const uri = "data:image/png;base64,iVBORw0KGgo=";
    expect(resolveImageUri(uri)).toBe(uri);
  });

  it("passes through http:// URLs", () => {
    const uri = "http://example.com/img.png";
    expect(resolveImageUri(uri)).toBe(uri);
  });

  it("passes through https:// URLs", () => {
    const uri = "https://cdn.example.com/img.png";
    expect(resolveImageUri(uri)).toBe(uri);
  });

  it("resolves s3:// URIs through proxy with auth token", () => {
    const uri = "s3://bucket/key.png";
    const result = resolveImageUri(uri);
    expect(result).toContain("/api/v1/images/resolve?uri=");
    expect(result).toContain("s3%3A%2F%2Fbucket%2Fkey.png");
    expect(result).toContain(`token=${encodeURIComponent(TOKEN)}`);
  });

  it("resolves memory:// URIs through proxy with auth token", () => {
    const uri = "memory://dataset/sample.png";
    const result = resolveImageUri(uri);
    expect(result).toContain("/api/v1/images/resolve?uri=");
    expect(result).toContain("memory%3A%2F%2Fdataset%2Fsample.png");
    expect(result).toContain(`token=${encodeURIComponent(TOKEN)}`);
  });

  it("returns fallback placeholder for null", () => {
    expect(resolveImageUri(null)).toBe(FALLBACK_PLACEHOLDER);
  });

  it("returns fallback placeholder for undefined", () => {
    expect(resolveImageUri(undefined)).toBe(FALLBACK_PLACEHOLDER);
  });

  it("returns fallback placeholder for unrecognized scheme", () => {
    expect(resolveImageUri("gs://bucket/file.png")).toBe(FALLBACK_PLACEHOLDER);
  });
});

describe("resolveImageUris", () => {
  it("resolves multiple URIs", () => {
    const results = resolveImageUris([
      "data:image/png;base64,AAA",
      "s3://bucket/key.png",
    ]);
    expect(results).toHaveLength(2);
    expect(results[0]).toBe("data:image/png;base64,AAA");
    expect(results[1]).toContain("/api/v1/images/resolve?uri=");
    expect(results[1]).toContain(`token=${encodeURIComponent(TOKEN)}`);
  });

  it("returns fallback for empty array", () => {
    expect(resolveImageUris([])).toEqual([FALLBACK_PLACEHOLDER]);
  });

  it("returns fallback for null", () => {
    expect(resolveImageUris(null)).toEqual([FALLBACK_PLACEHOLDER]);
  });

  it("returns fallback for undefined", () => {
    expect(resolveImageUris(undefined)).toEqual([FALLBACK_PLACEHOLDER]);
  });
});
