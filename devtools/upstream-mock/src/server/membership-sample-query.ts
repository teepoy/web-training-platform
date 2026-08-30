export const sampleProjectionColumns = [
  "wafer_key",
  "inspection_time",
  "defect_id",
  "test_id",
  "class_number",
  "rough_bin",
  "wafer_x",
  "wafer_y",
  "index_x",
  "index_y",
  "adder",
  "cluster",
  "images",
  "size_x",
  "size_y",
  "size_d",
  "area",
  "final_bin",
  "manual_bin",
  "kill_ratio",
  "lot_id",
  "wafer_id",
  "layer_id",
  "inspect_equip_id",
  "device",
  "origin_x",
  "origin_y",
  "die_size_x",
  "die_size_y",
  "recipe_id",
  "die_x",
  "die_y",
] as const;

const projectionExpressions: Record<string, string> = {
  wafer_key: "d.wafer_key AS wafer_key",
  inspection_time: "d.inspection_time AS inspection_time",
  defect_id: "d.defect_id AS defect_id",
  test_id: "d.test_id AS test_id",
  class_number: "d.class_number AS class_number",
  rough_bin: "d.rough_bin AS rough_bin",
  wafer_x: "d.wafer_x AS wafer_x",
  wafer_y: "d.wafer_y AS wafer_y",
  index_x: "d.index_x AS index_x",
  index_y: "d.index_y AS index_y",
  adder: "d.adder AS adder",
  cluster: "d.cluster AS cluster",
  images: "d.images AS images",
  size_x: "d.size_x AS size_x",
  size_y: "d.size_y AS size_y",
  size_d: "d.size_d AS size_d",
  area: "d.area AS area",
  final_bin: "d.final_bin AS final_bin",
  manual_bin: "d.manual_bin AS manual_bin",
  kill_ratio: "d.kill_ratio AS kill_ratio",
  lot_id: "i.lot_id AS lot_id",
  wafer_id: "i.wafer_id AS wafer_id",
  layer_id: "i.layer_id AS layer_id",
  inspect_equip_id: "i.inspect_equip_id AS inspect_equip_id",
  device: "i.device AS device",
  origin_x: "i.origin_x AS origin_x",
  origin_y: "i.origin_y AS origin_y",
  die_size_x: "i.die_size_x AS die_size_x",
  die_size_y: "i.die_size_y AS die_size_y",
  recipe_id: "i.recipe_id AS recipe_id",
  die_x: "((d.wafer_x - i.origin_x) % i.die_size_x) AS die_x",
  die_y: "((d.wafer_y - i.origin_y) % i.die_size_y) AS die_y",
};

export interface MembershipSampleQueryInput {
  inspectionTime: Date;
  waferKey: number;
  defectIds: number[];
  projection?: string[];
}

export interface MembershipSampleQuery {
  text: string;
  values: [number, Date, number[]];
}

export function buildMembershipSampleQuery(
  input: MembershipSampleQueryInput,
): MembershipSampleQuery {
  const projection = input.projection ?? [...sampleProjectionColumns];
  if (!projection.length) throw new TypeError("sample projection is required");
  const expressions = projection.map((column) => {
    const expression = projectionExpressions[column];
    if (!expression) throw new TypeError(`unsupported sample projection: ${column}`);
    return expression;
  });
  return {
    text: `SELECT ${expressions.join(", ")}
      FROM upstream_mock_defects d
      JOIN upstream_mock_inspections i
        ON d.wafer_key = i.wafer_key AND d.inspection_time = i.inspection_time
      JOIN unnest($3::bigint[]) WITH ORDINALITY requested(defect_id, ordinal)
        ON requested.defect_id = d.defect_id
      WHERE i.state = 'published'
        AND d.wafer_key = $1 AND d.inspection_time = $2
      ORDER BY requested.ordinal`,
    values: [input.waferKey, input.inspectionTime, input.defectIds],
  };
}
