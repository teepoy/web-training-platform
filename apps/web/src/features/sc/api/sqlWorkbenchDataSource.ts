import { tableFromIPC, type Table } from "apache-arrow";
import { pointInPolygon } from "@platform/sc-map-element";
import { API_BASE, requestRaw, withAuthQueryParams } from "@/shared/api/client";
import type {
  ScAggregateDataQuery,
  ScArrowQueryResult,
  ScDataFilter,
  ScDataParameter,
  ScDataQueryContext,
  ScGalleryDataQuery,
  ScGalleryPage,
  ScInvalidation,
  ScMapDataQuery,
  ScReticleProjection,
  ScSelectionQuery,
  ScWorkbenchDataSource,
} from "@/features/sc/domain/workbenchDataSource";
import type {
  ScSampleTableDisplayRow,
  ScSampleTableDistinctValuesQuery,
  ScSampleTableRowsPage,
  ScSampleTableRowsQuery,
} from "@/features/sc/domain/workbenchInteraction";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";

export type ScSqlWorkbenchScope =
  | { kind: "inspection"; inspectionTime: string; waferKey: number }
  | { kind: "dataset"; datasetId: string };

const QUERY_TIMEOUT_MS = 35_000;
const SAMPLE_COLUMNS = [
  "defect_id",
  "rough_bin",
  "class_number",
  "images",
  "test_id",
  "wafer_x",
  "wafer_y",
  "index_x",
  "index_y",
  "adder",
  "cluster_id",
  "die_x",
  "die_y",
  "reticle_x",
  "reticle_y",
  "size_x",
  "size_y",
  "size_d",
  "area",
  "final_bin",
  "manual_bin",
  "kill_ratio",
  "annotation_label",
  "prediction_label",
  "prediction_confidence",
] as const;
const ALLOWED_COLUMNS = new Set([
  ...SAMPLE_COLUMNS,
  "sample_id",
  "inspection_time",
  "wafer_key",
  "review_image_ids_json",
  "final_class",
]);
interface CompiledWhere {
  sql: string;
  parameters: ScDataParameter[];
}

function quotedColumn(field: string): string {
  if (!ALLOWED_COLUMNS.has(field)) throw new Error(`Unsupported SC data field: ${field}`);
  return `"${field}"`;
}

function positiveModulo(column: "index_x" | "index_y", shift: number, count: number): string {
  return `((("${column}" + ${shift}) % ${count}) + ${count}) % ${count}`;
}

function reticleExpression(
  field: "reticle_x" | "reticle_y",
  projection: ScReticleProjection,
): string {
  const { options, dieSizeX, dieSizeY } = projection;
  if (
    !Number.isInteger(options.xDieCount) ||
    !Number.isInteger(options.yDieCount) ||
    options.xDieCount <= 0 ||
    options.yDieCount <= 0 ||
    !Number.isInteger(options.xDieShift) ||
    !Number.isInteger(options.yDieShift) ||
    !Number.isFinite(dieSizeX) ||
    !Number.isFinite(dieSizeY) ||
    dieSizeX <= 0 ||
    dieSizeY <= 0
  ) {
    throw new Error("Reticle projection requires positive dimensions and integer options");
  }
  return field === "reticle_x"
    ? `"die_x" + (${positiveModulo("index_x", options.xDieShift, options.xDieCount)} * ${dieSizeX})`
    : `"die_y" + (${positiveModulo("index_y", options.yDieShift, options.yDieCount)} * ${dieSizeY})`;
}

function selectColumn(field: string, reticle?: ScReticleProjection): string {
  if ((field === "reticle_x" || field === "reticle_y") && reticle) {
    return `${reticleExpression(field, reticle)} AS "${field}"`;
  }
  return quotedColumn(field);
}

function filterColumn(field: string, reticle?: ScReticleProjection): string {
  if ((field === "reticle_x" || field === "reticle_y") && reticle) {
    return `(${reticleExpression(field, reticle)})`;
  }
  return quotedColumn(field);
}

export function compileScWhere(
  filters: readonly ScDataFilter[],
  reticle?: ScReticleProjection,
): CompiledWhere {
  const predicates: string[] = [];
  const parameters: ScDataParameter[] = [];
  for (const [field, operator, value] of filters) {
    const column = filterColumn(field, reticle);
    if (operator === "is null") {
      predicates.push(`${column} IS NULL`);
      continue;
    }
    if (operator === "in") {
      if (!Array.isArray(value)) throw new Error(`IN filter for ${field} requires an array`);
      if (value.length === 0) {
        predicates.push("FALSE");
        continue;
      }
      predicates.push(`${column} = ANY(?)`);
      parameters.push(value as boolean[] | number[] | string[]);
      continue;
    }
    if (operator === "not in") {
      if (!Array.isArray(value)) throw new Error(`NOT IN filter for ${field} requires an array`);
      if (value.length === 0) continue;
      predicates.push(`NOT (${column} = ANY(?))`);
      parameters.push(value as boolean[] | number[] | string[]);
      continue;
    }
    if (operator === "contains") {
      predicates.push(`CONTAINS(CAST(${column} AS VARCHAR), ?)`);
      parameters.push(String(value));
      continue;
    }
    if (!["==", "!=", ">", ">=", "<", "<="].includes(operator)) {
      throw new Error(`Unsupported SC filter operator: ${operator}`);
    }
    const sqlOperator = operator === "==" ? "=" : operator === "!=" ? "<>" : operator;
    predicates.push(`${column} ${sqlOperator} ?`);
    parameters.push(value as ScDataParameter);
  }
  return {
    sql: predicates.length > 0 ? ` WHERE ${predicates.join(" AND ")}` : "",
    parameters,
  };
}

function filtersFromTableFilter(
  filter: ScSampleTableFilter | undefined,
  omitField?: string,
): ScDataFilter[] {
  const result: ScDataFilter[] = [];
  for (const [field, condition] of Object.entries(filter ?? {})) {
    if (field === omitField) continue;
    quotedColumn(field);
    if (condition.filterType === "set" && condition.values.length > 0) {
      result.push([field, "in", condition.values]);
    } else if (condition.filterType === "number" && condition.type === "inRange") {
      result.push([field, ">=", condition.filter], [field, "<=", condition.filterTo]);
    }
  }
  return result;
}

function orderBy(sort: ScSampleTableSort | null | undefined): string {
  const field = sort?.direction ? sort.field : "defect_id";
  const direction = sort?.direction === "desc" ? "DESC" : "ASC";
  return ` ORDER BY ${quotedColumn(field)} ${direction}`;
}

function rowRecord(table: Table, index: number): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of table.schema.fields)
    result[field.name] = table.getChild(field.name)?.get(index);
  return result;
}

function numeric(value: unknown): number {
  const result = Number(value);
  return Number.isFinite(result) ? result : 0;
}

function nullableString(value: unknown): string | null {
  return value == null || value === "" ? null : String(value);
}

function sampleRow(row: Record<string, unknown>): ScSampleTableDisplayRow {
  return {
    defect_id: String(row.defect_id ?? ""),
    rough_bin: numeric(row.rough_bin),
    class_number: numeric(row.class_number),
    images: numeric(row.images),
    test_id: numeric(row.test_id),
    wafer_x: numeric(row.wafer_x),
    wafer_y: numeric(row.wafer_y),
    index_x: numeric(row.index_x),
    index_y: numeric(row.index_y),
    adder: numeric(row.adder),
    cluster_id: row.cluster_id == null ? null : numeric(row.cluster_id),
    die_x: numeric(row.die_x),
    die_y: numeric(row.die_y),
    reticle_x: numeric(row.reticle_x),
    reticle_y: numeric(row.reticle_y),
    size_x: numeric(row.size_x),
    size_y: numeric(row.size_y),
    size_d: numeric(row.size_d),
    area: numeric(row.area),
    final_bin: numeric(row.final_bin),
    manual_bin: numeric(row.manual_bin),
    kill_ratio: row.kill_ratio == null ? null : numeric(row.kill_ratio),
    annotation_label: nullableString(row.annotation_label),
    prediction_label: nullableString(row.prediction_label),
    prediction_confidence:
      row.prediction_confidence == null ? null : numeric(row.prediction_confidence),
  };
}

export class SqlWorkbenchDataSource implements ScWorkbenchDataSource {
  readonly scopeKey: string;

  private readonly queryUrl: string;
  private readonly eventsUrl: string;
  private readonly listeners = new Set<(event: ScInvalidation) => void>();
  private eventSource: EventSource | null = null;
  private readonly inFlightQueries = new Set<AbortController>();
  private knownRevision = 0;
  private closed = false;

  constructor(scope: ScSqlWorkbenchScope) {
    const scopePath =
      scope.kind === "inspection"
        ? `inspections/${encodeURIComponent(scope.inspectionTime)}/${encodeURIComponent(scope.waferKey)}`
        : `datasets/${encodeURIComponent(scope.datasetId)}`;
    this.scopeKey =
      scope.kind === "inspection"
        ? `inspection:${scope.inspectionTime}/${scope.waferKey}`
        : `dataset:${scope.datasetId}`;
    this.queryUrl = `${API_BASE}/sc/data/${scopePath}/query`;
    this.eventsUrl = `${API_BASE}/sc/data/${scopePath}/events`;
  }

  async loadMap(query: ScMapDataQuery): Promise<Uint8Array> {
    const columns = [
      "defect_id",
      "wafer_x",
      "wafer_y",
      "die_x",
      "die_y",
      "reticle_x",
      "reticle_y",
      query.legendColumn,
      "images",
    ];
    const compiled = compileScWhere(query.filters ?? [], query.reticle);
    return (
      await this.query(
        "sc-workbench.map",
        `SELECT ${[...new Set(columns)].map((field) => selectColumn(field, query.reticle)).join(", ")} ` +
          `FROM samples${compiled.sql} ORDER BY "defect_id"`,
        compiled.parameters,
      )
    ).ipc;
  }

  async loadRows(
    query: ScSampleTableRowsQuery & ScDataQueryContext,
  ): Promise<ScSampleTableRowsPage> {
    const filters = [
      ...(query.filters ?? []),
      ...filtersFromTableFilter(query.filter),
      ...(query.defectIds.length > 0
        ? ([["defect_id", "in", query.defectIds.map(Number)]] as ScDataFilter[])
        : []),
    ];
    const compiled = compileScWhere(filters, query.reticle);
    const offset = Number.parseInt(query.anchor, 10) || 0;
    const reticle = query.reticleOptions
      ? {
          options: query.reticleOptions,
          dieSizeX: query.reticle?.dieSizeX ?? 1,
          dieSizeY: query.reticle?.dieSizeY ?? 1,
        }
      : query.reticle;
    const columns = SAMPLE_COLUMNS.map((field) => selectColumn(field, reticle));
    const result = await this.query(
      "sc-workbench.table.rows",
      `SELECT ${columns.join(", ")}, COUNT(*) OVER () AS "__total" FROM samples${compiled.sql}` +
        `${orderBy(query.sort)} LIMIT ? OFFSET ?`,
      [...compiled.parameters, query.limit, offset],
    );
    const total = result.table.numRows > 0 ? numeric(result.table.getChild("__total")?.get(0)) : 0;
    const items = Array.from({ length: result.table.numRows }, (_, index) =>
      sampleRow(rowRecord(result.table, index)),
    );
    return {
      items,
      total,
      nextAnchor: offset + items.length < total ? String(offset + items.length) : null,
    };
  }

  async loadGallery(query: ScGalleryDataQuery): Promise<ScGalleryPage> {
    const galleryColumns =
      query.mode === "review"
        ? [
            "sample_id",
            "defect_id",
            "review_image_ids_json",
            "annotation_label",
            "prediction_label",
            "prediction_confidence",
          ]
        : ["defect_id", "annotation_label", "prediction_label", "prediction_confidence"];
    const filters = [
      ...(query.filters ?? []),
      ...filtersFromTableFilter(query.tableFilter),
      ...(query.tableSelection?.kind === "ids" && query.tableSelection.ids.length > 0
        ? ([["defect_id", "in", [...query.tableSelection.ids]]] as ScDataFilter[])
        : []),
      ...(query.tableSelection?.kind === "all" && query.tableSelection.excludedIds.length > 0
        ? ([["defect_id", "not in", [...query.tableSelection.excludedIds]]] as ScDataFilter[])
        : []),
      ...(query.mode === "review" ? ([["images", ">", 0]] as ScDataFilter[]) : []),
    ];
    const compiled = compileScWhere(filters, query.reticle);
    const result = await this.query(
      `sc-workbench.gallery.${query.mode}`,
      `SELECT ${galleryColumns.map((field) => selectColumn(field, query.reticle)).join(", ")}, ` +
        `COUNT(*) OVER () AS "__total" FROM samples${compiled.sql}` +
        `${orderBy(query.tableSort)} LIMIT ? OFFSET ?`,
      [...compiled.parameters, query.limit, query.offset],
    );
    const total = result.table.numRows > 0 ? numeric(result.table.getChild("__total")?.get(0)) : 0;
    return {
      ipc: result.ipc,
      total,
      nextOffset:
        query.offset + result.table.numRows < total ? query.offset + result.table.numRows : null,
    };
  }

  async loadAggregates(query: ScAggregateDataQuery): Promise<Record<string, number>> {
    const compiled = compileScWhere(query.filters ?? [], query.reticle);
    const column = filterColumn(query.field, query.reticle);
    const result = await this.query(
      `sc-workbench.aggregate.${query.field}`,
      `SELECT ${column} AS "group_key", COUNT(*) AS "group_count" FROM samples${compiled.sql} ` +
        `GROUP BY ${column} ORDER BY ${column}`,
      compiled.parameters,
    );
    const groups: Record<string, number> = {};
    for (let index = 0; index < result.table.numRows; index += 1) {
      const key = result.table.getChild("group_key")?.get(index);
      groups[key == null || key === "" ? "__unlabeled__" : String(key)] = numeric(
        result.table.getChild("group_count")?.get(index),
      );
    }
    return groups;
  }

  async loadDistinctValues(
    query: ScSampleTableDistinctValuesQuery & ScDataQueryContext,
  ): Promise<Array<string | number>> {
    const filters = [
      ...(query.filters ?? []),
      ...filtersFromTableFilter(query.filter, query.field),
      ...(query.search.trim()
        ? ([[query.field, "contains", query.search.trim()]] as ScDataFilter[])
        : []),
    ];
    const compiled = compileScWhere(filters, query.reticle);
    const column = filterColumn(query.field, query.reticle);
    const result = await this.query(
      `sc-workbench.distinct.${query.field}`,
      `SELECT DISTINCT ${column} AS ${quotedColumn(query.field)} FROM samples${compiled.sql} ` +
        `ORDER BY ${column} LIMIT ?`,
      [...compiled.parameters, query.limit],
    );
    return Array.from({ length: result.table.numRows }, (_, index) => {
      const value = result.table.getChild(query.field)?.get(index);
      return typeof value === "bigint" ? Number(value) : value;
    }).filter(
      (value): value is string | number => typeof value === "string" || typeof value === "number",
    );
  }

  async resolveSelection(query: ScSelectionQuery): Promise<number[]> {
    const filters = [...(query.filters ?? [])];
    const constraint = query.constraint;
    if (constraint.kind === "ids") {
      if (constraint.ids.length === 0) return [];
      filters.push(["defect_id", "in", [...constraint.ids]]);
    }
    if (constraint.kind === "random") {
      if (!Number.isInteger(constraint.limit) || constraint.limit <= 0) {
        throw new Error("Random selection limit must be a positive integer");
      }
      const compiled = compileScWhere(filters, query.reticle);
      const result = await this.query(
        "sc-workbench.selection.random",
        `SELECT "defect_id" FROM samples${compiled.sql} ORDER BY RANDOM() LIMIT ?`,
        [...compiled.parameters, constraint.limit],
      );
      return Array.from({ length: result.table.numRows }, (_, index) =>
        numeric(result.table.getChild("defect_id")?.get(index)),
      );
    }
    if (constraint.kind === "legend") {
      filters.push([
        constraint.field,
        constraint.value == null ? "is null" : "==",
        constraint.value,
      ]);
    } else if (constraint.kind === "rectangle" || constraint.kind === "polygon") {
      const region = constraint.kind === "polygon" ? constraint.selection.region : constraint;
      filters.push(
        [`${constraint.mode}_x`, ">=", region.x],
        [`${constraint.mode}_x`, "<=", region.x + ("width" in region ? region.width : region.w)],
        [`${constraint.mode}_y`, ">=", region.y],
        [`${constraint.mode}_y`, "<=", region.y + ("height" in region ? region.height : region.h)],
      );
    }
    const compiled = compileScWhere(filters, query.reticle);
    const columns =
      constraint.kind === "polygon"
        ? `"defect_id", ${selectColumn(`${constraint.mode}_x`, query.reticle)}, ${selectColumn(`${constraint.mode}_y`, query.reticle)}`
        : '"defect_id"';
    const result = await this.query(
      `sc-workbench.selection.${constraint.kind}`,
      `SELECT ${columns} FROM samples${compiled.sql} ORDER BY "defect_id"`,
      compiled.parameters,
    );
    const ids: number[] = [];
    for (let index = 0; index < result.table.numRows; index += 1) {
      if (constraint.kind === "polygon") {
        const point = {
          x: numeric(result.table.getChild(`${constraint.mode}_x`)?.get(index)),
          y: numeric(result.table.getChild(`${constraint.mode}_y`)?.get(index)),
        };
        if (!pointInPolygon(point, constraint.selection.points)) continue;
      }
      ids.push(numeric(result.table.getChild("defect_id")?.get(index)));
    }
    return ids;
  }

  subscribeInvalidations(listener: (event: ScInvalidation) => void): () => void {
    if (this.closed) throw new Error("SC workbench data source is closed");
    this.listeners.add(listener);
    this.ensureEventSource();
    return () => this.listeners.delete(listener);
  }

  close(): void {
    this.closed = true;
    this.listeners.clear();
    this.eventSource?.close();
    this.eventSource = null;
    for (const controller of this.inFlightQueries) controller.abort();
    this.inFlightQueries.clear();
  }

  private async query(
    description: string,
    sql: string,
    parameters: ScDataParameter[],
  ): Promise<ScArrowQueryResult & { ipc: Uint8Array }> {
    if (this.closed) throw new Error("SC workbench data source is closed");
    const controller = new AbortController();
    this.inFlightQueries.add(controller);
    try {
      const response = await requestRaw(
        this.queryUrl,
        {
          method: "POST",
          body: JSON.stringify({ description, sql, parameters }),
          signal: controller.signal,
        },
        QUERY_TIMEOUT_MS,
      );
      const revision = Number(response.headers.get("X-SC-Data-Revision") ?? "0");
      const contentType = response.headers.get("Content-Type") ?? "";
      if (!contentType.includes("application/vnd.apache.arrow.stream")) {
        throw new Error(
          `SC data provider returned unsupported content type: ${contentType || "missing"}`,
        );
      }
      if (!Number.isSafeInteger(revision) || revision < 0) {
        throw new Error("SC data provider returned an invalid revision");
      }
      this.assertCurrentRevision(revision);
      const ipc = new Uint8Array(await response.arrayBuffer());
      this.assertCurrentRevision(revision);
      this.knownRevision = revision;
      return { ipc, table: tableFromIPC(ipc), revision };
    } finally {
      this.inFlightQueries.delete(controller);
    }
  }

  private assertCurrentRevision(revision: number): void {
    if (revision < this.knownRevision) {
      throw new Error(
        `Discarded stale SC data response revision ${revision}; current revision is ${this.knownRevision}`,
      );
    }
  }

  private ensureEventSource(): void {
    if (this.eventSource || this.closed) return;
    const source = new EventSource(withAuthQueryParams(this.eventsUrl));
    source.addEventListener("invalidation", (rawEvent) => {
      const event = rawEvent as MessageEvent<string>;
      let payload: { scope: string; revision: number; changed_kinds: string[] };
      try {
        payload = JSON.parse(event.data) as typeof payload;
      } catch {
        return;
      }
      if (payload.scope !== this.scopeKey) return;
      if (!Number.isSafeInteger(payload.revision) || payload.revision < this.knownRevision) return;
      this.knownRevision = payload.revision;
      const invalidation: ScInvalidation = {
        scope: payload.scope,
        revision: payload.revision,
        changedKinds: payload.changed_kinds,
      };
      for (const listener of this.listeners) listener(invalidation);
    });
    this.eventSource = source;
  }
}
