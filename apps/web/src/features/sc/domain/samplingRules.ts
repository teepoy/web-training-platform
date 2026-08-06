export type ScSamplingRuleId = "global" | "conditional" | "quota" | "rate" | "total";

export type ScSamplingGroupRuleKind = "quota" | "rate";
export type ScSamplingQuotaUnit = "count" | "ratio";
export type ScSamplingRounding = "floor" | "ceil" | "nearest";
export type ScSamplingUnlistedPolicy = "exclude" | "keep";

export interface ScSamplingConditionalLimitRule {
  enabled: boolean;
  field: string;
  value: string;
  limit: number;
}

export interface ScSamplingGroupTarget {
  value: string;
  /** Count for count quotas; percentage in the inclusive range 0..100 otherwise. */
  amount: number;
}

export interface ScSamplingGroupRule {
  enabled: boolean;
  kind: ScSamplingGroupRuleKind;
  field: string;
  unit: ScSamplingQuotaUnit;
  targets: ScSamplingGroupTarget[];
  rounding: ScSamplingRounding;
  unlisted: ScSamplingUnlistedPolicy;
}

export interface ScSamplingTotalLimitRule {
  enabled: boolean;
  limit: number;
}

export interface ScSamplingProgram {
  globalFilterEnabled: boolean;
  conditional: ScSamplingConditionalLimitRule;
  group: ScSamplingGroupRule;
  total: ScSamplingTotalLimitRule;
}

export interface ScSamplingGroupPopulation {
  value: string;
  count: number;
}

export const SC_SAMPLING_GROUP_FIELDS = [
  { label: "Class", value: "class_number" },
  { label: "Rough Bin", value: "rough_bin" },
  { label: "Final Bin", value: "final_bin" },
  { label: "Manual Bin", value: "manual_bin" },
  { label: "Annotation", value: "annotation_label" },
  { label: "Prediction", value: "prediction_label" },
  { label: "Final Class", value: "final_class" },
];

export function createDefaultScSamplingProgram(): ScSamplingProgram {
  return {
    globalFilterEnabled: true,
    conditional: {
      enabled: false,
      field: "class_number",
      value: "",
      limit: 50,
    },
    group: {
      enabled: false,
      kind: "quota",
      field: "class_number",
      unit: "count",
      targets: [],
      rounding: "nearest",
      unlisted: "exclude",
    },
    total: {
      enabled: true,
      limit: 200,
    },
  };
}

export function cloneScSamplingProgram(program: ScSamplingProgram): ScSamplingProgram {
  return {
    globalFilterEnabled: program.globalFilterEnabled,
    conditional: { ...program.conditional },
    group: {
      ...program.group,
      targets: program.group.targets.map((target) => ({ ...target })),
    },
    total: { ...program.total },
  };
}

export function scSamplingProgramError(program: ScSamplingProgram): string | null {
  if (program.conditional.enabled) {
    if (!program.conditional.field || !program.conditional.value) {
      return "Choose a field and value for the conditional limit.";
    }
    if (!Number.isInteger(program.conditional.limit) || program.conditional.limit < 0) {
      return "Conditional limits must be non-negative integers.";
    }
  }

  if (program.group.enabled) {
    if (!program.group.field || program.group.targets.length === 0) {
      return "Configure at least one group target.";
    }
    if (
      program.group.targets.some(
        (target) =>
          !Number.isFinite(target.amount) ||
          target.amount < 0 ||
          (program.group.kind === "quota" &&
            program.group.unit === "count" &&
            !Number.isInteger(target.amount)) ||
          ((program.group.kind === "rate" || program.group.unit === "ratio") &&
            target.amount > 100),
      )
    ) {
      return program.group.kind === "quota" && program.group.unit === "count"
        ? "Group counts must be non-negative integers."
        : "Group percentages must be between 0 and 100.";
    }
    if (program.group.targets.every((target) => target.amount === 0)) {
      return "At least one group target must be greater than zero.";
    }
    if (program.group.kind === "quota" && program.group.unit === "ratio") {
      if (!program.total.enabled) return "Final ratio quotas require an enabled total limit.";
      const ratioTotal = program.group.targets.reduce((sum, target) => sum + target.amount, 0);
      if (Math.abs(ratioTotal - 100) > 1e-9) {
        return `Final composition ratios must total 100%; current total is ${ratioTotal}%.`;
      }
      if (program.group.unlisted === "keep") {
        return "Final ratio quotas require unlisted groups to be excluded.";
      }
    }
  }

  if (program.total.enabled) {
    if (!Number.isInteger(program.total.limit) || program.total.limit < 1) {
      return "The total limit must be a positive integer.";
    }
  } else if (!program.group.enabled) {
    return "Enable a group rule or total limit to bound the sampled cohort.";
  }

  return null;
}

export function largestRemainderCounts(
  targets: readonly ScSamplingGroupTarget[],
  total: number,
): number[] {
  const ideals = targets.map((target) => (target.amount / 100) * total);
  const counts = ideals.map(Math.floor);
  let remaining = total - counts.reduce((sum, count) => sum + count, 0);
  const ranked = ideals
    .map((ideal, index) => ({ index, remainder: ideal - Math.floor(ideal) }))
    .sort((left, right) => right.remainder - left.remainder || left.index - right.index);
  for (const item of ranked) {
    if (remaining <= 0) break;
    counts[item.index] = (counts[item.index] ?? 0) + 1;
    remaining -= 1;
  }
  return counts;
}
