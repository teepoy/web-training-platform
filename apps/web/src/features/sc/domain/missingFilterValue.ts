export const SC_MISSING_FILTER_OPTIONS = {
  annotation_label: { value: "__unlabeled__", label: "Unlabeled" },
  prediction_label: { value: "__no_prediction__", label: "No Prediction" },
  final_class: { value: "__unclassified__", label: "Unclassified" },
} as const;

export interface ScMissingFilterOption {
  value: string;
  label: string;
}

export function scMissingFilterOption(field: string): ScMissingFilterOption | null {
  return SC_MISSING_FILTER_OPTIONS[field as keyof typeof SC_MISSING_FILTER_OPTIONS] ?? null;
}

export function isScMissingFilterValue(field: string, value: unknown): boolean {
  return scMissingFilterOption(field)?.value === value;
}

export function splitScSetFilterValues(
  field: string,
  values: readonly (string | number)[],
): { values: Array<string | number>; includeMissing: boolean } {
  return {
    values: values.filter((value) => !isScMissingFilterValue(field, value)),
    includeMissing: values.some((value) => isScMissingFilterValue(field, value)),
  };
}
