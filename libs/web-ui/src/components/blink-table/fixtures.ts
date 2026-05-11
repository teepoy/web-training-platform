/**
 * Storybook / demo fixtures for the blink-table component.
 * Pure TypeScript data — no Vue components, no API calls.
 */

import type { BlinkRow, BlinkColumnDef } from "../../types/blink-table";

export const extraColumns: BlinkColumnDef[] = [
  { key: "filename", title: "Filename" },
  { key: "status", title: "Status" },
  { key: "score", title: "Score" },
];

const filenames = [
  "IMG_20240301_001.jpg",
  "IMG_20240301_002.jpg",
  "IMG_20240301_003.jpg",
  "IMG_20240301_004.jpg",
  "IMG_20240301_005.jpg",
  "IMG_20240301_006.jpg",
  "IMG_20240301_007.jpg",
  "IMG_20240301_008.jpg",
  "IMG_20240301_009.jpg",
  "IMG_20240301_010.jpg",
];

const statuses = [
  "reviewed",
  "pending",
  "flagged",
  "reviewed",
  "pending",
  "reviewed",
  "pending",
  "flagged",
  "reviewed",
  "pending",
];

const scores = [
  "0.92",
  "0.45",
  "0.88",
  "0.67",
  "0.95",
  "0.31",
  "0.78",
  "0.84",
  "0.62",
  "0.99",
];

/**
 * 10 representative rows with distinct A/B picsum images so the blink
 * toggle is visually obvious. Each row carries extra columns for a
 * realistic table feel without live API calls.
 */
export const blinkRows: BlinkRow[] = Array.from(
  { length: 10 },
  (_, i): BlinkRow => ({
    id: `blink-row-${String(i).padStart(2, "0")}`,
    imageA: `https://picsum.photos/160/120?random=${i}`,
    imageB: `https://picsum.photos/160/120?random=${i + 100}`,
    metadata: {
      index: i,
      filename: filenames[i],
    },
    cells: {
      filename: filenames[i],
      status: statuses[i],
      score: scores[i],
    },
  }),
);
