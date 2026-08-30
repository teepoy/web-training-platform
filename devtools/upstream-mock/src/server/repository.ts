import "server-only";

import { and, desc, eq, sql } from "drizzle-orm";

import {
  type AppendRecordsInput,
  type CreateInspectionInput,
  type InspectionKey,
  type InspectionResponse,
  type UpdateInspectionInput,
} from "./contracts";
import { db, pool } from "./db";
import {
  UpstreamMockConflictError,
  UpstreamMockNotFoundError,
  UpstreamMockUnavailableError,
  isUniqueViolation,
} from "./errors";
import { defects, inspections, patchArchives, reviewImages, upstreamMockClock } from "./schema";

type Transaction = Parameters<Parameters<typeof db.transaction>[0]>[0];
type InspectionRow = typeof inspections.$inferSelect;

function keyPredicate(key: InspectionKey) {
  return and(
    eq(inspections.waferKey, key.wafer_key),
    eq(inspections.inspectionTime, key.inspection_time),
  );
}

function toResponse(row: InspectionRow): InspectionResponse {
  return {
    wafer_key: row.waferKey,
    inspection_time: row.inspectionTime.toISOString(),
    lot_id: row.lotId,
    wafer_id: row.waferId,
    layer_id: row.layerId,
    device: row.device,
    inspect_equip_id: row.inspectEquipId,
    recipe_key: row.recipeKey,
    recipe_id: row.recipeId,
    origin_index_x: row.originIndexX,
    origin_index_y: row.originIndexY,
    center_x: row.centerX,
    center_y: row.centerY,
    origin_x: row.originX,
    origin_y: row.originY,
    die_size_x: row.dieSizeX,
    die_size_y: row.dieSizeY,
    state: row.state,
    published_at: row.publishedAt?.toISOString() ?? null,
    last_updated_at: row.lastUpdatedAt?.toISOString() ?? null,
    change_token: row.changeToken,
  };
}

function defectRows(key: InspectionKey, body: AppendRecordsInput | CreateInspectionInput) {
  return body.defects.map((item) => ({
    waferKey: key.wafer_key,
    inspectionTime: key.inspection_time,
    defectId: item.defect_id,
    testId: item.test_id,
    classNumber: item.class_number,
    roughBin: item.rough_bin,
    waferX: item.wafer_x,
    waferY: item.wafer_y,
    indexX: item.index_x,
    indexY: item.index_y,
    adder: item.adder,
    cluster: item.cluster,
    images: item.images,
    sizeX: item.size_x,
    sizeY: item.size_y,
    sizeD: item.size_d,
    area: item.area,
    finalBin: item.final_bin,
    manualBin: item.manual_bin,
    killRatio: item.kill_ratio,
  }));
}

function reviewRows(key: InspectionKey, body: AppendRecordsInput | CreateInspectionInput) {
  return body.review_images.map((item) => ({
    waferKey: key.wafer_key,
    inspectionTime: key.inspection_time,
    defectId: item.defect_id,
    imageId: item.image_id,
    imageType: item.image_type,
    imageFilespec: item.image_filespec,
  }));
}

function archiveRows(key: InspectionKey, body: AppendRecordsInput | CreateInspectionInput) {
  return body.patch_archives.map((item) => ({
    waferKey: key.wafer_key,
    inspectionTime: key.inspection_time,
    archiveId: item.archive_id,
    s3Bucket: item.s3_bucket,
    s3Key: item.s3_key,
  }));
}

async function insertChildren(
  tx: Transaction,
  key: InspectionKey,
  body: AppendRecordsInput | CreateInspectionInput,
): Promise<void> {
  const defectValues = defectRows(key, body);
  if (defectValues.length) await tx.insert(defects).values(defectValues);
  const reviewValues = reviewRows(key, body);
  if (reviewValues.length) await tx.insert(reviewImages).values(reviewValues);
  const archiveValues = archiveRows(key, body);
  if (archiveValues.length) await tx.insert(patchArchives).values(archiveValues);
}

async function lockedInspection(tx: Transaction, key: InspectionKey): Promise<InspectionRow> {
  const rows = await tx.select().from(inspections).where(keyPredicate(key)).for("update").limit(1);
  if (!rows[0]) throw new UpstreamMockNotFoundError();
  return rows[0];
}

async function nextChangeToken(tx: Transaction): Promise<number> {
  const result = await tx.execute<{ change_token: string | number }>(sql`
    UPDATE upstream_mock_clock
    SET next_change_token = next_change_token + 1
    WHERE id = 1
    RETURNING next_change_token - 1 AS change_token
  `);
  const token = result.rows[0]?.change_token;
  if (token === undefined) {
    throw new UpstreamMockUnavailableError(
      "upstream mock clock is missing; apply the database migrations",
    );
  }
  return Number(token);
}

export const upstreamMockRepository = {
  async ready(): Promise<void> {
    const rows = await db
      .select({ id: upstreamMockClock.id })
      .from(upstreamMockClock)
      .where(eq(upstreamMockClock.id, 1))
      .limit(1);
    if (!rows[0]) {
      throw new UpstreamMockUnavailableError(
        "upstream mock clock is missing; apply the database migrations",
      );
    }
  },

  async createDraft(body: CreateInspectionInput): Promise<InspectionResponse> {
    const key = {
      wafer_key: body.wafer_key,
      inspection_time: body.inspection_time,
    };
    try {
      await db.transaction(async (tx) => {
        await tx.insert(inspections).values({
          waferKey: body.wafer_key,
          inspectionTime: body.inspection_time,
          lotId: body.lot_id,
          waferId: body.wafer_id,
          layerId: body.layer_id,
          device: body.device,
          inspectEquipId: body.inspect_equip_id,
          recipeKey: body.recipe_key,
          recipeId: body.recipe_id,
          originIndexX: body.origin_index_x,
          originIndexY: body.origin_index_y,
          centerX: body.center_x,
          centerY: body.center_y,
          originX: body.origin_x,
          originY: body.origin_y,
          dieSizeX: body.die_size_x,
          dieSizeY: body.die_size_y,
          state: "draft",
          publishedAt: null,
          lastUpdatedAt: null,
          changeToken: null,
        });
        await insertChildren(tx, key, body);
      });
    } catch (error) {
      if (isUniqueViolation(error)) {
        throw new UpstreamMockConflictError(
          "inspection or one of its child records already exists",
        );
      }
      throw error;
    }
    return this.getInspection(key);
  },

  async appendRecords(body: AppendRecordsInput): Promise<void> {
    const key = {
      wafer_key: body.wafer_key,
      inspection_time: body.inspection_time,
    };
    try {
      await db.transaction(async (tx) => {
        const inspection = await lockedInspection(tx, key);
        if (inspection.state !== "draft") {
          throw new UpstreamMockConflictError(
            "child records can only be appended to a draft inspection",
          );
        }
        await insertChildren(tx, key, body);
      });
    } catch (error) {
      if (isUniqueViolation(error)) {
        throw new UpstreamMockConflictError("one of the child records already exists");
      }
      throw error;
    }
  },

  async publish(key: InspectionKey, publishedAt: Date): Promise<Record<string, string | number>> {
    if (publishedAt < key.inspection_time) {
      throw new TypeError("published_at must not precede inspection_time");
    }
    return db.transaction(async (tx) => {
      const inspection = await lockedInspection(tx, key);
      if (inspection.state !== "draft") {
        throw new UpstreamMockConflictError("only a draft inspection can be published");
      }
      const changeToken = await nextChangeToken(tx);
      await tx
        .update(inspections)
        .set({
          state: "published",
          publishedAt,
          lastUpdatedAt: publishedAt,
          changeToken,
        })
        .where(keyPredicate(key));
      return {
        wafer_key: key.wafer_key,
        inspection_time: key.inspection_time.toISOString(),
        published_at: publishedAt.toISOString(),
        last_updated_at: publishedAt.toISOString(),
        change_token: changeToken,
      };
    });
  },

  async updatePublished(body: UpdateInspectionInput) {
    const key = {
      wafer_key: body.wafer_key,
      inspection_time: body.inspection_time,
    };
    return db.transaction(async (tx) => {
      const inspection = await lockedInspection(tx, key);
      if (inspection.state !== "published" || !inspection.lastUpdatedAt) {
        throw new UpstreamMockConflictError(
          "only a published inspection can receive source updates",
        );
      }
      if (body.changed_at <= inspection.lastUpdatedAt) {
        throw new UpstreamMockConflictError(
          "changed_at must be later than the current last_updated_at",
        );
      }
      const changeToken = await nextChangeToken(tx);
      const updates: Partial<typeof inspections.$inferInsert> = {
        lastUpdatedAt: body.changed_at,
        changeToken,
      };
      const mapping = {
        lot_id: "lotId",
        wafer_id: "waferId",
        layer_id: "layerId",
        device: "device",
        inspect_equip_id: "inspectEquipId",
        recipe_key: "recipeKey",
        recipe_id: "recipeId",
        origin_index_x: "originIndexX",
        origin_index_y: "originIndexY",
        center_x: "centerX",
        center_y: "centerY",
        origin_x: "originX",
        origin_y: "originY",
        die_size_x: "dieSizeX",
        die_size_y: "dieSizeY",
      } as const;
      for (const [source, target] of Object.entries(mapping)) {
        const value = body[source as keyof typeof body];
        if (value !== undefined) {
          Object.assign(updates, { [target]: value });
        }
      }
      await tx.update(inspections).set(updates).where(keyPredicate(key));
      if (!inspection.publishedAt) {
        throw new UpstreamMockConflictError("published inspection is missing published_at");
      }
      return {
        wafer_key: key.wafer_key,
        inspection_time: key.inspection_time.toISOString(),
        published_at: inspection.publishedAt.toISOString(),
        last_updated_at: body.changed_at.toISOString(),
        change_token: changeToken,
      };
    });
  },

  async getInspection(key: InspectionKey): Promise<InspectionResponse> {
    const rows = await db.select().from(inspections).where(keyPredicate(key)).limit(1);
    if (!rows[0]) throw new UpstreamMockNotFoundError();
    return toResponse(rows[0]);
  },

  async listInspections(state?: "draft" | "published"): Promise<InspectionResponse[]> {
    const rows = state
      ? await db
          .select()
          .from(inspections)
          .where(eq(inspections.state, state))
          .orderBy(desc(inspections.inspectionTime), desc(inspections.waferKey))
      : await db
          .select()
          .from(inspections)
          .orderBy(desc(inspections.inspectionTime), desc(inspections.waferKey));
    return rows.map(toResponse);
  },

  async childCounts(key: InspectionKey) {
    await this.getInspection(key);
    const [defectCount, imageCount, archiveCount] = await Promise.all([
      db
        .select({ count: sql<number>`count(*)::int` })
        .from(defects)
        .where(
          and(eq(defects.waferKey, key.wafer_key), eq(defects.inspectionTime, key.inspection_time)),
        ),
      db
        .select({ count: sql<number>`count(*)::int` })
        .from(reviewImages)
        .where(
          and(
            eq(reviewImages.waferKey, key.wafer_key),
            eq(reviewImages.inspectionTime, key.inspection_time),
          ),
        ),
      db
        .select({ count: sql<number>`count(*)::int` })
        .from(patchArchives)
        .where(
          and(
            eq(patchArchives.waferKey, key.wafer_key),
            eq(patchArchives.inspectionTime, key.inspection_time),
          ),
        ),
    ]);
    return {
      defects: defectCount[0]?.count ?? 0,
      review_images: imageCount[0]?.count ?? 0,
      patch_archives: archiveCount[0]?.count ?? 0,
    };
  },

  async getPublishedInspection(key: InspectionKey) {
    const result = await pool.query(
      `SELECT i.*,
              (SELECT count(*)::int FROM upstream_mock_defects d
               WHERE d.wafer_key = i.wafer_key AND d.inspection_time = i.inspection_time) AS defects,
              (SELECT count(*)::int FROM upstream_mock_review_images r
               WHERE r.wafer_key = i.wafer_key AND r.inspection_time = i.inspection_time) AS images
       FROM upstream_mock_inspections i
       WHERE i.state = 'published' AND i.wafer_key = $1 AND i.inspection_time = $2`,
      [key.wafer_key, key.inspection_time],
    );
    return result.rows[0] ? upstreamInspection(result.rows[0]) : null;
  },

  async listPublishedInspections(filters: {
    startTime: Date;
    endTime: Date;
    lotId?: string;
    waferId?: string;
    layerId?: string;
    device?: string;
  }) {
    const values: unknown[] = [filters.startTime, filters.endTime];
    const predicates = [
      "i.state = 'published'",
      "i.inspection_time >= $1",
      "i.inspection_time < $2",
    ];
    for (const [column, value] of [
      ["lot_id", filters.lotId],
      ["wafer_id", filters.waferId],
      ["layer_id", filters.layerId],
      ["device", filters.device],
    ] as const) {
      if (!value) continue;
      const alternatives = value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .map((item) => {
          values.push(item.endsWith("*") ? `${item.slice(0, -1)}%` : item);
          return item.endsWith("*")
            ? `i.${column} LIKE $${values.length}`
            : `i.${column} = $${values.length}`;
        });
      if (alternatives.length) predicates.push(`(${alternatives.join(" OR ")})`);
    }
    const result = await pool.query(
      `SELECT i.*,
              (SELECT count(*)::int FROM upstream_mock_defects d
               WHERE d.wafer_key = i.wafer_key AND d.inspection_time = i.inspection_time) AS defects,
              (SELECT count(*)::int FROM upstream_mock_review_images r
               WHERE r.wafer_key = i.wafer_key AND r.inspection_time = i.inspection_time) AS images
       FROM upstream_mock_inspections i
       WHERE ${predicates.join(" AND ")}
       ORDER BY i.inspection_time DESC, i.wafer_key DESC`,
      values,
    );
    return result.rows.map(upstreamInspection);
  },

  async listPublishedSamples(key: InspectionKey, offset: number, count: number) {
    const result = await pool.query(
      `SELECT d.wafer_key, d.inspection_time, d.defect_id, d.test_id,
              d.class_number, d.rough_bin, d.wafer_x, d.wafer_y,
              d.index_x, d.index_y, d.adder, d.cluster, d.images,
              d.size_x, d.size_y, d.size_d, d.area, d.final_bin,
              d.manual_bin, d.kill_ratio, i.lot_id, i.wafer_id,
              i.layer_id, i.inspect_equip_id, i.device, i.origin_x,
              i.origin_y, i.die_size_x, i.die_size_y, i.recipe_id,
              ((d.wafer_x - i.origin_x) % i.die_size_x) AS die_x,
              ((d.wafer_y - i.origin_y) % i.die_size_y) AS die_y
       FROM upstream_mock_defects d
       JOIN upstream_mock_inspections i
         ON d.wafer_key = i.wafer_key AND d.inspection_time = i.inspection_time
       WHERE i.state = 'published' AND d.wafer_key = $1 AND d.inspection_time = $2
       ORDER BY d.defect_id
       LIMIT $3 OFFSET $4`,
      [key.wafer_key, key.inspection_time, count, offset],
    );
    return result.rows.map((row) => ({
      ...row,
      wafer_key: Number(row.wafer_key),
      inspection_time: new Date(row.inspection_time).toISOString(),
      defect_id: Number(row.defect_id),
    }));
  },

  async publishedSampleCount(key: InspectionKey): Promise<number> {
    const result = await pool.query(
      `SELECT count(*)::int AS count
       FROM upstream_mock_defects d
       JOIN upstream_mock_inspections i
         ON d.wafer_key = i.wafer_key AND d.inspection_time = i.inspection_time
       WHERE i.state = 'published' AND d.wafer_key = $1 AND d.inspection_time = $2`,
      [key.wafer_key, key.inspection_time],
    );
    return result.rows[0]?.count ?? 0;
  },

  async listPublishedReviewImages(key: InspectionKey) {
    const result = await pool.query(
      `SELECT r.defect_id, r.image_id, r.image_type, r.image_filespec
       FROM upstream_mock_review_images r
       JOIN upstream_mock_inspections i
         ON r.wafer_key = i.wafer_key AND r.inspection_time = i.inspection_time
       WHERE i.state = 'published' AND r.wafer_key = $1 AND r.inspection_time = $2
       ORDER BY r.defect_id, r.image_id`,
      [key.wafer_key, key.inspection_time],
    );
    return result.rows.map((row) => ({
      ...row,
      defect_id: Number(row.defect_id),
      image_id: Number(row.image_id),
    }));
  },

  async listPublishedPatchArchives(filters: {
    inspectionTime: Date;
    lotId: string;
    waferId: string;
    device: string;
    layerId: string;
  }) {
    const result = await pool.query(
      `SELECT p.s3_bucket, p.s3_key
       FROM upstream_mock_patch_archives p
       JOIN upstream_mock_inspections i
         ON p.wafer_key = i.wafer_key AND p.inspection_time = i.inspection_time
       WHERE i.state = 'published' AND i.inspection_time = $1
         AND i.lot_id = $2 AND i.wafer_id = $3 AND i.device = $4 AND i.layer_id = $5
       ORDER BY p.s3_key`,
      [filters.inspectionTime, filters.lotId, filters.waferId, filters.device, filters.layerId],
    );
    return result.rows;
  },
};

function upstreamInspection(row: Record<string, unknown>) {
  const updated = row.last_updated_at ? new Date(row.last_updated_at as string) : null;
  return {
    inspection_time: new Date(row.inspection_time as string).toISOString(),
    wafer_key: Number(row.wafer_key),
    lot_id: row.lot_id,
    wafer_id: row.wafer_id,
    device: row.device,
    layer_id: row.layer_id,
    center_x: row.center_x,
    center_y: row.center_y,
    origin_x: row.origin_x,
    origin_y: row.origin_y,
    die_size_x: row.die_size_x,
    die_size_y: row.die_size_y,
    eqp_id: row.inspect_equip_id,
    inspect_equip_id: row.inspect_equip_id,
    recipe_id: row.recipe_id,
    defects: row.defects,
    images: row.images,
    origin_index_x: row.origin_index_x,
    origin_index_y: row.origin_index_y,
    latest_update: updated ? Math.trunc(updated.getTime() / 1000) : 0,
    change_token: Number(row.change_token ?? 0),
  };
}
