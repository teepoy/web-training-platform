const MISSING_LEGEND_KEYS: Record<string, string> = {
  annotation_label: "__unlabeled__",
  prediction_label: "__no_prediction__",
  final_class: "__unclassified__",
};

export function normalizeLegendKey(column: string, value: unknown): string {
  if (value == null || value === "") {
    return MISSING_LEGEND_KEYS[column] ?? "__unlabeled__";
  }
  return String(value);
}

export function encodeLegendKey(key: string, codes: Map<string, number>, keys: string[]): number {
  const existing = codes.get(key);
  if (existing !== undefined) return existing;
  const code = keys.length;
  codes.set(key, code);
  keys.push(key);
  return code;
}

export function encodeLegendColorMap(
  colorMap: Record<string, string>,
  legendKeys: readonly string[],
): Record<string, string> {
  if (legendKeys.length === 0) return { ...colorMap };
  const encoded: Record<string, string> = {};
  legendKeys.forEach((key, code) => {
    const color = colorMap[key];
    if (color) encoded[String(code)] = color;
  });
  return encoded;
}
