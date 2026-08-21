import { beforeEach, describe, expect, it } from "vitest";
import { loadScSamplingPreference, saveScSamplingPreference } from "./samplingPreferences";

describe("SC sampling preferences", () => {
  beforeEach(() => localStorage.clear());

  it("keeps Annotation and Review pipelines as separate persisted preferences", () => {
    expect(loadScSamplingPreference("annotation").rules).toEqual([
      { type: "per_die_limit", limit: 10 },
      { type: "per_wafer_limit", limit: 200 },
    ]);
    expect(loadScSamplingPreference("review").rules).toEqual([
      { type: "per_wafer_limit", limit: 100 },
    ]);

    saveScSamplingPreference("annotation", {
      extraFilterEnabled: false,
      rules: [{ type: "per_die_limit", limit: 7 }],
    });
    saveScSamplingPreference("review", {
      extraFilterEnabled: true,
      rules: [{ type: "per_wafer_limit", limit: 80 }],
    });

    expect(loadScSamplingPreference("annotation")).toEqual({
      extraFilterEnabled: false,
      rules: [{ type: "per_die_limit", limit: 7 }],
    });
    expect(loadScSamplingPreference("review")).toEqual({
      extraFilterEnabled: true,
      rules: [{ type: "per_wafer_limit", limit: 80 }],
    });
  });
});
