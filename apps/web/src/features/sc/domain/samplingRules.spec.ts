import { describe, expect, it } from "vitest";
import {
  createDefaultScSamplingProgram,
  largestRemainderCounts,
  scSamplingProgramError,
} from "./samplingRules";

describe("SC sampling rules", () => {
  it("keeps the existing bounded random sampling behavior as the default", () => {
    const program = createDefaultScSamplingProgram();

    expect(program.globalFilterEnabled).toBe(true);
    expect(program.conditional.enabled).toBe(false);
    expect(program.group.enabled).toBe(false);
    expect(program.total).toEqual({ enabled: true, limit: 200 });
    expect(scSamplingProgramError(program)).toBeNull();
  });

  it("resolves final ratios with a deterministic largest-remainder allocation", () => {
    expect(
      largestRemainderCounts(
        [
          { value: "a", amount: 33.3 },
          { value: "b", amount: 33.3 },
          { value: "c", amount: 33.4 },
        ],
        10,
      ),
    ).toEqual([3, 3, 4]);
  });

  it("requires final ratios to total 100 and to have a later total limit", () => {
    const program = createDefaultScSamplingProgram();
    program.group.enabled = true;
    program.group.unit = "ratio";
    program.group.targets = [
      { value: "a", amount: 60 },
      { value: "b", amount: 30 },
    ];

    expect(scSamplingProgramError(program)).toContain("must total 100%");

    program.group.targets[1]!.amount = 40;
    program.total.enabled = false;
    expect(scSamplingProgramError(program)).toContain("require an enabled total limit");
  });

  it("does not allow an unbounded program", () => {
    const program = createDefaultScSamplingProgram();
    program.total.enabled = false;

    expect(scSamplingProgramError(program)).toContain("bound the sampled cohort");
  });
});
