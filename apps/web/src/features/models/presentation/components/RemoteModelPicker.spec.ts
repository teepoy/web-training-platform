import { createPinia, setActivePinia } from "pinia";
import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { NDataTable } from "naive-ui";
import type { PaginationProps } from "naive-ui";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelResponse } from "@/generated/orval/models";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { mountWithProviders } from "@/testing";
import { server } from "@/testing/msw/server";
import RemoteModelPicker from "./RemoteModelPicker.vue";

function model(id: string): ModelResponse {
  return {
    id,
    uri: `s3://models/${id}`,
    kind: "model",
    name: id,
    job_id: `job-${id}`,
    trainer_name: "YOLO SC",
    created_by: "user-1",
    creator_name: "Current User",
  };
}

function preparePinia() {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore(pinia).user = {
    id: "user-1",
    email: "user@example.com",
    name: "Current User",
    is_superadmin: false,
    created_at: "2026-01-01T00:00:00Z",
  };
  useOrgStore(pinia).currentOrgId = "org-1";
  return pinia;
}

describe("RemoteModelPicker", () => {
  beforeEach(() => {
    server.use(
      http.get("/api/v1/models/creators", () => HttpResponse.json([])),
      http.get("/api/v1/models/selected-model", () => HttpResponse.json(model("selected-model"))),
    );
  });

  it("keeps an off-page selection and sends compatibility before pagination", async () => {
    const requests: URL[] = [];
    server.use(
      http.get("/api/v1/models", ({ request }) => {
        requests.push(new URL(request.url));
        return HttpResponse.json({ items: [model("page-model")], total: 40 });
      }),
    );
    const { wrapper } = await mountWithProviders(RemoteModelPicker, {
      pinia: preparePinia(),
      props: {
        modelValue: "selected-model",
        active: true,
        compatibleViewIds: ["patch_image_v1", "review_image_v1"],
      },
    });

    await vi.waitFor(() => expect(requests).toHaveLength(1));
    await vi.waitFor(() =>
      expect(wrapper.emitted("update:selectedModel")?.at(-1)?.[0]).toMatchObject({
        id: "selected-model",
      }),
    );
    expect(requests[0]?.searchParams.get("compatible_view_id")).toBe(
      "patch_image_v1,review_image_v1",
    );
    expect(requests[0]?.searchParams.get("offset")).toBe("0");

    const pagination = wrapper.getComponent(NDataTable).props("pagination") as PaginationProps;
    pagination.onUpdatePage?.(2);
    await flushPromises();
    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1]?.searchParams.get("offset")).toBe("20");
    expect(wrapper.props("modelValue")).toBe("selected-model");
  });
});
