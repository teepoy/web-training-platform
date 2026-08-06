export type ScSamplingRuleId = "extra" | "conditional" | "quota" | "total";

export type ScSamplingQuotaUnit = "count" | "ratio";
export type ScSamplingRounding = "floor" | "ceil" | "nearest";

export const SC_SAMPLING_RANDOM_SEED = 42;

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
  field: string;
  unit: ScSamplingQuotaUnit;
  targets: ScSamplingGroupTarget[];
  /** Rule applied independently to every group not listed in targets. */
  othersAmount: number;
  rounding: ScSamplingRounding;
}

export interface ScSamplingTotalLimitRule {
  enabled: boolean;
  limit: number;
}

export interface ScSamplingProgram {
  extraFilterEnabled: boolean;
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
    extraFilterEnabled: true,
    conditional: {
      enabled: false,
      field: "class_number",
      value: "",
      limit: 50,
    },
    group: {
      enabled: false,
      field: "class_number",
      unit: "count",
      targets: [],
      othersAmount: 0,
      rounding: "nearest",
    },
    total: {
      enabled: true,
      limit: 200,
    },
  };
}

export function cloneScSamplingProgram(program: ScSamplingProgram): ScSamplingProgram {
  return {
    extraFilterEnabled: program.extraFilterEnabled,
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
    if (!program.group.field) {
      return "Choose a field for the group quota.";
    }
    const amounts = [
      ...program.group.targets.map((target) => target.amount),
      program.group.othersAmount,
    ];
    if (
      amounts.some(
        (amount) =>
          !Number.isFinite(amount) ||
          amount < 0 ||
          (program.group.unit === "count" && !Number.isInteger(amount)) ||
          (program.group.unit === "ratio" && amount > 100),
      )
    ) {
      return program.group.unit === "count"
        ? "Group counts must be non-negative integers."
        : "Group sample ratios must be between 0 and 100%.";
    }
    if (amounts.every((amount) => amount === 0)) {
      return "At least one group target must be greater than zero.";
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
