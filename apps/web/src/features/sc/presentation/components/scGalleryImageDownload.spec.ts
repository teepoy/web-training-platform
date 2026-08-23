import { describe, expect, it, vi } from "vitest";
import {
  submitScGalleryImageDownload,
  type ScGalleryDownloadPayload,
} from "./scGalleryImageDownload";

describe("submitScGalleryImageDownload", () => {
  it("uses a native POST form so large ZIP responses are not buffered by JavaScript", () => {
    const submit = vi
      .spyOn(HTMLFormElement.prototype, "submit")
      .mockImplementation(() => undefined);
    const payload: ScGalleryDownloadPayload = {
      items: [
        {
          inspection_time: "2026-08-21T00:00:00Z",
          wafer_key: 1,
          defect_id: "42",
          patch_image_types: ["Defective", "Difference"],
          review_image_ids: [7],
        },
      ],
      apply_color_mapping: false,
      gray_mappings: {},
    };

    submitScGalleryImageDownload(payload);

    expect(submit).toHaveBeenCalledOnce();
    const form = submit.mock.instances[0];
    expect(form.method).toBe("POST");
    expect(new URL(form.action).pathname).toBe("/api/v1/sc/gallery-downloads");
    expect((form.elements.namedItem("payload") as HTMLInputElement).value).toBe(
      JSON.stringify(payload),
    );
    expect(document.body.contains(form)).toBe(false);
    submit.mockRestore();
  });
});
