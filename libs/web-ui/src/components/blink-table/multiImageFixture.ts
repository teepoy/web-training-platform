/**
 * Multi-image seed data fixture for BlinkTable Storybook.
 *
 * Mimics the mock_multi_image.py seed format:
 * - 10 samples, each with 3-7 images
 * - Labels from CIFAR-100 subset
 * - Metadata: scatter_x, scatter_y, image_count, primary_image_index, view_mode
 * - Images: small colored inline SVGs for compact, visually distinct thumbnails
 */

import type { BlinkRow, BlinkColumnDef } from "../../types/blink-table";

const COLORS = [
  "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71",
  "#3498db", "#9b59b6", "#1abc9c",
];

function makeImageUri(color: string, label: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="${color}"/><text x="16" y="21" text-anchor="middle" font-size="11" fill="#fff" font-family="sans-serif">${label}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function makeImages(
  count: number,
  seed: number,
): { uris: string[]; labels: string[] } {
  const uris: string[] = [];
  const labels: string[] = [];
  for (let i = 0; i < count; i++) {
    const colorIdx = (seed + i) % COLORS.length;
    const label = `I${i + 1}`;
    uris.push(makeImageUri(COLORS[colorIdx], label));
    labels.push(label);
  }
  return { uris, labels };
}

const CIFAR100_LABEL_SUBSET = [
  "apple", "bicycle", "clock", "dolphin", "elephant",
  "forest", "house", "lion", "mushroom", "rocket",
];

const IMAGE_COUNTS = [3, 4, 5, 3, 6, 4, 7, 3, 5, 4];

interface MultiImageSample {
  id: string;
  imageUris: string[];
  label: string;
  scatterX: number;
  scatterY: number;
  imageCount: number;
  primaryImageIndex: number;
}

const samples: MultiImageSample[] = IMAGE_COUNTS.map((count, i) => {
  const { uris } = makeImages(count, i * 7);

  return {
    id: `multi-sample-${String(i + 1).padStart(4, "0")}`,
    imageUris: uris,
    label: CIFAR100_LABEL_SUBSET[i % CIFAR100_LABEL_SUBSET.length],
    scatterX: parseFloat(((i - 4.5) * 2.5 + (Math.random() - 0.5) * 1.5).toFixed(3)),
    scatterY: parseFloat(((4 - i) * 2.5 + (Math.random() - 0.5) * 1.5).toFixed(3)),
    imageCount: count,
    primaryImageIndex: 0,
  };
});

export const multiImageRows: BlinkRow[] = samples.map((s) => {
  const imageA = s.imageUris[0] ?? "";
  const imageB = s.imageUris[1] ?? "";

  const cells: Record<string, string> = {
    sample_id: s.id,
    label: s.label,
    image_count: String(s.imageCount),
  };

  for (let i = 0; i < s.imageUris.length; i++) {
    cells[`img_${i}`] = s.imageUris[i];
  }

  return {
    id: s.id,
    imageA,
    imageB,
    metadata: {
      scatter_x: s.scatterX,
      scatter_y: s.scatterY,
      image_count: s.imageCount,
      primary_image_index: s.primaryImageIndex,
      view_mode: "multi-image-mock",
    },
    cells,
  };
});

export const multiImageColumns: BlinkColumnDef[] = [
  { key: "sample_id", title: "Sample ID", width: 150 },
  { key: "label", title: "Label" },
  { key: "image_count", title: "Images", width: 70 },
  { key: "img_0", title: "Image 1", kind: "image", width: 120 },
  { key: "img_1", title: "Image 2", kind: "image", width: 120 },
  { key: "img_2", title: "Image 3", kind: "image", width: 120 },
  { key: "img_3", title: "Image 4", kind: "image", width: 120 },
  { key: "img_4", title: "Image 5", kind: "image", width: 120 },
  { key: "img_5", title: "Image 6", kind: "image", width: 120 },
  { key: "img_6", title: "Image 7", kind: "image", width: 120 },
];
