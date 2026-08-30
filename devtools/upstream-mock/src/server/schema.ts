import {
  bigint,
  check,
  doublePrecision,
  foreignKey,
  index,
  integer,
  pgTable,
  primaryKey,
  smallint,
  timestamp,
  unique,
  varchar,
} from "drizzle-orm/pg-core";
import { sql } from "drizzle-orm";

export const upstreamMockClock = pgTable(
  "upstream_mock_clock",
  {
    id: smallint("id").primaryKey(),
    nextChangeToken: bigint("next_change_token", { mode: "number" }).notNull(),
  },
  (table) => [
    check("ck_upstream_mock_clock_singleton", sql`${table.id} = 1`),
    check("ck_upstream_mock_clock_positive_token", sql`${table.nextChangeToken} > 0`),
  ],
);

export const inspections = pgTable(
  "upstream_mock_inspections",
  {
    waferKey: bigint("wafer_key", { mode: "number" }).notNull(),
    inspectionTime: timestamp("inspection_time", {
      withTimezone: true,
      mode: "date",
    }).notNull(),
    lotId: varchar("lot_id", { length: 50 }).notNull(),
    waferId: varchar("wafer_id", { length: 50 }).notNull(),
    layerId: varchar("layer_id", { length: 50 }).notNull(),
    device: varchar("device", { length: 50 }).notNull(),
    inspectEquipId: varchar("inspect_equip_id", { length: 50 }).notNull(),
    recipeKey: bigint("recipe_key", { mode: "number" }).notNull(),
    recipeId: varchar("recipe_id", { length: 50 }).notNull(),
    originIndexX: integer("origin_index_x").notNull(),
    originIndexY: integer("origin_index_y").notNull(),
    centerX: integer("center_x").notNull(),
    centerY: integer("center_y").notNull(),
    originX: integer("origin_x").notNull(),
    originY: integer("origin_y").notNull(),
    dieSizeX: integer("die_size_x").notNull(),
    dieSizeY: integer("die_size_y").notNull(),
    state: varchar("state", { length: 16 }).$type<"draft" | "published">().notNull(),
    publishedAt: timestamp("published_at", { withTimezone: true, mode: "date" }),
    lastUpdatedAt: timestamp("last_updated_at", {
      withTimezone: true,
      mode: "date",
    }),
    changeToken: bigint("change_token", { mode: "number" }),
  },
  (table) => [
    primaryKey({ columns: [table.waferKey, table.inspectionTime] }),
    unique("uq_upstream_mock_inspection_change_token").on(table.changeToken),
    index("ix_upstream_mock_inspections_published_time").on(table.state, table.inspectionTime),
    check("ck_upstream_mock_inspection_state", sql`${table.state} IN ('draft', 'published')`),
    check(
      "ck_upstream_mock_inspection_publication_fields",
      sql`(${table.state} = 'draft' AND ${table.publishedAt} IS NULL AND ${table.lastUpdatedAt} IS NULL AND ${table.changeToken} IS NULL) OR (${table.state} = 'published' AND ${table.publishedAt} IS NOT NULL AND ${table.lastUpdatedAt} IS NOT NULL AND ${table.changeToken} IS NOT NULL)`,
    ),
  ],
);

export const defects = pgTable(
  "upstream_mock_defects",
  {
    waferKey: bigint("wafer_key", { mode: "number" }).notNull(),
    inspectionTime: timestamp("inspection_time", {
      withTimezone: true,
      mode: "date",
    }).notNull(),
    defectId: bigint("defect_id", { mode: "number" }).notNull(),
    testId: integer("test_id").notNull(),
    classNumber: integer("class_number").notNull(),
    roughBin: integer("rough_bin").notNull(),
    waferX: integer("wafer_x").notNull(),
    waferY: integer("wafer_y").notNull(),
    indexX: integer("index_x").notNull(),
    indexY: integer("index_y").notNull(),
    adder: integer("adder").notNull(),
    cluster: integer("cluster").notNull(),
    images: integer("images").notNull(),
    sizeX: integer("size_x").notNull(),
    sizeY: integer("size_y").notNull(),
    sizeD: integer("size_d").notNull(),
    area: integer("area").notNull(),
    finalBin: integer("final_bin").notNull(),
    manualBin: integer("manual_bin").notNull(),
    killRatio: doublePrecision("kill_ratio").notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.waferKey, table.inspectionTime, table.defectId] }),
    foreignKey({
      columns: [table.waferKey, table.inspectionTime],
      foreignColumns: [inspections.waferKey, inspections.inspectionTime],
    }).onDelete("cascade"),
  ],
);

export const reviewImages = pgTable(
  "upstream_mock_review_images",
  {
    waferKey: bigint("wafer_key", { mode: "number" }).notNull(),
    inspectionTime: timestamp("inspection_time", {
      withTimezone: true,
      mode: "date",
    }).notNull(),
    defectId: bigint("defect_id", { mode: "number" }).notNull(),
    imageId: bigint("image_id", { mode: "number" }).notNull(),
    imageType: varchar("image_type", { length: 50 }).notNull(),
    imageFilespec: varchar("image_filespec", { length: 1024 }).notNull(),
  },
  (table) => [
    primaryKey({
      columns: [table.waferKey, table.inspectionTime, table.defectId, table.imageId],
    }),
    foreignKey({
      columns: [table.waferKey, table.inspectionTime],
      foreignColumns: [inspections.waferKey, inspections.inspectionTime],
    }).onDelete("cascade"),
  ],
);

export const patchArchives = pgTable(
  "upstream_mock_patch_archives",
  {
    waferKey: bigint("wafer_key", { mode: "number" }).notNull(),
    inspectionTime: timestamp("inspection_time", {
      withTimezone: true,
      mode: "date",
    }).notNull(),
    archiveId: bigint("archive_id", { mode: "number" }).notNull(),
    s3Bucket: varchar("s3_bucket", { length: 255 }).notNull(),
    s3Key: varchar("s3_key", { length: 512 }).notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.waferKey, table.inspectionTime, table.archiveId] }),
    unique("uq_upstream_mock_patch_archive_object").on(
      table.waferKey,
      table.inspectionTime,
      table.s3Bucket,
      table.s3Key,
    ),
    foreignKey({
      columns: [table.waferKey, table.inspectionTime],
      foreignColumns: [inspections.waferKey, inspections.inspectionTime],
    }).onDelete("cascade"),
  ],
);
