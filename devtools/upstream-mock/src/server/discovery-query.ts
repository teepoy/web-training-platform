export type InspectionDiscoveryFilters = {
  order: "primary_key" | "publication";
  pageSize: number;
  startTime?: Date;
  endTime?: Date;
  publishedFrom?: Date;
  publishedUntil?: Date;
  afterInspectionTime?: Date;
  afterWaferKey?: number;
  afterPublishedAt?: Date;
};

export function buildInspectionDiscoveryQuery(filters: InspectionDiscoveryFilters): {
  text: string;
  values: unknown[];
} {
  const values: unknown[] = [];
  const parameter = (value: unknown): string => {
    values.push(value);
    return `$${values.length}`;
  };
  const predicates = ["i.state = 'published'"];
  let orderBy: string;
  if (filters.order === "primary_key") {
    if (!filters.startTime || !filters.endTime) {
      throw new TypeError("start_time and end_time are required for primary-key discovery");
    }
    predicates.push(`i.inspection_time >= ${parameter(filters.startTime)}`);
    predicates.push(`i.inspection_time < ${parameter(filters.endTime)}`);
    if (filters.afterInspectionTime) {
      if (filters.afterWaferKey === undefined) {
        throw new TypeError("after_wafer_key is required with after_inspection_time");
      }
      predicates.push(
        `(i.inspection_time, i.wafer_key) > (${parameter(filters.afterInspectionTime)}, ${parameter(filters.afterWaferKey)})`,
      );
    }
    orderBy = "i.inspection_time, i.wafer_key";
  } else {
    if (!filters.publishedFrom || !filters.publishedUntil) {
      throw new TypeError(
        "published_from and published_until are required for publication discovery",
      );
    }
    predicates.push(`i.published_at >= ${parameter(filters.publishedFrom)}`);
    predicates.push(`i.published_at < ${parameter(filters.publishedUntil)}`);
    if (filters.afterPublishedAt) {
      if (filters.afterWaferKey === undefined || !filters.afterInspectionTime) {
        throw new TypeError(
          "after_published_at requires after_inspection_time and after_wafer_key",
        );
      }
      predicates.push(
        `(i.published_at, i.inspection_time, i.wafer_key) > (${parameter(filters.afterPublishedAt)}, ${parameter(filters.afterInspectionTime)}, ${parameter(filters.afterWaferKey)})`,
      );
    }
    orderBy = "i.published_at, i.inspection_time, i.wafer_key";
  }
  const limit = parameter(filters.pageSize);
  return {
    text: `SELECT i.*,
              (SELECT count(*)::int FROM upstream_mock_defects d
               WHERE d.wafer_key = i.wafer_key AND d.inspection_time = i.inspection_time) AS defects,
              (SELECT count(*)::int FROM upstream_mock_review_images r
               WHERE r.wafer_key = i.wafer_key AND r.inspection_time = i.inspection_time) AS images
       FROM upstream_mock_inspections i
       WHERE ${predicates.join(" AND ")}
       ORDER BY ${orderBy}
       LIMIT ${limit}`,
    values,
  };
}
