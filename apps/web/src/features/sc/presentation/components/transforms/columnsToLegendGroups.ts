export interface LegendGroup {
  count: number;
  defectIds: number[];
}

export function columnsToLegendGroups(
  data: Record<string, unknown[]>,
  groupBy: string,
): Record<string, LegendGroup> {
  const values = data[groupBy] as number[] | undefined;
  const defectIds = data.defect_id as number[] | undefined;

  const groups: Record<string, LegendGroup> = {};

  if (!values || !defectIds) return groups;

  for (let i = 0; i < values.length; i++) {
    const key = String(values[i] ?? "");
    if (!groups[key]) {
      groups[key] = { count: 0, defectIds: [] };
    }
    groups[key].count++;
    groups[key].defectIds.push(defectIds[i] ?? 0);
  }

  return groups;
}
