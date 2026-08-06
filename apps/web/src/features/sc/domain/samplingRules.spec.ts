import { describe, expect, it } from "vitest";
import { createDefaultScSamplingProgram, scSamplingProgramError } from "./samplingRules";

describe("SC sampling rules", () => {
  it("keeps the existing bounded random sampling behavior as the default", () => {
    const program = createDefaultScSamplingProgram();

    expect(program.extraFilterEnabled).toBe(true);
    expect(program.conditional.enabled).toBe(false);
    expect(program.group.enabled).toBe(false);
    expect(program.total).toEqual({ enabled: true, limit: 200 });
    expect(scSamplingProgramError(program)).toBeNull();
  });

  it("treats ratios as independent per-group sample percentages", () => {
    const program = createDefaultScSamplingProgram();
    program.group.enabled = true;
    program.group.unit = "ratio";
    program.group.targets = [
      { value: "a", amount: 2 },
      { value: "b", amount: 7.5 },
    ];
    program.group.othersAmount = 3;

    expect(scSamplingProgramError(program)).toBeNull();

    program.group.othersAmount = 101;
    expect(scSamplingProgramError(program)).toContain("between 0 and 100%");
  });

  it("does not allow an unbounded program", () => {
    const program = createDefaultScSamplingProgram();
    program.total.enabled = false;

    expect(scSamplingProgramError(program)).toContain("bound the sampled cohort");
  });
});
