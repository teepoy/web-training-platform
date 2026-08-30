import "server-only";

import type {
  CreateInspectionInput,
  DefectInput,
  InspectionResponse,
  ShowcaseScenarioInput,
} from "./contracts";
import { UpstreamMockConflictError, UpstreamMockNotFoundError } from "./errors";
import { publishArtifacts } from "./artifacts";
import { upstreamMockRepository } from "./repository";

type InspectionSpec = {
  waferKey: number;
  lotId: string;
  waferId: string;
  layerId: string;
  device: string;
  totalDefects: number;
  imagedDefects: number;
  imagesPerDefect: number;
  patchBitDepth: 8 | 12 | 16;
  referenceCount: number;
  differenceCount: number;
};

export function scenarioSpecs(input: ShowcaseScenarioInput): InspectionSpec[] {
  return [
    {
      waferKey: 1,
      lotId: "A123456",
      waferId: "24",
      layerId: "LAYER-M1",
      device: "DEVICE-DEMO-A",
      totalDefects: input.total_defects,
      imagedDefects: input.imaged_defects,
      imagesPerDefect: input.images_per_defect,
      patchBitDepth: 12,
      referenceCount: 2,
      differenceCount: 2,
    },
    {
      waferKey: 81,
      lotId: "GALLERY-VQA",
      waferId: "GRAY8-1R1D",
      layerId: "LAYER-GRAY8",
      device: "DEVICE-GALLERY-VQA",
      totalDefects: input.gallery_defects,
      imagedDefects: input.gallery_imaged_defects,
      imagesPerDefect: 1,
      patchBitDepth: 8,
      referenceCount: 1,
      differenceCount: 1,
    },
    {
      waferKey: 82,
      lotId: "GALLERY-VQA",
      waferId: "GRAY16-1R1D",
      layerId: "LAYER-GRAY16-1X",
      device: "DEVICE-GALLERY-VQA",
      totalDefects: input.gallery_defects,
      imagedDefects: input.gallery_imaged_defects,
      imagesPerDefect: 1,
      patchBitDepth: 16,
      referenceCount: 1,
      differenceCount: 1,
    },
    {
      waferKey: 83,
      lotId: "GALLERY-VQA",
      waferId: "GRAY16-2R2D",
      layerId: "LAYER-GRAY16-2X",
      device: "DEVICE-GALLERY-VQA",
      totalDefects: input.gallery_defects,
      imagedDefects: input.gallery_imaged_defects,
      imagesPerDefect: 1,
      patchBitDepth: 16,
      referenceCount: 2,
      differenceCount: 2,
    },
  ];
}

export function scenarioDefect(spec: InspectionSpec, defectId: number): DefectInput {
  const dieX = (defectId % 7) - 3;
  const dieY = (Math.floor(defectId / 7) % 7) - 3;
  const waferX = 150_000_000 + dieX * 8_000_000 + (defectId % 2_000_000);
  const waferY = 150_000_000 + dieY * 5_000_000 + (defectId % 1_000_000);
  const sizeX = 50 + (defectId % 451);
  const sizeY = 50 + ((defectId * 7) % 451);
  const classNumber = defectId % 3;
  return {
    defect_id: defectId,
    test_id: (defectId % 1000) + 1,
    class_number: classNumber,
    rough_bin: classNumber || 1,
    wafer_x: waferX,
    wafer_y: waferY,
    index_x: Math.trunc((waferX - 145_000_000) / 8_000_000),
    index_y: Math.trunc((waferY - 145_000_000) / 5_000_000),
    adder: 0,
    cluster: 0,
    images: defectId <= spec.imagedDefects ? spec.imagesPerDefect : 0,
    size_x: sizeX,
    size_y: sizeY,
    size_d: Math.trunc(Math.sqrt(sizeX ** 2 + sizeY ** 2)),
    area: sizeX * sizeY,
    final_bin: defectId % 256,
    manual_bin: (defectId * 3) % 256,
    kill_ratio: Number(((defectId % 1000) / 1000).toFixed(3)),
  };
}

function validateScenario(input: ShowcaseScenarioInput): void {
  if (input.published_at < input.inspection_time) {
    throw new TypeError("published_at must not precede inspection_time");
  }
  for (const [name, value] of Object.entries({
    total_defects: input.total_defects,
    images_per_defect: input.images_per_defect,
    gallery_defects: input.gallery_defects,
    defects_per_archive: input.defects_per_archive,
    append_batch_size: input.append_batch_size,
  })) {
    if (value <= 0) throw new TypeError(`${name} must be positive`);
  }
  if (input.imaged_defects < 0 || input.gallery_imaged_defects < 0) {
    throw new TypeError("imaged defect counts cannot be negative");
  }
}

function draft(input: ShowcaseScenarioInput, spec: InspectionSpec): CreateInspectionInput {
  return {
    wafer_key: spec.waferKey,
    inspection_time: input.inspection_time,
    lot_id: spec.lotId,
    wafer_id: spec.waferId,
    layer_id: spec.layerId,
    device: spec.device,
    inspect_equip_id: "EQ-TOOL-A1",
    recipe_key: 1,
    recipe_id: "RECIPE-STD-001",
    origin_index_x: 0,
    origin_index_y: 0,
    center_x: 150_000_000,
    center_y: 150_000_000,
    origin_x: 145_000_000,
    origin_y: 145_000_000,
    die_size_x: 8_000_000,
    die_size_y: 5_000_000,
    defects: [],
    review_images: [],
    patch_archives: [],
  };
}

async function ensureInspection(input: ShowcaseScenarioInput, spec: InspectionSpec) {
  const key = { wafer_key: spec.waferKey, inspection_time: input.inspection_time };
  let existing: InspectionResponse | undefined;
  try {
    existing = await upstreamMockRepository.getInspection(key);
  } catch (error) {
    if (!(error instanceof UpstreamMockNotFoundError)) throw error;
  }
  if (existing) {
    if (existing.state !== "published") {
      throw new UpstreamMockConflictError(
        "showcase inspection exists as a draft; inspect and resolve it before replaying the scenario",
      );
    }
    const identity = [existing.lot_id, existing.wafer_id, existing.layer_id, existing.device];
    const expected = [spec.lotId, spec.waferId, spec.layerId, spec.device];
    if (identity.some((value, index) => value !== expected[index])) {
      throw new UpstreamMockConflictError(
        "published showcase inspection conflicts with the requested scenario",
      );
    }
    const counts = await upstreamMockRepository.childCounts(key);
    const expectedCounts = {
      defects: spec.totalDefects,
      review_images: Math.min(spec.totalDefects, spec.imagedDefects) * spec.imagesPerDefect,
      patch_archives: Math.ceil(spec.totalDefects / input.defects_per_archive),
    };
    if (
      counts.defects !== expectedCounts.defects ||
      counts.review_images !== expectedCounts.review_images ||
      counts.patch_archives !== expectedCounts.patch_archives
    ) {
      throw new UpstreamMockConflictError(
        "published showcase inspection has different child-record counts",
      );
    }
    return { ...existing, reused: true };
  }

  await upstreamMockRepository.createDraft(draft(input, spec));
  const artifacts = await publishArtifacts({
    waferKey: spec.waferKey,
    inspectionTime: input.inspection_time,
    totalDefects: spec.totalDefects,
    imagedDefects: spec.imagedDefects,
    imagesPerDefect: spec.imagesPerDefect,
    defectsPerArchive: input.defects_per_archive,
    patchBitDepth: spec.patchBitDepth,
    referenceCount: spec.referenceCount,
    differenceCount: spec.differenceCount,
  });
  await upstreamMockRepository.appendRecords({
    ...key,
    defects: [],
    ...artifacts,
  });
  for (let start = 1; start <= spec.totalDefects; start += input.append_batch_size) {
    const end = Math.min(start + input.append_batch_size, spec.totalDefects + 1);
    await upstreamMockRepository.appendRecords({
      ...key,
      defects: Array.from({ length: end - start }, (_, index) =>
        scenarioDefect(spec, start + index),
      ),
      review_images: [],
      patch_archives: [],
    });
  }
  await upstreamMockRepository.publish(key, input.published_at);
  return { ...(await upstreamMockRepository.getInspection(key)), reused: false };
}

export async function publishDevShowcase(input: ShowcaseScenarioInput) {
  validateScenario(input);
  const results = [];
  for (const spec of scenarioSpecs(input)) {
    results.push(await ensureInspection(input, spec));
  }
  return { inspections: results };
}
