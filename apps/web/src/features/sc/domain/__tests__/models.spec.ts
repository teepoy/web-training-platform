import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  patchImageUrl,
  reviewImageUrl,
  scGalleryImageDownloadsUrl,
  scInspectionImageProfileUrl,
  scPatchUrl,
  scReviewUrl,
  buildScBlinkImageUrls,
  normalizeScImageRole,
  type ScPatchImageRole,
} from "../models";

const TOKEN = "test-jwt-token";

beforeEach(() => {
  localStorage.setItem("auth_token", TOKEN);
});

afterEach(() => {
  localStorage.removeItem("auth_token");
});

function expectAuthToken(url: string): void {
  expect(url).toContain(`token=${encodeURIComponent(TOKEN)}`);
}

// ── Raw URL constructors (no auth) ──────────────────────────────────────

describe("patchImageUrl", () => {
  it("encodes inspection time and defect id", () => {
    const url = patchImageUrl("2025-06-01T00:00:00Z", 1, "D-42", "template");
    expect(url).toBe("/api/v1/sc/images/2025-06-01T00%3A00%3A00Z/1/D-42/template");
  });

  it("handles bigint inspectionTime", () => {
    const url = patchImageUrl(BigInt(1717200000000), 3, 99, "defective");
    expect(url).toContain("/api/v1/sc/images/1717200000000/3/99/defective");
  });

  it("supports all three image types", () => {
    for (const t of ["template", "defective", "difference"] as const) {
      const url = patchImageUrl("t", 0, "d", t);
      expect(url).toContain(`/${t}`);
    }
  });

  it("does not include auth token", () => {
    const url = patchImageUrl("t", 0, "d", "template");
    expect(url).not.toContain("token=");
  });
});

describe("reviewImageUrl", () => {
  it("appends review_image_id query param", () => {
    const url = reviewImageUrl("t", 1, "d", 5);
    expect(url).toContain("/review?review_image_id=5");
  });

  it("does not include auth token", () => {
    const url = reviewImageUrl("t", 1, "d", 5);
    expect(url).not.toContain("token=");
  });
});

// ── Canonical authenticated helpers ─────────────────────────────────────

describe("image-parser gateway URLs", () => {
  it("encodes the inspection image profile identity", () => {
    expect(scInspectionImageProfileUrl("2026-08-01T04:00:00+08:00", 7)).toBe(
      "/api/v1/sc/inspections/2026-08-01T04%3A00%3A00%2B08%3A00/7/image-profile",
    );
  });

  it("returns the selected gallery image download endpoint", () => {
    expect(scGalleryImageDownloadsUrl()).toBe("/api/v1/sc/gallery-downloads");
  });
});

describe("scPatchUrl", () => {
  it("wraps patchImageUrl with auth query params", () => {
    const url = scPatchUrl("t", 1, "d", "template");
    expect(url).toContain("/api/v1/sc/images/t/1/d/template");
    expectAuthToken(url);
  });
});

describe("scReviewUrl", () => {
  it("wraps reviewImageUrl with auth query params", () => {
    const url = scReviewUrl("t", 1, "d", 7);
    expect(url).toContain("/api/v1/sc/images/t/1/d/review?review_image_id=7");
    expect(url).toContain("render_version=3");
    expectAuthToken(url);
  });
});

describe("buildScBlinkImageUrls", () => {
  it("returns all four image types with auth", () => {
    const urls = buildScBlinkImageUrls("t", 1, "d", [{ imageId: 1 }, { imageId: 2 }]);

    expect(urls.template).toBeTruthy();
    expect(urls.defective).toBeTruthy();
    expect(urls.difference).toBeTruthy();
    expect(urls.review).toHaveLength(2);

    expectAuthToken(urls.template);
    expectAuthToken(urls.defective);
    expectAuthToken(urls.difference);
    expect(urls.review[0]).toContain("review_image_id=1");
    expect(urls.review[1]).toContain("review_image_id=2");
    expectAuthToken(urls.review[0]);
    expectAuthToken(urls.review[1]);
  });

  it("handles empty review images", () => {
    const urls = buildScBlinkImageUrls("t", 1, "d");
    expect(urls.review).toEqual([]);
  });

  it("handles undefined review images", () => {
    const urls = buildScBlinkImageUrls("t", 1, "d", undefined);
    expect(urls.review).toEqual([]);
  });
});

// ── Role normalization ──────────────────────────────────────────────────

describe("normalizeScImageRole", () => {
  it("returns template for patch_template", () => {
    expect(normalizeScImageRole("patch_template")).toBe("template");
  });

  it("returns defective for PATCH_DEFECTIVE (case insensitive)", () => {
    expect(normalizeScImageRole("PATCH_DEFECTIVE")).toBe("defective");
  });

  it("returns difference for patch_difference", () => {
    expect(normalizeScImageRole("patch_difference")).toBe("difference");
  });

  it("returns null for review", () => {
    expect(normalizeScImageRole("review")).toBeNull();
  });

  it("returns null for unknown roles", () => {
    expect(normalizeScImageRole("unknown")).toBeNull();
  });

  it("returns null for empty string", () => {
    expect(normalizeScImageRole("")).toBeNull();
  });

  it("matches template substring", () => {
    expect(normalizeScImageRole("image_template")).toBe("template");
  });
});
