import "server-only";

import { deflateSync } from "node:zlib";

import {
  CreateBucketCommand,
  HeadBucketCommand,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import JSZip from "jszip";

import type { PatchArchiveInput, ReviewImageInput } from "./contracts";
import { upstreamMockConfig } from "./config";

const patchSize = 32;

function crc32(buffer: Buffer): number {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(tag: string, data: Buffer): Buffer {
  const payload = Buffer.concat([Buffer.from(tag, "ascii"), data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(payload));
  return Buffer.concat([length, payload, checksum]);
}

function png(side: number, bitDepth: number, colorType: number, rows: Buffer): Buffer {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(side, 0);
  header.writeUInt32BE(side, 4);
  header.writeUInt8(bitDepth, 8);
  header.writeUInt8(colorType, 9);
  return Buffer.concat([
    Buffer.from("89504e470d0a1a0a", "hex"),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(rows, { level: 6 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function grayPng(defectId: number, imageBias: number, bitDepth: number): Buffer {
  const maximum = 2 ** bitDepth - 1;
  const bytes: number[] = [];
  for (let y = 0; y < patchSize; y += 1) {
    bytes.push(0);
    for (let x = 0; x < patchSize; x += 1) {
      const index = y * patchSize + x;
      const value =
        index === 0
          ? 0
          : index === 1
            ? maximum
            : (defectId * 37 + imageBias * 13 + x * 29 + y * 17) % (maximum + 1);
      if (bitDepth === 8) bytes.push(value);
      else bytes.push((value >>> 8) & 0xff, value & 0xff);
    }
  }
  return png(patchSize, bitDepth === 8 ? 8 : 16, 0, Buffer.from(bytes));
}

function rgbPng(defectId: number, imageBias: number, side = 256): Buffer {
  const value = ((defectId * 17 + imageBias) % 180) + 40;
  const accent = (defectId * 31 + imageBias) % side;
  const bytes: number[] = [];
  for (let y = 0; y < side; y += 1) {
    bytes.push(0);
    for (let x = 0; x < side; x += 1) {
      const pixel = x === accent || y === accent ? 230 : value;
      bytes.push(pixel, pixel, pixel);
    }
  }
  return png(side, 8, 2, Buffer.from(bytes));
}

async function patchArchive(
  start: number,
  end: number,
  patchBitDepth: number,
  referenceCount: number,
  differenceCount: number,
): Promise<Buffer> {
  const imageTypes: Array<[string, number, number]> = [
    ["PatchDefective", 128, patchBitDepth],
    ...Array.from(
      { length: referenceCount },
      (_, index) =>
        [`PatchReference${index}`, 72 + index * 32, patchBitDepth] as [string, number, number],
    ),
    ...Array.from(
      { length: differenceCount },
      (_, index) =>
        [`PatchDifference${index}`, 196 + index * 28, patchBitDepth] as [string, number, number],
    ),
    ["PatchMask0", 1, 8],
  ];
  const archive = new JSZip();
  for (let defectId = start; defectId <= end; defectId += 1) {
    for (const [suffix, bias, bitDepth] of imageTypes) {
      archive.file(
        `${String(defectId).padStart(6, "0")}_${suffix}.png`,
        grayPng(defectId, bias, bitDepth),
      );
    }
  }
  return archive.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}

function timestampPath(value: Date): string {
  return value.toISOString().replace(/[-:]/g, "").replace("T", "_").slice(0, 15);
}

export async function publishArtifacts(input: {
  waferKey: number;
  inspectionTime: Date;
  totalDefects: number;
  imagedDefects: number;
  imagesPerDefect: number;
  defectsPerArchive: number;
  patchBitDepth: 8 | 12 | 16;
  referenceCount: number;
  differenceCount: number;
}): Promise<{
  review_images: ReviewImageInput[];
  patch_archives: PatchArchiveInput[];
}> {
  const config = upstreamMockConfig.s3();
  const client = new S3Client({
    endpoint: config.endpoint,
    region: config.region,
    forcePathStyle: true,
    credentials: {
      accessKeyId: config.accessKeyId,
      secretAccessKey: config.secretAccessKey,
    },
  });
  for (const bucket of [config.patchBucket, config.reviewBucket]) {
    try {
      await client.send(new HeadBucketCommand({ Bucket: bucket }));
    } catch {
      try {
        await client.send(new CreateBucketCommand({ Bucket: bucket }));
      } catch (error) {
        const name = (error as { name?: string }).name;
        if (name !== "BucketAlreadyOwnedByYou" && name !== "BucketAlreadyExists") {
          throw error;
        }
      }
    }
  }

  const timestamp = timestampPath(input.inspectionTime);
  const patch_archives: PatchArchiveInput[] = [];
  let archiveId = 1;
  for (let start = 1; start <= input.totalDefects; start += input.defectsPerArchive) {
    const end = Math.min(start + input.defectsPerArchive - 1, input.totalDefects);
    const key = `${timestamp}/${input.waferKey}/${String(start).padStart(6, "0")}-${String(end).padStart(6, "0")}.zip`;
    await client.send(
      new PutObjectCommand({
        Bucket: config.patchBucket,
        Key: key,
        Body: await patchArchive(
          start,
          end,
          input.patchBitDepth,
          input.referenceCount,
          input.differenceCount,
        ),
        ContentType: "application/zip",
      }),
    );
    patch_archives.push({
      archive_id: archiveId,
      s3_bucket: config.patchBucket,
      s3_key: key,
    });
    archiveId += 1;
  }

  const review_images: ReviewImageInput[] = [];
  const imaged = Math.min(input.totalDefects, input.imagedDefects);
  for (let defectId = 1; defectId <= imaged; defectId += 1) {
    for (let imageId = 1; imageId <= input.imagesPerDefect; imageId += 1) {
      const key = `${timestamp}/${input.waferKey}/${String(defectId).padStart(7, "0")}_${imageId}.png`;
      await client.send(
        new PutObjectCommand({
          Bucket: config.reviewBucket,
          Key: key,
          Body: rgbPng(defectId, imageId * 41),
          ContentType: "image/png",
        }),
      );
      review_images.push({
        defect_id: defectId,
        image_id: imageId,
        image_type: "SEM_TOP",
        image_filespec: `s3://${config.reviewBucket}/${key}`,
      });
    }
  }
  client.destroy();
  return { review_images, patch_archives };
}
