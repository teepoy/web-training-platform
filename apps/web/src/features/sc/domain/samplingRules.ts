export type ScSamplingRounding = "floor";
export type ScSamplingSizeField = "size_x" | "size_y" | "size_d" | "area";
export type ScSamplingRulePhase = "eligibility" | "selector" | "cap";

export const SC_SAMPLING_RANDOM_SEED = 42;

interface ScRule<Type extends string> {
  type: Type;
}

export interface ScSamplingPercentageRule<
  Type extends "cluster_percentage" | "repeater_percentage" | "random_percentage",
> extends ScRule<Type> {
  percentage: number;
  rounding: ScSamplingRounding;
}

export interface ScSamplingClassCodesRule<
  Type extends "exclude_class_codes" | "include_class_codes",
> extends ScRule<Type> {
  classCodes: number[];
}

export interface ScSamplingLimitRule<
  Type extends "per_die_limit" | "per_cluster_limit" | "per_repeater_limit" | "per_wafer_limit",
> extends ScRule<Type> {
  limit: number;
}

export interface ScSamplingCountRule<
  Type extends "cluster_count" | "repeater_count" | "random_count",
> extends ScRule<Type> {
  count: number;
}

export interface ScSamplingRequireImageRule extends ScRule<"require_image"> {}

export interface ScSamplingSizeRangeRule extends ScRule<"size_range"> {
  sizeField: ScSamplingSizeField;
  minimum: number;
  maximum: number;
}

export interface ScSamplingLargeDefectPercentageRule extends ScRule<"large_defect_percentage"> {
  percentage: number;
  rounding: ScSamplingRounding;
  sizeField: ScSamplingSizeField;
  minimum: number;
}

export interface ScSamplingLargeDefectCountRule extends ScRule<"large_defect_count"> {
  count: number;
  sizeField: ScSamplingSizeField;
  minimum: number;
}

export interface ScSamplingFinalClassTarget {
  value: string;
  percentage: number;
}

export interface ScSamplingFinalClassDistributionRule extends ScRule<"final_class_distribution"> {
  count: number;
  targets: ScSamplingFinalClassTarget[];
}

export type ScSamplingRule =
  | ScSamplingPercentageRule<"cluster_percentage">
  | ScSamplingPercentageRule<"repeater_percentage">
  | ScSamplingPercentageRule<"random_percentage">
  | ScSamplingClassCodesRule<"exclude_class_codes">
  | ScSamplingLimitRule<"per_die_limit">
  | ScSamplingCountRule<"cluster_count">
  | ScSamplingCountRule<"repeater_count">
  | ScSamplingCountRule<"random_count">
  | ScSamplingLimitRule<"per_cluster_limit">
  | ScSamplingLimitRule<"per_repeater_limit">
  | ScSamplingLimitRule<"per_wafer_limit">
  | ScSamplingRequireImageRule
  | ScSamplingSizeRangeRule
  | ScSamplingClassCodesRule<"include_class_codes">
  | ScSamplingLargeDefectPercentageRule
  | ScSamplingLargeDefectCountRule
  | ScSamplingFinalClassDistributionRule;

export type ScSamplingRuleId = ScSamplingRule["type"];

export interface ScSamplingRuleCatalogItem {
  id: ScSamplingRuleId;
  order: string;
  title: string;
  description: string;
  phase: ScSamplingRulePhase;
}

export const SC_REVIEW_SAMPLING_RULE_CATALOG: readonly ScSamplingRuleCatalogItem[] = [
  {
    id: "cluster_percentage",
    order: "01",
    title: "Cluster defects by percentage",
    description: "Randomly choose N% from defects whose Cluster ID is positive.",
    phase: "selector",
  },
  {
    id: "repeater_percentage",
    order: "02",
    title: "Repeater defects by percentage",
    description: "Randomly choose N% from defects whose Repeater ID is positive.",
    phase: "selector",
  },
  {
    id: "random_percentage",
    order: "03",
    title: "All defects by percentage",
    description: "Randomly choose N% from all eligible defects.",
    phase: "selector",
  },
  {
    id: "exclude_class_codes",
    order: "04",
    title: "Ignore Class Codes",
    description: "Remove specified Class Codes before any random draw.",
    phase: "eligibility",
  },
  {
    id: "per_die_limit",
    order: "05",
    title: "Maximum per Die",
    description: "Keep at most N selected defects on each Die.",
    phase: "cap",
  },
  {
    id: "cluster_count",
    order: "06",
    title: "Cluster defects by count",
    description: "Randomly choose up to N Cluster defects.",
    phase: "selector",
  },
  {
    id: "repeater_count",
    order: "07",
    title: "Repeater defects by count",
    description: "Randomly choose up to N Repeater defects.",
    phase: "selector",
  },
  {
    id: "random_count",
    order: "08",
    title: "All defects by count",
    description: "Randomly choose up to N eligible defects.",
    phase: "selector",
  },
  {
    id: "per_cluster_limit",
    order: "09",
    title: "Maximum per Cluster ID",
    description: "Keep at most N selected defects for each positive Cluster ID.",
    phase: "cap",
  },
  {
    id: "per_repeater_limit",
    order: "10",
    title: "Maximum per Repeater ID",
    description: "Keep at most N selected defects for each positive Repeater ID.",
    phase: "cap",
  },
  {
    id: "per_wafer_limit",
    order: "11",
    title: "Maximum per Wafer",
    description: "Keep at most N selected defects on each Wafer.",
    phase: "cap",
  },
  {
    id: "require_image",
    order: "12",
    title: "Only defects with images",
    description: "Remove defects that have no available image.",
    phase: "eligibility",
  },
  {
    id: "size_range",
    order: "13",
    title: "Defect Size range",
    description: "Keep defects inside an inclusive Size interval.",
    phase: "eligibility",
  },
  {
    id: "include_class_codes",
    order: "14",
    title: "Only specified Class Codes",
    description: "Keep only defects with one of the specified Class Codes.",
    phase: "eligibility",
  },
  {
    id: "large_defect_percentage",
    order: "15",
    title: "Large defects by percentage",
    description: "Randomly choose N% of defects at or above a Size threshold.",
    phase: "selector",
  },
  {
    id: "large_defect_count",
    order: "16",
    title: "Large defects by count",
    description: "Randomly choose up to N defects at or above a Size threshold.",
    phase: "selector",
  },
  {
    id: "final_class_distribution",
    order: "17",
    title: "Final Class distribution",
    description: "Split a total N by explicit Final Class percentages, then draw randomly.",
    phase: "selector",
  },
];

export interface ScSamplingProgram {
  extraFilterEnabled: boolean;
  rules: ScSamplingRule[];
}

export interface ScSamplingGroupPopulation {
  value: string;
  count: number;
}

export const SC_SAMPLING_SIZE_FIELDS = [
  { label: "Width", value: "size_x" },
  { label: "Height", value: "size_y" },
  { label: "Diameter", value: "size_d" },
  { label: "Area", value: "area" },
] satisfies Array<{ label: string; value: ScSamplingSizeField }>;

const ELIGIBILITY_RULES = new Set<ScSamplingRuleId>([
  "exclude_class_codes",
  "require_image",
  "size_range",
  "include_class_codes",
]);

export function createDefaultScSamplingRule(type: ScSamplingRuleId): ScSamplingRule {
  switch (type) {
    case "cluster_percentage":
    case "repeater_percentage":
    case "random_percentage":
      return { type, percentage: 10, rounding: "floor" };
    case "exclude_class_codes":
    case "include_class_codes":
      return { type, classCodes: [] };
    case "per_die_limit":
    case "per_cluster_limit":
    case "per_repeater_limit":
    case "per_wafer_limit":
      return { type, limit: 5 };
    case "cluster_count":
    case "repeater_count":
    case "random_count":
      return { type, count: type === "random_count" ? 200 : 50 };
    case "require_image":
      return { type };
    case "size_range":
      return { type, sizeField: "size_d", minimum: 0, maximum: 100 };
    case "large_defect_percentage":
      return { type, sizeField: "size_d", minimum: 100, percentage: 10, rounding: "floor" };
    case "large_defect_count":
      return { type, sizeField: "size_d", minimum: 100, count: 50 };
    case "final_class_distribution":
      return { type, count: 200, targets: [] };
  }
}

export function createDefaultScSamplingProgram(): ScSamplingProgram {
  return {
    extraFilterEnabled: true,
    rules: [{ type: "random_count", count: 200 }],
  };
}

export function cloneScSamplingProgram(program: ScSamplingProgram): ScSamplingProgram {
  return {
    extraFilterEnabled: program.extraFilterEnabled,
    rules: program.rules.map((rule) => {
      if (rule.type === "exclude_class_codes" || rule.type === "include_class_codes") {
        return { ...rule, classCodes: [...rule.classCodes] };
      }
      if (rule.type === "final_class_distribution") {
        return { ...rule, targets: rule.targets.map((target) => ({ ...target })) };
      }
      return { ...rule };
    }),
  };
}

function validPositiveInteger(value: number): boolean {
  return Number.isInteger(value) && value > 0;
}

function validPercentage(value: number): boolean {
  return Number.isFinite(value) && value > 0 && value <= 100;
}

export function scSamplingProgramError(program: ScSamplingProgram): string | null {
  if (program.rules.length === 0) return "Enable at least one sampling rule.";
  const ids = program.rules.map((rule) => rule.type);
  if (new Set(ids).size !== ids.length) return "Each sampling rule can be enabled only once.";
  if (ids.every((id) => ELIGIBILITY_RULES.has(id))) {
    return "Enable at least one selector or cap rule.";
  }

  for (const rule of program.rules) {
    if (
      rule.type === "cluster_percentage" ||
      rule.type === "repeater_percentage" ||
      rule.type === "random_percentage" ||
      rule.type === "large_defect_percentage"
    ) {
      if (!validPercentage(rule.percentage)) return "Sampling percentages must be within 0–100%.";
    }
    if (
      rule.type === "cluster_count" ||
      rule.type === "repeater_count" ||
      rule.type === "random_count" ||
      rule.type === "large_defect_count"
    ) {
      if (!validPositiveInteger(rule.count)) return "Sampling counts must be positive integers.";
    }
    if (
      rule.type === "per_die_limit" ||
      rule.type === "per_cluster_limit" ||
      rule.type === "per_repeater_limit" ||
      rule.type === "per_wafer_limit"
    ) {
      if (!validPositiveInteger(rule.limit)) return "Sampling caps must be positive integers.";
    }
    if (rule.type === "exclude_class_codes" || rule.type === "include_class_codes") {
      if (
        rule.classCodes.length === 0 ||
        rule.classCodes.some((value) => !Number.isInteger(value)) ||
        new Set(rule.classCodes).size !== rule.classCodes.length
      ) {
        return "Class Code rules require one or more unique integer codes.";
      }
    }
    if (rule.type === "size_range") {
      if (
        !Number.isFinite(rule.minimum) ||
        !Number.isFinite(rule.maximum) ||
        rule.minimum < 0 ||
        rule.maximum < rule.minimum
      ) {
        return "Size range requires non-negative bounds with minimum ≤ maximum.";
      }
    }
    if (rule.type === "large_defect_count" || rule.type === "large_defect_percentage") {
      if (!Number.isFinite(rule.minimum) || rule.minimum < 0) {
        return "Large-defect Size threshold must be non-negative.";
      }
    }
    if (rule.type === "final_class_distribution") {
      if (!validPositiveInteger(rule.count)) return "Final Class total must be a positive integer.";
      const values = rule.targets.map((target) => target.value);
      const percentage = rule.targets.reduce((sum, target) => sum + target.percentage, 0);
      if (
        rule.targets.length === 0 ||
        new Set(values).size !== values.length ||
        rule.targets.some((target) => !validPercentage(target.percentage)) ||
        Math.abs(percentage - 100) > 1e-6
      ) {
        return "Final Class targets must be unique and total exactly 100%.";
      }
    }
  }
  return null;
}

export function scSamplingRequiredFields(program: ScSamplingProgram): Set<string> {
  const fields = new Set<string>(["map_id"]);
  for (const rule of program.rules) {
    switch (rule.type) {
      case "cluster_percentage":
      case "cluster_count":
      case "per_cluster_limit":
        fields.add("cluster_id");
        break;
      case "repeater_percentage":
      case "repeater_count":
      case "per_repeater_limit":
        fields.add("repeater_id");
        break;
      case "exclude_class_codes":
      case "include_class_codes":
        fields.add("class_number");
        break;
      case "per_die_limit":
        fields.add("index_x");
        fields.add("index_y");
        fields.add("inspection_time");
        fields.add("wafer_key");
        break;
      case "per_wafer_limit":
        fields.add("inspection_time");
        fields.add("wafer_key");
        break;
      case "require_image":
        fields.add("images");
        break;
      case "size_range":
      case "large_defect_percentage":
      case "large_defect_count":
        fields.add(rule.sizeField);
        break;
      case "final_class_distribution":
        fields.add("final_class");
        break;
      case "random_percentage":
      case "random_count":
        break;
    }
  }
  return fields;
}
