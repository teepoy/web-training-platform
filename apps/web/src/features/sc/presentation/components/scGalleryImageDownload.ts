import { scGalleryImageDownloadsUrl } from "@/features/sc/domain/models";
import { withAuthQueryParams } from "@/shared/api/client";
import type { ScGalleryToneMapping } from "./scGalleryToneMapping";

export interface ScGalleryDownloadItem {
  inspection_time: string;
  wafer_key: number;
  defect_id: string;
  patch_image_types: string[];
  review_image_ids: number[];
}

export interface ScGalleryDownloadPayload {
  items: ScGalleryDownloadItem[];
  apply_color_mapping: boolean;
  gray_mappings: {
    defective_reference?: ScGalleryToneMapping;
    difference?: ScGalleryToneMapping;
  };
}

export function submitScGalleryImageDownload(payload: ScGalleryDownloadPayload): void {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = withAuthQueryParams(scGalleryImageDownloadsUrl());
  form.style.display = "none";

  const input = document.createElement("input");
  input.type = "hidden";
  input.name = "payload";
  input.value = JSON.stringify(payload);
  form.append(input);
  document.body.append(form);
  try {
    form.submit();
  } finally {
    form.remove();
  }
}
