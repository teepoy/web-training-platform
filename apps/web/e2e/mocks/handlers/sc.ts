import type { Page } from "@playwright/test";
import { create, toBinary } from "@bufbuild/protobuf";
import { tableFromArrays, tableToIPC } from "apache-arrow";
import { WaferMapResponseSchema } from "@/features/sc/generated/proto/sc/v1/sample_pb";

export interface ScInspectionOverrides {
  inspection_time?: string;
  wafer_key?: number;
  lot_id?: string;
  wafer_id?: string;
  center_x?: number;
  center_y?: number;
  origin_x?: number;
  origin_y?: number;
  die_size_x?: number;
  die_size_y?: number;
  layer_id?: string;
  eqp_id?: string;
  recipe_id?: string;
  defects?: number;
  images?: number;
  device?: string;
  total?: number;
  datasets?: Array<{ id: string; name: string }>;
}

export async function mockScInspections(
  page: Page,
  overrides?: ScInspectionOverrides,
): Promise<void> {
  const inspection = {
    inspection_time: overrides?.inspection_time ?? "2026-05-26T08:00:00",
    wafer_key: overrides?.wafer_key ?? 1,
    lot_id: overrides?.lot_id ?? "LOT-001",
    wafer_id: overrides?.wafer_id ?? "WAF-001",
    center_x: overrides?.center_x ?? 0,
    center_y: overrides?.center_y ?? 0,
    origin_x: overrides?.origin_x ?? -150000,
    origin_y: overrides?.origin_y ?? -150000,
    die_size_x: overrides?.die_size_x ?? 10000,
    die_size_y: overrides?.die_size_y ?? 10000,
    layer_id: overrides?.layer_id ?? "LAYER-M1",
    eqp_id: overrides?.eqp_id ?? "EQ-TOOL-A1",
    recipe_id: overrides?.recipe_id ?? "RECIPE-001",
    defects: overrides?.defects ?? 50,
    images: overrides?.images ?? 100,
    device: overrides?.device ?? "DEV-A001",
    datasets: overrides?.datasets ?? [],
  };

  await page.route("**/api/v1/sc/inspections*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [inspection],
        total: overrides?.total ?? 1,
      }),
    });
  });
}

export async function mockScInspectionSamples(page: Page): Promise<void> {
  await page.route("**/api/v1/sc/inspections/*/*/samples", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0 }),
    });
  });
}

export async function mockScInspectionImageProfile(page: Page): Promise<void> {
  await page.route("**/api/v1/sc/inspections/*/*/image-profile", async (route) => {
    const url = new URL(route.request().url());
    const segments = url.pathname.split("/");
    const inspectionTime = decodeURIComponent(segments.at(-3) ?? "2026-01-01T00:00:00Z");
    const waferKey = Number(segments.at(-2) ?? 1);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        inspection_time: inspectionTime,
        wafer_key: waferKey,
        reference_count: 1,
        difference_count: 1,
        mask_count: 0,
        patches: [
          { image_type: "Defective", image_id: null, bit_depth: 8, z_min: 0, z_max: 255 },
          { image_type: "Reference", image_id: 0, bit_depth: 8, z_min: 0, z_max: 255 },
          { image_type: "Difference", image_id: 0, bit_depth: 8, z_min: 0, z_max: 255 },
        ],
      }),
    });
  });
}

export interface ScDatasetOverrides {
  name?: string;
  label_space?: string[];
  task_spec?: Record<string, unknown>;
}

export async function mockScDataset(
  page: Page,
  datasetId: string,
  overrides?: ScDatasetOverrides,
): Promise<void> {
  const body = {
    id: datasetId,
    name: overrides?.name ?? "SC Wafer Dataset",
    dataset_type: "image_sc",
    storage_mode: "file_shard_sparse",
    view_types: ["image_input_v1", "patch_image_v1", "review_image_v1"],
    label_space: overrides?.label_space ?? ["Scratch", "Particle", "Pattern Defect"],
    task_spec: overrides?.task_spec ?? { task_type: "sc" },
    dataset_meta: {
      source_inspection_time: "2026-01-01T00:00:00",
      source_wafer_key: 1,
      geometry: {
        wafer_radius_nm: 150_000_000,
        center_x: 0,
        center_y: 0,
        origin_x: -150_000_000,
        origin_y: -150_000_000,
        die_size_x: 10_000_000,
        die_size_y: 10_000_000,
      },
    },
  };
  await page.route(`**/api/v1/datasets/${datasetId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  await mockScDataProvider(page, datasetId);
}

function mockScColumns(total: number): Record<string, Array<number | string | null>> {
  const defectIds = Array.from({ length: total }, (_, index) => index + 1);
  return {
    row_key: defectIds.map((id) => `row-${id}`),
    sample_id: defectIds.map((id) => `s-${id}`),
    defect_id: defectIds,
    rough_bin: defectIds.map((id) => id % 5),
    class_number: defectIds.map((id) => id % 3),
    images: defectIds.map(() => 0),
    test_id: defectIds.map((id) => id % 100),
    wafer_x: defectIds.map((id) => id * 1000),
    wafer_y: defectIds.map((id) => id * 2000),
    index_x: defectIds.map((id) => id % 37),
    index_y: defectIds.map((id) => id % 60),
    adder: defectIds.map(() => 0),
    cluster_id: defectIds.map((id) => String(id % 10)),
    repeater_id: defectIds.map((id) => String(id % 7)),
    die_x: defectIds.map((id) => id % 37),
    die_y: defectIds.map((id) => id % 60),
    reticle_x: defectIds.map((id) => id % 20),
    reticle_y: defectIds.map((id) => id % 30),
    size_x: defectIds.map(() => 100),
    size_y: defectIds.map(() => 100),
    size_d: defectIds.map(() => 141),
    area: defectIds.map(() => 10_000),
    final_bin: defectIds.map((id) => id % 256),
    manual_bin: defectIds.map((id) => id % 256),
    kill_ratio: defectIds.map((id) => (id % 100) / 100),
    annotation_label: defectIds.map(() => null),
    prediction_label: defectIds.map(() => null),
    prediction_confidence: defectIds.map(() => null),
    final_class: defectIds.map(() => null),
    review_image_ids_json: defectIds.map(() => "[]"),
  };
}

function selectedColumns(
  source: Record<string, Array<number | string | null>>,
  names: readonly string[],
): Record<string, Array<number | string | null>> {
  return Object.fromEntries(names.map((name) => [name, source[name] ?? []]));
}

export async function mockScDataProvider(
  page: Page,
  datasetId: string,
  total = 1000,
): Promise<void> {
  const rows = mockScColumns(total);
  await page.route("**/api/v1/sc/data/sample-table-descriptor", async (route) => {
    const columns = [
      ["defect_id", "Defect ID", 130, "set", "default", "integer"],
      ["row_key", "Sample ID", 260, "set", "default", "plain"],
      ["images", "Images", 110, "range", "default", "plain"],
      ["test_id", "Test ID", 120, "set", "default", "plain"],
      ["index_x", "Index X", 120, "range", "default", "plain"],
      ["index_y", "Index Y", 120, "range", "default", "plain"],
      ["wafer_x", "Wafer X", 120, "range", "default", "plain"],
      ["wafer_y", "Wafer Y", 120, "range", "default", "plain"],
      ["die_x", "Die X", 120, "range", "default", "plain"],
      ["die_y", "Die Y", 120, "range", "default", "plain"],
      ["size_x", "Size X", 120, "range", "default", "plain"],
      ["size_y", "Size Y", 120, "range", "default", "plain"],
      ["size_d", "Size D", 120, "range", "default", "plain"],
      ["area", "Area", 120, "range", "default", "plain"],
      ["class_number", "Class", 120, "set", "default", "plain"],
      ["rough_bin", "Rough Bin", 120, "set", "default", "plain"],
      ["final_bin", "Final Bin", 120, "set", "default", "plain"],
      ["manual_bin", "Manual Bin", 120, "set", "default", "plain"],
      ["adder", "Adder", 120, "set", "default", "plain"],
      ["cluster_id", "Cluster ID", 120, "set", "default", "plain"],
      ["repeater_id", "Repeater ID", 120, "set", "default", "plain"],
      ["kill_ratio", "Kill Ratio", 120, "range", "default", "fixed_3"],
      ["annotation_label", "Annotation", 140, "set", "reclassify", "plain"],
      ["prediction_label", "Prediction", 140, "set", "reclassify", "plain"],
      ["prediction_confidence", "Confidence", 130, "range", "reclassify", "fixed_3"],
      ["final_class", "Final Class", 120, "set", "filter_only", "plain"],
      ["sample_id", "Sample ID", 120, null, "internal", "plain"],
      ["review_image_ids_json", "Review Image IDs", 120, null, "internal", "plain"],
    ].map(([key, title, width, filter, visibility, format]) => ({
      key,
      title,
      width,
      filter,
      visibility,
      format,
    }));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ version: "sc.sample-table.v1", columns }),
    });
  });
  await page.route(`**/api/v1/sc/data/datasets/${datasetId}/events**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body:
        `event: invalidation\n` +
        `data: {"scope":"dataset:${datasetId}","revision":0,"changed_kinds":[]}\n\n`,
    });
  });
  await page.route(`**/api/v1/sc/data/datasets/${datasetId}/query`, async (route) => {
    const request = route.request().postDataJSON() as {
      description?: string;
      sql: string;
      parameters: unknown[];
      sampling?: {
        seed: number;
        program: {
          rules: Array<{
            type: string;
            count?: number;
          }>;
        };
      };
    };
    const sql = request.sql;
    let columns: Record<string, Array<number | string | null>>;
    if (request.description === "sc-workbench.selection.sampling-program") {
      const randomCount = request.sampling?.program.rules.find(
        (rule) => rule.type === "random_count",
      );
      if (randomCount?.count === undefined) {
        await route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Mock sampling requires random_count" }),
        });
        return;
      }
      const limit = randomCount.count;
      columns = { defect_id: (rows.defect_id ?? []).slice(0, limit) };
    } else if (sql.includes('AS "group_key"')) {
      columns = { group_key: [0, 1, 2], group_count: [334, 333, 333] };
    } else if (sql.startsWith("SELECT DISTINCT")) {
      const field = /SELECT DISTINCT "([a-z_]+)"/.exec(sql)?.[1] ?? "rough_bin";
      columns = { [field]: [0, 1, 2] };
    } else if (sql.includes("COUNT(*) OVER")) {
      const limit = Number(request.parameters.at(-2) ?? 200);
      const offset = Number(request.parameters.at(-1) ?? 0);
      const pageSize = Math.min(limit, Math.max(0, total - offset));
      const names = sql.includes('"rough_bin"')
        ? [
            "row_key",
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
          ]
        : sql.includes('"sample_id"')
          ? [
              "row_key",
              "sample_id",
              "defect_id",
              "review_image_ids_json",
              "annotation_label",
              "prediction_label",
              "prediction_confidence",
            ]
          : [
              "row_key",
              "defect_id",
              "annotation_label",
              "prediction_label",
              "prediction_confidence",
            ];
      columns = Object.fromEntries(
        Object.entries(selectedColumns(rows, names)).map(([name, values]) => [
          name,
          values.slice(offset, offset + pageSize),
        ]),
      );
      columns.__total = Array.from({ length: pageSize }, () => total);
    } else if (/^SELECT "defect_id" FROM samples/.test(sql)) {
      columns = { defect_id: rows.defect_id ?? [] };
    } else {
      columns = selectedColumns(rows, [
        "row_key",
        "defect_id",
        "wafer_x",
        "wafer_y",
        "die_x",
        "die_y",
        "reticle_x",
        "reticle_y",
        "class_number",
        "rough_bin",
        "annotation_label",
        "prediction_label",
        "final_class",
        "images",
      ]);
    }
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.apache.arrow.stream",
      headers: {
        "X-SC-Data-Revision": "0",
        "X-SC-Worker-PID": "100",
        "X-SC-Cache": "hit",
        "Server-Timing": "materialize;dur=1, duckdb;dur=1",
      },
      body: Buffer.from(tableToIPC(tableFromArrays(columns))),
    });
  });
}

export interface ScViewSampleRow {
  sample_id: string;
  inspection_time: string;
  wafer_key: number;
  defect_id: string | number;
  wafer_x: number;
  wafer_y: number;
  rough_bin: number;
  class_number: number;
  review_images?: Array<{ image_id: number }>;
  images?: Array<{
    role: string;
    image_id: string;
    image_type?: string;
    content_type?: string;
    url: string;
  }>;
}

export async function mockScViewSamples(
  page: Page,
  datasetId: string,
  viewType = "patch_image_v1",
  overrides?: { items?: ScViewSampleRow[]; total?: number },
): Promise<void> {
  const items: ScViewSampleRow[] = overrides?.items ?? [
    {
      sample_id: "sample-sc-1",
      inspection_time: "2026-05-26T08:00:00",
      wafer_key: 1,
      defect_id: "defect-001",
      wafer_x: 1000,
      wafer_y: 2000,
      rough_bin: 1,
      class_number: 3,
      review_images: [],
      images: [],
    },
    {
      sample_id: "sample-sc-2",
      inspection_time: "2026-05-26T08:00:00",
      wafer_key: 1,
      defect_id: "defect-002",
      wafer_x: 1500,
      wafer_y: 2500,
      rough_bin: 2,
      class_number: 5,
      review_images: [],
      images: [],
    },
  ];
  const body = { items, total: overrides?.total ?? items.length };
  await page.route(`**/api/v1/datasets/${datasetId}/views/${viewType}/samples**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

function makeFakePlotPointsBuffer(sampleCount: number): Buffer {
  const pts = Array.from({ length: sampleCount * 6 }, (_, i) => i % 100);
  const msg = create(WaferMapResponseSchema, {
    total: sampleCount,
    waferPoints: pts,
    diePoints: pts,
  });
  return Buffer.from(toBinary(WaferMapResponseSchema, msg));
}

export async function mockScPlotPoints(
  page: Page,
  datasetId: string,
  sampleCount = 1000,
): Promise<void> {
  const body = makeFakePlotPointsBuffer(sampleCount);
  await page.route(`**/api/v1/sc/datasets/${datasetId}/plot-points/stream**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [
        'event: progress\ndata: {"event_type":"progress","operation":"sc.plot-points","status":"loading","message":"Preparing plot points"}\n\n',
        'event: done\ndata: {"event_type":"done"}\n\n',
      ].join(""),
    });
  });
  await page.route(`**/api/v1/sc/datasets/${datasetId}/plot-points**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/x-protobuf",
      body,
    });
  });
}

export async function mockScDefectIds(page: Page, datasetId: string, total = 1000): Promise<void> {
  const body = Buffer.alloc(total * 4);
  for (let index = 0; index < total; index += 1) {
    body.writeInt32LE(index + 1, index * 4);
  }
  await page.route(`**/api/v1/sc/datasets/${datasetId}/defect-ids.bin**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      body,
    });
  });
}

export async function mockScViewSamplesPaged(
  page: Page,
  datasetId: string,
  viewType = "patch_image_v1",
  total = 1000,
  pageSize = 200,
): Promise<void> {
  await page.route(`**/api/v1/datasets/${datasetId}/views/${viewType}/samples**`, async (route) => {
    const url = new URL(route.request().url());
    const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
    const limit = parseInt(url.searchParams.get("limit") ?? String(pageSize), 10);
    const items = Array.from({ length: Math.min(limit, Math.max(0, total - offset)) }, (_, i) => ({
      sample_id: `s-${offset + i}`,
      inspection_time: "2026-01-01T00:00:00",
      wafer_key: 1,
      defect_id: String(offset + i + 1),
      wafer_x: (offset + i) * 100,
      wafer_y: (offset + i) * 200,
      die_x: (offset + i) % 10,
      die_y: (offset + i) % 8,
      rough_bin: (offset + i) % 5,
      class_number: (offset + i) % 3,
      review_images: [],
      images: [],
    }));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items, total }),
    });
  });
}

export async function mockScSamplesWithLabels(
  page: Page,
  datasetId: string,
  total = 1000,
  pageSize = 200,
): Promise<void> {
  await page.route(`**/api/v1/datasets/${datasetId}/samples-with-labels**`, async (route) => {
    const url = new URL(route.request().url());
    const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
    const limit = parseInt(url.searchParams.get("limit") ?? String(pageSize), 10);
    const items = Array.from({ length: Math.min(limit, Math.max(0, total - offset)) }, (_, i) => ({
      id: `s-${offset + i}`,
      latest_annotation: null,
    }));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items, total }),
    });
  });
}
