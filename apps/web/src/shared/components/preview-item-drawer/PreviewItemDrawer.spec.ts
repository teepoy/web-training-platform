import { describe, it, expect } from "vitest";
import { nextTick } from "vue";
import { mountWithProviders } from "@/testing";
import PreviewItemDrawer from "./PreviewItemDrawer.vue";
import type { PreviewItem } from "@/shared/api/preview";

const validItem: PreviewItem = {
  upstream_item_id: "upstream-001",
  image_uris: ["https://picsum.photos/300/200?random=99"],
  metadata: {
    filename: "sample_001.jpg",
    source: "imagenet",
    class_name: "tabby cat",
  },
};

function bodyText(): string {
  return document.body.textContent ?? "";
}

describe("PreviewItemDrawer", () => {
  it("does not render drawer content when show is false", async () => {
    const { wrapper } = await mountWithProviders(PreviewItemDrawer, {
      props: {
        show: false,
        item: null,
      },
    });

    await nextTick();

    const html = wrapper.html();
    expect(html).not.toContain("Item Preview");
    expect(html).not.toContain("No item selected");
  });

  it("renders image and upstream_item_id when show is true with a valid item", async () => {
    await mountWithProviders(PreviewItemDrawer, {
      props: {
        show: true,
        item: validItem,
      },
    });

    await nextTick();

    expect(bodyText()).toContain(validItem.upstream_item_id);
  });

  it('shows "No item selected" when show is true and item is null', async () => {
    await mountWithProviders(PreviewItemDrawer, {
      props: {
        show: true,
        item: null,
      },
    });

    await nextTick();

    expect(bodyText()).toContain("No item selected");
  });

  it('shows "No metadata" when show is true and item has empty metadata', async () => {
    await mountWithProviders(PreviewItemDrawer, {
      props: {
        show: true,
        item: {
          ...validItem,
          metadata: {},
        },
      },
    });

    await nextTick();

    expect(bodyText()).toContain("No metadata");
  });
});
