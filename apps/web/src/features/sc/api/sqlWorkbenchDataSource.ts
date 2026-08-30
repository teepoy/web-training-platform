import { tableFromIPC, type Table } from "apache-arrow";
import { pointInPolygon } from "@platform/sc-map-element";
import {
  API_BASE,
  isApiError,
  requestData,
  requestRaw,
  withAuthQueryParams,
} from "@/shared/api/client";
import type {
  ScAggregateDataQuery,
  ScArrowQueryResult,
  ScDataColumn,
  ScDataFilter,
  ScDataFilterExpression,
  ScDataParameter,
  ScDataQueryContext,
  ScGalleryDataQuery,
  ScGalleryPage,
  ScInvalidation,
  ScMapDataQuery,
  ScNumericRange,
  ScNumericRangeQuery,
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
import { buildScDataFilters } from "@/features/sc/application/workbenchDataFilter";
import {
  cloneScSamplingProgram,
  scSamplingProgramError,
  scSamplingRequiredFields,
  type ScSamplingProgram,
  type ScSamplingRule,
} from "@/features/sc/domain/samplingRules";
import {
  isScMissingFilterValue,
  scMissingFilterOption,
} from "@/features/sc/domain/missingFilterValue";

export type ScSqlWorkbenchScope =
  | { kind: "inspection"; inspectionTime: string; waferKey: number }
  | { kind: "dataset"; datasetId: string }
  | { kind: "collection"; collectionId: string; revisionId: string };

const QUERY_TIMEOUT_MS = 35_000;
const QUERY_MAX_ATTEMPTS = 2;
const QUERY_GZIP_MIN_BYTES = 4_096;
const SAMPLE_TABLE_DESCRIPTOR_VERSION = "sc.sample-table.v1";
const SAMPLE_TABLE_DESCRIPTOR_URL = `${API_BASE}/sc/data/sample-table-descriptor`;
const RETRYABLE_QUERY_STATUSES = new Set([408, 429, 500, 502, 503, 504]);
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
  "repeater_id",
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
const DEFAULT_ALLOWED_COLUMNS = new Set<string>([
  ...SAMPLE_COLUMNS,
  "row_key",
  "map_id",
  "sample_id",
  "source_dataset_id",
  "source_sample_id",
  "collection_member_id",
  "inspection_time",
  "wafer_key",
  "review_image_ids_json",
  "final_class",
]);
interface CompiledWhere {
  sql: string;
  parameters: ScDataParameter[];
}

async function encodeQueryBody(payload: object): Promise<{
  body: BodyInit;
  headers?: HeadersInit;
}> {
  const json = JSON.stringify(payload);
  if (new TextEncoder().encode(json).byteLength < QUERY_GZIP_MIN_BYTES) {
    return { body: json };
  }
  if (typeof CompressionStream === "undefined") {
    return { body: json };
  }
  const compressed = await new Response(
    new Blob([json], { type: "application/json" })
      .stream()
      .pipeThrough(new CompressionStream("gzip")),
  ).arrayBuffer();
  return {
    body: compressed,
    headers: { "Content-Encoding": "gzip" },
  };
}

interface ScSampleTableDescriptorResponse {
  version: string;
  columns: Array<{
    key: string;
    title: string;
    width: number;
    filter: "set" | "range" | null;
    visibility: "default" | "reclassify" | "filter_only" | "internal";
    format: "plain" | "integer" | "fixed_3";
  }>;
}

function sampleTableDescriptorByColumn(
  descriptor: ScSampleTableDescriptorResponse,
): Map<string, NonNullable<ScDataColumn["presentation"]>> {
  if (descriptor.version !== SAMPLE_TABLE_DESCRIPTOR_VERSION) {
    throw new Error(`Unsupported SC sample-table descriptor: ${descriptor.version}`);
  }
  const result = new Map<string, NonNullable<ScDataColumn["presentation"]>>();
  descriptor.columns.forEach((column, order) => {
    if (result.has(column.key)) {
      throw new Error(`SC sample-table descriptor contains duplicate column: ${column.key}`);
    }
    result.set(column.key, { ...column, order });
  });
  return result;
}

function isRetryableQueryError(error: unknown): boolean {
  if (!isApiError(error)) return false;
  if (error.kind === "network" || error.kind === "timeout") return true;
  return error.status !== null && RETRYABLE_QUERY_STATUSES.has(error.status);
}

function quotedColumn(
  field: string,
  allowedColumns: ReadonlySet<string> = DEFAULT_ALLOWED_COLUMNS,
): string {
  if (!allowedColumns.has(field)) throw new Error(`Unsupported SC data field: ${field}`);
  return `"${field.replace(/"/g, '""')}"`;
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

function selectColumn(
  field: string,
  reticle?: ScReticleProjection,
  allowedColumns: ReadonlySet<string> = DEFAULT_ALLOWED_COLUMNS,
): string {
  if ((field === "reticle_x" || field === "reticle_y") && reticle) {
    return `${reticleExpression(field, reticle)} AS "${field}"`;
  }
  return quotedColumn(field, allowedColumns);
}

function filterColumn(
  field: string,
  reticle?: ScReticleProjection,
  allowedColumns: ReadonlySet<string> = DEFAULT_ALLOWED_COLUMNS,
): string {
  if ((field === "reticle_x" || field === "reticle_y") && reticle) {
    return `(${reticleExpression(field, reticle)})`;
  }
  return quotedColumn(field, allowedColumns);
}

function scFilterFields(filters: readonly ScDataFilterExpression[]): string[] {
  return filters.flatMap((filter) =>
    Array.isArray(filter) ? [filter[0]] : scFilterFields(filter.items),
  );
}

export function compileScWhere(
  filters: readonly ScDataFilterExpression[],
  reticle?: ScReticleProjection,
  allowedColumns: ReadonlySet<string> = DEFAULT_ALLOWED_COLUMNS,
): CompiledWhere {
  const parameters: ScDataParameter[] = [];
  const predicates = filters
    .map((filter) => compileScFilterExpression(filter, parameters, reticle, allowedColumns))
    .filter((predicate): predicate is string => predicate !== null);
  return {
    sql: predicates.length > 0 ? ` WHERE ${predicates.join(" AND ")}` : "",
    parameters,
  };
}

function compileScFilterExpression(
  filter: ScDataFilterExpression,
  parameters: ScDataParameter[],
  reticle: ScReticleProjection | undefined,
  allowedColumns: ReadonlySet<string>,
): string | null {
  if (!Array.isArray(filter)) {
    const predicates = filter.items
      .map((item) => compileScFilterExpression(item, parameters, reticle, allowedColumns))
      .filter((predicate): predicate is string => predicate !== null);
    if (predicates.length === 0) return null;
    return `(${predicates.join(` ${filter.combinator.toUpperCase()} `)})`;
  }
  const [field, operator, value] = filter;
  const column = filterColumn(field, reticle, allowedColumns);
  if (operator === "is null") {
    return `${column} IS NULL`;
  }
  if (operator === "in") {
    if (!Array.isArray(value)) throw new Error(`IN filter for ${field} requires an array`);
    if (value.length === 0) return "FALSE";
    parameters.push(value as boolean[] | number[] | string[]);
    return `${column} = ANY(?)`;
  }
  if (operator === "in or null") {
    if (!Array.isArray(value)) throw new Error(`IN OR NULL filter for ${field} requires an array`);
    if (value.length === 0) return `${column} IS NULL`;
    parameters.push(value as boolean[] | number[] | string[]);
    return `(${column} = ANY(?) OR ${column} IS NULL)`;
  }
  if (operator === "not in") {
    if (!Array.isArray(value)) throw new Error(`NOT IN filter for ${field} requires an array`);
    if (value.length === 0) return null;
    parameters.push(value as boolean[] | number[] | string[]);
    return `NOT (${column} = ANY(?))`;
  }
  if (operator === "not in or null" || operator === "not in and not null") {
    if (!Array.isArray(value)) throw new Error(`NOT IN filter for ${field} requires an array`);
    const nullPredicate =
      operator === "not in or null" ? `${column} IS NULL` : `${column} IS NOT NULL`;
    if (value.length === 0) return nullPredicate;
    const join = operator === "not in or null" ? "OR" : "AND";
    parameters.push(value as boolean[] | number[] | string[]);
    return `(NOT (${column} = ANY(?)) ${join} ${nullPredicate})`;
  }
  if (operator === "contains") {
    parameters.push(String(value));
    return `CONTAINS(CAST(${column} AS VARCHAR), ?)`;
  }
  if (!["==", "!=", ">", ">=", "<", "<="].includes(operator)) {
    throw new Error(`Unsupported SC filter operator: ${operator}`);
  }
  const sqlOperator = operator === "==" ? "=" : operator === "!=" ? "<>" : operator;
  parameters.push(value as ScDataParameter);
  return `${column} ${sqlOperator} ?`;
}

interface CompiledSamplingSelection {
  sql: string;
  parameters: ScDataParameter[];
  sampling: {
    seed: number;
    program: { rules: ScSamplingRule[] };
  };
}

export function compileScSamplingSelection(
  filters: readonly ScDataFilterExpression[],
  program: ScSamplingProgram,
  seed: number,
  reticle?: ScReticleProjection,
  allowedColumns: ReadonlySet<string> = DEFAULT_ALLOWED_COLUMNS,
): CompiledSamplingSelection {
  const validationError = scSamplingProgramError(program);
  if (validationError) throw new Error(validationError);
  if (!Number.isSafeInteger(seed) || seed < 0) {
    throw new Error("Sampling seed must be a non-negative safe integer");
  }

  const compiledWhere = compileScWhere(filters, reticle, allowedColumns);
  const baseColumns = [...scSamplingRequiredFields(program)]
    .map((field) => quotedColumn(field, allowedColumns))
    .join(", ");
  const transportProgram = cloneScSamplingProgram(program);
  return {
    sql: `SELECT ${baseColumns} FROM samples${compiledWhere.sql}`,
    parameters: compiledWhere.parameters,
    sampling: {
      seed,
      program: {
        rules: transportProgram.rules,
      },
    },
  };
}

function filtersFromTableFilter(
  filter: ScSampleTableFilter | undefined,
  omitField?: string,
  allowedColumns: ReadonlySet<string> = DEFAULT_ALLOWED_COLUMNS,
): ScDataFilter[] {
  for (const field of Object.keys(filter ?? {})) {
    if (field === omitField) continue;
    quotedColumn(field, allowedColumns);
  }
  return buildScDataFilters(filter, { omitField });
}

function orderBy(
  sort: ScSampleTableSort | null | undefined,
  allowedColumns: ReadonlySet<string> = DEFAULT_ALLOWED_COLUMNS,
): string {
  const field = sort?.direction ? sort.field : "defect_id";
  const direction = sort?.direction === "desc" ? "DESC" : "ASC";
  return ` ORDER BY ${quotedColumn(field, allowedColumns)} ${direction}`;
}

function stableTableOrderBy(
  sort: ScSampleTableSort | null | undefined,
  allowedColumns: ReadonlySet<string>,
): string {
  const ordered = orderBy(sort, allowedColumns);
  if (sort?.field === "row_key") return ordered;
  return `${ordered}, ${quotedColumn("row_key", allowedColumns)} ASC`;
}

function rowIdentityColumn(columns: readonly ScDataColumn[]): "row_key" {
  const names = new Set(columns.map((column) => column.name));
  if (names.has("row_key")) return "row_key";
  throw new Error("SC workbench rows are missing the required physical row_key column");
}

function rowRecord(table: Table, index: number): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of table.schema.fields)
    result[field.name] = normalizeArrowValue(table.getChild(field.name)?.get(index));
  return result;
}

function normalizeArrowValue(value: unknown): unknown {
  if (typeof value !== "bigint") return value;
  const numeric = Number(value);
  return Number.isSafeInteger(numeric) ? numeric : value.toString();
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
    ...row,
    row_key: String(row.row_key ?? row.sample_id ?? row.defect_id ?? ""),
    sample_id: row.sample_id == null ? null : String(row.sample_id),
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
    repeater_id: row.repeater_id == null ? null : numeric(row.repeater_id),
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
  private columnsPromise: Promise<ScDataColumn[]> | null = null;
  private rowCountCache: { key: string; total: number } | null = null;
  private knownRevision = 0;
  private closed = false;

  constructor(scope: ScSqlWorkbenchScope) {
    const scopePath =
      scope.kind === "inspection"
        ? `inspections/${encodeURIComponent(scope.inspectionTime)}/${encodeURIComponent(scope.waferKey)}`
        : scope.kind === "collection"
          ? `collections/${encodeURIComponent(scope.collectionId)}/revisions/${encodeURIComponent(scope.revisionId)}`
          : `datasets/${encodeURIComponent(scope.datasetId)}`;
    this.scopeKey =
      scope.kind === "inspection"
        ? `inspection:${scope.inspectionTime}/${scope.waferKey}`
        : scope.kind === "collection"
          ? `collection:${scope.collectionId}/${scope.revisionId}`
          : `dataset:${scope.datasetId}`;
    this.queryUrl = `${API_BASE}/sc/data/${scopePath}/query`;
    this.eventsUrl = `${API_BASE}/sc/data/${scopePath}/events`;
  }

  loadColumns(): Promise<ScDataColumn[]> {
    if (this.columnsPromise) return this.columnsPromise;
    const request = Promise.all([
      this.query("sc-workbench.schema", "SELECT * FROM samples LIMIT 0", []),
      requestData<ScSampleTableDescriptorResponse>(SAMPLE_TABLE_DESCRIPTOR_URL),
    ]).then(([{ table }, descriptor]) => {
      const presentationByColumn = sampleTableDescriptorByColumn(descriptor);
      return table.schema.fields.map((field) => {
        const presentation = presentationByColumn.get(field.name);
        return {
          name: field.name,
          arrowType: field.type.toString(),
          nullable: field.nullable,
          ...(presentation ? { presentation } : {}),
        };
      });
    });
    this.columnsPromise = request.catch((error: unknown) => {
      this.columnsPromise = null;
      throw error;
    });
    return this.columnsPromise;
  }

  async loadMap(query: ScMapDataQuery): Promise<Uint8Array> {
    const columns = [
      "map_id",
      "wafer_x",
      "wafer_y",
      "die_x",
      "die_y",
      "reticle_x",
      "reticle_y",
      query.legendColumn,
      "images",
    ];
    const allowedColumns = await this.allowedColumnsFor([
      ...columns,
      ...scFilterFields(query.filters ?? []),
    ]);
    const compiled = compileScWhere(query.filters ?? [], query.reticle, allowedColumns);
    return (
      await this.query(
        "sc-workbench.map",
        `SELECT ${[...new Set(columns)]
          .map((field) => selectColumn(field, query.reticle, allowedColumns))
          .join(", ")} ` + `FROM samples${compiled.sql} ORDER BY "map_id"`,
        compiled.parameters,
      )
    ).ipc;
  }

  async loadRows(
    query: ScSampleTableRowsQuery & ScDataQueryContext,
  ): Promise<ScSampleTableRowsPage> {
    const sourceColumns = await this.loadColumns();
    const allowedColumns = this.allowedColumns(sourceColumns);
    const identityColumn = rowIdentityColumn(sourceColumns);
    const filters = [
      ...(query.filters ?? []),
      ...filtersFromTableFilter(query.filter, undefined, allowedColumns),
      ...(query.defectIds.length > 0
        ? ([[identityColumn, "in", query.defectIds]] as ScDataFilter[])
        : []),
    ];
    const compiled = compileScWhere(filters, query.reticle, allowedColumns);
    const offset = Number.parseInt(query.anchor, 10) || 0;
    const reticle = query.reticleOptions
      ? {
          options: query.reticleOptions,
          dieSizeX: query.reticle?.dieSizeX ?? 1,
          dieSizeY: query.reticle?.dieSizeY ?? 1,
        }
      : query.reticle;
    const columns = [
      ...sourceColumns.map((field) => selectColumn(field.name, reticle, allowedColumns)),
      ...(["reticle_x", "reticle_y"] as const)
        .filter((field) => !sourceColumns.some((column) => column.name === field))
        .map((field) => selectColumn(field, reticle, allowedColumns)),
    ];
    const stableOrder = stableTableOrderBy(query.sort, allowedColumns);
    const countKey = JSON.stringify([this.knownRevision, compiled.sql, compiled.parameters]);
    const totalRequest = this.loadRowCount(
      countKey,
      compiled.sql,
      compiled.parameters,
      query.signal,
    );
    const rowsRequest = this.query(
      "sc-workbench.table.rows",
      `WITH "__sc_page_ids" AS (` +
        `SELECT ${quotedColumn(identityColumn, allowedColumns)} FROM samples${compiled.sql}${stableOrder} LIMIT ? OFFSET ?` +
        `) SELECT ${columns.join(", ")} FROM samples ` +
        `INNER JOIN "__sc_page_ids" USING (${quotedColumn(identityColumn, allowedColumns)})${stableOrder}`,
      [...compiled.parameters, query.limit, offset],
      query.signal,
    );
    const [total, result] = await Promise.all([totalRequest, rowsRequest]);
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
    const sourceColumns = await this.loadColumns();
    const sourceColumnNames = new Set(sourceColumns.map((column) => column.name));
    const identityColumn = rowIdentityColumn(sourceColumns);
    const requestedGalleryColumns =
      query.mode === "review"
        ? [
            "row_key",
            "sample_id",
            "source_dataset_id",
            "source_sample_id",
            "inspection_time",
            "wafer_key",
            "defect_id",
            "review_image_ids_json",
            "annotation_label",
            "prediction_label",
            "prediction_confidence",
          ]
        : [
            "row_key",
            "sample_id",
            "source_dataset_id",
            "source_sample_id",
            "inspection_time",
            "wafer_key",
            "defect_id",
            "annotation_label",
            "prediction_label",
            "prediction_confidence",
          ];
    const galleryColumns = requestedGalleryColumns.filter((field) => sourceColumnNames.has(field));
    if (!galleryColumns.includes("defect_id")) {
      throw new Error("SC gallery rows are missing the required defect_id column");
    }
    const allowedColumns = this.allowedColumns(sourceColumns);
    for (const field of [
      ...galleryColumns,
      ...Object.keys(query.tableFilter ?? {}),
      ...scFilterFields(query.filters ?? []),
      ...(query.tableSort?.field ? [query.tableSort.field] : []),
    ]) {
      quotedColumn(field, allowedColumns);
    }
    const filters = [
      ...(query.filters ?? []),
      ...filtersFromTableFilter(query.tableFilter, undefined, allowedColumns),
      ...(query.tableSelection?.kind === "ids" && query.tableSelection.ids.length > 0
        ? ([[identityColumn, "in", [...query.tableSelection.ids]]] as ScDataFilter[])
        : []),
      ...(query.tableSelection?.kind === "all" && query.tableSelection.excludedIds.length > 0
        ? ([[identityColumn, "not in", [...query.tableSelection.excludedIds]]] as ScDataFilter[])
        : []),
    ];
    const compiled = compileScWhere(filters, query.reticle, allowedColumns);
    const result = await this.query(
      `sc-workbench.gallery.${query.mode}`,
      `SELECT ${galleryColumns
        .map((field) => selectColumn(field, query.reticle, allowedColumns))
        .join(", ")}, ` +
        `COUNT(*) OVER () AS "__total" FROM samples${compiled.sql}` +
        `${orderBy(query.tableSort, allowedColumns)} LIMIT ? OFFSET ?`,
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
    const allowedColumns = await this.allowedColumnsFor([
      query.field,
      ...scFilterFields(query.filters ?? []),
    ]);
    const compiled = compileScWhere(query.filters ?? [], query.reticle, allowedColumns);
    const column = filterColumn(query.field, query.reticle, allowedColumns);
    const result = await this.query(
      `sc-workbench.aggregate.${query.field}`,
      `SELECT ${column} AS "group_key", COUNT(*) AS "group_count" FROM samples${compiled.sql} ` +
        `GROUP BY ${column} ORDER BY ${column}`,
      compiled.parameters,
    );
    const groups: Record<string, number> = {};
    const missingOption = scMissingFilterOption(query.field);
    for (let index = 0; index < result.table.numRows; index += 1) {
      const key = result.table.getChild("group_key")?.get(index);
      groups[key == null || key === "" ? (missingOption?.value ?? "__unlabeled__") : String(key)] =
        numeric(result.table.getChild("group_count")?.get(index));
    }
    return groups;
  }

  async loadNumericRange(query: ScNumericRangeQuery): Promise<ScNumericRange | null> {
    const allowedColumns = await this.allowedColumnsFor([
      query.field,
      ...scFilterFields(query.filters ?? []),
    ]);
    const compiled = compileScWhere(query.filters ?? [], query.reticle, allowedColumns);
    const column = filterColumn(query.field, query.reticle, allowedColumns);
    const result = await this.query(
      `sc-workbench.range.${query.field}`,
      `SELECT MIN(${column}) AS "__min", MAX(${column}) AS "__max" FROM samples${compiled.sql}`,
      compiled.parameters,
    );
    if (result.table.numRows === 0) return null;
    const rawMin = result.table.getChild("__min")?.get(0);
    const rawMax = result.table.getChild("__max")?.get(0);
    if (rawMin == null || rawMax == null) return null;
    const min = Number(rawMin);
    const max = Number(rawMax);
    return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : null;
  }

  async loadDistinctValues(
    query: ScSampleTableDistinctValuesQuery & ScDataQueryContext,
  ): Promise<Array<string | number>> {
    const allowedColumns = await this.allowedColumnsFor([
      query.field,
      ...Object.keys(query.filter ?? {}),
      ...scFilterFields(query.filters ?? []),
    ]);
    const missingOption = scMissingFilterOption(query.field);
    const searchMatchesMissing =
      missingOption !== null &&
      missingOption.label.toLowerCase().includes(query.search.trim().toLowerCase());
    const filters = [
      ...(query.filters ?? []),
      ...filtersFromTableFilter(query.filter, query.field, allowedColumns),
      ...(query.search.trim() && !searchMatchesMissing
        ? ([[query.field, "contains", query.search.trim()]] as ScDataFilter[])
        : []),
    ];
    const compiled = compileScWhere(filters, query.reticle, allowedColumns);
    const column = filterColumn(query.field, query.reticle, allowedColumns);
    const result = await this.query(
      `sc-workbench.distinct.${query.field}`,
      `SELECT DISTINCT ${column} AS ${quotedColumn(query.field, allowedColumns)} FROM samples${compiled.sql} ` +
        `ORDER BY ${column} LIMIT ?`,
      [...compiled.parameters, query.limit],
    );
    return Array.from({ length: result.table.numRows }, (_, index) => {
      const value = result.table.getChild(query.field)?.get(index);
      if (value == null && missingOption) return missingOption.value;
      return typeof value === "bigint" ? Number(value) : value;
    }).filter(
      (value): value is string | number => typeof value === "string" || typeof value === "number",
    );
  }

  async resolveRowKeys(query: ScDataQueryContext): Promise<string[]> {
    const sourceColumns = await this.loadColumns();
    const allowedColumns = this.allowedColumns(sourceColumns);
    const identityColumn = rowIdentityColumn(sourceColumns);
    const compiled = compileScWhere(query.filters ?? [], query.reticle, allowedColumns);
    const identity = quotedColumn(identityColumn, allowedColumns);
    const result = await this.query(
      "sc-workbench.workflow-row-keys",
      `SELECT ${identity} FROM samples${compiled.sql} ORDER BY ${identity}`,
      compiled.parameters,
    );
    return Array.from({ length: result.table.numRows }, (_, index) =>
      String(result.table.getChild(identityColumn)?.get(index) ?? ""),
    ).filter((value) => value.length > 0);
  }

  async resolveSelection(query: ScSelectionQuery): Promise<number[]> {
    const filters = [...(query.filters ?? [])];
    const constraint = query.constraint;
    const allowedColumns = await this.allowedColumnsFor([
      ...scFilterFields(query.filters ?? []),
      ...(constraint.kind === "legend" ? [constraint.field] : []),
      ...(constraint.kind === "sampling-program"
        ? [...scSamplingRequiredFields(constraint.program)]
        : []),
    ]);
    if (constraint.kind === "ids") {
      if (constraint.ids.length === 0) return [];
      filters.push(["map_id", "in", [...constraint.ids]]);
    }
    if (constraint.kind === "random") {
      if (!Number.isInteger(constraint.limit) || constraint.limit <= 0) {
        throw new Error("Random selection limit must be a positive integer");
      }
      if (!Number.isSafeInteger(constraint.seed) || constraint.seed < 0) {
        throw new Error("Random selection seed must be a non-negative safe integer");
      }
      const compiled = compileScWhere(filters, query.reticle, allowedColumns);
      const result = await this.query(
        "sc-workbench.selection.random",
        `SELECT "map_id" FROM samples${compiled.sql} ORDER BY HASH("map_id", ?) LIMIT ?`,
        [...compiled.parameters, constraint.seed, constraint.limit],
      );
      return Array.from({ length: result.table.numRows }, (_, index) =>
        numeric(result.table.getChild("map_id")?.get(index)),
      );
    }
    if (constraint.kind === "sampling-program") {
      const compiled = compileScSamplingSelection(
        filters,
        constraint.program,
        constraint.seed,
        query.reticle,
        allowedColumns,
      );
      const result = await this.query(
        "sc-workbench.selection.sampling-program",
        compiled.sql,
        compiled.parameters,
        undefined,
        compiled.sampling,
      );
      return Array.from({ length: result.table.numRows }, (_, index) =>
        numeric(result.table.getChild("map_id")?.get(index)),
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
    const compiled = compileScWhere(filters, query.reticle, allowedColumns);
    const columns =
      constraint.kind === "polygon"
        ? `"map_id", ${selectColumn(`${constraint.mode}_x`, query.reticle, allowedColumns)}, ${selectColumn(`${constraint.mode}_y`, query.reticle, allowedColumns)}`
        : '"map_id"';
    const result = await this.query(
      `sc-workbench.selection.${constraint.kind}`,
      `SELECT ${columns} FROM samples${compiled.sql} ORDER BY "map_id"`,
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
      ids.push(numeric(result.table.getChild("map_id")?.get(index)));
    }
    return ids;
  }

  subscribeInvalidations(listener: (event: ScInvalidation) => void): () => void {
    if (this.closed) throw new Error("SC workbench data source is closed");
    this.listeners.add(listener);
    this.ensureEventSource();
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) {
        this.eventSource?.close();
        this.eventSource = null;
      }
    };
  }

  close(): void {
    this.closed = true;
    this.listeners.clear();
    this.rowCountCache = null;
    this.eventSource?.close();
    this.eventSource = null;
    for (const controller of this.inFlightQueries) controller.abort();
    this.inFlightQueries.clear();
  }

  private allowedColumns(columns: readonly ScDataColumn[]): Set<string> {
    return new Set([...DEFAULT_ALLOWED_COLUMNS, ...columns.map((column) => column.name)]);
  }

  private async allowedColumnsFor(fields: readonly string[]): Promise<ReadonlySet<string>> {
    if (fields.every((field) => DEFAULT_ALLOWED_COLUMNS.has(field))) {
      return DEFAULT_ALLOWED_COLUMNS;
    }
    return this.allowedColumns(await this.loadColumns());
  }

  private async query(
    description: string,
    sql: string,
    parameters: ScDataParameter[],
    signal?: AbortSignal,
    sampling?: CompiledSamplingSelection["sampling"],
  ): Promise<ScArrowQueryResult & { ipc: Uint8Array }> {
    if (this.closed) throw new Error("SC workbench data source is closed");
    const controller = new AbortController();
    const abortQuery = () => controller.abort(signal?.reason);
    if (signal?.aborted) abortQuery();
    else signal?.addEventListener("abort", abortQuery, { once: true });
    this.inFlightQueries.add(controller);
    try {
      for (let attempt = 1; attempt <= QUERY_MAX_ATTEMPTS; attempt += 1) {
        try {
          const encoded = await encodeQueryBody({
            description,
            sql,
            parameters,
            ...(sampling ? { sampling } : {}),
          });
          const response = await requestRaw(
            this.queryUrl,
            {
              method: "POST",
              ...encoded,
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
          this.observeRevision(revision);
          return { ipc, table: tableFromIPC(ipc), revision };
        } catch (error) {
          if (attempt >= QUERY_MAX_ATTEMPTS || this.closed || !isRetryableQueryError(error)) {
            throw error;
          }
          console.warn("[sc-data-provider] transient query failed; retrying once", {
            description,
            error,
          });
        }
      }
      throw new Error(`SC data query exhausted its retry attempts: ${description}`);
    } finally {
      signal?.removeEventListener("abort", abortQuery);
      this.inFlightQueries.delete(controller);
    }
  }

  private async loadRowCount(
    key: string,
    whereSql: string,
    parameters: ScDataParameter[],
    signal?: AbortSignal,
  ): Promise<number> {
    if (this.rowCountCache?.key === key) return this.rowCountCache.total;
    const result = await this.query(
      "sc-workbench.table.count",
      `SELECT COUNT(*) AS "__total" FROM samples${whereSql}`,
      parameters,
      signal,
    );
    const total = result.table.numRows > 0 ? numeric(result.table.getChild("__total")?.get(0)) : 0;
    const currentKey = JSON.stringify([this.knownRevision, whereSql, parameters]);
    this.rowCountCache = { key: currentKey, total };
    return total;
  }

  private observeRevision(revision: number): void {
    if (revision > this.knownRevision) this.rowCountCache = null;
    this.knownRevision = revision;
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
      const previousRevision = this.knownRevision;
      this.observeRevision(payload.revision);
      if (payload.changed_kinds.length === 0 && payload.revision === previousRevision) return;
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
