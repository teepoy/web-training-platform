import type { Component } from "vue";
import type { ScSamplingRuleId } from "@/features/sc/domain/samplingRules";
import ClusterPercentageRuleEditor from "./ClusterPercentageRuleEditor.vue";
import RepeaterPercentageRuleEditor from "./RepeaterPercentageRuleEditor.vue";
import RandomPercentageRuleEditor from "./RandomPercentageRuleEditor.vue";
import ExcludeClassCodesRuleEditor from "./ExcludeClassCodesRuleEditor.vue";
import PerDieLimitRuleEditor from "./PerDieLimitRuleEditor.vue";
import ClusterCountRuleEditor from "./ClusterCountRuleEditor.vue";
import RepeaterCountRuleEditor from "./RepeaterCountRuleEditor.vue";
import RandomCountRuleEditor from "./RandomCountRuleEditor.vue";
import PerClusterLimitRuleEditor from "./PerClusterLimitRuleEditor.vue";
import PerRepeaterLimitRuleEditor from "./PerRepeaterLimitRuleEditor.vue";
import PerWaferLimitRuleEditor from "./PerWaferLimitRuleEditor.vue";
import RequireImageRuleEditor from "./RequireImageRuleEditor.vue";
import SizeRangeRuleEditor from "./SizeRangeRuleEditor.vue";
import IncludeClassCodesRuleEditor from "./IncludeClassCodesRuleEditor.vue";
import LargeDefectPercentageRuleEditor from "./LargeDefectPercentageRuleEditor.vue";
import LargeDefectCountRuleEditor from "./LargeDefectCountRuleEditor.vue";
import FinalClassDistributionRuleEditor from "./FinalClassDistributionRuleEditor.vue";

export type ScSamplingRuleEditorPlacement = "inline" | "modal";
export type ScSamplingRuleOptionSource = "class_number" | "final_class";

export interface ScSamplingRuleEditorDescriptor {
  component: Component;
  placement: ScSamplingRuleEditorPlacement;
  optionSource?: ScSamplingRuleOptionSource;
}

export const SC_SAMPLING_RULE_EDITORS = {
  cluster_percentage: { component: ClusterPercentageRuleEditor, placement: "inline" },
  repeater_percentage: { component: RepeaterPercentageRuleEditor, placement: "inline" },
  random_percentage: { component: RandomPercentageRuleEditor, placement: "inline" },
  exclude_class_codes: {
    component: ExcludeClassCodesRuleEditor,
    placement: "modal",
    optionSource: "class_number",
  },
  per_die_limit: { component: PerDieLimitRuleEditor, placement: "inline" },
  cluster_count: { component: ClusterCountRuleEditor, placement: "inline" },
  repeater_count: { component: RepeaterCountRuleEditor, placement: "inline" },
  random_count: { component: RandomCountRuleEditor, placement: "inline" },
  per_cluster_limit: { component: PerClusterLimitRuleEditor, placement: "inline" },
  per_repeater_limit: { component: PerRepeaterLimitRuleEditor, placement: "inline" },
  per_wafer_limit: { component: PerWaferLimitRuleEditor, placement: "inline" },
  require_image: { component: RequireImageRuleEditor, placement: "inline" },
  size_range: { component: SizeRangeRuleEditor, placement: "modal" },
  include_class_codes: {
    component: IncludeClassCodesRuleEditor,
    placement: "modal",
    optionSource: "class_number",
  },
  large_defect_percentage: {
    component: LargeDefectPercentageRuleEditor,
    placement: "modal",
  },
  large_defect_count: { component: LargeDefectCountRuleEditor, placement: "modal" },
  final_class_distribution: {
    component: FinalClassDistributionRuleEditor,
    placement: "modal",
    optionSource: "final_class",
  },
} satisfies Record<ScSamplingRuleId, ScSamplingRuleEditorDescriptor>;

export function scSamplingRuleEditor(id: ScSamplingRuleId): ScSamplingRuleEditorDescriptor {
  return SC_SAMPLING_RULE_EDITORS[id];
}
